"""A zero dividend yield is a wrong default, not a safe one.

WHAT WOULD BREAK. `--dividend-yield` defaulted to zero, so every underlying
that pays was priced as though it did not. Measured on a real 173 day TLT
chain against its actual 4.7 percent trailing yield: at-the-money implied
volatility solved to 0.0737 instead of 0.1133, understated by 54 percent,
and delta to 0.635 instead of 0.491, overstated by 23 percent. Every Greek,
every probability of profit and every structure built on a dividend payer
inherited that, and it is worst at the long expiries people hold.

The yield is now fetched. These tests cover the three ways that can go
wrong: the wrong number, a confident number where there should be none, and
silently dropping the user's own value.
"""

import json

import pytest

from optiondesk.cli import chain as chain_cmd
from optiondesk.providers.base import CAP_DIVIDEND_YIELD
from optiondesk_engine.pricing.black_scholes import implied_vol
from optiondesk_engine.pricing.greeks_full import all_greeks


# ------------------------------------------------------- the size of it

def test_ignoring_a_real_yield_moves_the_numbers_that_matter():
    """The regression that motivated the change, as arithmetic.

    Priced from one real quote: a TLT call struck at 83 with the underlying
    at 82.88, 173 days out, mid 3.05, at a 4 percent rate. Solving with no
    dividend yield against solving with the real one is not a rounding
    difference.
    """
    spot, strike, t, rate, mid = 82.88, 83.0, 173 / 365.0, 0.04, 3.05
    without = implied_vol(mid, spot, strike, t, "call", rate, 0.0)
    with_yield = implied_vol(mid, spot, strike, t, "call", rate, 0.047)
    assert without is not None and with_yield is not None
    assert with_yield > without * 1.2, (
        "the yield must move implied volatility materially, got {:.4f} "
        "against {:.4f}".format(with_yield, without))

    delta_without = all_greeks(spot, strike, t, without, "call", rate,
                               0.0)["delta"]
    delta_with = all_greeks(spot, strike, t, with_yield, "call", rate,
                            0.047)["delta"]
    assert delta_without - delta_with > 0.05, (
        "delta must move materially, got {:.4f} against {:.4f}".format(
            delta_without, delta_with))


# ------------------------------------------------------------ the fetch

class _YieldProvider:
    """A stand-in for the provider, answering only this capability."""

    name = "stub-dividends"
    tier = "free"
    requires_key = False
    capabilities = (CAP_DIVIDEND_YIELD,)
    terms_url = None
    notes = "test double"

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def available(self):
        return True

    def dividend_yield(self, symbol, spot=None):
        self.calls.append((symbol, spot))
        return dict(self.answer, symbol=symbol)


def _args(tmp_path, **overrides):
    class Args:
        symbol = "TEST"
        expiry = None
        provider = None
        rate = 0.04
        dividend_yield = None
        out_dir = str(tmp_path)
    for key, value in overrides.items():
        setattr(Args, key, value)
    return Args()


@pytest.fixture
def desk(monkeypatch, provider_registry, stub_provider, provider_chain,
         tmp_path):
    """A chain from the stub, with the dividend provider swappable."""
    def build(dividend_answer):
        stub_provider(chain=provider_chain())
        provider = _YieldProvider(dividend_answer)
        provider_registry.register(provider)
        provider_registry.PRIORITY[CAP_DIVIDEND_YIELD] = [provider.name]
        return provider
    return build


def _written(tmp_path):
    files = sorted(tmp_path.glob("chain_*.json"))
    assert files, "no artifact written"
    return json.loads(files[0].read_text(encoding="utf-8"))


def test_a_fetched_yield_is_used_and_its_source_recorded(desk, tmp_path):
    desk({"dividend_yield": 0.047, "source": "trailing_12m_payments",
          "note": None, "sources_agree": True})
    summary = chain_cmd.run(_args(tmp_path))
    assert summary["dividend_yield"] == pytest.approx(0.047)
    assert summary["dividend_yield_source"] == "trailing_12m_payments"
    artifact = _written(tmp_path)
    assert artifact["dividend_yield"] == pytest.approx(0.047)
    assert artifact["dividend_yield_source"] == "trailing_12m_payments"


def test_the_users_own_yield_is_never_overridden(desk, tmp_path):
    """A flag the caller passed must not be replaced by a fetched value."""
    provider = desk({"dividend_yield": 0.047, "source": "fetched",
                     "note": None, "sources_agree": True})
    summary = chain_cmd.run(_args(tmp_path, dividend_yield=0.02))
    assert summary["dividend_yield"] == pytest.approx(0.02)
    assert summary["dividend_yield_source"] == "user"
    assert provider.calls == [], (
        "the provider was asked even though the caller supplied a value")


