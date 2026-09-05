"""Provider registry: selection, strictness, and failure containment."""

import sys

import pytest

from optiondesk import config, providers
from optiondesk.providers.base import (
    CAP_OPTION_CHAIN,
    Provider,
    ProviderUnavailable,
)
from optiondesk.providers.yahoo import YahooProvider


class Dummy(Provider):
    name = "dummy"
    tier = "free"
    requires_key = False
    capabilities = (CAP_OPTION_CHAIN,)

    def __init__(self, ok=True, raises=False):
        self.ok = ok
        self.raises = raises

    def available(self):
        if self.raises:
            raise RuntimeError("this provider is broken")
        return self.ok

    def option_chain(self, symbol, expiry=None):
        return {"symbol": symbol, "expiry": expiry or "2026-09-18",
                "days_to_expiry": 21.0, "contracts": [],
                "listed_expiries": []}


@pytest.fixture
def registry():
    """Register test providers and restore the registry afterwards.

    Without this the dummy stays registered for the rest of the session and
    every later test runs against a registry the author did not intend.
    """
    original = dict(providers._REGISTRY)
    yield providers
    providers._REGISTRY.clear()
    providers._REGISTRY.update(original)


def test_resolve_prefers_named_provider(registry):
    registry.register(Dummy(ok=True))
    provider, choice = registry.resolve(CAP_OPTION_CHAIN, "dummy")
    assert provider.name == "dummy"
    assert choice["chosen"] == "dummy"
    assert choice["degraded"] is False


def test_naming_a_provider_is_strict_by_default(registry):
    # Someone who names a provider usually has a data-quality reason.
    # Serving them a different one silently is the substitution this
    # project exists to avoid, so the default refuses.
    registry.register(Dummy(ok=False))
    with pytest.raises(ProviderUnavailable) as excinfo:
        registry.resolve(CAP_OPTION_CHAIN, "dummy")
    assert "no substitute was permitted" in str(excinfo.value)


def test_fallback_is_available_but_must_be_asked_for(registry):
    registry.register(Dummy(ok=False))
    provider, choice = registry.resolve(CAP_OPTION_CHAIN, "dummy",
                                        strict=False)
    assert provider.name != "dummy"
    assert choice["degraded"] is True
    assert any("dummy" in reason for reason in choice["skipped"])


def test_a_broken_provider_does_not_break_resolution(registry):
    # A provider that raises while reporting its own availability must not
    # take the registry down with it.
    registry.register(Dummy(raises=True))
    provider, choice = registry.resolve(CAP_OPTION_CHAIN, "dummy",
                                        strict=False)
    assert provider.name != "dummy"
    assert any("RuntimeError" in reason for reason in choice["skipped"])


def test_a_broken_provider_does_not_blank_the_inventory(registry):
    registry.register(Dummy(raises=True))
    described = registry.describe_all()
    assert "error" in described["dummy"]
    assert described["dummy"]["available"] is False
    # Every other provider must still be reported.
    assert "yahoo" in described


def test_resolve_raises_naming_every_candidate(registry, monkeypatch):
    registry.register(Dummy(ok=False))
    monkeypatch.setitem(registry.PRIORITY, CAP_OPTION_CHAIN, ["dummy"])
    with pytest.raises(ProviderUnavailable) as excinfo:
        registry.resolve(CAP_OPTION_CHAIN)
    message = str(excinfo.value)
    assert "dummy" in message and "not available" in message


def test_unknown_capability_is_an_error():
    with pytest.raises(KeyError):
        providers.resolve("no_such_capability")


def test_describe_all_never_leaks_a_key():
    described = providers.describe_all()
    assert "yahoo" in described
    blob = repr(described).lower()
    assert "api_key" not in blob and "secret" not in blob
    assert described["yahoo"]["requires_key"] is False


def test_demo_mode_blocks_every_external_provider(registry, monkeypatch):
    monkeypatch.setenv("PUBLIC_DATA_MODE", "demo")
    with pytest.raises(ProviderUnavailable) as excinfo:
        registry.resolve(CAP_OPTION_CHAIN, "yahoo")
    assert "no substitute was permitted" in str(excinfo.value)
    assert registry.describe_all()["yahoo"]["access_allowed"] is False


def test_licensed_mode_fails_closed_without_provider_approval(
        registry, monkeypatch):
    monkeypatch.setenv("PUBLIC_DATA_MODE", "licensed")
    with pytest.raises(ProviderUnavailable):
        registry.resolve(CAP_OPTION_CHAIN, "yahoo")
    described = registry.describe_all()["yahoo"]
    assert described["public_redistribution_approved"] is False
    assert described["public_mcp_delivery_approved"] is False


