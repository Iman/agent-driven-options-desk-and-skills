"""optiondesk keys: see, set and locate provider credentials.

Nothing here needs a key to work. Free providers cover chains, quotes,
rates and history, and every paid provider is skipped automatically when
its key is absent. This command exists so that adding one is a single
step rather than a hunt through documentation.

Where a key is stored, and why there. The default target is
~/.optiondesk/config.env, outside any repository, created with owner-only
permissions. A key in a project directory is one careless commit away from
being public, and .gitignore is a convention rather than a guarantee.

A key value is never printed in full, never logged, and never written into
an artifact. list shows the first and last two characters so you can tell
which key is loaded without exposing it.
"""

import argparse
import getpass
import json
import os
import stat
from pathlib import Path

from optiondesk import config as config_module
from optiondesk.config import (
    PROVIDER_KEY_VARS,
    USER_CONFIG,
    provider_key,
    setting,
)

MASK_VISIBLE = 2


def add_arguments(parser):
    """Register the key subcommand and its optional value, which is prompted
    for with hidden input when omitted.
    """
    parser.add_argument("action", nargs="?", default="list",
                        choices=("list", "set", "unset", "path"),
                        help="what to do")
    parser.add_argument("provider", nargs="?", default=None,
                        help="provider name, for set and unset")
    parser.add_argument("--value", default=None,
                        help="the key itself. Omit to be prompted without "
                             "the value appearing on screen or in your "
                             "shell history")
    return parser


def _mask(value):
    if not value:
        return None
    if len(value) <= MASK_VISIBLE * 2:
        return "*" * len(value)
    return "{}{}{}".format(value[:MASK_VISIBLE],
                           "*" * (len(value) - MASK_VISIBLE * 2),
                           value[-MASK_VISIBLE:])


def _assigns(path, variable):
    """True when this file assigns this exact variable.

    Written as a per line comparison rather than a substring test because
    the substring version reported FMP_API_KEY as coming from a file whose
    only content was EXTRA_FMP_API_KEY, which sends somebody debugging a
    credential to the wrong place and leaves the real source unnamed.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, _ = line.partition("=")
        if name.strip() == variable:
            return True
    return False


def _source_of(variable):
    """Where a key is coming from, without revealing it."""
    if os.environ.get(variable):
        return "environment"
    cwd_env = Path.cwd() / ".env"
    if _assigns(cwd_env, variable):
        return str(cwd_env)
    if _assigns(USER_CONFIG, variable):
        return str(USER_CONFIG)
    return None


def _write(variable, value):
    """Upsert one variable in the user config, owner-readable only.

    The file is opened with mode 0o600 rather than written and then
    tightened afterwards. The two step version put the key on disk group
    and world readable for the moment between the write and the chmod, and
    a backup daemon or a file indexer reading in that window is enough to
    copy it somewhere with looser permissions than this file ever had.

    The chmod stays, and covers the other case: a config file that already
    existed with looser permissions, where a creation mode is not applied
    because nothing is being created.
    """
    USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if USER_CONFIG.exists():
        lines = [line for line in USER_CONFIG.read_text(
            encoding="utf-8").splitlines()
            if not line.startswith(variable + "=")]
    if value is not None:
        lines.append("{}={}".format(variable, value))
    body = "\n".join(line for line in lines if line.strip()) + "\n"
    handle = os.open(str(USER_CONFIG),
                     os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(body)
    os.chmod(USER_CONFIG, stat.S_IRUSR | stat.S_IWUSR)
    # Any process that has already resolved a setting holds a parsed copy
    # of these files. Without this line the value just written is invisible
    # to the rest of the same process, which would let set report a mask of
    # null for a key that is on disk and correct.
    config_module._DOTENV_CACHE = None
    return USER_CONFIG


def run(args):
    """List, set or locate provider credentials, without printing one in full.
    """
    if args.action == "path":
        return {
            "config": str(USER_CONFIG),
            "exists": USER_CONFIG.exists(),
            "resolution_order": [
                "a command line flag",
                "the environment",
                ".env in the working directory",
                str(USER_CONFIG),
                "the free provider, when one can serve the capability",
            ],
        }

    if args.action == "list":
        rows = []
        for provider, variable in sorted(PROVIDER_KEY_VARS.items()):
            if not variable:
                rows.append({"provider": provider, "needs_key": False,
                             "configured": True, "source": None,
                             "variable": None, "masked": None})
                continue
            value = setting(variable)
            rows.append({
                "provider": provider,
                "needs_key": True,
                "configured": bool(value),
                "variable": variable,
                "source": _source_of(variable) if value else None,
                "masked": _mask(value),
            })
        return {
            "config": str(USER_CONFIG),
            "providers": rows,
            "note": ("Every paid provider is optional. The desk runs on "
                     "free sources with no key at all, and a provider "
                     "whose key is absent is skipped rather than failing."),
        }

    if not args.provider:
        raise ValueError("which provider? Try: optiondesk keys list")
    provider = args.provider.lower()
    if provider not in PROVIDER_KEY_VARS:
        raise ValueError("unknown provider {!r}. Known: {}".format(
            provider, ", ".join(sorted(PROVIDER_KEY_VARS))))
    variable = PROVIDER_KEY_VARS[provider]
    if not variable:
        raise ValueError("{} needs no key".format(provider))

    if args.action == "unset":
        path = _write(variable, None)
        return {"action": "unset", "provider": provider,
                "variable": variable, "config": str(path),
                "still_set_elsewhere": bool(setting(variable)),
                "note": ("Removed from the config file. If it is still set "
                         "in your environment or a .env file, it will keep "
                         "being found.")}

    value = args.value
    if value is None:
        # getpass keeps the key off the screen and out of shell history,
        # which is the whole reason to prefer the prompt over --value.
        value = getpass.getpass(
            "{} key (input hidden): ".format(provider)).strip()
    if not value:
        raise ValueError("no key given, nothing was written")

    path = _write(variable, value)
    return {
        "action": "set",
        "provider": provider,
        "variable": variable,
        "config": str(path),
        "permissions": oct(stat.S_IMODE(os.stat(path).st_mode)),
        "masked": _mask(provider_key(provider)),
        "note": ("Stored outside any repository. It is never printed in "
                 "full, never logged, and never written into an artifact."),
    }


def main(argv=None):
    """Parse argv for this command alone and run it, so the command works when
    invoked directly as well as through the dispatcher.
    """
    parser = add_arguments(argparse.ArgumentParser(
        prog="optiondesk keys", description=__doc__.splitlines()[0]))
    args = parser.parse_args(argv)
    print(json.dumps(run(args), indent=1, default=str))
    return 0
