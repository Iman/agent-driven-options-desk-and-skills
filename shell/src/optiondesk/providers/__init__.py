"""Provider registry: capability in, provider out.

Order within a capability is priority order. The first provider that is
available answers. A paid provider placed above a free one is used only when
its key is present, so the same code path serves a user with keys and a user
with none, and the artifact records which one actually answered.

Adding a provider is two steps: implement the class, add it to PRIORITY.
No caller changes.
"""

from optiondesk.providers.base import (
    ALL_CAPABILITIES,
    CAP_DIVIDEND_YIELD,
    CAP_OPTION_CHAIN,
    CAP_RISK_FREE_RATE,
    CAP_UNDERLYING_HISTORY,
    CAP_UNDERLYING_QUOTE,
    Provider,
    ProviderDataError,
    ProviderError,
    ProviderUnavailable,
)
from optiondesk.providers.alphavantage import AlphaVantageProvider
from optiondesk.providers.yahoo import YahooProvider

_REGISTRY = {}


def register(provider):
    """Add a provider to the registry under its own name."""
    _REGISTRY[provider.name] = provider
    return provider


register(YahooProvider())
register(AlphaVantageProvider())

# Priority per capability. Paid providers, once implemented, sit above
# yahoo here; they are skipped automatically when their key is absent.
PRIORITY = {
    CAP_OPTION_CHAIN: ["yahoo"],
    CAP_RISK_FREE_RATE: ["yahoo"],
    # Yahoo first: free and unlimited. Alpha Vantage is the fallback,
    # because its free tier allows roughly 25 requests a day and burning
    # them on a routine pull would leave nothing for the day it is needed.
    CAP_UNDERLYING_HISTORY: ["yahoo", "alphavantage"],
    CAP_UNDERLYING_QUOTE: ["yahoo", "alphavantage"],
    CAP_DIVIDEND_YIELD: ["yahoo"],
}


def get(name):
    """Return a provider by name, or raise listing the names that do exist."""
    if name not in _REGISTRY:
        raise KeyError("unknown provider {!r}. Known: {}".format(
            name, ", ".join(sorted(_REGISTRY))))
    return _REGISTRY[name]


def _reason(provider):
    """Why a provider reports itself unavailable, in the provider's words.

    The registry used to write "missing dependency or key" for every
    skipped provider. That was a guess, and wrong for the commonest case:
    PUBLIC_DATA_MODE=demo refuses every external provider with the key and
    the library both present, and the message sent the user looking for
    an install problem that did not exist. The provider knows which gate
    closed and says so; one that raises while explaining itself is
    reported as such rather than allowed to take the registry down.
    """
    try:
        reason = provider.unavailable_reason()
    except Exception as exc:
        return "its reason check raised {}: {}".format(
            type(exc).__name__, exc)
    return reason or "the provider reports itself unavailable without a reason"


def resolve(capability, preferred=None, strict=True):
    """Return the provider that will answer, and why it was chosen.

    A named preferred provider is honoured strictly by default: if it
    cannot answer, this raises rather than quietly returning a different
    one. Someone who names a provider is usually doing it for a data
    quality reason, and silently serving them another source is exactly
    the substitution this project exists to avoid. Pass strict=False to
    allow the fallback.

    Raises ProviderUnavailable listing every candidate and why each was
    skipped, so the user is never left guessing which dependency or key is
    missing.
    """
    if capability not in PRIORITY:
        raise KeyError("unknown capability {!r}. Known: {}".format(
            capability, ", ".join(ALL_CAPABILITIES)))
    if preferred and strict:
        order = [preferred]
    elif preferred:
        order = [preferred] + [n for n in PRIORITY[capability]
                               if n != preferred]
    else:
        order = list(PRIORITY[capability])

    skipped = []
    for name in order:
        provider = _REGISTRY.get(name)
        if provider is None:
            skipped.append("{}: not registered".format(name))
            continue
        if capability not in provider.capabilities:
            skipped.append("{}: does not supply {}".format(name, capability))
            continue
        try:
            usable = provider.available()
        except Exception as exc:
            # A provider that raises while reporting its own availability
            # must not take down the registry, and must not take down
            # status reporting for every other provider either.
            skipped.append("{}: availability check raised {}: {}".format(
                name, type(exc).__name__, exc))
            continue
        if not usable:
            skipped.append("{}: not available ({})".format(
                name, _reason(provider)))
            continue
        return provider, {"chosen": name,
                          "degraded": bool(skipped),
                          "skipped": skipped}
    if preferred and strict:
        raise ProviderUnavailable(
            "provider {!r} cannot supply {} and no substitute was "
            "permitted: {}".format(preferred, capability,
                                   "; ".join(skipped) or "unknown reason"))
    raise ProviderUnavailable(
        "no provider can supply {}. Tried: {}".format(
            capability, "; ".join(skipped) or "none"))


def describe_all():
    """Inventory for status reporting.

    One provider raising must not blank the whole inventory, so a failure
    is reported in that provider's own row.
    """
    out = {}
    for name, provider in sorted(_REGISTRY.items()):
        try:
            out[name] = provider.describe()
        except Exception as exc:
            out[name] = {"name": name, "available": False,
                         "error": "{}: {}".format(type(exc).__name__, exc)}
    return out


__all__ = ["register", "get", "resolve", "describe_all", "PRIORITY",
           "Provider", "ProviderError", "ProviderUnavailable",
           "ProviderDataError", "CAP_OPTION_CHAIN", "CAP_UNDERLYING_QUOTE",
           "CAP_RISK_FREE_RATE", "CAP_UNDERLYING_HISTORY",
           "CAP_DIVIDEND_YIELD",
           "ALL_CAPABILITIES"]
