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

import os

from optiondesk.config import PUBLIC_DATA_MODES, has_key, public_data_mode

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
    public_redistribution_approved = False
    public_web_display_approved = False
    public_mcp_delivery_approved = False
    public_derived_outputs_approved = False
    public_storage_approved = False
    terms_reviewed_on = None
    local_acknowledgement_env = None
    local_acknowledgement_value = None

    def access_status(self):
        """Report whether this process may use the provider.

        Provider availability and data permission are separate facts. A key
        or dependency can make a provider technically available without
        granting rights to publish its data.
        """
        mode = public_data_mode()
        if mode not in PUBLIC_DATA_MODES:
            return {
                "mode": mode,
                "allowed": False,
                "reason": (
                    "PUBLIC_DATA_MODE is invalid. Use local, demo, or "
                    "licensed. Access is denied until it is corrected."
                ),
            }
        if mode == "demo":
            return {
                "mode": mode,
                "allowed": False,
                "reason": "demo mode blocks every external data provider",
            }
        if mode == "licensed":
            approved = bool(
                self.public_redistribution_approved
                and self.public_web_display_approved
                and self.public_mcp_delivery_approved
                and self.public_derived_outputs_approved
                and self.public_storage_approved
            )
            return {
                "mode": mode,
                "allowed": approved,
                "reason": (
                    "provider has an explicit public-use approval"
                    if approved else
                    "provider is not approved for public web and MCP use"
                ),
            }
        if self.local_acknowledgement_env:
            accepted = os.environ.get(self.local_acknowledgement_env)
            expected = self.local_acknowledgement_value
            if accepted != expected:
                return {
                    "mode": mode,
                    "allowed": False,
                    "reason": (
                        "local terms acknowledgement is missing; set {}={} "
                        "only after reading the provider terms"
                    ).format(self.local_acknowledgement_env, expected),
                }
        return {"mode": mode, "allowed": True, "reason": "local use"}

    def require_access(self):
        status = self.access_status()
        if not status["allowed"]:
            raise ProviderUnavailable(
                "{} data access denied: {}".format(
                    self.name, status["reason"]))

    def available(self):
        """True when this provider could answer a request right now."""
        raise NotImplementedError

    def unavailable_reason(self):
        """Why available() is false right now, or None when it is true.

        Read by the registry when it skips a provider, so the refusal
        names the gate that actually closed rather than guessing. The
        gates, in the order available() meets them: the data boundary
        (demo mode, an invalid mode, a licence approval that is not
        recorded, a terms acknowledgement that is missing), a key that is
        not configured, and a dependency the subclass knows it needs. The
        registry used to print "missing dependency or key" for all of
        them, which was wrong for the commonest: in demo mode every
        external provider is refused with its key and its library both
        present.
        """
        access = self.access_status()
        if not access["allowed"]:
            return access["reason"]
        if self.requires_key and not has_key(self.name):
            return ("no API key configured; run 'optiondesk keys set {}' "
                    "or set its environment variable".format(self.name))
        return self.missing_dependency()

    def missing_dependency(self):
        """Name a library this provider needs and cannot import, or None."""
        return None

    def describe(self):
        access = self.access_status()
        available = bool(self.available())
        return {
            "name": self.name,
            "tier": self.tier,
            "requires_key": self.requires_key,
            "capabilities": list(self.capabilities),
            "available": available,
            "unavailable_reason": (None if available
                                   else self.unavailable_reason()),
            "terms_url": self.terms_url,
            "notes": self.notes,
            "data_mode": access["mode"],
            "access_allowed": access["allowed"],
            "access_reason": access["reason"],
            "public_redistribution_approved": bool(
                self.public_redistribution_approved),
            "public_web_display_approved": bool(
                self.public_web_display_approved),
            "public_mcp_delivery_approved": bool(
                self.public_mcp_delivery_approved),
            "public_derived_outputs_approved": bool(
                self.public_derived_outputs_approved),
            "public_storage_approved": bool(self.public_storage_approved),
            "terms_reviewed_on": self.terms_reviewed_on,
        }

    def option_chain(self, symbol, expiry=None, **kwargs):
        raise NotImplementedError

    def underlying_quote(self, symbol, **kwargs):
        raise NotImplementedError

    def risk_free_rate(self, **kwargs):
        raise NotImplementedError

    def underlying_history(self, symbol, **kwargs):
        raise NotImplementedError
