#!/usr/bin/env bash
#
# Option desk installer.
#
# Installs the shell, optionally the analytics engine, the agent skills, and
# registers the MCP server with whichever agent runtimes are present.
#
# From a checkout:
#
#     ./install.sh
#
# From the network, once the repository is published:
#
#     curl -fsSL <RAW_URL>/install.sh | bash
#
# Piping a script from the internet into a shell runs whatever that URL
# happens to serve. Read it first. This one is short on purpose.
#
# Everything it does is confined to:
#   $PREFIX/venv, $PREFIX/src   (default ~/.optiondesk)
#   ~/.local/bin                two symlinks, never overwriting your files
#   ~/.claude/skills/<name>     skill files, marked so uninstall knows them
#   ~/.agents/skills/<name>     the same files again, where Codex and
#                               ChatGPT look for them
#   agent runtime configs       one MCP entry each, only when the CLI exists
#
# pip also writes its own cache (~/Library/Caches/pip or ~/.cache/pip) and
# leaves __pycache__ directories in the checkout. Uninstall does not remove
# either, because neither belongs to this project.
#
# Re-running is safe. --uninstall reverses all of it.

set -euo pipefail

VERSION="0.1.0"
PREFIX="${OPTIONDESK_PREFIX:-$HOME/.optiondesk}"
BIN_DIR="${OPTIONDESK_BIN_DIR:-$HOME/.local/bin}"
CLAUDE_SKILLS_DIR="${OPTIONDESK_CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
# Claude Code reads ~/.claude/skills and nowhere else. Codex and ChatGPT
# read ~/.agents/skills, the convention the universal agents share. The
# same five skills go to both: installing to one only leaves whichever
# runtime the user actually has possibly seeing nothing, from a script
# that reported success.
AGENTS_SKILLS_DIR="${OPTIONDESK_AGENTS_SKILLS_DIR:-$HOME/.agents/skills}"
# A full URL, never a bare owner/name. `git clone owner/name` resolves
# against the current working directory, so a bare identifier turns a
# remote install into a local one silently: reproduced by planting
# ./Iman/agent-driven-options-desk-and-skills and watching the clone
# take it. Anyone running the one-line install from a directory an
# attacker can write to would have installed that instead.
REPO="${OPTIONDESK_REPO:-https://github.com/Iman/agent-driven-options-desk-and-skills.git}"
REF="${OPTIONDESK_REF:-main}"

WITH_ENGINE=1
WITH_SKILLS=1
WITH_MCP=1
WITH_KEYS=1
SKILLS_ONLY=0
DRY_RUN=0
UNINSTALL=0
ASSUME_YES=0

SERVER_NAME="optiondesk"

say() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '  would run: %s\n' "$*"
  else
    "$@"
  fi
}

