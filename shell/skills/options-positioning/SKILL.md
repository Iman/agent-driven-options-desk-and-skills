---
name: options-positioning
description: Dealer gamma exposure by strike, call and put walls, the gamma flip level, max pain, put-call ratios, and volatility smile geometry including at-the-money implied volatility, 25-delta risk reversal, butterfly, skew slope and the implied expected move. Use when the user asks where the walls are, whether dealers are long or short gamma, what the gamma flip level is, where max pain sits, what the put-call ratio is, how steep the skew is, what the market implies for a move, or asks about positioning and dealer hedging.
---

# Positioning and volatility geometry

One command over a whole chain, not a band around spot, because a wall
three hundred points away is exactly what a band would hide.

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
