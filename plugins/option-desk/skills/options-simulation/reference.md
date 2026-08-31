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

## Diagnostics, and the gate

converged is true only when split R-hat is below 1.05 and effective sample
size is at least 100 on every parameter, and the sampler actually accepted
proposals. A chain that never moved used to pass; it now fails.

The effective sample size estimator truncates its autocorrelation sum,
which overstates for a badly mixing chain. Below about 30, do not trust the
number itself.

## What the numbers are

Value at risk and expected shortfall are on the underlying's return over
the horizon, expressed as positive losses. Expected shortfall is the mean
of the tail beyond the value at risk, so it is always the larger number. If
they are equal, the tail held one path and the run is flagged.

## The comparison that matters

Probability of profit under realised volatility, next to the same
probability under implied. The gap is the market's forecast disagreeing
with the recent past. Neither side is the truth. Report it as a
disagreement, never as an edge.

## Antithetic pairs

Shocks are mirrored, with an independent parameter draw per path. GARCH has
no leverage term so the mirror is exact and unbiased. Mirroring reduces the
variance of the centre and increases it in the extreme tail, so a tail
number from few paths is noisier than a central one.
