"""The guide pages under docs/wiki must hold together and stay honest.

WHAT WOULD BREAK. The wiki is written as relative Markdown so it reads in a
checkout and, after a mechanical link conversion, on GitHub's wiki. A link
to a page that was renamed, or to an anchor whose heading was reworded,
renders fine and leads nowhere; nothing else in the suite looks at these
pages, so the first reader to notice would be a stranger. Three of the
pages are frozen copies of an earlier README, FAQ and INSTALL, and a
manifest records the hashes they were frozen at. Without a check, an edit
to a "preserved" page silently turns history into fiction.
"""

import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
WIKI = ROOT / "docs" / "wiki"
MANIFEST = ROOT / "docs" / "reference-preservation.json"

LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*)$")


def _anchors(path):
    """Heading ids the way GitHub derives them: lower case, punctuation
    dropped, spaces to hyphens. Enough for the anchors this wiki uses."""
    found = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = HEADING.match(line)
        if not match:
            continue
        text = match.group(1).strip().lower()
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"[`*_]", "", text)
        text = re.sub(r"[^\w\s-]", "", text)
        found.add(re.sub(r"\s+", "-", text.strip()))
    return found


def test_every_relative_wiki_link_and_anchor_resolves():
    broken = []
    for page in sorted(WIKI.glob("*.md")):
        for _, _, target in LINK.findall(page.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path, _, anchor = target.partition("#")
            dest = page if not path else (page.parent / path).resolve()
            if not dest.exists():
                broken.append("{} -> {} (missing)".format(page.name, target))
            elif anchor and dest.suffix == ".md" and anchor not in _anchors(dest):
                broken.append("{} -> {} (no such anchor)".format(page.name,
                                                                 target))
    assert not broken, "broken wiki links: {}".format(broken[:10])


def test_the_sidebar_names_every_guide_page():
    """A page the sidebar omits is a page nobody finds."""
    sidebar = (WIKI / "_Sidebar.md").read_text(encoding="utf-8")
    listed = {t for _, _, t in LINK.findall(sidebar) if t.endswith(".md")}
    pages = {p.name for p in WIKI.glob("*.md") if not p.name.startswith("_")}
    # The user-guide stub is a landing page for an old link, not a guide.
    pages.discard("Option-Desk-user-guide.md")
    missing = sorted(pages - listed)
    assert not missing, "not in _Sidebar.md: {}".format(missing)


def test_the_preserved_reference_pages_match_their_manifest():
    """Each frozen page is a header, a rule, then the original body."""
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert entries, "the preservation manifest is empty"
    for entry in entries:
        page = ROOT / entry["archive"]
        text = page.read_text(encoding="utf-8")
        header, separator, body = text.partition("\n---\n\n")
        assert separator, "{} has no header separator".format(page.name)
        assert entry["source_commit"][:7] in header, (
            "{} does not name the revision it preserves".format(page.name))
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert digest == entry["body_sha256"], (
            "{} no longer matches the body it was frozen at; the manifest "
            "says {} and the page hashes to {}".format(
                page.name, entry["body_sha256"][:12], digest[:12]))
        assert body.count("```mermaid") == entry["mermaid_diagrams"], (
            "{} carries a different number of Mermaid diagrams than the "
            "manifest records".format(page.name))
