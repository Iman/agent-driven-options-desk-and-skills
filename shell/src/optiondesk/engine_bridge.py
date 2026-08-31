"""The single seam between the shell and the analytics engine.

Only this module imports the engine. Every other part of the shell asks it
for analytics. That keeps the dependency auditable with one grep, and it
means the shell still runs, and still writes an honest degraded artifact,
when the engine is not installed.

Installing the engine is a deliberate act by the user. The shell never
installs it silently.
"""

ENGINE_PACKAGE = "optiondesk-engine"

MISSING_MESSAGE = (
    "The analytics engine is not installed, so no Greeks were computed. "
    "Install it with 'pip install optiondesk-engine' (or 'pip install -e "
    "engine' from a source checkout). It carries the same noncommercial "
    "licence as the rest of the project; see LICENSES.md."
)

try:  # pragma: no cover - trivially environment dependent
    from optiondesk_engine import (
        GREEK_KEYS,
        LICENSE as engine_license,
        __version__ as engine_version,
        all_greeks,
        bs_price,
        implied_vol,
    )
    from optiondesk_engine import analytics as _analytics
    from optiondesk_engine import backtest as _backtest
    from optiondesk_engine import simulation as _simulation
    from optiondesk_engine import strategies as _strategies
    AVAILABLE = True
except ImportError:  # pragma: no cover
    GREEK_KEYS = ()
    engine_version = None
    all_greeks = None
    bs_price = None
    implied_vol = None
    _analytics = None
    _backtest = None
    _simulation = None
    _strategies = None
    AVAILABLE = False


class EngineUnavailable(RuntimeError):
    """Raised when analytics are requested and the engine is absent."""

    def __init__(self, message=MISSING_MESSAGE):
        super().__init__(message)


def require():
    """Return the engine module surface, or raise with a fixable message."""
    if not AVAILABLE:
        raise EngineUnavailable()
    return {
        "all_greeks": all_greeks,
        "bs_price": bs_price,
        "implied_vol": implied_vol,
        "GREEK_KEYS": GREEK_KEYS,
        "version": engine_version,
    }


def strategies():
    """The engine's strategy surface: playbook, payoff, friction.

    Reached through here rather than imported directly, so the licence
    boundary stays checkable with one grep. An audit found a command
    importing optiondesk_engine.strategies directly, which was harmless at
    runtime but broke the invariant that every document in this repository
    asserts.
    """
    if not AVAILABLE:
        raise EngineUnavailable()
    return _strategies


def analytics():
    """The engine's chain analytics surface: exposure, walls, max pain."""
    if not AVAILABLE:
        raise EngineUnavailable()
    return _analytics


def simulation():
    """The engine's simulation surface: GARCH-t posterior and paths."""
    if not AVAILABLE:
        raise EngineUnavailable()
    return _simulation


def backtest():
    """The engine's backtest surface: the runner and its statistics."""
    if not AVAILABLE:
        raise EngineUnavailable()
    return _backtest


def status():
    """Describe engine availability for artifacts and for tools/list."""
    return {
        "available": AVAILABLE,
        "package": ENGINE_PACKAGE,
        "version": engine_version,
        "license": engine_license if AVAILABLE else None,
        "message": None if AVAILABLE else MISSING_MESSAGE,
    }
