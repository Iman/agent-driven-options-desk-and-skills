---
description: Refresh one underlying and report only what materially changed since the last run. Built for scheduled loops.
argument-hint: SYMBOL [EXPIRY]
---

Refresh $1 and report only what changed. Written to be run repeatedly, so
it must stay quiet when nothing has moved.

Cadence matters here. The free provider serves the last settled close, not
an intraday price, so nothing this command watches can move more than once
per trading session. Schedule it once a day after the close, with
`/schedule every weekday at 21:30: run /desk-watch SPY`. A thirty minute
loop would re-pull the same close and report nothing, repeatedly.

## 1. Capture the baseline BEFORE refreshing anything

The refresh overwrites the artifacts in place, because filenames are keyed
by underlying and expiry alone. Read the old values first or there is
nothing left to compare against.

```
DESK="${OPTIONDESK_ARTIFACTS:-$HOME/TradingDesk/option-desk}"
ls -t "$DESK"/exposure_$1_*.json | head -3
```

From the newest exposure artifact for the expiry you are watching, record:
`spot`, `smile.atm_iv`, `smile.risk_reversal`, `exposure.regime`,
`exposure.call_wall.strike`, `exposure.put_wall.strike`, and
`meta.degraded` with `meta.degraded_reason`.

## 2. Refresh

```
optiondesk chain $1 ${2:+--expiry $2}
optiondesk greeks --band 0.06
optiondesk exposure
```

## 3. Report only these, each with its previous value beside it

- spot moved more than one percent
- at-the-money implied volatility moved more than one volatility point
- the gamma regime flipped between dampening and amplifying
- either wall moved to a different strike
- the 25 delta risk reversal moved more than half a point
- an artifact is newly degraded for a reason that was not there before

On that last one, be specific. Most chains here are marked degraded because
some contracts fall back to the provider's published implied volatility,
which is routine and is not news. A degradation that appeared since the
last run, or one with a different reason, is.

If none of the six is true, say "no material change", give the spot and the
session it belongs to, and stop. Do not restate the desk.

Never open, mark or close a position from this command. It observes.
