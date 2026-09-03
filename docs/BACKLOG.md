# Backlog

Work that is known, measured and not done. Everything here came out of
adversarial verification of this project's own numbers rather than from a
wish list, so each item carries what was measured, where the code is, and
what "finished" means for it. Nothing is filed on a hunch.

If you want to contribute, the items marked **good first issue** are
self-contained and have a clear finish line. The rest are worth reading
before you rely on a figure this desk produces.

Two rules apply to every item, from [CONTRIBUTING.md](../CONTRIBUTING.md):
a fix ships with a test that has been seen to fail against the unfixed
code, and any test that guards a claim ships with an entry in
`scripts/mutate.py` proving it can fail. Five tests in this repository have
passed against deliberately broken code. They were caught by the mutation
harness and not by review, which is why the second rule exists.

---

## 1. Property-based tests for the pricer

**Size**: medium. **Good first issue** for the first invariant, then it
grows as you like.

Three independent verifications found eleven defects that a suite of more
than nine hundred tests did not. The suite tests examples. What it does not
do is explore, and every one of those defects lived in a corner nobody
thought to write an example for: a deep in the money contract at the
solver's seed, a rate of exactly zero, a maximum landing on a scan
boundary.

`hypothesis` would generate the corners and shrink a failure to its
smallest form. Invariants worth asserting, in rough order of value:

- put-call parity, `C - P = S exp(-qT) - K exp(-rT)`, to machine precision
- price monotone increasing in volatility, and in tenor for a call
- delta within [0, 1] for calls and [-1, 0] for puts, at every input
- every analytic Greek within tolerance of a central finite difference of
  `bs_price`, at random points rather than at a fixed grid
- implied volatility round trip: price at a sigma, solve, recover it
- no arbitrage bounds on every generated price

Where: `engine/tests/`, against `engine/src/optiondesk_engine/pricing/`.
`hypothesis` would be the project's first test-only dependency, which is a
deliberate decision rather than an oversight, so raise it in the pull
request.

**Finished when**: the invariants above run on generated inputs in CI, and
at least one of them has been shown to fail against a deliberately broken
pricer.

## 2. A canary on the implied volatility solver's refusal rate

**Size**: small. **Good first issue.**

The solver spent an unknown period refusing contracts it could identify,
because it tested vega at the Newton seed rather than at the answer. On one
live SPY chain that was 41 contracts, it pushed the provider-volatility
fallback to 12.2 percent, and it was the sole reason the chain and its
Greek ladder were both marked degraded. Nothing noticed, because a chain
reporting some untidiness looks like market data rather than a bug.

Fixed in `engine/src/optiondesk_engine/pricing/black_scholes.py`. What is
missing is the guard that would have caught it: pull one real chain and
fail if the unsolved share exceeds a small threshold.

Where: `shell/tests/`, behind the same marker the other network tests use
(`shell/tests/marks.py`), so an offline run skips it.

**Finished when**: a marked test fails on a chain whose unsolved share
exceeds roughly two percent, with the threshold justified in the test's
own docstring rather than chosen to pass today.

## 3. Effective sample size in the backtest artifact

**Size**: small to medium.

The backtest enters every five trading days and holds for thirty, so each
trade shares 25 of its 30 days with its neighbour. Measured
autocorrelation is positive through lag five and collapses at lag six,
exactly the geometry of the overlap, and the effective sample is 64 to 88
rather than 233. The significance test and the interval now respect that
through block resampling, and the artifact records the block.

What it does not record is the effective sample size itself. "233 trades,
64 of them independent" is more honest than either number alone, and it is
computable from the returns with a Bartlett kernel at the overlap lag.

Where: `engine/src/optiondesk_engine/backtest/stats.py`, then the artifact
and the dashboard's backtest table.

**Finished when**: `performance_stats` reports an effective sample size, the
schema carries it, the panel shows it beside the trade count, and a test
fixes its value on a series with known autocorrelation.

## 4. Report how tightly an implied volatility is identified

**Size**: medium.

The `MIN_VEGA` gate reduces the problem it names rather than closing it.
Vega grows with sigma, so a solve on a flat curve drifts upward until vega
just clears the threshold and accepts there. Measured worst case over a
9,126-case sweep: 0.124 absolute error in sigma, 24.8 times relative.

It does not bite on current chains. The widest interval that reprices
within tolerance across the 338 solved contracts of one live chain was
6e-6, and inside the Greek ladder's band it was 2.1e-7. So this is a
property of the function rather than a wrong number on disk today.

The honest fix is not a tighter gate, it is a published width: the interval
of sigma that reprices within tolerance, so a reader can see when a
volatility is pinned and when it is merely consistent.

Where: `engine/src/optiondesk_engine/pricing/black_scholes.py`, and the
chain snapshot schema.

**Finished when**: a solved contract carries the width of its
identification interval, and a test shows the width widening on a flat
curve and staying tight at the money.

## 5. Pooled effective sample size, or rename the field

**Size**: small. **Good first issue.**

`garch.py` reports the minimum single-chain effective sample size and calls
it `ess`. The standard quantity is pooled across chains, and on this
posterior the published number is understated by roughly a factor of two:
mu reads 444 where the pooled figure is 864, alpha 135 against 344.

