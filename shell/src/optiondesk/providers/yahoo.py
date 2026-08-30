"""Yahoo Finance provider, through yfinance. Free, no key, delayed.

This is the default so that a fresh clone works with no signup. It is also
the weakest link in the chain, and the class is written to say so rather
than to paper over it.

Two failure modes are handled explicitly because both have produced silent
wrong answers in production before:

1. A partial session bar with an empty close. Taking the last row yields
   NaN, and a NaN spot does not announce itself: every later comparison
   against NaN is false, so range checks pass instead of tripping. The fix
   is to take the last row that has a real close, and to report which
   session that was in spot_asof.

2. No usable implied volatility on a contract. A defaulted volatility
   produces a complete and entirely fictional Greek ladder. Such contracts
   carry iv null and are counted, never filled in.

Yahoo data is for personal use under Yahoo's terms. Redistribution is not
granted by this project's licence. See DISCLAIMER.md section 5.
"""

import math
from datetime import datetime, timezone

from optiondesk.providers.base import (
    CAP_OPTION_CHAIN,
    CAP_RISK_FREE_RATE,
    CAP_UNDERLYING_HISTORY,
    CAP_UNDERLYING_QUOTE,
    Provider,
    ProviderDataError,
    ProviderUnavailable,
)

FALLBACK_RATE = 0.04
RATE_SYMBOL = "^IRX"  # 13-week US T-bill, quoted in percent


def _num(value, default=None):
    """float() with anything non-finite mapped to the default.

    isnan alone is not enough: an infinity passes it, and then int() on
    the volume field raises OverflowError several layers away from the
    quote that caused it.
    """
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return default if not math.isfinite(out) else out


