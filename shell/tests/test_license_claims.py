"""Every surface that states a licence must state the current one.

The project moved from a split of MIT for the shell and AGPL for the engine
to one PolyForm Noncommercial licence. The relicensing commit changed the
LICENSE files, the package metadata and the prose in README and FAQ, and
missed nineteen places that keep making the old claim: the module docstring
and the status() report of engine_bridge, the installer's licence notice and
its interactive prompt, eleven engine test headers, a JSON schema
description, an MCP tool description, a skill's failure-mode advice, the
inventory generator, the disclaimer, and the contributor agreement, which
still described a dual licence the project no longer offers.

The doctor command was reporting AGPL-3.0-only to users for as long as that
was true of nothing. This file exists so the next licence change cannot be
declared finished while any of these still disagree.

MIT and AGPL are not banned words. They are correct in THIRD-PARTY.md about
other people's software, and in the passages of README and FAQ that explain
what changed and why. The scan below covers the surfaces that speak for this
project in the present tense.
"""

import json
import pathlib

import pytest

from optiondesk import engine_bridge

ROOT = pathlib.Path(__file__).resolve().parents[2]

# Files that state this project's own licence, as a claim about now.
CLAIM_SURFACES = [
    "install.sh",
    "DISCLAIMER.md",
    "CLA.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "engine/README.md",
    "shell/README.md",
    "agent/README.md",
    "shell/src/optiondesk/engine_bridge.py",
    "shell/src/optiondesk/mcp/server.py",
    "shell/src/optiondesk/artifacts.py",
    "shell/src/optiondesk/contracts/greeks_ladder.schema.json",
    "scripts/inventory.py",
]

SUPERSEDED = ("AGPL", "MIT")


def _claim_files():
    for name in CLAIM_SURFACES:
        path = ROOT / name
        if path.exists():
            yield name, path


@pytest.mark.parametrize("name", [n for n, _ in _claim_files()])
def test_no_surface_still_claims_the_old_licences(name):
    """One file per case, so a failure names the file rather than a count."""
    text = (ROOT / name).read_text(encoding="utf-8", errors="ignore")
    for token in SUPERSEDED:
        if token == "AGPL" and name == "CLA.md":
            # Point 4 forbids importing AGPL code. That is a statement about
            # other people's licences, not a claim about this one.
            continue
        assert token not in text, (
            "{} still claims {}, which this project no longer uses".format(
                name, token))


def test_the_engine_licence_is_reported_from_the_engine(monkeypatch):
    """status() held its own copy of the string, so the engine could be
    relicensed without the report noticing. It did exactly that.
    """
    engine = pytest.importorskip("optiondesk_engine")
    status = engine_bridge.status()
    if not status["available"]:
        pytest.skip("engine not installed")
    assert status["license"] == engine.LICENSE
    assert status["license"] == "PolyForm-Noncommercial-1.0.0"


def test_every_package_declares_the_same_licence():
    """Three pyproject files, one licence. A component drifting back to its
    own terms is how the split arose in the first place.
    """
    seen = {}
    for package in ("shell", "engine", "agent"):
        text = (ROOT / package / "pyproject.toml").read_text(encoding="utf-8")
        line = [l for l in text.splitlines() if l.startswith("license")]
        assert line, "{} declares no licence".format(package)
        seen[package] = line[0]
    assert len(set(seen.values())) == 1, seen
    assert "PolyForm-Noncommercial-1.0.0" in next(iter(seen.values()))


def test_the_schema_description_names_no_licence_at_all():
    """A contract description is read by other people's tooling. It had the
    engine's licence embedded in it, which meant relicensing changed a
    published schema.
    """
    path = ROOT / "shell/src/optiondesk/contracts/greeks_ladder.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    assert "AGPL" not in schema["description"]
    assert "licen" not in schema["description"].lower()
