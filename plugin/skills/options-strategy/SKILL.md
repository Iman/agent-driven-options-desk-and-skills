---
name: options-strategy
description: "Build and compare multi-leg option structures from a chain: iron condors, iron butterflies, call butterflies, vertical spreads both debit and credit, straddles, strangles, covered calls, cash-secured puts and protective puts. Produces legs, breakevens, maximum gain and loss, reward to risk, model probability of profit, net position Greeks and an estimate of what the round trip costs at quoted spreads, then ranks every structure side by side. Use when the user asks what structure fits a view, what an iron condor would pay, which spread is better, what the breakevens are, how much a trade can lose, or asks to compare strategies. Not for order placement and not for recommendations."
---

# Option strategies

Three commands. Build one structure, list what exists, or compare them all.

## Run it

```
optiondesk strategy --list                    # the playbook, as data
optiondesk strategy iron_condor               # build one from the latest chain
optiondesk strategy --recommend 1 --vol-view crush
optiondesk compare                            # every structure, ranked
```

`strategy` takes `--snapshot PATH` to pick a chain, `--size` for contracts
per leg, and `--underlying-entry` for structures that hold the underlying.
`--recommend N` takes an outlook from -2 (strong bearish) through 0
(neutral) to +2 (strong bullish), with `--vol-view crush|expand|neutral`,
`--owns-underlying` and `--direction-unknown`.

`compare` builds every buildable structure from one snapshot and ranks
them. Add `--include-underlying` for covered calls and the like.

## The five-direction framework

Structures are organised by which of five outcomes they need, anchored on
the one standard deviation expected move: strong bearish, mild bearish,
neutral, mild bullish, strong bullish. Three of the five sit inside the
normal expected range and two are extreme. That is why a vertical spread
beats a naked long option for most views: it reaches maximum profit on a
normal move rather than needing an extreme one.

## Reporting rules you must follow

The ranking is by model expected profit per unit of capital at risk. Quote
the caveat with it, every time: expectations come from a lognormal model at
a single at-the-money volatility while the market prices each strike
differently, so a positive expectation largely measures that disagreement
rather than an edge.

A structure whose friction verdict is untradeable is excluded from the
ranking. Say so rather than presenting it as a candidate.

Premiums are mid quotes. They are not fills, and a real entry crosses the
spread on every leg. Maximum gain or loss may come back as the string
"unlimited", which is a fact about the structure and must never be
rendered as a number.

Nothing here is advice. Present structures as analysis of what a shape
would pay under stated assumptions, never as what the user should do, and
never recommend an entry, an exit or a size.

Cite the artifact path when reporting from it. The artifact is the record;
prose is a summary of it, and a number quoted without its source cannot be
checked later.

Read `degraded` before quoting anything. When it is true, give
`degraded_reason` first, in the same breath as the number rather than as a
footnote. Both fields are in the summary the command prints, not only in
the artifact.

## Going deeper

- `reference.md`: all seventeen structures in a table with what each needs and when it pays, the five direction framework, the friction verdicts, and the fields that are not numbers.
- `workflows/choose-a-structure.md`: turning a view into a structure, and the rules for reporting one.
