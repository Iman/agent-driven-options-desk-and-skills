#!/usr/bin/env bash
#
# Option desk: install what is missing, run every stage on live data, and
# leave a dashboard serving on this machine.
#
# This is demo.sh with the setup in front of it. It finds or builds the
# Python environment, repairs a virtualenv built for the wrong CPU
# architecture, passes an explicit Yahoo terms acknowledgement, pulls real chains,
# computes the Greek ladder, dealer positioning, every structure with a
# ranking, a GARCH-t simulation and a backtest per structure, opens a paper
# position and marks it, then serves the page over all of it.
#
# Two things it does differently from demo.sh, both because they were
# measured on this machine on 2026-09-08:
#
#   Expiry choice. demo.sh takes the first expiry in a 25 to 60 day window.
#   On that date the first was a weekly with 257 SPY contracts while the
#   month-end expiry listed 578 and the third-Friday monthly 396. Depth was
#   decided by which date happened to fall first, so this script prefers
#   the standard cycle, third Friday or month end, and picks the deepest of
#   those by counting the contracts it actually received. The nearest
#   weeklies are pulled as well, with their own Greek ladder and dealer
#   positioning, because short-dated gamma is the thing a weekly is worth
#   looking at. They are not ranked against the deep expiry: a weekly has
#   a fraction of the strikes and would lose on depth alone.
#
#   Session awareness. Outside 09:30 to 16:00 America/New_York the free
#   provider publishes every bid, ask and open interest as zero. The run
#   still works and the artifacts still say so, but the warning comes
#   first rather than being inferred later from an implied volatility
#   fallback.
#
# Nothing here places an order. Everything it writes goes to one directory
# you can delete afterwards.
#
# Research software. Not investment advice. See DISCLAIMER.md.

set -euo pipefail

