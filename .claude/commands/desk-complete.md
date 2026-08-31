---
description: Bring one underlying to a complete artifact set against checkable criteria. Built for goal-based loops.
argument-hint: SYMBOL [EXPIRY]
arguments: [symbol, expiry]
---

Bring the desk on $symbol to a complete state, for expiry $expiry if one was given
and the nearest listed expiry beyond a week otherwise. This has a
deterministic finish, which is what makes it usable with `/goal`:

```
/goal run /desk-complete SPY until every criterion is met, stop after 5 tries
```

## The criteria, all checkable without judgement

Read them from the artifacts, not from the command output.

1. A chain snapshot exists for the chosen expiry and `counts.with_iv` is at
   least 90 percent of the contract count.
2. A Greek ladder exists with at least 50 graded rows.
3. An exposure artifact exists with a call wall, a put wall and a smile.
4. A comparison exists with `rankable_count` of 5 or more.
5. A simulation exists whose `posterior.converged` is true and whose
   `simulation.horizon_days` is at least `days_to_expiry` from the chain,
   rounded up. Simulation artifacts are keyed by horizon rather than
   expiry, so the horizon is what ties one to the expiry you are working
   on. Round up: `days_to_expiry` is fractional, and a horizon of 31
   against 31.1 days misses by an afternoon and fails this criterion.
6. No artifact is degraded for a reason other than implied volatility
   fallback. That one reason is routine on this data source: between 15 and
   60 percent of contracts on a live SPY chain price at the provider's
   published volatility because an intrinsic-dominated price identifies
   none, and any threshold that treats it as failure never passes. Report
   it, do not retry it.

## What to run

Each attempt runs only what is missing or failing, not the chain again.

```
optiondesk expiries $symbol
optiondesk chain $symbol --expiry <chosen>
optiondesk greeks --band 0.06
optiondesk exposure
optiondesk compare
optiondesk simulate $symbol --horizon <days to expiry, rounded up> --draws 4000
```

## When something is short

- too few contracts with implied volatility: try the next expiry out. A one
  or two day expiry has the fewest two-sided quotes and the most
  intrinsic-dominated prices, so it fails criterion 1 most often.
- thin ladder: the band is what limits it. `/desk-open` uses `--band 0.06`;
  widening to `--band 0.10`, which is the command's own default, admits
  more strikes.
- fewer than five rankable structures: the chain is too sparse. Try a
  further expiry rather than rerunning the same one.
- simulation not converged: raise `--draws` to 4000, then 6000. Two failures
  at 6000 is a stop, not a third attempt.
- degraded for a reason other than volatility fallback: report it and stop.
  A provider that is not answering is not fixed by asking again.

## When you finish

State which criteria are met and which are not, with the number beside
each. If one cannot be met, say why in one line and stop rather than
retrying: a sparse expiry does not improve on the third attempt.
