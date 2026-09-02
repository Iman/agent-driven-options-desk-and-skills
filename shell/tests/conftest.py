"""Shared fixtures.

The synthetic snapshot is deliberately imperfect: it contains one contract
with no implied volatility and one far out of the money strike, so every test
exercises the skip paths rather than only the happy path.
"""

import pytest

from optiondesk.artifacts import envelope
from optiondesk.contracts import CHAIN_SNAPSHOT


@pytest.fixture(autouse=True)
def acknowledge_local_yahoo_terms(monkeypatch):
    """Tests use fakes, but they still cross the production access gate."""
    monkeypatch.setenv("OPTIONDESK_ACCEPT_YAHOO_TERMS", "personal-use")
    monkeypatch.delenv("PUBLIC_DATA_MODE", raising=False)


@pytest.fixture
def snapshot():
    contracts = []
    for strike, iv in ((90.0, 0.32), (95.0, 0.27), (100.0, 0.22),
                       (105.0, 0.24), (110.0, None), (150.0, 0.40)):
        for kind in ("call", "put"):
            contracts.append({
                "symbol": "TEST{}{}".format(kind[0].upper(), int(strike)),
                "type": kind,
                "strike": strike,
                "bid": 1.0,
                "ask": 1.2,
                "mid": 1.1,
                "last": 1.1,
                "volume": 10,
                "open_interest": 100,
                "iv": iv,
                "iv_source": "solved_mid" if iv else None,
                "iv_provider": iv,
            })
    return {
        "meta": envelope(schema=CHAIN_SNAPSHOT, tool="test fixture",
                         provider_used="fixture"),
        "underlying": "TEST",
        "spot": 100.0,
        "spot_asof": "2026-08-28",
        "risk_free_rate": 0.04,
        "dividend_yield": 0.0,
        "expiry": "2026-09-18",
        "days_to_expiry": 21.0,
        "contracts": contracts,
        "counts": {"calls": 6, "puts": 6, "with_iv": 10, "without_iv": 2},
    }