# Re-exec natively on Apple silicon before anything is built.
#
# A Homebrew bash under /usr/local is an x86_64 binary, so a script whose
# shebang is /usr/bin/env bash runs translated on an arm64 machine, and
# every wheel installed from it is x86_64. The virtualenv then imports
# cleanly from that shell and fails from every native one with
# "incompatible architecture (have 'x86_64', need 'arm64')". The system
# bash is universal, so the run continues in it. A script arriving on
# stdin, as curl into bash does, has no file to re-exec and is left alone.
if [ "$(uname -s)" = "Darwin" ] \
    && [ "${OPTIONDESK_NATIVE_ARCH:-0}" != "1" ] \
    && [ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" = "1" ] \
    && [ "$(uname -m)" != "arm64" ] \
    && [ -r "$0" ] \
    && [ -x /usr/bin/arch ] \
    && [ -x /bin/bash ]; then
  export OPTIONDESK_NATIVE_ARCH=1
  exec /usr/bin/arch -arm64 /bin/bash "$0" "$@"
fi

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

SYMBOLS="SPY QQQ"
OUT_DIR="${OPTIONDESK_ARTIFACTS:-$HOME/TradingDesk/option-desk-demo}"
PREFIX="${OPTIONDESK_PREFIX:-$HOME/.optiondesk}"
PORT=8787
HORIZON=30
PERIOD=5y
STRUCTURE=iron_condor
NEAR_MIN=20
NEAR_MAX=70
FAR_MIN=80
FAR_MAX=200
WEEKLIES=2
WITH_DASHBOARD=1
OPEN_BROWSER=1
WITH_TESTS=0
WITH_BACKTESTS=1
WITH_SIMULATION=1
FORCE_INSTALL=0
DRY_RUN=0
ACCEPT_YAHOO_TERMS=0

STRUCTURES="bear_put_spread broken_wing_butterfly bull_call_spread \
cash_secured_put covered_call iron_butterfly iron_condor jade_lizard \
long_call long_call_butterfly long_put protective_put ratio_spread \
straddle strangle"

usage() {
  cat <<'USAGE'
Usage: ./run.sh [options]

Installs anything missing, runs every stage on live data, serves the page.

  --symbols "SPY QQQ"   underlyings to run (default: SPY QQQ)
  --out-dir DIR         where artifacts go (default: ~/TradingDesk/option-desk-demo)
  --port N              dashboard port (default: 8787)
  --horizon N           simulation horizon in business days (default: 30)
  --period P            history for the backtest, e.g. 2y or 5y (default: 5y)
  --structure NAME      structure opened as the paper position (default: iron_condor)
  --near-window "A B"   day range the near expiry is chosen from (default: 20 70)
  --far-window "A B"    day range the far expiry is chosen from (default: 80 200)
  --weeklies N          nearest weekly expiries to pull as well, each with
                        its own Greek ladder and dealer positioning
                        (default: 2, use 0 for none)
  --reinstall           run the installer even when the tool is already working
  --accept-yahoo-terms  acknowledge local personal use after reading Yahoo's terms
  --with-tests          install the test dependencies and run all three suites
  --no-backtests        skip the per-structure backtests, which are the slow part
  --no-simulation       skip the GARCH-t simulation
  --no-dashboard        run the analytics, do not serve the page
  --no-open             serve the page but do not open a browser
  --dry-run             print every command, run none of them
  --help                this text

The runner passes --accept-yahoo-terms to ./install.sh only when you supply
that flag. Otherwise, the installer can ask interactively. A previously
recorded acknowledgement remains in effect. Read Yahoo's terms before
accepting: https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html
The acknowledgement grants no hosting, redistribution or public display
rights. Remove it by deleting its line from ~/.optiondesk/config.env.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --symbols) SYMBOLS="${2:?--symbols needs a list}"; shift 2 ;;
    --out-dir) OUT_DIR="${2:?--out-dir needs a directory}"; shift 2 ;;
    --port) PORT="${2:?--port needs a number}"; shift 2 ;;
    --horizon) HORIZON="${2:?--horizon needs a number}"; shift 2 ;;
    --period) PERIOD="${2:?--period needs a period}"; shift 2 ;;
    --structure) STRUCTURE="${2:?--structure needs a name}"; shift 2 ;;
    --near-window) NEAR_MIN="${2%% *}"; NEAR_MAX="${2##* }"; shift 2 ;;
    --far-window) FAR_MIN="${2%% *}"; FAR_MAX="${2##* }"; shift 2 ;;
    --weeklies) WEEKLIES="${2:?--weeklies needs a number}"; shift 2 ;;
    --reinstall) FORCE_INSTALL=1; shift ;;
    --accept-yahoo-terms) ACCEPT_YAHOO_TERMS=1; shift ;;
    --with-tests) WITH_TESTS=1; shift ;;
    --no-backtests) WITH_BACKTESTS=0; shift ;;
    --no-simulation) WITH_SIMULATION=0; shift ;;
    --no-dashboard) WITH_DASHBOARD=0; shift ;;
    --no-open) OPEN_BROWSER=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) printf 'unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

say() { printf '\n== %s\n' "$*"; }
note() { printf '   %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '   %s\n' "$*"
    return 0
  fi
  "$@"
}

# ------------------------------------------------------------------- setup

VENV="$PREFIX/venv"
DESK=""

# The tool is usable when doctor runs and reports a provider that can
# supply an option chain. Anything less means the install is incomplete,
# whatever is on disk, so the installer runs and the check repeats.
desk_is_ready() {
  local candidate="$1"
  [ -x "$candidate" ] || return 1
  local report
  report="$("$candidate" doctor 2>/dev/null)" || return 1
  printf '%s' "$report" | python3 -c '
import json, sys
try:
    report = json.load(sys.stdin)
except Exception:
    raise SystemExit(1)
for provider in report.get("providers", {}).values():
    if provider.get("available") and "option_chain" in provider.get(
            "capabilities", ()):
        raise SystemExit(0)
raise SystemExit(1)
' >/dev/null 2>&1
}

