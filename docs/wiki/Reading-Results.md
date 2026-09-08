# Read the results

[Guide home](Home.md) | [Dashboard tour](Dashboard.md)

Read the source, timestamp, and quality flags before the calculated values.
The same rule applies to terminal output, agent replies, and dashboard charts.

## Data and quality

| Field or label | Meaning | What to do |
|---|---|---|
| `provider_used` and source | Origin recorded by the calculation | Distinguish synthetic data, user snapshots, and provider data. |
| Capture time | Time associated with the input | Distinguish it from the artifact-generation time. |
| `degraded` | Reduced quality or an unavailable required input | Read the reason before using the values. |
| `notes` | Other observations and assumptions | Read them even when degradation is false. |
| Missing IV | No usable implied volatility for that contract | Read the skip counts. Do not substitute a guessed value. |
| `unlimited` | Unbounded modeled gain or loss | Do not treat it as missing data or a finite amount. |

An artifact can be internally valid without being current or useful for a particular research question.
Synthetic screenshots demonstrate the interface, not market performance.

## Greeks and positioning

The ladder contains contract sensitivities.
Read its units block before combining or comparing values.
In particular, a unit change in volatility is different from a one-percentage-point change.

Dealer exposure adds open interest and an assumed position sign to contract gamma.
The assumed dealer holdings are not observed holdings.
A wall or flip is conditional on that assumption and the available chain.

## Structures and ranking

Read the legs and quantity signs before the summary.
Check whether stock ownership, collateral, or a second expiry is part of the structure.

Probability of profit is conditional on the stated model.
The comparison score orders structures under that model.
It is neither a recommendation nor evidence of an achievable return.

For a two-expiry structure, inspect how the surviving leg is valued.
A maximum found over a scan window does not establish a global maximum.
An entry delta ratio does not establish bounded tail risk.

## Simulation

The GARCH-t simulation models the underlying from price history.
It answers a different question from a probability calculated with chain IV.

If `converged` is false, do not quote the posterior quantiles as reliable estimates.
Inspect the parameter diagnostics and repeat the analysis with appropriate settings.
More draws do not guarantee convergence.

## Backtests and paper positions

A backtest uses modeled premiums and omits trading costs and execution effects named in its honesty statement.
Overlapping entries require the reported block treatment for uncertainty estimates.
Read the benchmark over the same windows.

A paper position records a plan before later marks.
It has no broker execution, fill verification, or account reconciliation.
A missing later quote can make a position unmarkable.

Next: [Research examples](Examples.md).
