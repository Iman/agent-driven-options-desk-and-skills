"""The Yahoo provider, driven by a fake client rather than the network.

The real yfinance module is never called. A fake is placed on the provider's
own client slot, so every line under test is the provider's own translation
of a frame into contracts.
"""

import math
import sys
import types

import pytest

from optiondesk.providers.base import ProviderDataError, ProviderUnavailable
from optiondesk.providers.yahoo import (
    FALLBACK_RATE,
    RATE_SYMBOL,
    YahooProvider,
    _num,
)

pd = pytest.importorskip("pandas")

FAR_FUTURE = "2099-12-18"
LONG_PAST = "2020-01-17"


def frame(rows):
    return pd.DataFrame(rows)


def history_frame(closes, dates):
    return pd.DataFrame({"Close": list(closes)},
                        index=pd.to_datetime(list(dates)))


def fake_client(calls=None, puts=None, options=(FAR_FUTURE,), histories=None):
    """A stand-in for the yfinance module, with one Ticker class."""
    class Chain:
        pass

    class Ticker:
        def __init__(self, symbol):
            self.symbol = symbol

        @property
        def options(self):
            return tuple(options)

        def option_chain(self, expiry):
            chain = Chain()
            chain.calls = frame(calls or [])
            chain.puts = frame(puts or [])
            return chain

        def history(self, period=None, auto_adjust=None):
            return (histories or {}).get(self.symbol)

    return types.SimpleNamespace(Ticker=Ticker)


def provider_with(**kwargs):
    provider = YahooProvider()
    provider._yf = fake_client(**kwargs)
    return provider


def call_row(**overrides):
    row = {"contractSymbol": "C100", "strike": 100.0, "bid": 1.0, "ask": 1.2,
           "lastPrice": 1.1, "volume": 5, "openInterest": 9,
           "impliedVolatility": 0.25}
    row.update(overrides)
    return row


# ------------------------------------------------------------------- _num

@pytest.mark.parametrize("value", [None, "", "abc", float("nan"),
                                   float("inf"), float("-inf"), object()])
def test_num_maps_anything_unusable_to_the_default(value):
    """Catches an infinity slipping through an isnan-only check.

    An infinity passes isnan, and int() on it then raises OverflowError
    several layers away from the quote that caused it.
    """
    assert _num(value) is None
    assert _num(value, 0) == 0


def test_num_converts_real_numbers():
    """Catches the guard rejecting the values it exists to let through."""
    assert _num("3.5") == 3.5
    assert _num(2) == 2.0
    assert _num(0) == 0.0


# ------------------------------------------------------------ option_chain

def test_a_zero_bid_is_a_real_quote_and_not_the_last_trade():
    """Catches truthiness being tested where presence is meant.

    A zero bid is a quote. Testing `if bid and ask` substituted the last
    traded price for the mid on 181 of 492 contracts in one live SPY chain,
    and 178 of those then had a volatility solved from the substituted
    number.
    """
    provider = provider_with(calls=[call_row(bid=0.0, ask=0.05,
                                             lastPrice=3.0)])
    contract = provider.option_chain("TEST")["contracts"][0]

    assert contract["bid"] == 0.0
    assert contract["mid"] == pytest.approx(0.025)
    assert contract["mid_source"] == "quote"
    assert contract["last"] == 3.0


def test_a_zero_bid_and_a_zero_ask_are_still_a_quote():
    """Catches the same substitution at the other end of the same branch."""
    provider = provider_with(calls=[call_row(bid=0.0, ask=0.0,
                                             lastPrice=3.0)])
    contract = provider.option_chain("TEST")["contracts"][0]

    assert contract["mid"] == 0.0
    assert contract["mid_source"] == "quote"


def test_a_missing_side_falls_back_to_the_last_trade_and_says_so():
    """Catches a stale last trade being passed off as a mid.

    The fallback is legitimate, but a caller has to be able to count how
    much of the chain rests on it.
    """
    provider = provider_with(calls=[call_row(bid=None, ask=1.2,
                                             lastPrice=1.5)])
    contract = provider.option_chain("TEST")["contracts"][0]

    assert contract["mid"] == 1.5
    assert contract["mid_source"] == "last_trade"


def test_no_quote_and_no_trade_leaves_the_mid_empty():
    """Catches a price being invented for a contract that has none."""
    provider = provider_with(calls=[call_row(bid=None, ask=None,
                                             lastPrice=None)])
    contract = provider.option_chain("TEST")["contracts"][0]

    assert contract["mid"] is None
    assert contract["mid_source"] is None


def test_non_finite_counts_do_not_reach_the_contract():
    """Catches a NaN volume or an infinite open interest being cast to int.

    Both raise several layers away from the row that produced them, which
    is the failure the numeric guard exists to prevent.
    """
    provider = provider_with(calls=[call_row(volume=float("nan"),
                                             openInterest=float("inf"),
                                             impliedVolatility=float("nan"))])
    contract = provider.option_chain("TEST")["contracts"][0]

    assert contract["volume"] == 0
    assert contract["open_interest"] == 0
    assert contract["iv_provider"] is None


