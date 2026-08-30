---
name: options-simulation
description: Simulate an underlying forward from its own realised behaviour using a Bayesian GARCH(1,1) model with Student-t innovations sampled by MCMC, then report the posterior predictive fan, value at risk, expected shortfall, and the profit distribution of any structures already built. Use when the user asks what the underlying might do, what the downside is, what value at risk or expected shortfall looks like, how likely a structure is to profit given how the stock actually moves, or asks for a Monte Carlo, a simulation, an MCMC, or a distribution of outcomes.
---

# Simulation

A second opinion on probability. Everything else in this desk prices from
the volatility the options are quoted at; this prices from the volatility
the underlying has actually shown.

## Run it

```
optiondesk simulate SPY --horizon 14
```

Options: `--paths` (default 20000, run in antithetic pairs), `--draws` and
`--burn` per chain, `--chains` (default 2, needed for the R-hat
diagnostic), `--period` for how much history to fit, and
`--no-structures` to skip the per-structure distributions.

## What the model is

GARCH(1,1) with standardised Student-t innovations: volatility clusters
and the tail is fatter than a normal admits. Estimated by adaptive
random-walk Metropolis rather than maximum likelihood, because a point
estimate hides how uncertain alpha and beta are, and that uncertainty
dominates at these horizons. Each simulated path draws its own parameter
set, so the fan carries parameter uncertainty rather than being narrower
than the data supports.

## Convergence is not optional

Read `posterior.converged` before quoting a single quantile. It is false
when split R-hat exceeds 1.05 or effective sample size falls below 100 on
any parameter, and it means the chains have not agreed. Say so, and
suggest raising `--draws`, rather than reporting the numbers anyway.

## The comparison that matters

For every structure on disk, the output gives probability of profit under
realised volatility next to the same probability under implied. The gap
between them is the market's forecast disagreeing with the recent past.
Neither side is the truth. Report the gap as a disagreement, never as an
edge, and never as a reason to trade.

Value at risk and expected shortfall are on the underlying's return over
the horizon, as positive losses, from the model. They are not a limit and
not a worst case.
