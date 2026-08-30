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
    """Current UTC time as an ISO-8601 string ending in Z.

    Every artifact carries one, so timestamps written on different machines
    still order correctly.
    """
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


ARCHIVE_DIRNAME = "archive"


def _archive_stamp(path):
    """The time the outgoing artifact was generated, for its archived name.

    Its own `meta.generated_utc` is preferred over the file's mtime,
    because the mtime is when the bytes landed and the envelope is when the
    measurement was taken. They differ whenever a file is copied.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            stamp = json.load(handle).get("meta", {}).get("generated_utc")
    except (ValueError, OSError, AttributeError):
        stamp = None
    if not isinstance(stamp, str) or not stamp:
        try:
            stamp = datetime.fromtimestamp(
                path.stat().st_mtime, timezone.utc).isoformat()
        except OSError:
            stamp = utc_now()
    # Colons are legal on this filesystem and a nuisance on others.
    return stamp.replace(":", "").replace("-", "").replace("+0000", "Z")


def archive_existing(path):
    """Move an artifact about to be replaced into the archive.

    WHY THE LIVE NAME DOES NOT CHANGE. Filenames are keyed by underlying
    and expiry, so re-pulling the same chain replaced the previous one
    outright and no measurement quoted from it could be produced again.
    Timestamping the live file would fix that and break every consumer
    that resolves the newest artifact by name: the dashboard, `expiries`,
    the plan reuse in `compare`, and the graph's stage check. So the
    timestamp goes on the outgoing copy instead, and the live name is
    exactly what it was.

    Identical content is not archived. Re-running a command that produces
    the same bytes is not a new measurement, and archiving it would fill
    the directory with copies of one answer.

    Returns the archived path, or None if there was nothing to archive.
    Never raises: losing the archive is worse than nothing, but losing the
    write because the archive failed would be worse still.
    """
    if os.environ.get("OPTIONDESK_ARCHIVE", "1") == "0":
        return None
    try:
        if not path.exists():
            return None
        archive_dir = path.parent / ARCHIVE_DIRNAME / utc_now()[:10]
        archive_dir.mkdir(parents=True, exist_ok=True)
        target = archive_dir / "{}_{}{}".format(
            path.stem, _archive_stamp(path), path.suffix)
        if target.exists():
            return None
        os.replace(path, target)
        return target
    except OSError:
        return None


def write_json(payload, filename, directory=None):
    """Write one artifact atomically. Returns the path written.

    Raises ValueError if the payload contains a NaN or an infinity, which
    is deliberate: those are not representable in strict JSON, and an
    artifact that only Python can read is not an interchange format.

    An artifact this replaces is moved into `archive/<date>/` first, under
    a name carrying the time it was generated. Set OPTIONDESK_ARCHIVE=0 to
    turn that off.
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
    # After the temporary file is written, so a serialisation failure
    # cannot archive the old artifact and then leave nothing in its place.
    if path.exists() and path.read_bytes() != tmp.read_bytes():
        archive_existing(path)
    os.replace(tmp, path)
    return path


def read_json(path):
    """Read one artifact from disk.

    Raises rather than returning an empty default, because a caller that
    silently reads nothing goes on to report on an empty desk as though it were
    a quiet one.
    """
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
