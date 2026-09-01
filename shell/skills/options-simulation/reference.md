# Reference: the model, the diagnostics, and what they permit

## The model

GARCH(1,1) with standardised Student-t innovations:

    r = mu + sigma * z,  z standardised t with nu degrees of freedom
    sigma^2 = omega + alpha * residual^2 + beta * sigma^2

Volatility clusters and the tail is fatter than a normal admits. Estimated
by adaptive random walk Metropolis on the unconditional variance
parameterisation, which reduces the correlation between the level and the
persistence enough to lift effective sample size by a factor of ten or so.

Each simulated path draws its own parameter set, so the fan carries
parameter uncertainty rather than being narrower than the data supports.

## Run time

(draws + burn) x chains iterations, each walking every observation. Pure
Python, single threaded, no progress output.

Measured, 18 core arm64, 1253 observations:

| draws | burn | chains | wall clock |
|---|---|---|---|
| 3000 | 1000 | 2 | about 8 seconds |
| 6000 | 2000 | 4 | about 27 seconds |

That is roughly 1.6 microseconds per iteration-observation on that machine.
Scale it by your own hardware and by your history length. Ten years of
daily data at 6000 draws across four chains is four times the work of the
second row.

The command warns before it starts. Nothing is wrong when it goes quiet.


## Diagnostics, and the gate

converged is true only when split R-hat is below 1.05 and effective sample
size is at least 100 on every parameter, and the sampler actually accepted
proposals. A chain that never moved used to pass; it now fails.

The effective sample size estimator truncates its autocorrelation sum,
which overstates for a badly mixing chain. Below about 30, do not trust the
number itself.

It is also the MINIMUM over single chains rather than the pooled figure the
name implies, and on a live posterior it understated the standard quantity
by roughly a factor of two. The gate is therefore stricter than it looks,
which is the safe direction, but do not quote it as a standard ESS.

## What the numbers are

Value at risk and expected shortfall are on the underlying's return over
the horizon, expressed as positive losses. Expected shortfall is the mean
of the tail beyond the value at risk, so it is always the larger number. If
they are equal, the tail held one path and the run is flagged.

They are not drift free. On a live SPY fit the posterior median drift was
about 26 percent a year, so a 30 day value at risk of 3.92 percent sat only
that far below spot while the distance from the median down to the fifth
percentile was 6.98 points. Quote the median return beside the tail figure
or a reader will hear a narrower distribution than the model fitted.

## The comparison that matters

Probability of profit under realised volatility, next to the same
probability under implied. The gap is the market's forecast disagreeing
with the recent past. Neither side is the truth. Report it as a
disagreement, never as an edge.

## There are no antithetic pairs

Paths are independent draws, one posterior parameter set each. Artifacts
written before September 2026 carry `antithetic: true` and it was never
true: of ten thousand pairs, none shared a shock sequence, because the
shocks were drawn inside the sign loop and negating an independent
symmetric draw yields another independent draw. The construction did
nothing, and the test guarding it asserted the flag rather than the
property.

It was removed rather than repaired. Mirroring would require the two halves
of a pair to share a parameter draw, and each path drawing its own
parameters is worth more: parameter uncertainty dominates the tail, which
is what a risk number is for.

If you are reading an older artifact, treat that field as unreliable rather
than as history.
