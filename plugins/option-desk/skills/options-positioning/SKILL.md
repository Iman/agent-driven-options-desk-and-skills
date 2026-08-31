---
name: options-positioning
description: Dealer gamma exposure by strike, call and put walls, the gamma flip level, max pain, put-call ratios, and volatility smile geometry including at-the-money implied volatility, 25-delta risk reversal, butterfly, skew slope and the implied expected move. Use when the user asks where the walls are, whether dealers are long or short gamma, what the gamma flip level is, where max pain sits, what the put-call ratio is, how steep the skew is, what the market implies for a move, or asks about positioning and dealer hedging. This is chain-wide geometry rather than per-contract Greeks. Not for order placement and not for recommendations.
---

# Positioning and volatility geometry

One command over a whole chain, not a band around spot, because a wall
three hundred points away is exactly what a band would hide.

## Execution route

Prefer `option_chain_snapshot` to retrieve the whole chain and
`option_positioning` to analyse it. If a matching MCP tool is not available,
use the `optiondesk` commands below. If neither MCP nor the CLI is available,
say that no fresh positioning result can be produced; do not invent figures
or present example or remembered values as current.

## Run it

```
optiondesk chain SPY --expiry 2026-09-18
optiondesk exposure
```

`exposure` takes `--snapshot PATH` and `--multiplier` (100 for US equity
options).

## What comes back

Exposure per strike split into calls and puts, the cumulative profile, the
call and put walls, the gamma flip level where the cumulative profile
crosses zero, max pain with its full payout profile, open interest and
volume ratios, and the smile: at-the-money implied volatility, the
25-delta risk reversal, the butterfly, a least-squares skew slope and the
one standard deviation expected move.

## The assumption you must state

Every sign rests on the convention that dealers are long calls and short
puts against the public. That convention is often wrong for a single name,
especially around events and in heavily retail-traded tickers, and the
walls move with it. The artifact carries the assumption in a field; quote
it whenever you quote a wall.

Positive net exposure is read as hedging that dampens moves, negative as
hedging that amplifies them. That is an interpretation, not a measurement.

Max pain describes where open interest sits. It is not a forecast of where
price goes, and the evidence that price gravitates to it is thin.

Contracts with no open interest recorded are excluded rather than counted
as zero, because an absent number is not a zero and treating it as one
moves every wall.

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
The full terms are in DISCLAIMER.md, which ships beside this skill when it
is installed from a package and sits at the repository root otherwise. The
substance is already above: research software, not advice, modelled numbers
that are not fills.

## Going deeper

- `reference.md`: the exposure formula and its units, what the walls and the flip level are, why there is often more than one flip, and the limits of max pain and the smile metrics.
- `workflows/read-the-book.md`: the order to read the numbers in, what each is worth, and what never to say.