usage() {
  cat <<'USAGE'
Option desk installer

Usage: ./install.sh [options]

Options:
  --prefix DIR          install root (default ~/.optiondesk)
  --bin-dir DIR         where the commands are linked (default ~/.local/bin)
  --skills-dir DIR      Claude skills directory (default ~/.claude/skills)
  --agents-skills-dir DIR
                        Codex and ChatGPT skills directory, the shared
                        .agents convention (default ~/.agents/skills)
  --repo URL            git URL to clone when not run from a checkout
  --ref REF             branch or tag to clone (default main)
  --no-engine           install the shell only, without the analytics engine.
                        Greeks are unavailable; the shell says so and keeps
                        working
  --no-skills           do not copy skills into either skills directory
  --skills-only         install just the skills, with no Python, no engine,
                        no commands linked and no MCP registration
  --no-mcp              do not register the MCP server with any runtime
  --no-keys             skip the optional provider key prompt
  --uninstall           remove everything this installer created
  --dry-run             print what would happen, change nothing
  --yes                 do not pause on the engine licence notice
  --version             print the installer version
  -h, --help            this message

Environment equivalents: OPTIONDESK_PREFIX, OPTIONDESK_BIN_DIR,
OPTIONDESK_CLAUDE_SKILLS_DIR, OPTIONDESK_AGENTS_SKILLS_DIR,
OPTIONDESK_REPO, OPTIONDESK_REF.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="${2:?--prefix needs a directory}"; shift 2 ;;
    --bin-dir) BIN_DIR="${2:?--bin-dir needs a directory}"; shift 2 ;;
    --skills-dir) CLAUDE_SKILLS_DIR="${2:?--skills-dir needs a directory}"; shift 2 ;;
    --agents-skills-dir) AGENTS_SKILLS_DIR="${2:?--agents-skills-dir needs a directory}"; shift 2 ;;
    --repo) REPO="${2:?--repo needs a URL}"; shift 2 ;;
    --ref) REF="${2:?--ref needs a ref}"; shift 2 ;;
    --no-engine) WITH_ENGINE=0; shift ;;
    --no-skills) WITH_SKILLS=0; shift ;;
    --skills-only) SKILLS_ONLY=1; WITH_MCP=0; WITH_KEYS=0; shift ;;
    --no-mcp) WITH_MCP=0; shift ;;
    --no-keys) WITH_KEYS=0; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    --version) say "option-desk installer $VERSION"; exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option $1. Try --help" ;;
  esac
done

VENV="$PREFIX/venv"
SRC="$PREFIX/src"

# ---------------------------------------------------------------- uninstall