def test_an_unavailable_yield_degrades_and_says_what_to_do(desk, tmp_path):
    """Falling back to zero silently is the defect this replaces."""
    desk({"dividend_yield": None, "source": None, "sources_agree": True,
          "note": "a cash index carries no dividend series here"})
    summary = chain_cmd.run(_args(tmp_path))
    assert summary["dividend_yield"] == 0.0
    assert summary["dividend_yield_source"] is None
    assert summary["degraded"] is True
    reason = summary["degraded_reason"] or ""
    assert "dividend yield assumed zero" in reason, reason
    assert "--dividend-yield" in reason, (
        "the reason must say what the reader can do about it")


def test_a_provider_that_raises_does_not_take_the_chain_with_it(desk,
                                                                tmp_path):
    """A chain is still worth having with a yield that had to be assumed."""
    from optiondesk import providers

    # Set the chain up first, then swap the dividend provider for one that
    # fails, so the only thing broken is the yield.
    desk({"dividend_yield": 0.01, "source": "stub", "sources_agree": True,
          "note": None})

    class Exploding(_YieldProvider):
        name = "stub-dividends-exploding"

        def dividend_yield(self, symbol, spot=None):
            raise RuntimeError("upstream is down")

    provider = Exploding({})
    providers.register(provider)
    providers.PRIORITY[CAP_DIVIDEND_YIELD] = [provider.name]

    summary = chain_cmd.run(_args(tmp_path))
    assert summary["degraded"] is True
    assert "upstream is down" in (summary["degraded_reason"] or "")
    assert summary["contracts"] > 0, "the chain itself was lost"


# -------------------------------------------------- the published field

class _FakeSeries:
    """Enough of a dividends series for the provider to sum."""

    def __init__(self, values, index):
        self._values, self.index = values, index

    def __len__(self):
        return len(self._values)

    def __getitem__(self, mask):
        return _FakeSeries([v for v, keep in zip(self._values, mask) if keep],
                           self.index)

    def sum(self):
        return sum(self._values)


class _FakeStamp:
    """A timestamp with the one method the provider calls on it."""

    @staticmethod
    def date():
        return "2026-08-15"


class _FakeIndex(list):
    tz = "UTC"

    def tz_localize(self, _):
        return self

    def __ge__(self, other):
        return [True] * len(self)


class _FakeTicker:
    def __init__(self, dividends, published):
        self.dividends = dividends
        self.info = {"dividendYield": published}


def _provider_with(dividends, published, spot):
    from optiondesk.providers.yahoo import YahooProvider

    class Fake(YahooProvider):
        def _client(self):
            index = _FakeIndex([_FakeStamp()] * len(dividends))

            class Client:
                @staticmethod
                def Ticker(_symbol):
                    return _FakeTicker(_FakeSeries(list(dividends), index),
                                       published)
            return Client()

        def underlying_quote(self, symbol, period="5d"):
            return {"symbol": symbol, "spot": spot, "spot_asof": "2026-08-28"}

    return Fake()


def test_the_published_yield_is_read_as_a_percentage():
    """The unit trap, pinned with the case that exposed it.

    FXE pays 0.802 on a 106.98 price, which is 0.75 percent, and the
    published field reads 0.74 meaning percent. An earlier version guessed
    the unit from the size of the number and converted only values above
    one, so 0.74 became 74 percent, the cross-check disagreed with itself
    and a correct yield was refused. Any underlying yielding under one
    percent was affected.
    """
    result = _provider_with([0.802], 0.74, 106.98).dividend_yield("FXE")
    assert result["sources_agree"] is True, result["note"]
    assert result["dividend_yield"] == pytest.approx(0.0075, abs=1e-4)
    assert result["published"] == pytest.approx(0.0074, abs=1e-4)


def test_sources_that_disagree_produce_no_yield_at_all():
    """Picking a side between 38.8 and 61.7 percent is not a measurement."""
    result = _provider_with([4.058], 61.68, 10.45).dividend_yield("BITO")
    assert result["dividend_yield"] is None
    assert result["sources_agree"] is False
    assert "disagree" in (result["note"] or "")


def test_a_cash_index_is_refused_rather_than_reported_as_zero():
    """An index has no dividend series here, and its yield is not zero.

    Reporting zero would be indistinguishable from gold, which genuinely
    pays nothing, and would shift the forward on every SPX option.
    """
    result = _provider_with([], None, 7711.76).dividend_yield("^SPX")
    assert result["dividend_yield"] is None
    assert "--dividend-yield" in (result["note"] or "")


def test_an_underlying_that_truly_pays_nothing_reports_zero_not_none():
    """Zero and unknown are different facts and must not collapse."""
    result = _provider_with([], 0.0, 408.89).dividend_yield("GLD")
    assert result["dividend_yield"] == 0.0
    assert result["source"] == "trailing_12m_payments"