class Args:
    """Stand-in for an argparse namespace."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.fixture
def args_factory():
    return Args


# --------------------------------------------------------------------------
# Provider stubbing.
#
# Nothing below this line touches the network. A stub is registered through
# the public providers.register and the registry, including its priority
# table, is restored afterwards; without the restore a stub stays registered
# for the rest of the session and every later test runs against a registry
# its author did not intend.
# --------------------------------------------------------------------------

import math

from optiondesk import engine_bridge, providers
from optiondesk.providers.base import (
    CAP_OPTION_CHAIN,
    CAP_RISK_FREE_RATE,
    CAP_UNDERLYING_HISTORY,
    CAP_UNDERLYING_QUOTE,
    Provider,
)

# Defined in marks.py and re-exported here, so that importing it from
# either place keeps working. See marks.py for why it moved.
from marks import needs_engine  # noqa: E402,F401


class StubProvider(Provider):
    """A provider that answers from memory and records what was asked.

    Every method can be told to raise instead, which is how the failing
    provider paths are exercised without inventing a network error.
    """

    name = "stub"
    tier = "free"
    requires_key = False
    capabilities = (CAP_OPTION_CHAIN, CAP_UNDERLYING_QUOTE,
                    CAP_RISK_FREE_RATE, CAP_UNDERLYING_HISTORY)
    terms_url = None
    notes = "test double"

    def __init__(self, chain=None, quote=None, rate=None, history=None,
                 expiries=None, raises=None):
        self.calls = []
        self._chain = chain
        self._quote = quote or {"symbol": "TEST", "spot": 100.0,
                                "spot_asof": "2026-08-28"}
        self._rate = rate or {"rate": 0.04, "source": "stub",
                              "degraded": False, "reason": None}
        self._history = history
        self._expiries = list(expiries or ["2026-09-18", "2026-10-16"])
        self.raises = raises

    def available(self):
        return True

    def _answer(self, what, payload):
        self.calls.append(what)
        if self.raises is not None:
            raise self.raises
        return payload

    def underlying_quote(self, symbol, **kwargs):
        return self._answer("underlying_quote", dict(self._quote,
                                                     symbol=symbol))

    def risk_free_rate(self, **kwargs):
        return self._answer("risk_free_rate", dict(self._rate))

    def expiries(self, symbol):
        return self._answer("expiries", list(self._expiries))

    def option_chain(self, symbol, expiry=None, **kwargs):
        chain = dict(self._chain or {})
        chain.setdefault("symbol", symbol)
        chain.setdefault("expiry", expiry or self._expiries[0])
        chain.setdefault("days_to_expiry", 30.0)
        chain.setdefault("actual_days_to_expiry", 30.0)
        chain.setdefault("expired", False)
        chain.setdefault("contracts", [])
        chain.setdefault("listed_expiries", list(self._expiries))
        return self._answer("option_chain", chain)

    def underlying_history(self, symbol, period="2y", **kwargs):
        history = dict(self._history or {})
        history.setdefault("symbol", symbol)
        history.setdefault("period", period)
        return self._answer("underlying_history", history)


@pytest.fixture
def provider_registry():
    """Give the registry back exactly as it was found.

    Both the registry and PRIORITY are snapshotted: a test that repoints a
    capability at a stub and does not put the list back leaves every later
    test resolving to that stub.
    """
    original_registry = dict(providers._REGISTRY)
    original_priority = {key: list(value)
                         for key, value in providers.PRIORITY.items()}
    yield providers
    providers._REGISTRY.clear()
    providers._REGISTRY.update(original_registry)
    providers.PRIORITY.clear()
    providers.PRIORITY.update(original_priority)


@pytest.fixture
def stub_provider(provider_registry):
    """Register a StubProvider and make it the only candidate."""
    def register(**kwargs):
        stub = StubProvider(**kwargs)
        provider_registry.register(stub)
        for capability in stub.capabilities:
            provider_registry.PRIORITY[capability] = [stub.name]
        return stub
    return register


# --------------------------------------------------------------------------
# Chain builders.
#
# Prices are real model values from the engine, so a volatility solved back
# out of a mid returns the volatility that produced it. A hand-picked number
# would make every solve fail and hide the difference between the solved and
# the published path.
# --------------------------------------------------------------------------

STRIKES = (80.0, 85.0, 90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0)
SPOT = 100.0
DAYS = 30.0
RATE = 0.04


def _iv_for(strike, base=0.30, skew=0.0008):
    return base - skew * (strike - SPOT)


def _contract(bs_price, strike, kind, days=DAYS, spot=SPOT, rate=RATE,
              dividend_yield=0.0, solved=True, unsolvable=False,
              no_price=False, open_interest=500):
    """One contract as a provider hands it over: iv unsolved, mid quoted."""
    iv = _iv_for(strike)
    price = bs_price(spot, strike, days / 365.0, iv, kind, rate,
                     dividend_yield)
    # The mid is the model value exactly, so a volatility solved back out of
    # it returns the volatility that produced it. Quoting a rounded midpoint
    # of a fixed-width spread instead would perturb every cheap wing enough
    # to make the solve look broken.
    bid = round(price * 0.98, 4)
    ask = round(price * 1.02, 4)
    mid = price
    if unsolvable:
        # Below intrinsic, so no volatility reproduces it and the solve
        # returns nothing. The published figure is still there to fall back
        # on, which is the branch under test.
        mid, bid, ask = 0.01, 0.0, 0.02
    if no_price:
        mid = bid = ask = None
    return {
        "symbol": "TEST{}{:g}".format(kind[0].upper(), strike),
        "type": kind,
        "strike": strike,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "mid_source": "quote" if mid is not None else None,
        "last": round(price, 4),
        "volume": 100,
        "open_interest": open_interest,
        "iv": iv if solved else None,
        "iv_source": "solved_mid" if solved else None,
        "iv_provider": None if no_price else iv,
    }


@pytest.fixture
def provider_chain():
    """Factory for the shape a provider returns: no iv solved yet."""
    if not engine_bridge.AVAILABLE:
        pytest.skip("analytics engine not installed")
    bs_price = engine_bridge.require()["bs_price"]

    def build(strikes=STRIKES, kinds=("call", "put"), unsolvable=(),
              no_price=(), expiry="2026-09-18", days=DAYS, expired=False):
        contracts = []
        for strike in strikes:
            for kind in kinds:
                contracts.append(_contract(
                    bs_price, strike, kind, days=days, solved=False,
                    unsolvable=(strike, kind) in unsolvable,
                    no_price=(strike, kind) in no_price))
        return {"symbol": "TEST", "expiry": expiry, "days_to_expiry": days,
                "actual_days_to_expiry": -1.0 if expired else days,
                "expired": expired, "contracts": contracts,
                "listed_expiries": [expiry, "2026-10-16"]}

    return build


@pytest.fixture
def chain_snapshot():
    """Factory for a written snapshot: volatilities already solved."""
    if not engine_bridge.AVAILABLE:
        pytest.skip("analytics engine not installed")
    bs_price = engine_bridge.require()["bs_price"]

    def build(underlying="TEST", expiry="2026-09-18", strikes=STRIKES,
              days=DAYS, no_iv=(), no_open_interest=(), degraded=False,
              degraded_reason=None, notes=None):
        contracts = []
        for strike in strikes:
            for kind in ("call", "put"):
                contract = _contract(
                    bs_price, strike, kind, days=days,
                    solved=(strike, kind) not in no_iv,
                    open_interest=(None if (strike, kind) in no_open_interest
                                   else 500))
                contracts.append(contract)
        with_iv = sum(1 for c in contracts if c["iv"] is not None)
        return {
            "meta": envelope(schema=CHAIN_SNAPSHOT, tool="test fixture",
                             provider_used="stub", degraded=degraded,
                             degraded_reason=degraded_reason, notes=notes),
            "underlying": underlying,
            "spot": SPOT,
            "spot_asof": "2026-08-28",
            "risk_free_rate": RATE,
            "dividend_yield": 0.0,
            "expiry": expiry,
            "days_to_expiry": days,
            "contracts": contracts,
            "counts": {"calls": len(strikes), "puts": len(strikes),
                       "with_iv": with_iv,
                       "without_iv": len(contracts) - with_iv},
        }

    return build


@pytest.fixture
def log_returns():
    """A deterministic return series long enough for the volatility model."""
    import random

    rng = random.Random(11)
    prices = [100.0]
    for _ in range(300):
        prices.append(prices[-1] * (1.0 + rng.gauss(0.0004, 0.011)))
    returns = [math.log(b / a) for a, b in zip(prices, prices[1:])]
    return {"symbol": "TEST", "period": "2y", "closes": prices,
            "dates": ["2026-01-01"] * len(prices), "returns": returns,
            "first": "2025-01-02", "last": "2026-08-28",
            "last_close": prices[-1]}