find_desk() {
  for candidate in \
      "${OPTIONDESK_BIN:-}" \
      "$(command -v optiondesk 2>/dev/null || true)" \
      "$VENV/bin/optiondesk" \
      "$HOME/.local/bin/optiondesk" \
      "$HERE/shell/.venv/bin/optiondesk"; do
    [ -n "$candidate" ] && [ -x "$candidate" ] && { printf '%s' "$candidate"; return 0; }
  done
  return 1
}

install_desk() {
  [ -x "$HERE/install.sh" ] || die "install.sh is missing from $HERE"
  local flags="--yes --no-keys"
  [ "$ACCEPT_YAHOO_TERMS" -eq 1 ] && flags="$flags --accept-yahoo-terms"
  [ "$DRY_RUN" -eq 1 ] && flags="$flags --dry-run"
  say "Installing the desk"
  # shellcheck disable=SC2086
  "$HERE/install.sh" $flags || die "the installer did not finish"
}

say "Option desk: install, run, serve"
note "repository: $HERE"
note "artifacts:  $OUT_DIR"
note "symbols:    $SYMBOLS"
[ "$DRY_RUN" -eq 1 ] && note "dry run: nothing below is executed"

DESK="$(find_desk || true)"
if [ "$FORCE_INSTALL" -eq 1 ] || [ -z "$DESK" ] || ! desk_is_ready "$DESK"; then
  if [ -z "$DESK" ]; then
    note "optiondesk was not found"
  elif [ "$FORCE_INSTALL" -eq 1 ]; then
    note "reinstalling as asked"
  else
    note "optiondesk is present but cannot answer for an option chain"
  fi
  install_desk
  DESK="$(find_desk || true)"
  if [ "$DRY_RUN" -eq 0 ]; then
    [ -n "$DESK" ] || die "the installer finished but optiondesk is still not on PATH.
Add $HOME/.local/bin to PATH, or set OPTIONDESK_BIN to the binary."
    desk_is_ready "$DESK" || {
      "$DESK" doctor || true
      die "no provider can supply an option chain. The doctor report above says why."
    }
  fi
fi
[ -n "$DESK" ] || DESK="$VENV/bin/optiondesk"

PY="$VENV/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

note "tool:       $DESK"
export OPTIONDESK_ARTIFACTS="$OUT_DIR"
run mkdir -p "$OUT_DIR"

if [ "$WITH_TESTS" -eq 1 ]; then
  say "Test dependencies and the three suites"
  run "$VENV/bin/pip" install --quiet pytest -e "$HERE/agent[graph]"
  run "$PY" -m pytest "$HERE/engine/tests" -q
  run "$PY" -m pytest "$HERE/shell/tests" -q
  run "$PY" -m pytest "$HERE/agent/tests" -q
fi

say "What is installed, and what can answer"
run "$DESK" doctor

# --------------------------------------------------------------- the clock

say "Is the market open"
SESSION_OPEN=0
if [ "$DRY_RUN" -eq 0 ]; then
  if "$PY" - <<'SESSION'; then SESSION_OPEN=1; fi
import datetime as dt

try:
    from zoneinfo import ZoneInfo
    now = dt.datetime.now(ZoneInfo("America/New_York"))
    zone = "America/New_York"
except Exception:
    now = dt.datetime.now()
    zone = "local time, no timezone database found"

open_at = now.replace(hour=9, minute=30, second=0, microsecond=0)
close_at = now.replace(hour=16, minute=0, second=0, microsecond=0)
weekday = now.weekday() < 5
inside = weekday and open_at <= now <= close_at

print("   now: {} ({})".format(now.strftime("%Y-%m-%d %H:%M %a"), zone))
if inside:
    print("   the session is open, so quotes and open interest are live")
else:
    print("   the session is CLOSED. The free provider publishes every bid,")
    print("   ask and open interest as zero outside 09:30 to 16:00, so this")
    print("   run will produce chains with no two-sided quotes. Implied")
    print("   volatility falls back to the provider's published figure or")
    print("   goes missing, and every artifact below says so. Re-run during")
    print("   the session for a quoted book.")
    print("   This check knows weekends, not exchange holidays.")

