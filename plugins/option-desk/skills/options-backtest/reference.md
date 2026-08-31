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
this large by chance, flipping the sign of each trade at random. Two sided,
because a rule that reliably loses is also a finding.

The bootstrap interval resamples trades to put bounds on the mean.
excludes_zero is the honest version of "significant".

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
