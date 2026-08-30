"""Provider registry: selection, strictness, and failure containment."""

import pytest

from optiondesk import providers
from optiondesk.providers.base import (
    CAP_OPTION_CHAIN,
    Provider,
    ProviderUnavailable,
)


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