# Every skill directory is considered, not only those named options-*, and
# only the marker this installer writes authorises removal. A symlink is
# never removed: this script only ever copies, so a link here was made by
# someone else.
#
# Both destinations go through this one function rather than through two
# copies of the rule. Two copies are two places for the marker check to
# rot, and the one that rotted would delete a directory the user wrote.
uninstall_skills_from() {
  local dir="$1"
  [ -d "$dir" ] || return 0
  for skill in "$dir"/*; do
    [ -d "$skill" ] || continue
    if [ -L "$skill" ]; then
      continue
    fi
    if [ -f "$skill/.installed-by-optiondesk" ]; then
      run rm -rf "$skill"
      say "  removed $skill"
    fi
  done
}

uninstall() {
  say "Removing the option desk."

  # Symlinks are only removed when they point into this installation.
  # A file of the same name that the user wrote themselves, or a link
  # pointing somewhere else, is theirs and stays.
  for name in optiondesk optiondesk-mcp; do
    target="$BIN_DIR/$name"
    [ -e "$target" ] || [ -L "$target" ] || continue
    if [ -L "$target" ] && [ "$(readlink "$target")" = "$VENV/bin/$name" ]; then
      run rm -f "$target"
      say "  removed $target"
    else
      warn "left $target in place: it is not a link into $VENV"
    fi
  done

  uninstall_skills_from "$CLAUDE_SKILLS_DIR"
  uninstall_skills_from "$AGENTS_SKILLS_DIR"
  if [ "$WITH_MCP" -eq 1 ]; then
    # Only ever removes an entry under this script's own server name, so a
    # differently named server pointing at the same binary is left alone.
    if command -v claude >/dev/null 2>&1; then
      run claude mcp remove "$SERVER_NAME" -s user >/dev/null 2>&1 || true
    fi
    if command -v codex >/dev/null 2>&1; then
      run codex mcp remove "$SERVER_NAME" >/dev/null 2>&1 || true
    fi
    if command -v gemini >/dev/null 2>&1; then
      run gemini mcp remove "$SERVER_NAME" >/dev/null 2>&1 || true
    fi
  else
    say "  leaving MCP registrations in place, as requested"
  fi
  # Only the two directories this installer creates are removed. An
  # earlier version deleted $PREFIX outright, which turns
  # "--uninstall --prefix ~/Documents" into data loss. The prefix itself
  # is removed only if it is empty afterwards.
  for created in "$VENV" "$SRC"; do
    if [ -d "$created" ]; then
      run rm -rf "$created"
      say "  removed $created"
    fi
  done
  if [ -d "$PREFIX" ] && [ "$DRY_RUN" -eq 0 ]; then
    if rmdir "$PREFIX" 2>/dev/null; then
      say "  removed $PREFIX (it was empty)"
    else
      warn "left $PREFIX in place: it holds files this installer did not create"
    fi
  fi
  say "Done. Artifacts already written were left untouched."
  exit 0
}

[ "$UNINSTALL" -eq 1 ] && uninstall

# ------------------------------------------------------------------ sources

script_dir() {
  # Where this file lives, or failure when it does not live anywhere,
  # which is what "piped from a URL" means.
  #
  # The list of names below is not sufficient on its own and was not
  # discovered by reading: CI caught it. Bash on Linux reports
  # BASH_SOURCE[0] as "main" for a script read from standard input, which
  # matches none of these, so `dirname main` gave "." and the installer
  # decided the CURRENT DIRECTORY was a checkout. A piped install run from
  # inside any directory holding a shell/pyproject.toml then installed that
  # directory instead of cloning the repository the user asked for. That is
  # the same failure as `git clone owner/name` resolving against the
  # working directory, which this file already refuses further down.
  #
  # The check that actually holds is the last one: a real script is a file
  # that exists. Anything else is stdin.
  case "${BASH_SOURCE[0]:-}" in
    ""|bash|sh|main|-|/dev/fd/*|/proc/self/fd/*|/dev/stdin) return 1 ;;
  esac
  [ -f "${BASH_SOURCE[0]}" ] || return 1
  ( cd "$(dirname "${BASH_SOURCE[0]}")" && pwd )
}

require_remote_repo() {
  # Refuse anything git would resolve against the working directory.
  #
  # This is not hypothetical tidiness. `git clone owner/name` clones
  # ./owner/name when it exists, so a value that looks like a GitHub
  # identifier installs whatever is sitting in the directory the user
  # happened to run from. A local path is still allowed, but only when it
  # is said explicitly: an absolute path or a file:// URL.
  case "$1" in
    https://*|http://*|git://*|ssh://*|file:///*) return 0 ;;
    /*) return 0 ;;
    *@*:*) return 0 ;;
    *)
      die "refusing to clone '$1': it is not an explicit remote. A bare \
owner/name is resolved by git against the current directory, so it would \
install whatever happens to sit there. Use a full URL, or an absolute path \
for a local checkout."
      ;;
  esac
}

resolve_source() {
  local here
  if here="$(script_dir)" && [ -f "$here/shell/pyproject.toml" ]; then
    SOURCE="$here"
    say "Installing from the checkout at $SOURCE"
    return
  fi
  [ -n "$REPO" ] || die "not run from a checkout, so --repo URL (or \
OPTIONDESK_REPO) is required. The published URL goes in the REPO default \
once the repository is public."
  command -v git >/dev/null 2>&1 || die "git is required to clone $REPO"
  require_remote_repo "$REPO"
  if [ -d "$SRC/.git" ]; then
    say "Updating the existing clone at $SRC"
    run git -C "$SRC" fetch --depth 1 origin "$REF"
    run git -C "$SRC" checkout -q FETCH_HEAD
  else
    say "Cloning $REPO ($REF) into $SRC"
    run mkdir -p "$(dirname "$SRC")"
    run git clone --depth 1 --branch "$REF" "$REPO" "$SRC"
  fi
  SOURCE="$SRC"
}

# ------------------------------------------------------------------- python

python_bin() {
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)'; then
        printf '%s' "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

licence_notice() {
  cat <<'NOTICE'

  This project, engine included, is licensed under the PolyForm
  Noncommercial License 1.0.0. Personal use, research, teaching and any
  other noncommercial use are permitted. Use for or within a business, or
  any use that makes money, requires a separate written agreement with the
  author.

  Install the shell alone with --no-engine if you do not want the engine.
  The shell still runs; it reports that Greeks are unavailable rather than
  guessing them.

NOTICE
  if [ "$ASSUME_YES" -eq 0 ] && [ -t 0 ] && [ "$DRY_RUN" -eq 0 ]; then
    printf '  Continue and install the analytics engine? [Y/n] '
    read -r reply || reply=""
    case "$reply" in
      [Nn]*) WITH_ENGINE=0; say "  Continuing without the engine." ;;
    esac
  fi
}

install_packages() {
  local py
  py="$(python_bin)" || die "python 3.11 or newer is required and was not found"
  say "Using $($py --version 2>&1)"

  if [ ! -d "$VENV" ]; then
    say "Creating the virtualenv at $VENV"
    run "$py" -m venv "$VENV"
  else
    say "Reusing the virtualenv at $VENV"
  fi

  local pip="$VENV/bin/pip"
  run "$pip" install --quiet --upgrade pip

  say "Installing the shell with the free Yahoo provider"
  run "$pip" install --quiet -e "$SOURCE/shell[yahoo]"

  if [ "$WITH_ENGINE" -eq 1 ]; then
    licence_notice
  fi
  if [ "$WITH_ENGINE" -eq 1 ]; then
    say "Installing the analytics engine"
    run "$pip" install --quiet -e "$SOURCE/engine"
  else
    say "Skipping the analytics engine, as requested"
  fi
}

link_commands() {
  run mkdir -p "$BIN_DIR"
  for name in optiondesk optiondesk-mcp; do
    [ -e "$VENV/bin/$name" ] || [ "$DRY_RUN" -eq 1 ] || continue
    target="$BIN_DIR/$name"
    if [ -e "$target" ] || [ -L "$target" ]; then
      # A regular file here belongs to the user. A symlink pointing
      # elsewhere might too. Only a link into this installation, or
      # nothing at all, may be replaced.
      if [ ! -L "$target" ]; then
        warn "left $target in place: it is a regular file, not a link this installer made. Remove it first, or pass --bin-dir."
        continue
      fi
      current="$(readlink "$target")"
      case "$current" in
        "$VENV/bin/$name") ;;
        *)
          warn "left $target in place: it links to $current, not into $VENV"
          continue
          ;;
      esac
    fi
    # -n matters: without it, a symlink to a directory is followed and the
    # new link lands inside that directory, outside the declared bin dir.
    run ln -sfn "$VENV/bin/$name" "$target"
    if [ "$DRY_RUN" -eq 1 ]; then
      say "  would link $target"
    else
      say "  linked $target"
    fi
  done
  case ":${PATH}:" in
    *":$BIN_DIR:"*) ;;
    *)
      warn "$BIN_DIR is not on your PATH."
      warn "  Add this line to your shell profile:"
      warn "    export PATH=\"$BIN_DIR:\$PATH\""
      warn "  Until then, call $VENV/bin/optiondesk directly."
      warn "  This matters for the Claude Code plugin: its MCP entry names"
      warn "  the bare command optiondesk-mcp and resolves it through PATH."
      ;;
  esac
}

install_skills_into() {
  # One destination, one mechanism. The Claude directory and the .agents
  # directory both come through here, so the marker, the refusal to adopt
  # a directory this script did not create, and the dry run wording cannot
  # drift apart between them.
  local dest="$1"
  local count=0
  run mkdir -p "$dest"
  for skill in "$SOURCE"/shell/skills/*/; do
    [ -f "$skill/SKILL.md" ] || continue
    local name target
    name="$(basename "$skill")"
    target="$dest/$name"
    if [ -e "$target" ] && [ ! -f "$target/.installed-by-optiondesk" ]; then
      warn "$target exists and was not installed by this script; leaving it alone"
      continue
    fi
    # rm against the path unlinks a symlink rather than descending through
    # it, so a link someone else left here cannot turn the copy below into
    # a write outside $dest.
    run rm -rf "$target"
    run cp -R "$skill" "$target"
    if [ -f "$SOURCE/DISCLAIMER.md" ]; then
      run cp "$SOURCE/DISCLAIMER.md" "$target/DISCLAIMER.md"
    fi
    run touch "$target/.installed-by-optiondesk"
    if [ "$DRY_RUN" -eq 1 ]; then
      say "  would install skill $name into $dest"
    else
      say "  installed skill $name into $dest"
    fi
    count=$((count + 1))
  done
  if [ "$count" -eq 0 ]; then
    warn "no skills installed into $dest: every one was skipped, see the warnings above"
  fi
}

