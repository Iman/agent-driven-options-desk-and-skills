---
name: options-backtest
description: Test an option structure against real price history with modelled premiums, and run a paper forward test that records positions before their outcome is known and marks them against later chains. Reports win rate, mean return on capital at risk, drawdown, a permutation test, a bootstrap interval and a buy-and-hold benchmark. Use when the user asks whether a strategy has worked historically, to backtest or forward test something, whether an edge is real or chance, how a structure performed, or asks to paper trade, track a position, or mark a trade. Not for order placement and not for recommendations, and a backtest result is not a forecast.
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

## What you must say about a result

Four things, in this order, every time. The full argument for each is in
`reference.md`; these are the versions you cannot skip.

1. Quote the `honesty` field from the artifact before the headline number.
   It is not boilerplate: premiums are modelled and entry and exit use the
   same model, so the test cannot see an edge that comes from the market
   disagreeing with that model.
2. Give the benchmark alongside the result. A structure that is long the
   market shows the market's drift, and without the benchmark that drift
   gets credited to the strategy.
3. Give the p-value with its caveat, not on its own. A strategy chosen
   because its backtest looked good has already spent its degrees of
   freedom.
4. Under thirty trades, decline to draw conclusions.

For a forward test, two more. It is paper, so entry and marks are mid
quotes and a real entry would have crossed the spread on every leg; what it
removes is hindsight, not cost. And a position with a leg missing from the
newer chain comes back unmarkable rather than marked at zero. Report it
that way: a missing wing marked at zero turns a losing short spread into a
full credit win, which is the most flattering error available and appears
exactly when the position is in trouble.

## Reporting rules

These hold for every number this skill produces.

Cite the artifact path when reporting from it. The artifact is the record;
prose is a summary of it, and a number quoted without its source cannot be
checked later.

Read `degraded` before quoting anything. When it is true, say so and give
`degraded_reason` first, in the same breath as the number rather than as a
footnote. Every command carries both fields in the summary it prints, not
only in the artifact.

Do not re-derive numbers yourself. If a figure is not in the artifact, say
it is not there rather than computing a replacement, and never substitute a
default for a value the pipeline refused to produce.

Premiums are model values or mid quotes from delayed third-party data. They
are not fills, and a real entry crosses the spread on every leg.

Never recommend a trade, an entry, an exit or a size. This is research
software and it is not investment advice. Present the analysis and let the
reader decide.

## Going deeper

- `reference.md`: the honesty rule in full, how the statistics are computed, and the caveat that outranks all of them.
- `workflows/evaluate-a-rule.md`: the four questions in the order that stops a backtest selling itself.