def test_invalid_public_mode_denies_access(registry, monkeypatch):
    monkeypatch.setenv("PUBLIC_DATA_MODE", "licenced")
    with pytest.raises(ProviderUnavailable):
        registry.resolve(CAP_OPTION_CHAIN, "yahoo")
    assert "invalid" in registry.describe_all()["yahoo"][
        "access_reason"].lower()


def test_yahoo_requires_explicit_local_acknowledgement(monkeypatch):
    monkeypatch.delenv("OPTIONDESK_ACCEPT_YAHOO_TERMS", raising=False)
    described = providers.get("yahoo").describe()
    assert described["access_allowed"] is False
    assert "acknowledgement" in described["access_reason"]


# ------------------------------------------------- the reason for a refusal
#
# resolve() used to write "not available (missing dependency or key)" for
# every provider whose available() was false. That was a guess, and wrong
# for the commonest case: demo mode refuses every external provider with
# the key and the library both present, and the message sent the user
# looking for an install problem that did not exist.

def test_the_refusal_names_demo_mode_when_that_is_the_cause(registry,
                                                            monkeypatch):
    monkeypatch.setenv("PUBLIC_DATA_MODE", "demo")
    with pytest.raises(ProviderUnavailable) as excinfo:
        registry.resolve(CAP_OPTION_CHAIN, "yahoo")
    message = str(excinfo.value)
    assert "demo mode blocks every external data provider" in message
    assert "missing dependency or key" not in message


def test_the_refusal_names_the_missing_acknowledgement(registry,
                                                       monkeypatch):
    monkeypatch.delenv("OPTIONDESK_ACCEPT_YAHOO_TERMS", raising=False)
    with pytest.raises(ProviderUnavailable) as excinfo:
        registry.resolve(CAP_OPTION_CHAIN, "yahoo")
    assert "acknowledgement is missing" in str(excinfo.value)


def test_the_refusal_names_the_missing_key(registry, monkeypatch):
    class Keyed(Dummy):
        name = "keyed"
        requires_key = True

    monkeypatch.setitem(config.PROVIDER_KEY_VARS, "keyed",
                        "KEYED_TEST_PROVIDER_TOKEN")
    monkeypatch.delenv("KEYED_TEST_PROVIDER_TOKEN", raising=False)
    registry.register(Keyed(ok=False))
    with pytest.raises(ProviderUnavailable) as excinfo:
        registry.resolve(CAP_OPTION_CHAIN, "keyed")
    message = str(excinfo.value)
    assert "no API key configured" in message
    assert "optiondesk keys set keyed" in message


def test_the_refusal_names_the_missing_dependency(registry, monkeypatch):
    # A fresh adapter, because the registered one may have imported the
    # library already and cached it.
    monkeypatch.setitem(sys.modules, "yfinance", None)
    registry.register(YahooProvider())
    with pytest.raises(ProviderUnavailable) as excinfo:
        registry.resolve(CAP_OPTION_CHAIN, "yahoo")
    assert "yfinance is not installed" in str(excinfo.value)


def test_a_provider_that_gives_no_reason_is_still_reported_as_unavailable(
        registry):
    registry.register(Dummy(ok=False))
    with pytest.raises(ProviderUnavailable) as excinfo:
        registry.resolve(CAP_OPTION_CHAIN, "dummy")
    message = str(excinfo.value)
    assert "dummy: not available" in message
    assert "without a reason" in message


def test_a_reason_check_that_raises_does_not_take_the_registry_down(
        registry, monkeypatch):
    dummy = Dummy(ok=False)
    monkeypatch.setattr(dummy, "unavailable_reason",
                        lambda: 1 / 0)
    registry.register(dummy)
    provider, choice = registry.resolve(CAP_OPTION_CHAIN, "dummy",
                                        strict=False)
    assert provider.name != "dummy"
    assert any("ZeroDivisionError" in reason for reason in choice["skipped"])


def test_describe_carries_the_reason_a_provider_is_unavailable(registry,
                                                               monkeypatch):
    monkeypatch.setenv("PUBLIC_DATA_MODE", "demo")
    described = registry.describe_all()["yahoo"]
    assert described["available"] is False
    assert "demo mode" in described["unavailable_reason"]
    # And nothing in it names a key variable, which the leak test above
    # would otherwise read as a secret.
    assert "api_key" not in repr(described).lower()
