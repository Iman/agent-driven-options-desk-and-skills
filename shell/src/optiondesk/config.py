"""Configuration: where artifacts go, and how provider credentials resolve.

Resolution order for any setting, highest priority first:

  1. an explicit argument passed by the caller (a CLI flag)
  2. an environment variable
  3. a key/value line in a .env file in the current working directory
  4. a key/value line in ~/.optiondesk/config.env
  5. the documented default

Credentials are read, never written, never logged and never copied into an
artifact. The only thing an artifact records is which provider answered and
whether the result was degraded.
"""

import os
from pathlib import Path

DEFAULT_ARTIFACT_DIR = Path.home() / "TradingDesk" / "option-desk"
USER_CONFIG = Path.home() / ".optiondesk" / "config.env"

# Environment variable names for optional paid providers. Absent keys are
# normal, not an error: the free tier is the default path.
PROVIDER_KEY_VARS = {
    "yahoo": None,
    "tradier": "TRADIER_API_KEY",
    "fmp": "FMP_API_KEY",
    "alpaca": "ALPACA_API_KEY",
    "polygon": "POLYGON_API_KEY",
    "alphavantage": "ALPHAVANTAGE_API_KEY",
    "finviz": "FINVIZ_API_KEY",
}

PUBLIC_DATA_MODES = ("local", "demo", "licensed")

_DOTENV_CACHE = None


def _load_dotenv_files():
    global _DOTENV_CACHE
    if _DOTENV_CACHE is not None:
        return _DOTENV_CACHE
    values = {}
    for path in (USER_CONFIG, Path.cwd() / ".env"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    _DOTENV_CACHE = values
    return values


def setting(name, default=None, override=None):
    """Resolve one setting through the documented precedence chain."""
    if override is not None:
        return override
    env = os.environ.get(name)
    if env:
        return env
    dotenv = _load_dotenv_files().get(name)
    if dotenv:
        return dotenv
    return default


def artifact_dir(override=None):
    """Directory artifacts are written to. Created on demand by the writer."""
    value = setting("OPTIONDESK_ARTIFACTS", None, override)
    return Path(value).expanduser() if value else DEFAULT_ARTIFACT_DIR


def public_data_mode(override=None):
    """Return the data boundary selected for this process.

    ``local`` permits providers under their local-use rules. ``demo`` does
    not permit any external provider. ``licensed`` permits only providers
    that carry an explicit public-redistribution approval in the code.
    Unknown values remain unknown so the provider gate can fail closed.
    """
    value = setting("PUBLIC_DATA_MODE", "local", override)
    return str(value).strip().lower()


def provider_key(provider):
    """API key for a provider, or None when it needs none or has none set."""
    var = PROVIDER_KEY_VARS.get(provider)
    if not var:
        return None
    return setting(var)


def has_key(provider):
    """True when a provider that requires a key has one available."""
    var = PROVIDER_KEY_VARS.get(provider)
    if not var:
        return True
    return bool(setting(var))


def configured_providers():
    """Report which providers could answer, without revealing any secret."""
    return {name: {"requires_key": bool(var), "key_present": has_key(name)}
            for name, var in PROVIDER_KEY_VARS.items()}