def test_the_provider_never_solves_a_volatility_itself():
    """Catches the pricing model leaking across the licence boundary.

    Only the engine solves volatility. A provider that filled iv in would
    put analytics in the MIT shell and make the boundary unauditable.
    """
    provider = provider_with(calls=[call_row(impliedVolatility=0.25)])
    contract = provider.option_chain("TEST")["contracts"][0]

    assert contract["iv"] is None
    assert contract["iv_source"] is None
    assert contract["iv_provider"] == 0.25


def test_contracts_come_back_sorted_by_type_then_strike():
    """Catches an unordered chain, which every downstream pairing assumes."""
    provider = provider_with(
        calls=[call_row(strike=110.0), call_row(strike=90.0)],
        puts=[call_row(strike=105.0), call_row(strike=95.0)])
    contracts = provider.option_chain("TEST")["contracts"]

    assert [(c["type"], c["strike"]) for c in contracts] == [
        ("call", 90.0), ("call", 110.0), ("put", 95.0), ("put", 105.0)]


def test_an_unlisted_expiry_is_refused_with_the_available_ones():
    """Catches a silent fall back to a different expiry.

    Answering with the nearest listed expiry instead would hand back a
    chain for a date the caller did not ask for.
    """
    provider = provider_with(calls=[call_row()],
                             options=(FAR_FUTURE, "2098-01-16"))
    with pytest.raises(ProviderDataError) as excinfo:
        provider.option_chain("TEST", "2050-06-21")

    assert "2050-06-21" in str(excinfo.value)
    assert FAR_FUTURE in str(excinfo.value)


def test_no_expiry_given_takes_the_nearest_listed():
    """Catches the default expiry drifting to the far end of the listing."""
    provider = provider_with(calls=[call_row()],
                             options=(FAR_FUTURE, "2098-01-16"))
    assert provider.option_chain("TEST")["expiry"] == FAR_FUTURE


def test_an_expiry_already_past_is_flagged_and_its_floor_is_visible():
    """Catches the day-count floor disguising an expiry that has gone.

    The floor keeps a same-day contract priceable. Applied to a past date
    it produces numbers that look ordinary and mean nothing, so the true
    figure has to travel alongside it.
    """
    provider = provider_with(calls=[call_row()], options=(LONG_PAST,))
    chain = provider.option_chain("TEST")

    assert chain["expired"] is True
    assert chain["days_to_expiry"] == 0.25
    assert chain["actual_days_to_expiry"] < 0


def test_a_live_expiry_is_not_flagged():
    """Catches every chain being marked expired, which would degrade all of
    them and empty the flag of meaning."""
    provider = provider_with(calls=[call_row()], options=(FAR_FUTURE,))
    chain = provider.option_chain("TEST")

    assert chain["expired"] is False
    assert chain["days_to_expiry"] > 1000


def test_a_symbol_with_no_listed_expiries_is_an_error():
    """Catches an empty listing being returned as a normal answer.

    An empty result that looks real is the substitution this project is
    built to avoid.
    """
    provider = provider_with(options=())
    with pytest.raises(ProviderDataError) as excinfo:
        provider.expiries("TEST")
    assert "no option expirations" in str(excinfo.value)


# --------------------------------------------------------- underlying_quote

def test_an_unsettled_bar_is_ignored_and_the_session_is_reported():
    """Catches a NaN spot passing every later range check.

    A NaN does not announce itself: every comparison against it is false,
    so bounds checks pass instead of tripping. The last settled close is
    used and the session it belongs to is recorded.
    """
    provider = provider_with(histories={"TEST": history_frame(
        [99.0, 101.0, float("nan")],
        ["2026-08-26", "2026-08-27", "2026-08-28"])})
    quote = provider.underlying_quote("TEST")

    assert quote["spot"] == 101.0
    assert quote["spot_asof"] == "2026-08-27"
    assert quote["bars_ignored_without_close"] == 1
    assert not math.isnan(quote["spot"])


def test_bars_with_closes_are_not_reported_as_ignored():
    """Catches the ignored count being wrong, which would misreport how
    stale a quote is."""
    provider = provider_with(histories={"TEST": history_frame(
        [99.0, 101.0], ["2026-08-27", "2026-08-28"])})
    quote = provider.underlying_quote("TEST")

    assert quote["spot"] == 101.0
    assert quote["bars_ignored_without_close"] == 0


def test_a_frame_with_no_settled_close_is_an_error():
    """Catches every bar being unsettled producing a quote anyway."""
    provider = provider_with(histories={"TEST": history_frame(
        [float("nan")], ["2026-08-28"])})
    with pytest.raises(ProviderDataError) as excinfo:
        provider.underlying_quote("TEST")
    assert "unsettled" in str(excinfo.value)


