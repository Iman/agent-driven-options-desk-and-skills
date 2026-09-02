"""Alpha Vantage provider: daily history behind a user-supplied key.

A Tier 1 provider, meaning it is used only when its key is present and is
skipped silently when it is not. It supplies price history, which the
simulation and the backtest need, and does not supply option chains: Alpha
Vantage's option endpoints are a paid tier, and pretending otherwise would
produce a provider that fails at the worst moment.

Why have it at all when Yahoo is free. Yahoo is a scraped, unofficial
endpoint that changes without notice. Alpha Vantage is a documented API
with a contract behind it, so when the two disagree the disagreement is
worth knowing about, and when Yahoo breaks this keeps working.

The free tier is heavily rate limited, currently around 25 requests a day
and one per second, so this provider sits below Yahoo in priority rather
than above it: it is the one you fall back to, not the one you burn on
every run.

The free tier also caps daily history at the most recent 100 closes.
outputsize=full is a paid feature and returns an error rather than data, so
the request is made as compact and the returned series says how much
history it actually carries. Ninety-nine returns is barely enough to fit a
volatility model and nowhere near enough to backtest, and the artifact must
say so rather than quietly fitting on a tenth of the intended window.

The key never appears in a log, an artifact or an error message. It is read
through the config chain at call time and passed only in the query string.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from optiondesk.config import provider_key
from optiondesk.providers.base import (
    CAP_UNDERLYING_HISTORY,
    CAP_UNDERLYING_QUOTE,
    Provider,
    ProviderDataError,
    ProviderUnavailable,
)

ENDPOINT = "https://www.alphavantage.co/query"
TIMEOUT_SECONDS = 30


class AlphaVantageProvider(Provider):

    """Alpha Vantage, the fallback for underlying history and quotes.

    Needs a key, and is skipped rather than failing when there is not one. Its
    free tier allows roughly 25 requests a day, so it sits below the free
    unlimited provider in every priority list.
    """
    name = "alphavantage"
    tier = "paid"
    requires_key = True
    capabilities = (CAP_UNDERLYING_HISTORY, CAP_UNDERLYING_QUOTE)
    terms_url = "https://www.alphavantage.co/terms_of_service/"
    notes = ("Documented API behind a user key. Free tier is rate limited "
             "to roughly 25 requests a day, so it sits below Yahoo in "
             "priority. Daily history only: option chains are a paid tier "
             "and are not claimed here. No public redistribution approval "
             "is recorded for this adapter.")
    terms_reviewed_on = "2026-09-02"

    def available(self):
        return bool(provider_key("alphavantage")) and bool(
            self.access_status()["allowed"])

    def _request(self, params):
        self.require_access()
        key = provider_key("alphavantage")
        if not key:
            raise ProviderUnavailable(
                "no Alpha Vantage key configured. Set ALPHAVANTAGE_API_KEY "
                "in the environment, in .env, or in "
                "~/.optiondesk/config.env, or run 'optiondesk keys set "
                "alphavantage'.")
        query = dict(params)
        query["apikey"] = key
        url = "{}?{}".format(ENDPOINT, urllib.parse.urlencode(query))
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as body:
                payload = json.loads(body.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # The URL carries the key, so it must never reach the message.
            raise ProviderDataError(
                "Alpha Vantage returned HTTP {}".format(exc.code)) from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ProviderDataError(
                "Alpha Vantage unreachable: {}".format(
                    type(exc).__name__)) from None
        except ValueError as exc:
            raise ProviderDataError(
                "Alpha Vantage returned something that is not JSON") from None

        # Rate limits and bad symbols come back as a 200 with a message,
        # which is exactly the shape that gets mistaken for data.
        for field in ("Note", "Information", "Error Message"):
            if field in payload:
                raise ProviderDataError("Alpha Vantage: {}".format(
                    str(payload[field])[:200]))
        return payload

    def underlying_history(self, symbol, period="2y"):
        """Daily closes and log returns.

        period is honoured approximately, by trimming the full series to
        the requested number of years, because the API offers compact or
        full rather than a date range.
        """
        import math

        # compact, not full: full is a paid feature and returns an error
        # message with a 200 status, which is the shape most likely to be
        # mistaken for data.
        payload = self._request({
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": "compact",
        })
        series = payload.get("Time Series (Daily)")
        if not series:
            raise ProviderDataError(
                "{}: no daily series returned".format(symbol))

        rows = sorted(series.items())
        years = 2.0
        if period.endswith("y"):
            try:
                years = float(period[:-1])
            except ValueError:
                years = 2.0
        keep = max(60, int(years * 252))
        rows = rows[-keep:]

        dates = [date for date, _ in rows]
        prices = [float(values["4. close"]) for _, values in rows]
        if len(prices) < 60:
            raise ProviderDataError(
                "{}: only {} closes available, too few to estimate a "
                "volatility model".format(symbol, len(prices)))

        returns = []
        spliced = 0
        for previous, current in zip(prices, prices[1:]):
            if previous <= 0 or current <= 0:
                spliced += 1
                continue
            returns.append(math.log(current / previous))

        requested = keep
        limited = len(prices) < requested
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
            "requested_observations": requested,
            "truncated_by_plan": limited,
            "limitation": ("the free plan caps daily history at the most "
                           "recent 100 closes, so {} of the {} requested "
                           "are available".format(len(prices), requested)
                           if limited else None),
        }

    def underlying_quote(self, symbol, period="5d"):
        payload = self._request({"function": "GLOBAL_QUOTE",
                                 "symbol": symbol})
        quote = payload.get("Global Quote") or {}
        price = quote.get("05. price")
        if price is None:
            raise ProviderDataError(
                "{}: no quote returned".format(symbol))
        return {
            "symbol": symbol,
            "spot": float(price),
            "spot_asof": quote.get("07. latest trading day"),
            "bars_ignored_without_close": 0,
        }
