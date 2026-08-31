---
description: Pull a chain, grade it, read positioning, and rank every structure for one underlying
argument-hint: SYMBOL [EXPIRY]
arguments: [symbol, expiry]
---

Open the desk on $symbol for the expiry $expiry, or the nearest listed expiry when
none is given.

Run these in order, reading each summary before the next:

1. `optiondesk expiries $symbol`
2. `optiondesk chain $symbol` with `--expiry $expiry` if an expiry was given
3. `optiondesk greeks --band 0.06`
4. `optiondesk exposure`
5. `optiondesk compare`

Then report, in this order and no other:

- whether any artifact came back degraded, and why, before any number
- spot with its `spot_asof` date, since it is the last settled close
- the positioning headline: regime, the walls, the flip nearest spot, and
  the dealer assumption that all three rest on
- at-the-money volatility, the 25 delta risk reversal, and the expected
  move with its horizon
- the top of the structure ranking with its criterion and its caveat,
  stating maximum loss before maximum gain

Do not recommend a trade. This produces an analysis of what is priced, not
a view on what to do about it.

Two agents are available when the answer matters more than the summary. If
a number looks surprising, or the artifacts may be stale or incomplete,
hand the set to `desk-data-auditor` before reporting from it. If a
structure has been chosen and the next step would be acting on it, hand it
to `options-risk-reviewer`, which re-derives the risk without having seen
the reasoning that produced the structure.
