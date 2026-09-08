# Synthetic teaching samples

These files describe fictional inputs. They contain no provider quotes, customer data, account positions, or observed price history.
They demonstrate the interface and calculation workflow, not an investment result.

## Start with a chain

- [chain-synth.json](chain-synth.json): the near-expiry sample for the [first walkthrough](../docs/wiki/Getting-Started.md).
- [chain-synth-far.json](chain-synth-far.json): the second expiry for [time-spread examples](../docs/wiki/Examples.md#compare-two-expiries).

Each file contains 62 contracts: calls and puts at 31 strikes from 70 through 130 in steps of two.
The underlying label is `SYNTH` and spot is 100.
The valuation date is fixed at September 8, 2026.
The near and far scenarios use 30 and 60 calendar days to expiry.

The `days_to_expiry` field freezes that teaching scenario.
The sample remains an illustration when its calendar dates become historical.
Do not carry this frozen day count into a real-data import.

The authored rate is 0.04 and the dividend yield is 0.01.
IV follows `0.26 - 0.0015 * (strike - 100) + 0.000035 * (strike - 100)^2`.
The engine prices each contract with Black-Scholes-Merton at those inputs.
Bid and ask are synthetic offsets around that model price.
Volume and open interest use authored strike patterns. They are not measurements.

## Open the complete visual example

The [dashboard](dashboard/) directory contains saved synthetic artifacts for the full screenshot tour.
It includes chain analytics, two-expiry structures, simulation, and backtests.
You can view it without a provider or a new calculation:

```sh
optiondesk dashboard --out-dir examples/dashboard
```

Open `http://127.0.0.1:8787` and select `SYNTH`, expiry `2026-10-08`.
This directory is a frozen example. Use `artifacts/tutorial` for your own walkthrough outputs.

## Synthetic history

[synthetic-history.json](synthetic-history.json) records the authored history used for the full dashboard capture.
It contains 756 generated log returns and 757 closes.
Generation used Python's `random.Random(73)` with Gaussian log returns, mean `0.0002` and standard deviation `0.014`.
The close series was scaled to finish at 100.
Date labels cover weekdays ending September 8, 2026. They do not establish exchange sessions or observations.

The simulation used the normal command implementation with a temporary in-memory provider serving only this fixture.
Settings were 30 days, 10,000 paths, 3,000 posterior draws, 1,000 burn-in iterations, and two chains.
The recorded result retains its actual convergence diagnostics.

Backtests used the same synthetic history, normal command implementation, and default window settings.
Their source labels and honesty statements explicitly identify synthetic inputs.
No statistic was adjusted to improve the appearance of a result.

The CLI does not currently expose a history-file import command.
The frozen artifacts let readers inspect every panel without claiming such an interface exists.
The chain walkthrough uses the public CLI throughout.

## Provenance and reuse

The source revision, capture date, file hashes, and image inventory are in [screenshot provenance](../docs/SCREENSHOT-PROVENANCE.md).
The normal artifact schemas validate the saved JSON outputs.
Input history and chain files use their documented input formats instead.

Keep the synthetic label on screenshots or results that you reuse.
The repository license applies to these supplied examples.
