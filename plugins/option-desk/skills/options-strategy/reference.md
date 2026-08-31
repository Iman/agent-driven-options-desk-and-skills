# Reference: the seventeen structures and what each needs

## Single expiry

| structure | type | needs | pays when |
|---|---|---|---|
| long_call | debit | strong bullish | a large move up |
| long_put | debit | strong bearish | a large move down |
| bull_call_spread | debit | mild bullish | a normal move up |
| bear_put_spread | debit | mild bearish | a normal move down |
| cash_secured_put | credit | neutral to mild bullish | anything but a large fall |
| covered_call | credit | neutral to mild bullish | sideways, with the underlying held |
| protective_put | debit | either extreme | a fall, while keeping the upside |
| straddle | debit | either extreme | a large move, direction unknown |
| strangle | debit | either extreme | a larger move, more cheaply |
| iron_condor | credit | range bound | the price staying inside the wings |
| iron_butterfly | credit | pinned | the price finishing near one strike |
| long_call_butterfly | debit | pinned | the price finishing near the body |
| ratio_spread | credit | a rise that stops short of the short strikes | the price ending near the short strike, and it loses without limit above |
| broken_wing_butterfly | credit | pinned, with one side you do not fear | the price finishing near the body, with no loss on the unfeared side |
| jade_lizard | credit | neutral to mildly bullish, volatility rich | the price staying above the short put, with no upside risk when the credit exceeds the call width |

## Two expiries

| structure | type | needs | pays when |
|---|---|---|---|
| calendar_spread | debit | the price sitting still | the near leg decays faster than the far |
| diagonal_spread | debit | a drift toward the short strike | decay plus a directional lean |

A calendar's payoff is a curve, not line segments, because the far leg is
still alive when the near one expires. Its maximum gain and loss are found
by scanning a range and are reported with the range that was scanned.

## The five directions

Anchored on the one standard deviation expected move, not on an opinion:
strong bearish and strong bullish sit outside the band, mild bearish, mild
bullish and neutral sit inside it. A spread reaches its maximum on a normal
move; a naked long option needs an extreme one. That is the whole reason a
professional prefers the spread.

## Friction verdicts

ok, under 10 percent of the premium; thin, up to 25 percent, the edge must
be real to survive; untradeable, above that, or a leg quoting wider than 40
percent of its own mid, or a leg with no bid at all. Untradeable structures
are excluded from any ranking.

## Fields that are not numbers

max_gain and max_loss can be the string "unlimited". That is a fact about
the structure. Never render it as a number, and never substitute a large
one.
