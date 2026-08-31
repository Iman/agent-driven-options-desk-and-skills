"""The screenshots referenced by the documentation must exist, and the
screenshots on disk must be referenced.

A broken image in a README is invisible to every test that reads text, and
an orphaned megabyte in a repository is invisible to everything. Both have
happened here: the gallery was regenerated with better names while the
index still pointed at the old ones.
"""

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SHOTS = ROOT / "docs" / "screenshots"
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+\.png)\)")


def _referenced():
    """Every png referenced by README.md or docs/SCREENSHOTS.md, resolved."""
    found = set()
    for doc, base in ((ROOT / "README.md", ROOT),
                      (ROOT / "docs" / "SCREENSHOTS.md", ROOT / "docs")):
        if not doc.exists():
            continue
        for match in IMAGE.findall(doc.read_text(encoding="utf-8")):
            if match.startswith("http"):
                continue
            found.add((base / match).resolve())
    return found


def test_every_referenced_screenshot_exists():
    missing = sorted(str(p.relative_to(ROOT)) for p in _referenced()
                     if not p.exists())
    assert not missing, "referenced but not on disk: {}".format(missing)


def test_every_screenshot_on_disk_is_referenced():
    if not SHOTS.exists():
        pytest.skip("no screenshots in this checkout")
    referenced = _referenced()
    orphans = sorted(str(p.relative_to(ROOT)) for p in SHOTS.rglob("*.png")
                     if p.resolve() not in referenced)
    assert not orphans, "on disk but referenced nowhere: {}".format(orphans)


def test_the_gallery_covers_every_kind():
    """Sections, panels and charts. A capture run that silently produced
    only one of the three would still pass the two tests above.
    """
    if not (SHOTS / "gallery").exists():
        pytest.skip("no gallery in this checkout")
    for kind, least in (("sections", 8), ("panels", 25), ("charts", 20)):
        found = list((SHOTS / "gallery" / kind).glob("*.png"))
        assert len(found) >= least, "{}: {} images".format(kind, len(found))