install_skills() {
  [ "$WITH_SKILLS" -eq 1 ] || { say "Skipping skills, as requested"; return; }
  if [ -z "$(find "$SOURCE/shell/skills" -name SKILL.md -print -quit 2>/dev/null)" ]; then
    warn "no skills found under $SOURCE/shell/skills"
    return
  fi
  # Every SKILL.md ends by pointing at DISCLAIMER.md, saying it "ships
  # beside this skill when it is installed from a package and sits at the
  # repository root otherwise". An install from here is neither: the skill
  # lands in a skills directory with no repository around it, so that
  # pointer resolved to nothing. scripts/package.py already carries the
  # file into the zips and the plugin bundle. The copy in
  # install_skills_into is the same fix for the path this script owns.
  #
  # Its absence is a warning and not a failure. The substance of the
  # disclaimer is already inline in every skill, so the skill is still
  # usable, and refusing to install over a missing document would be a
  # worse outcome than installing without it.
  if [ ! -f "$SOURCE/DISCLAIMER.md" ]; then
    warn "no DISCLAIMER.md under $SOURCE; installing the skills without it. Each SKILL.md still carries the substance inline."
  fi
  install_skills_into "$CLAUDE_SKILLS_DIR"
  install_skills_into "$AGENTS_SKILLS_DIR"
}

