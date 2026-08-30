#!/usr/bin/env bash
#
# Option desk installer.
#
# Installs the MIT shell, optionally the AGPL engine, the agent skills, and
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
REPO="${OPTIONDESK_REPO:-}"
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
  --repo URL            git URL to clone when not run from a checkout
  --ref REF             branch or tag to clone (default main)
  --no-engine           install the MIT shell only, without the AGPL engine.
                        Greeks are unavailable; the shell says so and keeps
                        working
  --no-skills           do not copy skills into the Claude skills directory
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
OPTIONDESK_CLAUDE_SKILLS_DIR, OPTIONDESK_REPO, OPTIONDESK_REF.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="${2:?--prefix needs a directory}"; shift 2 ;;
    --bin-dir) BIN_DIR="${2:?--bin-dir needs a directory}"; shift 2 ;;
    --skills-dir) CLAUDE_SKILLS_DIR="${2:?--skills-dir needs a directory}"; shift 2 ;;
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

  # Every skill directory is considered, not only those named options-*,
  # and only the marker this installer writes authorises removal. A
  # symlink is never removed: this script only ever copies, so a link
  # here was made by someone else.
  if [ -d "$CLAUDE_SKILLS_DIR" ]; then
    for skill in "$CLAUDE_SKILLS_DIR"/*; do
      [ -d "$skill" ] || continue
      if [ -L "$skill" ]; then
        continue
      fi
      if [ -f "$skill/.installed-by-optiondesk" ]; then
        run rm -rf "$skill"
        say "  removed $skill"
      fi
    done
  fi
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
  # Empty when the script is piped from a URL, which is how the installer
  # tells "run from a checkout" from "run from curl".
  case "${BASH_SOURCE[0]:-}" in
    ""|bash|/dev/fd/*|/proc/self/fd/*) return 1 ;;
  esac
  ( cd "$(dirname "${BASH_SOURCE[0]}")" && pwd )
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

  The analytics engine is licensed AGPL-3.0, separately from the MIT shell.
  Running it privately carries no obligation. Running a MODIFIED version as
  a network service obliges you to offer that modified source to its users.

  Install the shell alone with --no-engine if that does not suit you. The
  shell still runs; it reports that Greeks are unavailable rather than
  guessing them.

NOTICE
  if [ "$ASSUME_YES" -eq 0 ] && [ -t 0 ] && [ "$DRY_RUN" -eq 0 ]; then
    printf '  Continue and install the AGPL engine? [Y/n] '
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

  say "Installing the MIT shell with the free Yahoo provider"
  run "$pip" install --quiet -e "$SOURCE/shell[yahoo]"

  if [ "$WITH_ENGINE" -eq 1 ]; then
    licence_notice
  fi
  if [ "$WITH_ENGINE" -eq 1 ]; then
    say "Installing the AGPL analytics engine"
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

install_skills() {
  [ "$WITH_SKILLS" -eq 1 ] || { say "Skipping skills, as requested"; return; }
  run mkdir -p "$CLAUDE_SKILLS_DIR"
  local count=0
  for skill in "$SOURCE"/shell/skills/*/; do
    [ -f "$skill/SKILL.md" ] || continue
    local name target
    name="$(basename "$skill")"
    target="$CLAUDE_SKILLS_DIR/$name"
    if [ -e "$target" ] && [ ! -f "$target/.installed-by-optiondesk" ]; then
      warn "$target exists and was not installed by this script; leaving it alone"
      continue
    fi
    run rm -rf "$target"
    run cp -R "$skill" "$target"
    run touch "$target/.installed-by-optiondesk"
    if [ "$DRY_RUN" -eq 1 ]; then
      say "  would install skill $name"
    else
      say "  installed skill $name"
    fi
    count=$((count + 1))
  done
  if [ "$count" -eq 0 ]; then
    if [ -n "$(find "$SOURCE/shell/skills" -name SKILL.md -print -quit 2>/dev/null)" ]; then
      warn "no skills installed: every one was skipped, see the warnings above"
    else
      warn "no skills found under $SOURCE/shell/skills"
    fi
  fi
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
print("  engine:    " + ("available " + str(engine["version"]) + " (AGPL-3.0)"
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
