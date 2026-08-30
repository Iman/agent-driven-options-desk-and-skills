#!/usr/bin/env python3
"""Build every installable form of this project from one source.

There is one source of truth for the skills, `shell/skills`, and several
places people install from. Rather than maintaining copies by hand, this
builds them:

  dist/skills/<name>.zip      one zip per skill, for uploading in claude.ai
  dist/option-desk-skills.zip all five together
  plugin/                     a Claude Code plugin: skills, commands,
                              agents and the MCP server declaration
  .claude-plugin/marketplace.json
                              the marketplace entry that makes the plugin
                              installable with /plugin marketplace add

Run it after changing a skill, a command or an agent:

    python3 scripts/package.py

It prints what it wrote and verifies each zip round trips.
"""

import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "shell" / "skills"
COMMANDS = ROOT / ".claude" / "commands"
AGENTS = ROOT / ".claude" / "agents"
DIST = ROOT / "dist"
PLUGIN = ROOT / "plugin"

VERSION = "0.1.0"
AUTHOR = {"name": "Iman Samizadeh"}
DESCRIPTION = (
    "Option analytics an agent can drive: chains, the full Greek ladder, "
    "dealer positioning, seventeen structures with ranking, a GARCH-t "
    "simulation, backtests with modelled premiums, and a paper forward "
    "test. Research software, not investment advice."
)


def _skill_dirs():
    return sorted(p for p in SKILLS.iterdir()
                  if p.is_dir() and (p / "SKILL.md").exists())


def _copy_tree(source, target):
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc",
                                                  ".installed-by-optiondesk"))


# Every skill tells the reader to see DISCLAIMER.md at the repository root.
# In a standalone install there is no repository, so the pointer dangled.
# It travels with the skill instead.
CARRIED = ("DISCLAIMER.md",)


def _carry_into(archive, prefix):
    """Put the repository level documents a skill points at inside the zip."""
    for name in CARRIED:
        source = ROOT / name
        if source.exists():
            archive.write(source, Path(prefix) / name)


def build_zips():
    """One zip per skill plus a bundle, laid out as claude.ai expects.

    The zip contains the skill directory, not its contents loose, because
    the uploader takes the directory name as the skill name.
    """
    target = DIST / "skills"
    target.mkdir(parents=True, exist_ok=True)
    written = []

    for skill in _skill_dirs():
        path = target / "{}.zip".format(skill.name)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(skill.rglob("*")):
                if item.is_dir() or item.name == ".installed-by-optiondesk":
                    continue
                archive.write(item, Path(skill.name) / item.relative_to(skill))
            _carry_into(archive, skill.name)
        written.append(path)

    bundle = DIST / "option-desk-skills.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for skill in _skill_dirs():
            for item in sorted(skill.rglob("*")):
                if item.is_dir() or item.name == ".installed-by-optiondesk":
                    continue
                archive.write(item,
                              Path(skill.name) / item.relative_to(skill))
            _carry_into(archive, skill.name)
    written.append(bundle)

    # A zip that cannot be opened is worse than no zip, so each is read back.
    for path in written:
        with zipfile.ZipFile(path) as archive:
            broken = archive.testzip()
            if broken is not None:
                raise SystemExit("corrupt entry in {}: {}".format(path,
                                                                  broken))
    return written


def build_plugin():
    """A Claude Code plugin directory, assembled from the same sources."""
    PLUGIN.mkdir(exist_ok=True)
    (PLUGIN / ".claude-plugin").mkdir(exist_ok=True)

    manifest = {
        "name": "option-desk",
        "version": VERSION,
        "description": DESCRIPTION,
        "author": AUTHOR,
        "keywords": ["options", "greeks", "volatility", "risk", "trading",
                     "quantitative-finance", "backtesting", "mcp"],
        "license": "MIT",
    }
    (PLUGIN / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    for source, name in ((SKILLS, "skills"), (COMMANDS, "commands"),
                         (AGENTS, "agents")):
        if source.exists():
            _copy_tree(source, PLUGIN / name)

    # The skills point at it, and a plugin install has no repository to
    # find it in.
    for name in CARRIED:
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, PLUGIN / name)

    # The MCP server is what gives the plugin its tools. The command is
    # resolved at install time rather than hardcoded to one machine.
    (PLUGIN / ".mcp.json").write_text(json.dumps({
        "mcpServers": {
            "optiondesk": {
                "type": "stdio",
                "command": "optiondesk-mcp",
                "args": [],
            }
        }
    }, indent=2) + "\n", encoding="utf-8")

    (PLUGIN / "README.md").write_text(
        "# option-desk plugin\n\n"
        "Built by `scripts/package.py` from `shell/skills`, "
        "`.claude/commands` and `.claude/agents`. Do not edit here: edit "
        "the sources and rebuild, or the next build will discard your "
        "changes.\n\n"
        "The MCP server entry expects `optiondesk-mcp` on PATH, which "
        "`install.sh` puts there. The skills, commands and agents work "
        "without it; only the tools need it.\n",
        encoding="utf-8")
    return PLUGIN


def build_marketplace():
    """The marketplace manifest that makes the plugin one command to add."""
    (ROOT / ".claude-plugin").mkdir(exist_ok=True)
    marketplace = {
        "name": "option-desk",
        "owner": AUTHOR,
        "description": "Option analytics for agent runtimes.",
        "version": VERSION,
        "plugins": [
            {
                "name": "option-desk",
                "description": DESCRIPTION,
                "source": "./plugin",
                "category": "finance",
            }
        ],
    }
    path = ROOT / ".claude-plugin" / "marketplace.json"
    path.write_text(json.dumps(marketplace, indent=2) + "\n",
                    encoding="utf-8")
    return path


def main():
    zips = build_zips()
    plugin = build_plugin()
    marketplace = build_marketplace()

    print("skill archives, for uploading in claude.ai:")
    for path in zips:
        print("  {:44} {:>7} bytes".format(
            str(path.relative_to(ROOT)), path.stat().st_size))
    skills = len(_skill_dirs())
    commands = len(list((PLUGIN / "commands").glob("*.md"))) \
        if (PLUGIN / "commands").exists() else 0
    agents = len(list((PLUGIN / "agents").glob("*.md"))) \
        if (PLUGIN / "agents").exists() else 0
    print("plugin: {} with {} skills, {} commands, {} agents, "
          "1 mcp server".format(plugin.relative_to(ROOT), skills, commands,
                                agents))
    print("marketplace: {}".format(marketplace.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
