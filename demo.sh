#!/usr/bin/env bash
#
# Option desk demo: pull real data and run every stage, end to end.
#
# Downloads two expiries for each underlying from the free provider,
# computes the Greek ladder, dealer positioning, every structure with a
# ranking, a GARCH-t simulation, a backtest over real history, opens a paper
# position and marks it, then serves the dashboard over all of it.
#
# Nothing here needs an API key. Nothing here places an order. Everything it
# writes goes to one directory you can delete afterwards.
#
# Research software. Not investment advice. See DISCLAIMER.md.

set -euo pipefail

SYMBOLS="SPY QQQ"
OUT_DIR="${OPTIONDESK_ARTIFACTS:-$HOME/TradingDesk/option-desk-demo}"
PORT=8787
DRY_RUN=0
WITH_DASHBOARD=1
HORIZON=30
PERIOD=5y
STRUCTURE=iron_condor
STRUCTURES="bear_put_spread broken_wing_butterfly bull_call_spread \
cash_secured_put covered_call iron_butterfly iron_condor jade_lizard \
long_call long_call_butterfly long_put protective_put ratio_spread \
straddle strangle"

usage() {
  cat <<'USAGE'
Usage: ./demo.sh [options]

  --symbols "SPY QQQ"   underlyings to run (default: SPY QQQ)
  --out-dir DIR         where artifacts go (default: ~/TradingDesk/option-desk-demo)
  --port N              dashboard port (default: 8787)
  --horizon N           simulation horizon in business days (default: 30)
  --period P            history for the backtest, e.g. 2y or 5y (default: 5y)
  --structure NAME      structure to open as the paper position (default: iron_condor)
                        every structure is backtested regardless
  --no-dashboard        run the analytics, do not serve the page
  --dry-run             print every command, run none of them
  --help                this text

Every stage writes one schema-validated artifact. Re-running is safe: an
artifact that would be replaced is archived under archive/<date>/ first.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --symbols) SYMBOLS="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --horizon) HORIZON="$2"; shift 2 ;;
    --period) PERIOD="$2"; shift 2 ;;
    --structure) STRUCTURE="$2"; shift 2 ;;
    --no-dashboard) WITH_DASHBOARD=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

say() { printf '\n== %s\n' "$*"; }
note() { printf '   %s\n' "$*"; }

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '   %s\n' "$*"
    return 0
  fi
  "$@"
}

# ---------------------------------------------------------------- the tool

DESK="${OPTIONDESK_BIN:-}"
if [ -z "$DESK" ]; then
  if command -v optiondesk >/dev/null 2>&1; then
    DESK="$(command -v optiondesk)"
  elif [ -x "$HOME/.optiondesk/bin/optiondesk" ]; then
    DESK="$HOME/.optiondesk/bin/optiondesk"
  elif [ -x "./shell/.venv/bin/optiondesk" ]; then
    DESK="./shell/.venv/bin/optiondesk"
  fi
fi

if [ -z "$DESK" ]; then
  cat >&2 <<'MISSING'
optiondesk was not found.

Install it with ./install.sh, or from a checkout:

  python -m venv .venv && . .venv/bin/activate
  pip install -e "shell[yahoo]" -e engine

If it is installed but not on PATH, add ~/.local/bin to PATH or set
OPTIONDESK_BIN to the binary.
MISSING
  exit 1
fi

PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || { echo "python3 not found" >&2; exit 1; }

export OPTIONDESK_ARTIFACTS="$OUT_DIR"
run mkdir -p "$OUT_DIR"

say "Option desk demo"
note "tool:      $DESK"
note "artifacts: $OUT_DIR"
note "symbols:   $SYMBOLS"
[ "$DRY_RUN" -eq 1 ] && note "dry run: nothing below is executed"

say "What is installed, and what can answer"
run "$DESK" doctor

# Two expiries per symbol: a near one for the structures, a far one so the
# calendar and diagonal have a second leg to reach for.
pick_expiries() {
  "$DESK" expiries "$1" 2>/dev/null | "$PYTHON" -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)
rows = data.get("expiries", [])
near = [r for r in rows if 25 <= r["days_to_expiry"] <= 60]
far = [r for r in rows if 80 <= r["days_to_expiry"] <= 200]
out = []
if near:
    out.append(near[0]["expiry"])
if far:
    out.append(far[0]["expiry"])
print(" ".join(out))
'
}

for symbol in $SYMBOLS; do
  say "$symbol: what expiries are listed"
  run "$DESK" expiries "$symbol"

  if [ "$DRY_RUN" -eq 1 ]; then
    expiries="NEAR FAR"
  else
    expiries="$(pick_expiries "$symbol" || true)"
  fi
  if [ -z "$expiries" ]; then
    note "no expiry in the wanted range for $symbol, skipping it"
    continue
  fi

  for expiry in $expiries; do
    say "$symbol $expiry: the chain"
    run "$DESK" chain "$symbol" --expiry "$expiry"
  done

  near_expiry="${expiries%% *}"
  snapshot="$OUT_DIR/chain_${symbol}_${near_expiry}.json"

  say "$symbol: the full Greek ladder"
  run "$DESK" greeks --snapshot "$snapshot" --band 0.08

  say "$symbol: where dealer hedging concentrates"
  run "$DESK" exposure --snapshot "$snapshot"

  say "$symbol: every structure, built and ranked"
  # --include-underlying so the covered call and the protective put are in
  # the table too. The calendar and the diagonal build themselves from the
  # far expiry pulled above, so all seventeen end up on one page.
  run "$DESK" compare --snapshot "$snapshot" --include-underlying --rebuild

  say "$symbol: the underlying simulated forward from its own behaviour"
  note "this one fits a GARCH posterior by MCMC and can take a while on a"
  note "slow machine, with no output until it finishes. Let it run."
  run "$DESK" simulate "$symbol" --horizon "$HORIZON" --period "$PERIOD"

  say "$symbol: every structure across real history, with modelled premiums"
  note "one backtest per structure, so the page compares them rather than"
  note "showing whichever one happened to be run"
  for structure in $STRUCTURES; do
    if [ "$DRY_RUN" -eq 1 ]; then
      printf '   %s\n' "$DESK backtest $symbol $structure --period $PERIOD --holding-days 30 --entry-every 5"
      continue
    fi
    if "$DESK" backtest "$symbol" "$structure" --period "$PERIOD" \
        --holding-days 30 --entry-every 5 >/dev/null 2>&1; then
      printf '   %-24s done\n' "$structure"
    else
      # A structure that spans two expiries has no single-expiry history to
      # walk, and one that needs the underlying is not a pure option trade.
      # Neither is an error worth stopping for.
      printf '   %-24s skipped\n' "$structure"
    fi
  done
done

first_symbol="${SYMBOLS%% *}"

say "A paper position, so the forward ledger has something in it"
run "$DESK" forward open --strategy "$STRUCTURE" --underlying "$first_symbol" \
    --thesis "opened by demo.sh, paper only"
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

if [ "$WITH_DASHBOARD" -eq 1 ]; then
  say "The dashboard"
  note "http://127.0.0.1:$PORT"
  note "stop it with ctrl-c"
  run "$DESK" dashboard --host 127.0.0.1 --port "$PORT"
else
  note "start the dashboard yourself with: $DESK dashboard --port $PORT"
fi