class YahooProvider(Provider):

    """The free default, with no key and no signup.

    Covers option chains, underlying history, quotes and a risk free rate
    proxy. Data is delayed and third party, which is stated in every artifact
    it fills rather than assumed to be understood.
    """
    name = "yahoo"
    tier = "free"
    requires_key = False
    capabilities = (CAP_OPTION_CHAIN, CAP_UNDERLYING_QUOTE,
                    CAP_RISK_FREE_RATE, CAP_UNDERLYING_HISTORY)
    terms_url = "https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html"
    notes = ("Delayed and indicative. Personal use under Yahoo's terms; "
             "this project grants no data redistribution rights.")

    def __init__(self):
        self._yf = None

    def _client(self):
        if self._yf is None:
            try:
                import yfinance
            except ImportError as exc:
                raise ProviderUnavailable(
                    "yfinance is not installed. Install it with "
                    "'pip install yfinance' or 'pip install \"optiondesk"
                    "[yahoo]\"' to use the free Yahoo provider."
                ) from exc
            self._yf = yfinance
        return self._yf

    def available(self):
        try:
            self._client()
        except ProviderUnavailable:
            return False
        return True

    def underlying_quote(self, symbol, period="5d"):
        """Last settled close, and the session it belongs to."""
        yf = self._client()
        hist = yf.Ticker(symbol).history(period=period, auto_adjust=False)
        if hist is None or hist.empty:
            raise ProviderDataError(
                "{}: no price history returned".format(symbol))
        closes = hist["Close"].dropna()
        if closes.empty:
            raise ProviderDataError(
                "{}: {} bars returned, none with a close. The newest bar is "
                "probably an unsettled session.".format(symbol, len(hist)))
        return {
            "symbol": symbol,
            "spot": float(closes.iloc[-1]),
            "spot_asof": str(closes.index[-1].date()),
            "bars_ignored_without_close": int(len(hist) - len(closes)),
        }

    def risk_free_rate(self):
        """13-week T-bill yield as a decimal, or the documented fallback."""
        try:
            quote = self.underlying_quote(RATE_SYMBOL)
        except (ProviderDataError, ProviderUnavailable):
            return {"rate": FALLBACK_RATE, "source": "fallback_constant",
                    "degraded": True,
                    "reason": "{} unavailable".format(RATE_SYMBOL)}
        return {"rate": quote["spot"] / 100.0, "source": RATE_SYMBOL,
                "degraded": False, "reason": None}

    def underlying_history(self, symbol, period="2y"):
        """Daily closes and the log returns computed from them.

        Log returns rather than simple ones because the simulation
        compounds them, and a sum of log returns is the log of the
        compounded price while a sum of simple returns is nothing in
        particular.

        A non-positive close is skipped along with the return either side
        of it, so the series is spliced rather than ended. That is a
        deliberate trade and it is not free: a splice joins two prices that
        were never adjacent, which understates the volatility across the
        gap. The count is reported so a caller can see how much splicing
        happened. Missing closes cannot reach this point, since dropna has
        already removed them.
        """
        yf = self._client()
        frame = yf.Ticker(symbol).history(period=period, auto_adjust=True)
        if frame is None or frame.empty:
            raise ProviderDataError(
                "{}: no price history returned".format(symbol))
        closes = frame["Close"].dropna()
        if len(closes) < 60:
            raise ProviderDataError(
                "{}: only {} closes available, too few to estimate a "
                "volatility model".format(symbol, len(closes)))
        prices = [float(v) for v in closes.tolist()]
        dates = [str(index.date()) for index in closes.index]
        returns = []
        spliced = 0
        for previous, current in zip(prices, prices[1:]):
            if previous <= 0 or current <= 0:
                spliced += 1
                continue
            returns.append(math.log(current / previous))
        return {
            "symbol": symbol,
            "period": period,
            "closes": prices,
            "dates": dates,
            "returns": returns,
            "spliced_gaps": spliced,
            "first": dates[0],
            "last": dates[-1],
            "last_close": prices[-1],
        }

    def expiries(self, symbol):
        yf = self._client()
        listed = list(yf.Ticker(symbol).options or [])
        if not listed:
            raise ProviderDataError(
                "{}: no option expirations listed".format(symbol))
        return listed

    def option_chain(self, symbol, expiry=None):
        """Raw chain for one expiry. Volatility is left to the caller.

        The provider does not solve implied volatility, because the pricing
        model that solves it lives in the separately licensed engine. What
        comes back here is quotes plus whatever volatility the provider
        itself published, clearly labelled as theirs.
        """
        yf = self._client()
        ticker = yf.Ticker(symbol)
        listed = self.expiries(symbol)
        chosen = expiry or listed[0]
        if chosen not in listed:
            raise ProviderDataError(
                "{}: expiry {} is not listed. Available: {}".format(
                    symbol, chosen, ", ".join(listed[:8])))

        chain = ticker.option_chain(chosen)
        now = datetime.now(timezone.utc)
        # 21:00 UTC is the US close under standard time and an hour late
        # under daylight time. The error is under an hour on a horizon of
        # days, and it is recorded rather than hidden.
        expiry_dt = datetime.strptime(chosen, "%Y-%m-%d").replace(
            hour=21, tzinfo=timezone.utc)
        actual_days = (expiry_dt - now).total_seconds() / 86400.0
        # Floor at a quarter day so a contract expiring today still prices
        # instead of dividing by zero. The floor must never disguise an
        # expiry that has already passed, so the true figure travels with
        # it and the caller can refuse.
        days = max(actual_days, 0.25)
        expired = actual_days <= 0

        contracts = []
        for kind, frame in (("call", chain.calls), ("put", chain.puts)):
            for row in frame.to_dict("records"):
                bid = _num(row.get("bid"))
                ask = _num(row.get("ask"))
                last = _num(row.get("lastPrice"))
                # A zero bid is a real quote and must not be confused with
                # a missing one. Testing truthiness here substituted the
                # last traded price for the mid on 181 of 492 contracts in
                # one live SPY chain, and 178 of those had an implied
                # volatility solved from the substituted number.
                if bid is not None and ask is not None:
                    mid = (bid + ask) / 2.0
                    mid_source = "quote"
                else:
                    mid = last
                    mid_source = "last_trade" if last is not None else None
                provider_iv = _num(row.get("impliedVolatility"))
                contracts.append({
                    "symbol": str(row.get("contractSymbol") or ""),
                    "type": kind,
                    "strike": float(row["strike"]),
                    "bid": bid,
                    "ask": ask,
                    "mid": mid,
                    "mid_source": mid_source,
                    "last": last,
                    "volume": int(_num(row.get("volume"), 0) or 0),
                    "open_interest": int(_num(row.get("openInterest"), 0)
                                         or 0),
                    "iv": None,
                    "iv_source": None,
                    "iv_provider": provider_iv,
                })
        contracts.sort(key=lambda c: (c["type"], c["strike"]))
        return {
            "symbol": symbol,
            "expiry": chosen,
            "days_to_expiry": round(days, 4),
            "actual_days_to_expiry": round(actual_days, 4),
            "expired": expired,
            "contracts": contracts,
            "listed_expiries": listed,
        }