register_mcp() {
  [ "$WITH_MCP" -eq 1 ] || { say "Skipping MCP registration, as requested"; return; }
  local server="$VENV/bin/optiondesk-mcp"
  local found=0

  # Each registration is attempted only when its CLI exists. In a dry run
  # the command is printed and nothing is claimed: an earlier version
  # swallowed the "would run" line and reported "registered" in past
  # tense while changing nothing.
  register_one() {
    local label="$1"
    shift
    if [ "$DRY_RUN" -eq 1 ]; then
      printf '  would register with %s: %s\n' "$label" "$*"
      return 0
    fi
    if "$@" >/dev/null 2>&1; then
      say "  registered with $label"
    else
      warn "could not register with $label; run: $*"
    fi
  }

  if command -v claude >/dev/null 2>&1; then
    found=1
    [ "$DRY_RUN" -eq 1 ] || claude mcp remove "$SERVER_NAME" -s user >/dev/null 2>&1 || true
    register_one "Claude Code" claude mcp add "$SERVER_NAME" -s user -- "$server"
  fi

  if command -v codex >/dev/null 2>&1; then
    found=1
    [ "$DRY_RUN" -eq 1 ] || codex mcp remove "$SERVER_NAME" >/dev/null 2>&1 || true
    register_one "Codex" codex mcp add "$SERVER_NAME" -- "$server"
  fi

  if command -v gemini >/dev/null 2>&1; then
    found=1
    [ "$DRY_RUN" -eq 1 ] || gemini mcp remove "$SERVER_NAME" >/dev/null 2>&1 || true
    register_one "Gemini CLI" gemini mcp add -s user \
      --description "Option desk analytics" -- "$SERVER_NAME" "$server"
  fi

  [ "$found" -eq 1 ] || say "  no agent runtime CLI found; nothing to register"
}

