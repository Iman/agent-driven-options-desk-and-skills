"""Provider interface.

A capability is what a caller needs ("option_chain"), not who supplies it
("yahoo"). Callers ask the registry for a capability and get whichever
provider can answer, so adding a paid provider later changes a registry
entry and nothing else.

Every provider reports three things honestly: whether it needs a key,
whether it can run right now, and what it actually returned. A provider that
cannot answer raises ProviderUnavailable with a message a user can act on.
It never returns an empty result that looks like a real one.
"""

CAP_OPTION_CHAIN = "option_chain"
CAP_UNDERLYING_QUOTE = "underlying_quote"
CAP_RISK_FREE_RATE = "risk_free_rate"
CAP_UNDERLYING_HISTORY = "underlying_history"
CAP_DIVIDEND_YIELD = "dividend_yield"

ALL_CAPABILITIES = (CAP_OPTION_CHAIN, CAP_UNDERLYING_QUOTE,
                    CAP_RISK_FREE_RATE, CAP_UNDERLYING_HISTORY,
                    CAP_DIVIDEND_YIELD)


class ProviderError(RuntimeError):
    """Base class for provider failures."""


class ProviderUnavailable(ProviderError):
    """The provider cannot run: missing dependency, missing key, no network.

    The message must tell the user what to do about it, because this is the
    error they will actually see.
    """


class ProviderDataError(ProviderError):
    """The provider ran and returned something unusable."""


class Provider:
    """Base class. Subclasses set the attributes and implement what they
    support; the registry never calls a method a provider did not declare."""

    name = "abstract"
    tier = "free"
    requires_key = False
    capabilities = ()
    terms_url = None
    notes = ""

    def available(self):
        """True when this provider could answer a request right now."""
        raise NotImplementedError

    def describe(self):
        return {
            "name": self.name,
            "tier": self.tier,
            "requires_key": self.requires_key,
            "capabilities": list(self.capabilities),
            "available": bool(self.available()),
            "terms_url": self.terms_url,
            "notes": self.notes,
        }

    def option_chain(self, symbol, expiry=None, **kwargs):
        raise NotImplementedError

    def underlying_quote(self, symbol, **kwargs):
        raise NotImplementedError

    def risk_free_rate(self, **kwargs):
        raise NotImplementedError

    def underlying_history(self, symbol, **kwargs):
        raise NotImplementedError
