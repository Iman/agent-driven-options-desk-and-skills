#!/usr/bin/env python3
"""Build every installable form of this project from one source.

There is one source of truth for the skills, `shell/skills`, and several
places people install from. Rather than maintaining copies by hand, this
builds them:

  dist/skills/<name>.zip      one portable archive per agent skill
  dist/option-desk-skills.zip all six together for Claude skill upload
  dist/option-desk-openai-skills.zip
                              one skills-only OpenAI plugin archive
  plugins/option-desk/        one dual-host plugin: OpenAI/Codex plus Claude
  .claude-plugin/marketplace.json
                              the Claude Code marketplace entry
  .agents/plugins/marketplace.json
                              the ChatGPT and Codex marketplace entry

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
PLUGIN = ROOT / "plugins" / "option-desk"
ASSETS = ROOT / "assets"

BRANDING = {
    "logo": "openai-directory-icon.png",
    "composerIcon": "openai-composer-icon.png",
}
PUBLISH_IGNORES = {".DS_Store", ".installed-by-optiondesk", "__pycache__"}

VERSION = "0.3.0"
AUTHOR = {"name": "Iman Samizadeh"}
REPOSITORY = "https://github.com/Iman/agent-driven-options-desk-and-skills"
DESCRIPTION = (
    "Option analytics an agent can drive: chains, the full Greek ladder, "
    "dealer positioning, twenty-three structures with ranking, a GARCH-t "
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
                    ignore=shutil.ignore_patterns(*PUBLISH_IGNORES, "*.pyc"))


def _publishable(path):
    """Return whether a source file belongs in a release artifact."""
    return (path.is_file()
            and not PUBLISH_IGNORES.intersection(path.parts)
            and path.suffix != ".pyc")


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


def _codex_manifest(include_mcp):
    """Return the shared Codex manifest, with optional local MCP wiring."""
    keywords = ["options", "greeks", "volatility", "risk", "trading",
                "quantitative-finance", "backtesting", "mcp", "skills",
                "claude-skills", "agent-skills", "langgraph",
                "options-pricing"]
    if include_mcp:
        description = DESCRIPTION
        long_description = (
            "Build option-chain research artifacts, inspect Greeks and "
            "positioning, show plots, compare structures, simulate outcomes, and "
            "backtest rules. Research software, not investment advice."
        )
        default_prompts = [
            "Show SPY option plots for the nearest expiry.",
            "Read dealer positioning for QQQ.",
            "Compare option structures for a neutral TLT view.",
        ]
    else:
        keywords.remove("mcp")
        description = (
            "Interpret user-provided option-chain data and research artifacts "
            "using focused workflows for Greeks, positioning, strategy, "
            "simulation, and backtests. Users must have the right to share "
            "their inputs. Research software, not investment advice."
        )
        long_description = (
            "Interpret user-provided option research without fetching live "
            "data. Review Greeks and positioning, compare structures, and "
            "assess simulations and backtests. Use only data that you have "
            "the right to share. Research software, not investment advice."
        )
        default_prompts = [
            "Explain the main risks in this option-chain snapshot.",
            "Compare these option structures and their trade-offs.",
            "Review this backtest for weak evidence and overlap.",
        ]
    interface = {
        "displayName": "Option Desk",
        "shortDescription": "Research listed options.",
        "longDescription": long_description,
        "developerName": AUTHOR["name"],
        "category": "Finance",
        "capabilities": ["Read", "Write"] if include_mcp else ["Read"],
        "websiteURL": REPOSITORY,
        "logo": "./assets/{}".format(BRANDING["logo"]),
        "composerIcon": "./assets/{}".format(BRANDING["composerIcon"]),
        "brandColor": "#2F6FEB",
        # Codex enforces MAX_DEFAULT_PROMPT_COUNT = 3 and
        # MAX_DEFAULT_PROMPT_LEN = 128, neither of which appears in the
        # prose documentation. A fourth entry is rejected outright.
        "defaultPrompt": default_prompts,
    }
    manifest = {
        "name": "option-desk",
        "version": VERSION,
        "description": description,
        "author": AUTHOR,
        "homepage": REPOSITORY,
        "repository": REPOSITORY,
        "license": "PolyForm-Noncommercial-1.0.0",
        "keywords": keywords,
        "skills": "./skills/",
        "interface": interface,
    }
    if include_mcp:
        manifest["mcpServers"] = "./.mcp.json"
    return manifest


def _branding_sources():
    """Return required branding paths, failing before an invalid release."""
    sources = [ASSETS / name for name in BRANDING.values()]
    missing = [path for path in sources if not path.is_file()]
    if missing:
        raise SystemExit("missing plugin branding: {}".format(
            ", ".join(str(path.relative_to(ROOT)) for path in missing)))
    return sources


def build_zips():
    """Build portable skill zips and host-specific aggregate archives.

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
                if not _publishable(item):
                    continue
                archive.write(item, Path(skill.name) / item.relative_to(skill))
            _carry_into(archive, skill.name)
        written.append(path)

    bundle = DIST / "option-desk-skills.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for skill in _skill_dirs():
            for item in sorted(skill.rglob("*")):
                if not _publishable(item):
                    continue
                archive.write(item,
                              Path(skill.name) / item.relative_to(skill))
            _carry_into(archive, skill.name)
    written.append(bundle)

    # Public OpenAI skills-only submissions need the plugin manifest and
    # skills/ layout, but must not carry an MCP descriptor or declaration.
    openai = DIST / "option-desk-openai-skills.zip"
    with zipfile.ZipFile(openai, "w", zipfile.ZIP_DEFLATED) as archive:
        manifest = json.dumps(_codex_manifest(include_mcp=False), indent=2)
        archive.writestr(".codex-plugin/plugin.json", manifest + "\n")
        for skill in _skill_dirs():
            prefix = Path("skills") / skill.name
            for item in sorted(skill.rglob("*")):
                if not _publishable(item):
                    continue
                archive.write(item, prefix / item.relative_to(skill))
        _carry_into(archive, "")
        for source in _branding_sources():
            archive.write(source, Path("assets") / source.name)
    written.append(openai)

    # A zip that cannot be opened is worse than no zip, so each is read back.
    for path in written:
        with zipfile.ZipFile(path) as archive:
            broken = archive.testzip()
            if broken is not None:
                raise SystemExit("corrupt entry in {}: {}".format(path,
                                                                  broken))
    return written