raise SystemExit(0 if inside else 1)
SESSION
fi

# -------------------------------------------------------------- the stages

# The near expiry, chosen by depth among the standard cycle.
#
# Weeklies list a fraction of the strikes a month-end or third-Friday
# expiry does, and the difference is large: 257 contracts against 578 for
# SPY on 2026-09-08. Every downstream stage inherits that ladder, so the
# choice is made on the counts actually returned rather than on date order.
standard_cycle_expiries() {
  "$DESK" expiries "$1" 2>/dev/null | "$PY" -c '
import datetime as dt
import json
import sys

low, high = float(sys.argv[1]), float(sys.argv[2])
try:
    rows = json.load(sys.stdin).get("expiries", [])
except Exception:
    raise SystemExit(1)

def standard(value):
    """Third Friday or the last calendar day of a month.

    Those are the cycles the listing venue carries a full strike ladder
    for. A weekly is a subset and shows it.
    """
    date = dt.date.fromisoformat(value)
    third_friday = date.weekday() == 4 and 15 <= date.day <= 21
    month_end = (date + dt.timedelta(days=1)).month != date.month
    return third_friday or month_end

inside = [r for r in rows if low <= r["days_to_expiry"] <= high]
cycle = [r for r in inside if standard(r["expiry"])]
chosen = cycle or inside
print(" ".join(r["expiry"] for r in chosen))
' "$2" "$3"
}

# The nearest expiries that are not on the standard cycle.
#
# Same date arithmetic as above, inverted. Anything already expiring today
# is skipped: a zero-day contract has no ladder worth a Greek surface and
# the desk floors its time to expiry, which makes every derived value
# meaningless.
weekly_expiries() {
  "$DESK" expiries "$1" 2>/dev/null | "$PY" -c '
import datetime as dt
import json
import sys

wanted = int(sys.argv[1])
try:
    rows = json.load(sys.stdin).get("expiries", [])
except Exception:
    raise SystemExit(1)


def standard(value):
    date = dt.date.fromisoformat(value)
    third_friday = date.weekday() == 4 and 15 <= date.day <= 21
    month_end = (date + dt.timedelta(days=1)).month != date.month
    return third_friday or month_end


weekly = [r["expiry"] for r in rows
          if r["days_to_expiry"] >= 1 and not standard(r["expiry"])]
print(" ".join(weekly[:wanted]))
' "$2"
}

deepest_snapshot() {
  # Contract counts come from the artifacts already written, so choosing
  # the deepest expiry costs no extra provider call beyond the pulls.
  local symbol="$1"
  shift
  "$PY" - "$OUT_DIR" "$symbol" "$@" <<'DEEPEST'
import json
import pathlib
import sys

out_dir = pathlib.Path(sys.argv[1])
symbol = sys.argv[2]
best = None
for expiry in sys.argv[3:]:
    path = out_dir / "chain_{}_{}.json".format(symbol, expiry)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        continue
    count = len(payload.get("contracts", ()))
    if best is None or count > best[0]:
        best = (count, path, expiry)
if best is None:
    raise SystemExit(1)
print("{}\t{}\t{}".format(best[2], best[0], best[1]))
DEEPEST
}

