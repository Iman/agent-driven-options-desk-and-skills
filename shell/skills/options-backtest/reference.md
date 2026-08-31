# Reference: what a result here can and cannot support

## The honesty rule, in full

Underlying closes are real. Option premiums are Black-Scholes values at
trailing realised volatility. There is no spread, no slippage, no
assignment, no early exercise, no borrow cost and no margin. Entry and exit
are priced by the same model, so a backtest here cannot detect any edge
that comes from the market disagreeing with that model. What it measures is
a structure's payoff geometry against real moves.

Volatility for entry pricing comes from the trailing window only. Using the
volatility realised over the holding period would be lookahead and would
make every short premium structure look profitable.

## The statistics

One unit of capital at risk per trade, returns summed rather than
compounded, so the curve and the drawdown are in units of per trade risk.
Compounding would assume the whole account is risked on every trade.

The permutation test asks how often a rule with no edge produces a mean
this large by chance, flipping signs at random. Two sided, because a rule
that reliably loses is also a finding.

Signs are flipped a BLOCK at a time, not a trade at a time, and the
bootstrap resamples blocks rather than single trades. The windows overlap:
a thirty day hold entered every five trading days shares twenty-five of its
thirty days with its neighbour, the measured autocorrelation is positive
through lag five and collapses at lag six, and the effective sample is 64
to 88 rather than 233. Flipping trades independently assumes an
independence the data does not have and understates the standard error by
about a factor of two. Correcting it moved four structures on this desk
from below 0.05 to above it, one of them from 0.0005 to 0.148.

Every artifact carries `overlap_block`. When it is above one the p-value
beside it is a block p-value and the trade count is not the number of
independent observations. Say both.

The bootstrap interval puts bounds on the mean the same way.
excludes_zero is the honest version of "significant", and it is honest
only at the right block: two structures stopped excluding zero when the
overlap was respected.

The benchmark holds the underlying over the same windows. A structure that
is simply long the market shows the market's drift, and without the
benchmark that drift gets credited to the strategy.

## The caveat that outranks all of them

A p-value is only a p-value for a hypothesis chosen before seeing the data.
A strategy selected because its backtest looked good has already spent its
degrees of freedom, and the number then understates how easily the result
could be chance.

Under thirty trades, decline to draw conclusions.

## Forward testing

Paper. Entry and marks are mid quotes, so a real entry would cross the
spread on every leg. What it removes is hindsight, not cost. A position
with any leg missing from the later chain is reported unmarkable rather
than marked at zero, because a missing wing marked at zero turns a losing
short spread into a full credit win.