def test_an_empty_frame_is_an_error():
    """Catches an empty response being turned into a zero price."""
    provider = provider_with(histories={"TEST": history_frame([], [])})
    with pytest.raises(ProviderDataError) as excinfo:
        provider.underlying_quote("TEST")
    assert "no price history" in str(excinfo.value)


# ----------------------------------------------------------- risk_free_rate

def test_the_bill_yield_is_converted_from_percent_to_a_decimal():
    """Catches a rate used at a hundred times its real value.

    The bill is quoted in percent and every model here takes a decimal, so
    the conversion is the whole job.
    """
    provider = provider_with(histories={RATE_SYMBOL: history_frame(
        [5.25], ["2026-08-28"])})
    rate = provider.risk_free_rate()

    assert rate["rate"] == pytest.approx(0.0525)
    assert rate["source"] == RATE_SYMBOL
    assert rate["degraded"] is False


def test_an_unavailable_bill_falls_back_and_says_it_degraded():
    """Catches a substituted constant being presented as a fetched rate.

    Every rho computed downstream rests on this number, so the substitution
    has to be visible.
    """
    provider = provider_with(histories={RATE_SYMBOL: history_frame([], [])})
    rate = provider.risk_free_rate()

    assert rate["rate"] == FALLBACK_RATE
    assert rate["source"] == "fallback_constant"
    assert rate["degraded"] is True
    assert RATE_SYMBOL in rate["reason"]


# -------------------------------------------------------- underlying_history

def daily(count, start=100.0, step=0.5):
    closes = [start + step * i for i in range(count)]
    dates = pd.date_range("2024-01-01", periods=count, freq="D")
    return pd.DataFrame({"Close": closes}, index=dates)


def test_history_returns_are_log_returns():
    """Catches simple returns being used where log returns are compounded.

    A sum of log returns is the log of the compounded price; a sum of
    simple returns is nothing in particular, and the simulation sums them.
    """
    provider = provider_with(histories={"TEST": daily(80)})
    history = provider.underlying_history("TEST")
    closes = history["closes"]

    assert len(history["returns"]) == len(closes) - 1
    assert history["returns"][0] == pytest.approx(
        math.log(closes[1] / closes[0]))
    assert history["last_close"] == closes[-1]
    assert history["first"] == history["dates"][0]
    assert history["last"] == history["dates"][-1]


def test_history_too_short_to_fit_a_model_is_refused():
    """Catches a volatility model being fitted to a handful of points.

    A posterior from fifty observations is not a weaker answer, it is a
    number with no support, and it looks identical to a real one.
    """
    provider = provider_with(histories={"TEST": daily(40)})
    with pytest.raises(ProviderDataError) as excinfo:
        provider.underlying_history("TEST")
    assert "too few" in str(excinfo.value)


def test_history_never_emits_an_infinite_return():
    """Catches a zero or negative close producing an infinite log return.

    One infinity poisons the whole variance estimate and every quantile
    computed from it.
    """
    frame_with_zero = daily(80)
    frame_with_zero.iloc[40, 0] = 0.0
    provider = provider_with(histories={"TEST": frame_with_zero})
    returns = provider.underlying_history("TEST")["returns"]

    assert all(math.isfinite(value) for value in returns)


def test_history_with_no_data_is_an_error():
    """Catches an empty history being fitted as though it were a series."""
    provider = provider_with(histories={"TEST": history_frame([], [])})
    with pytest.raises(ProviderDataError) as excinfo:
        provider.underlying_history("TEST")
    assert "no price history" in str(excinfo.value)


# ------------------------------------------------------------- availability

def test_the_provider_reports_itself_unavailable_without_yfinance(
        monkeypatch):
    """Catches a missing optional dependency surfacing as an ImportError
    from somewhere unrelated.

    The registry decides what can answer by calling this, and the message a
    user sees has to name the package to install.
    """
    monkeypatch.setitem(sys.modules, "yfinance", None)
    provider = YahooProvider()

    assert provider.available() is False
    with pytest.raises(ProviderUnavailable) as excinfo:
        provider._client()
    assert "pip install yfinance" in str(excinfo.value)


def test_describe_reports_the_terms_without_claiming_redistribution():
    """Catches the data terms being dropped from the inventory.

    A licence on this software grants no rights over the data it retrieves,
    and the provider row is where that is recorded.
    """
    described = YahooProvider().describe()

    assert described["name"] == "yahoo"
    assert described["requires_key"] is False
    assert "legal.yahoo.com" in described["terms_url"]
    assert "redistribution" in described["notes"].lower()
    assert described["public_redistribution_approved"] is False
    assert described["public_web_display_approved"] is False
    assert described["public_mcp_delivery_approved"] is False