for symbol in $SYMBOLS; do
  say "$symbol: which expiries are listed"
  run "$DESK" expiries "$symbol"

  if [ "$DRY_RUN" -eq 1 ]; then
    note "would pull the standard-cycle expiries and keep the deepest"
    continue
  fi

  near_candidates="$(standard_cycle_expiries "$symbol" "$NEAR_MIN" "$NEAR_MAX" || true)"
  far_candidates="$(standard_cycle_expiries "$symbol" "$FAR_MIN" "$FAR_MAX" || true)"

  if [ -z "$near_candidates" ]; then
    warn "no expiry between $NEAR_MIN and $NEAR_MAX days for $symbol, skipping it"
    continue
  fi

  say "$symbol: the chains"
  pulled=""
  for expiry in $near_candidates; do
    if "$DESK" chain "$symbol" --expiry "$expiry" >/dev/null 2>&1; then
      printf '   %-12s pulled\n' "$expiry"
      pulled="$pulled $expiry"
    else
      printf '   %-12s failed\n' "$expiry"
    fi
  done
  [ -n "$pulled" ] || { warn "no chain pulled for $symbol, skipping it"; continue; }

  # shellcheck disable=SC2086
  picked="$(deepest_snapshot "$symbol" $pulled)" || {
    warn "no usable snapshot for $symbol, skipping it"
    continue
  }
  near_expiry="$(printf '%s' "$picked" | cut -f1)"
  near_count="$(printf '%s' "$picked" | cut -f2)"
  snapshot="$(printf '%s' "$picked" | cut -f3)"
  note "deepest near expiry: $near_expiry with $near_count contracts"

  # The clock said the session was open; this says whether the provider
  # agreed. A run started one minute after the bell on 2026-09-08 pulled
  # 25 quoted contracts of 578 because the provider was still serving its
  # overnight snapshot, and 45 minutes later the same expiry came back
  # with 568. A stale feed inside the session looks exactly like a closed
  # market, so it has to be named as the different thing it is.
  quoted_share="$("$PY" -c '
import json
import sys
contracts = json.load(open(sys.argv[1]))["contracts"]
quoted = sum(1 for c in contracts
             if (c.get("bid") or 0) > 0 and (c.get("ask") or 0) > 0)
print("{} {}".format(quoted, len(contracts)))
' "$snapshot" 2>/dev/null || echo "0 0")"
  quoted_now="${quoted_share%% *}"
  quoted_of="${quoted_share##* }"
  if [ "$quoted_of" -gt 0 ] && [ $((quoted_now * 2)) -lt "$quoted_of" ]; then
    if [ "$SESSION_OPEN" -eq 1 ]; then
      warn "only $quoted_now of $quoted_of contracts are quoted while the"
      warn "session is open. The provider snapshot is stale, not the"
      warn "market: wait a few minutes and re-run. Everything below is"
      warn "built on an unquoted book and is flagged degraded."
    else
      note "$quoted_now of $quoted_of contracts quoted, as expected outside"
      note "the session"
    fi
  fi

  # The far leg exists so the calendar and the diagonal have something to
  # reach for. One is enough, and it is not ranked by depth.
  far_expiry="${far_candidates%% *}"
  if [ -n "$far_expiry" ]; then
    if "$DESK" chain "$symbol" --expiry "$far_expiry" >/dev/null 2>&1; then
      note "far expiry for the calendars: $far_expiry"
    else
      warn "could not pull the far expiry $far_expiry for $symbol"
    fi
  else
    warn "no expiry between $FAR_MIN and $FAR_MAX days for $symbol: the"
    warn "calendar and diagonal structures will be skipped"
  fi

  if [ "$WEEKLIES" -gt 0 ]; then
    say "$symbol: the nearest weeklies"
    weekly_list="$(weekly_expiries "$symbol" "$WEEKLIES" || true)"
    if [ -z "$weekly_list" ]; then
      note "none listed that are not already on the standard cycle"
    fi
    for expiry in $weekly_list; do
      weekly_snapshot="$OUT_DIR/chain_${symbol}_${expiry}.json"
      if ! "$DESK" chain "$symbol" --expiry "$expiry" >/dev/null 2>&1; then
        printf '   %-12s chain failed\n' "$expiry"
        continue
      fi
      weekly_count="$("$PY" -c '