def build_plugin():
    """A dual-host Claude and OpenAI/Codex plugin from the same sources."""
    if PLUGIN.exists():
        shutil.rmtree(PLUGIN)
    PLUGIN.mkdir(parents=True)
    (PLUGIN / ".claude-plugin").mkdir(exist_ok=True)
    (PLUGIN / ".codex-plugin").mkdir(exist_ok=True)

    keywords = ["options", "greeks", "volatility", "risk", "trading",
                "quantitative-finance", "backtesting", "mcp", "skills",
                "claude-skills", "agent-skills", "langgraph",
                "options-pricing"]
    claude_manifest = {
        "name": "option-desk",
        "version": VERSION,
        "description": DESCRIPTION,
        "author": AUTHOR,
        # These are what search matches on. "skills" and "claude-skills"
        # are here rather than in the repository name, where they would
        # cost eleven characters of every install URL forever and would
        # name the smallest of six surfaces.
        "keywords": keywords,
        "license": "PolyForm-Noncommercial-1.0.0",
    }
    (PLUGIN / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(claude_manifest, indent=2) + "\n", encoding="utf-8")

    codex_manifest = _codex_manifest(include_mcp=True)
    (PLUGIN / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(codex_manifest, indent=2) + "\n", encoding="utf-8")

    for source, name in ((SKILLS, "skills"), (COMMANDS, "commands"),
                         (AGENTS, "agents")):
        if source.exists():
            _copy_tree(source, PLUGIN / name)

    asset_target = PLUGIN / "assets"
    asset_target.mkdir(exist_ok=True)
    for source in _branding_sources():
        shutil.copy2(source, asset_target / source.name)

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
        "`.claude/commands` and `.claude/agents`. It carries both "
        "`.codex-plugin` and `.claude-plugin` manifests. Do not edit here: "
        "edit the sources and rebuild, or the next build will discard your "
        "changes.\n\n"
        "The MCP server entry expects `optiondesk-mcp` on PATH, which "
        "`install.sh` puts there.\n\n"
        "What reaches which host. The six skills work in Claude Code, "
        "ChatGPT and Codex. The two agents are Claude only: Codex reads "
        "agents as TOML under ~/.codex/agents and ignores these Markdown "
        "ones entirely, so they ship here as inert weight for that host. "
        "The commands are Claude first: Codex converts a plugin's commands "
        "into skills at install time but skips any command whose body uses "
        "$1-style placeholders, so five of the six do not appear there and "
        "desk-mark does.\n\n"
        "Without the local binary the skills remain instructions and "
        "cannot produce fresh market numbers. ChatGPT on the web also "
        "needs a hosted HTTP MCP connector to execute the tools; this "
        "bundle provides only local stdio MCP.\n",
        encoding="utf-8")
    return PLUGIN


def build_marketplaces():
    """Write the Claude and OpenAI/Codex repository marketplaces."""
    (ROOT / ".claude-plugin").mkdir(exist_ok=True)
    claude_marketplace = {
        "name": "option-desk",
        "owner": AUTHOR,
        "description": "Option analytics for agent runtimes.",
        "version": VERSION,
        "plugins": [
            {
                "name": "option-desk",
                "description": DESCRIPTION,
                "source": "./plugins/option-desk",
                "category": "finance",
            }
        ],
    }
    claude_path = ROOT / ".claude-plugin" / "marketplace.json"
    claude_path.write_text(json.dumps(claude_marketplace, indent=2) + "\n",
                           encoding="utf-8")

    codex_marketplace = {
        "name": "option-desk",
        "interface": {"displayName": "Option Desk"},
        "plugins": [
            {
                "name": "option-desk",
                "source": {
                    "source": "local",
                    "path": "./plugins/option-desk",
                },
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Finance",
            }
        ],
    }
    codex_path = ROOT / ".agents" / "plugins" / "marketplace.json"
    codex_path.parent.mkdir(parents=True, exist_ok=True)
    codex_path.write_text(json.dumps(codex_marketplace, indent=2) + "\n",
                          encoding="utf-8")
    return [claude_path, codex_path]


def main():
    zips = build_zips()
    plugin = build_plugin()
    marketplaces = build_marketplaces()

    print("portable skill archives and host-specific bundles:")
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
    print("marketplaces: {}".format(
        ", ".join(str(path.relative_to(ROOT)) for path in marketplaces)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
