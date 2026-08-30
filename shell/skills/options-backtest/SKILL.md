---
name: options-backtest
description: Test an option structure against real price history with modelled premiums, and run a paper forward test that records positions before their outcome is known and marks them against later chains. Reports win rate, mean return on capital at risk, drawdown, a permutation test, a bootstrap interval and a buy-and-hold benchmark. Use when the user asks whether a strategy has worked historically, to backtest or forward test something, whether an edge is real or chance, how a structure performed, or asks to paper trade, track a position, or mark a trade.
---

# Backtest and forward test

Two different questions. A backtest asks what a rule would have done. A
forward test asks what a position actually did from the moment it was
written down.

## Backtest

```
optiondesk backtest SPY iron_condor --holding-days 30 --entry-every 5 --period 5y
```

Enters the structure on a fixed schedule, holds to expiry, settles against
the real close. Reports trades, win rate, mean return on capital at risk,
total in risk units, drawdown, a permutation test, a bootstrap interval
for the mean, and the same schedule holding the underlying instead.

## Forward test

```
optiondesk forward open --strategy iron_condor --thesis "range bound into expiry"
optiondesk forward mark            # after a newer chain snapshot exists
optiondesk forward status
optiondesk forward close --id <id> --price 775
```

## What you must say about a backtest result

The honesty statement is in the artifact and it is not boilerplate.
Underlying closes are real; premiums are Black-Scholes values at trailing
realised volatility. There is no spread, no slippage, no assignment, no
early exercise. Entry and exit are priced by the same model, so a backtest
here cannot detect any edge that comes from the market disagreeing with
that model. It measures a structure's payoff geometry against real moves.

Read the benchmark before praising a result. A structure that is simply
long the market will show the market's drift, and the buy-and-hold column
is there so that is visible rather than credited to the strategy.

Read the p-value and say what it means: how often a rule with no edge
produces a mean this large by chance. And read its caveat: a strategy
chosen because its backtest looked good has already spent its degrees of
freedom, so the number understates how easily the result could be chance.

Under thirty trades, decline to draw conclusions.

## What you must say about a forward test

It is paper. Entry and marks are mid quotes, so a real entry would have
crossed the spread on every leg. What it removes is hindsight, not cost.

A position with any leg missing from the newer chain comes back
unmarkable, not marked at zero. Report it that way: a missing wing marked
at zero turns a losing short spread into a full-credit win, which is the
most flattering possible error and appears exactly when the position is in
trouble.