import json
import sys
print(len(json.load(open(sys.argv[1]))["contracts"]))
' "$weekly_snapshot" 2>/dev/null || echo 0)"
      printf '   %-12s %s contracts\n' "$expiry" "$weekly_count"
      # A weekly is worth looking at for short-dated gamma, so it gets the
      # ladder and the dealer positioning. It is not compared, simulated
      # or backtested: those read the deep expiry chosen above.
      "$DESK" greeks --snapshot "$weekly_snapshot" --band 0.05 \
          >/dev/null 2>&1 || warn "greeks failed for $symbol $expiry"
      "$DESK" exposure --snapshot "$weekly_snapshot" \
          >/dev/null 2>&1 || warn "exposure failed for $symbol $expiry"
    done
  fi

  say "$symbol: the full Greek ladder"
  run "$DESK" greeks --snapshot "$snapshot" --band 0.08

  say "$symbol: where dealer hedging concentrates"
  run "$DESK" exposure --snapshot "$snapshot"

  say "$symbol: every structure, built and ranked"
  run "$DESK" compare --snapshot "$snapshot" --include-underlying --rebuild

  if [ "$WITH_SIMULATION" -eq 1 ]; then
    say "$symbol: the underlying simulated forward from its own behaviour"
    note "this fits a GARCH posterior by MCMC and can take a while on a slow"
    note "machine, with no output until it finishes. Let it run."
    run "$DESK" simulate "$symbol" --horizon "$HORIZON" --period "$PERIOD"
  fi

  if [ "$WITH_BACKTESTS" -eq 1 ]; then
    say "$symbol: every structure across real history, modelled premiums"
    for structure in $STRUCTURES; do
      if "$DESK" backtest "$symbol" "$structure" --period "$PERIOD" \
          --holding-days 30 --entry-every 5 >/dev/null 2>&1; then
        printf '   %-24s done\n' "$structure"
      else
        # A structure spanning two expiries has no single-expiry history to
        # walk, and one that needs the underlying is not a pure option
        # trade. Neither is an error worth stopping for.
        printf '   %-24s skipped\n' "$structure"
      fi
    done
  fi
done

first_symbol="${SYMBOLS%% *}"

say "A paper position, so the forward ledger has something in it"
run "$DESK" forward open --strategy "$STRUCTURE" --underlying "$first_symbol" \
    --thesis "opened by run.sh, paper only"
run "$DESK" forward mark
run "$DESK" forward status

say "Done"
note "artifacts written to $OUT_DIR"
if [ "$DRY_RUN" -eq 0 ]; then
  count=$(find "$OUT_DIR" -maxdepth 1 -name '*.json' | wc -l | tr -d ' ')
  note "$count artifacts on disk"
fi
note "every figure above came from free, delayed, third-party data"
note "premiums are mid quotes and modelled values, never fills"

# ----------------------------------------------------------- the live page

if [ "$WITH_DASHBOARD" -eq 0 ]; then
  note "start the dashboard yourself with: $DESK dashboard --port $PORT"
  exit 0
fi

say "The dashboard"
note "http://127.0.0.1:$PORT"
note "stop it with ctrl-c"

if [ "$DRY_RUN" -eq 1 ]; then
  printf '   %s\n' "$DESK dashboard --host 127.0.0.1 --port $PORT"
  exit 0
fi

if [ "$OPEN_BROWSER" -eq 1 ]; then
  # The browser opens once the port answers, so the first paint is the
  # dashboard rather than a connection refused page.
  (
    for _ in $(seq 1 60); do
      if "$PY" -c '
import socket, sys
probe = socket.socket()
probe.settimeout(0.4)
try:
    probe.connect(("127.0.0.1", int(sys.argv[1])))
except OSError:
    raise SystemExit(1)
finally:
    probe.close()
' "$PORT" 2>/dev/null; then
        if command -v open >/dev/null 2>&1; then
          open "http://127.0.0.1:$PORT"
        elif command -v xdg-open >/dev/null 2>&1; then
          xdg-open "http://127.0.0.1:$PORT"
        fi
        break
      fi
      sleep 0.5
    done
  ) &
fi

exec "$DESK" dashboard --host 127.0.0.1 --port "$PORT"