configure_keys() {
  # Optional, interactive, and skippable. The desk runs on free sources
  # with no key at all, so this must never look like a requirement: a
  # setup step that appears mandatory is how a working install gets
  # abandoned at the first prompt.
  [ "$WITH_KEYS" -eq 1 ] || { say "Skipping the key prompt, as requested"; return 0; }
  [ "$DRY_RUN" -eq 0 ] || { say "  would offer the optional key prompt"; return 0; }
  [ -t 0 ] || return 0

  local optiondesk="$VENV/bin/optiondesk"
  [ -x "$optiondesk" ] || return 0

  cat <<'KEYS'

  Optional: provider keys.

  Everything works without any key. Chains, Greeks, positioning,
  structures, simulation and backtests all run on free sources. A key only
  adds an alternative provider, and one whose key is missing is skipped
  rather than failing.

  Keys are stored in ~/.optiondesk/config.env, outside any repository,
  readable only by you. They are never printed, logged, or written into an
  artifact.

KEYS
  printf '  Configure a provider key now? [y/N] '
  read -r reply || reply=""
  case "$reply" in
    [Yy]*) ;;
    *) say "  Skipped. Add one later with: optiondesk keys set alphavantage"
       return 0 ;;
  esac

  while :; do
    printf '  Provider (alphavantage, tradier, fmp, alpaca, polygon, finviz), or blank to finish: '
    read -r provider || provider=""
    [ -n "$provider" ] || break
    "$optiondesk" keys set "$provider" >/dev/null 2>&1 \
      && say "  stored $provider" \
      || warn "could not store $provider; try: optiondesk keys set $provider"
  done
}

verify() {
  [ "$DRY_RUN" -eq 1 ] && return 0
  local out
  if ! out="$("$VENV/bin/optiondesk" doctor 2>&1)"; then
    warn "optiondesk doctor did not run cleanly:"
    printf '%s\n' "$out" >&2
    return 1
  fi
  printf '%s' "$out" | "$VENV/bin/python" -c '
import json, sys
report = json.load(sys.stdin)
engine = report["engine"]
providers = [name for name, p in report["providers"].items() if p["available"]]
print("  engine:    " + ("available " + str(engine["version"])
                         + " (" + str(engine["license"]) + ")"
                         if engine["available"] else "not installed"))
print("  providers: " + (", ".join(providers) or "none available"))
print("  artifacts: " + report["artifact_dir"])
'
}

main() {
  say "Option desk installer $VERSION"
  [ "$DRY_RUN" -eq 1 ] && say "Dry run: nothing will change."
  resolve_source

  if [ "$SKILLS_ONLY" -eq 1 ]; then
    # The skills are plain markdown and are useful on their own: they
    # describe the commands, the conventions and the reporting rules. An
    # agent that has them but not the tools can still explain the desk, it
    # simply cannot run it.
    say "Installing the skills only: no virtualenv, no engine, no tools."
    install_skills
    say ""
    say "Done. The commands the skills describe are not installed, so run"
    say "the installer without --skills-only when you want them."
    exit 0
  fi

  install_packages
  link_commands
  install_skills
  register_mcp
  configure_keys
  say ""
  say "Checking the installation:"
  if ! verify; then
    warn "the installation did not verify. Nothing above is a working "
    warn "install: fix the error, then re-run this script."
    exit 1
  fi
  cat <<'NEXT'

Try it:

  optiondesk chain SPY
  optiondesk greeks --band 0.05
  optiondesk exposure
  optiondesk compare
  optiondesk dashboard

Provider keys are optional and can be added at any time:

  optiondesk keys list
  optiondesk keys set alphavantage

No API key is needed. The default data source is Yahoo, which is free and
delayed. Outputs are research artifacts: modelled option premiums, not
tradable quotes, and not investment advice. See DISCLAIMER.md.

Remove everything with: ./install.sh --uninstall
NEXT
}

main