The direction is conservative, so the `MIN_ESS` gate is stricter than it
appears rather than laxer, and nothing downstream is wrong because of it.
But the field is labelled `ess` in the artifact and "ESS" in the dashboard
without saying which quantity it is.

Either compute the pooled value or rename the field to say what it is.

Where: `engine/src/optiondesk_engine/simulation/garch.py`.

**Finished when**: the artifact's field name and its value agree, and a
test pins both against a series with a known answer.

## 6. One quantile estimator, not two

**Size**: small. **Good first issue.**

The fan's fifth percentile and the reported value at risk disagree by 0.0032
percentage points of return, because one interpolates at position
`0.05(n-1)` and the other takes the plain order statistic at
`floor(0.05n) - 1`. Immaterial in size. It means the fan band and the risk
number are not the same number, which a reader would reasonably assume.

Where: `engine/src/optiondesk_engine/simulation/paths.py`.

**Finished when**: both paths call one helper, and a test asserts the fan
band equals the corresponding risk figure exactly.

## 7. Persist the posterior draws, or stop claiming the diagnostics

**Size**: medium.

`simulation_SPY_30d.json` stores per-parameter summaries and the R-hat and
effective sample size, but not the draws. An auditor therefore cannot
recompute the diagnostics from the artifact: they can only re-run the
sampler and check the estimator, which is a different claim.

Either persist a thinned sample of the draws, or say in the artifact that
the diagnostics are not reproducible from it.

Where: `shell/src/optiondesk/cli/simulate.py` and the simulation schema.

**Finished when**: either the draws are on disk and a test recomputes
R-hat from the artifact alone, or the artifact says plainly that they are
not.

## 8. The benchmark uses a different window count from the structure

**Size**: small. **Good first issue.**

Sixteen of seventeen backtests trade the same 233 windows as the buy and
hold benchmark. `broken_wing_butterfly` traded 227, because some entries
found no viable structure, and it is still compared against the 233-window
benchmark. Over its own windows buy and hold returned 1.593 percent rather
than 1.556. A 0.037 percentage point discrepancy, and the panel says "over
the same windows".

Where: `shell/src/optiondesk/cli/backtest.py`, the `_benchmark` helper.

**Finished when**: the benchmark is computed over the windows the structure
actually traded, and a test with a deliberately skipped entry proves it.

## 9. Two price implementations, and a comment saying there is one

**Size**: small.

`black_scholes.py` states that the finite-difference tests differentiate
the same function the analytic Greeks are checked against, "rather than
against a second, subtly different one". `greeks_full.py` contains that
second one. It omits the floor that clamps a tiny negative price to zero,
so `all_greeks["price"]` goes negative where `bs_price` returns zero, worst
case minus 6.7e-14.

Nobody would act on 6.7e-14. The sentence asserting the invariant is the
defect, because the next reader will believe it.

Where: `engine/src/optiondesk_engine/pricing/greeks_full.py`.

**Finished when**: either the second implementation calls the first, or the
comment says there are two and why, and a test compares them.

## 10. Elasticity is amplified by cancellation noise

**Size**: small.

`lam` is `delta * spot / price`, guarded only by `price > 0`. Where the
price sits at the double-precision cancellation floor the guard passes and
the result is meaningless: minus 10,976 against an exact minus 1,118, on an
option worth 2.3e-15. Twenty-eight of 910 grid cases exceed 1e-6 relative,
all at prices below 1e-12, and the live ladder's worst error is 8.2e-14
because its band keeps prices far from the floor.

Where: `engine/src/optiondesk_engine/pricing/greeks_full.py`.

**Finished when**: elasticity is null rather than a large number where the
price carries no significant digits, and a test pins the boundary.

## 11. The gamma flip level is an artifact of where the strike ladder starts

**Size**: medium, mostly a presentation decision.

The reported flip on the live chain is 306.82 against a spot of 765.68,
sixty percent below it, and it is the only crossing. The code says why in
its own note: the cumulative profile is anchored at the lowest listed
strike rather than at zero. The note is honest and the number is still on
the tile row with nothing attached.

Either anchor the profile somewhere defensible, or stop presenting a level
that is not one.

Where: `engine/src/optiondesk_engine/analytics/exposure.py` and the
positioning tiles in `shell/src/optiondesk/dashboard/page.py`.

**Finished when**: the tile either shows a level that survives a change of
strike ladder, or says what it is measuring.

## 12. Decide what the two-expiry structures owe the reader

**Size**: medium.

Time spread plans carry `probability: null` and `net_greeks: null`, hard
coded, with no note explaining it. Everything else in the comparison
carries both, which is why those six rows are excluded from the ranking.
The probability of profit under a lognormal settlement is not defined the
same way when one leg survives the mark, so null may well be right. It is
undocumented either way.

Where: `shell/src/optiondesk/cli/strategy.py`.

**Finished when**: the plan either carries the two fields with a stated
definition, or carries a note saying why it cannot.

---

## Not planned

**A hosted MCP server in this repository.** The MCP server here is a local
stdio process by design. The separate hosted project provides browser access
with a different data policy, deployment, and threat model.

**More structures.** Twenty-three is past the point where another one
teaches anything. The verification work suggests the returns are higher on
checking what is here.

**Anything that places an order.** Not a backlog item. Not a direction.
