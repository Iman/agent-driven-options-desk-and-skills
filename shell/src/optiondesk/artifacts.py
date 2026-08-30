"""Artifact envelope and atomic writing.

Every artifact this project writes carries the same meta block, because a
number without provenance cannot be audited later. The block records what
produced it, when, from which provider, and whether the result was degraded.

Atomic write: serialise to a temporary file in the destination directory,
then os.replace. A reader can then never catch a half-written file, and a
failed run cannot leave a truncated artifact that looks complete.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from optiondesk import __version__
from optiondesk.config import artifact_dir

# Carried inside every artifact. Short by necessity, and it points at the
# full terms rather than trying to restate them.
DISCLAIMER = (
    "Research output, not investment advice, and not a recommendation or "
    "solicitation. Option premiums here are theoretical model values, not "
    "quotes and not achievable fills. Market data is third-party, may be "
    "delayed or wrong, and its redistribution is governed by the provider's "
    "terms. No warranty. See DISCLAIMER.md."
)

LICENSE_NOTE = (
    "Produced by optiondesk (MIT shell) and, where analytics are present, "
    "optiondesk-engine (AGPL-3.0). See LICENSES.md."
)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def envelope(schema, tool, provider_used, degraded=False,
             degraded_reason=None, inputs=None, engine_version=None,
             notes=None):
    """Build the meta block shared by every artifact.

    Two distinct fields, because collapsing them destroys the signal.

    degraded means the run produced lower quality output than this pipeline
    normally can: a provider fell back, a rate could not be fetched, the
    analytics engine was absent. A consumer should hesitate before quoting
    the numbers, and degraded_reason says why.

    notes records ordinary observations that are not defects. A chain where
    some far wing contracts carry no quotes and therefore no implied
    volatility is a normal chain, not a broken run. Marking that degraded
    would make almost every artifact degraded and the flag would stop
    meaning anything.
    """
    return {
        "schema": schema,
        "generated_utc": utc_now(),
        "tool": tool,
        "shell_version": __version__,
        "engine_version": engine_version,
        "provider_used": provider_used,
        "degraded": bool(degraded),
        "degraded_reason": degraded_reason,
        "notes": list(notes or []),
        "inputs": inputs or {},
        "disclaimer": DISCLAIMER,
        "license": LICENSE_NOTE,
    }


def write_json(payload, filename, directory=None):
    """Write one artifact atomically. Returns the path written.

    Raises ValueError if the payload contains a NaN or an infinity, which
    is deliberate: those are not representable in strict JSON, and an
    artifact that only Python can read is not an interchange format.
    """
    target_dir = Path(directory) if directory else artifact_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        # allow_nan is off deliberately. The default writes NaN and
        # Infinity as bare tokens, which Python reads back and a strict
        # RFC 8259 parser rejects, so a non-finite number would leave this
        # process looking healthy and break somewhere else. Failing here
        # names the field instead.
        json.dump(payload, handle, indent=1, sort_keys=False,
                  allow_nan=False)
        handle.write("\n")
    os.replace(tmp, path)
    return path


def read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def latest(pattern, directory=None):
    """Most recently modified artifact matching a glob, or None.

    Used by the dashboard and by tools that chain off the previous step
    without being told the exact filename.
    """
    target_dir = Path(directory) if directory else artifact_dir()
    if not target_dir.exists():
        return None
    matches = sorted(target_dir.glob(pattern),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None
