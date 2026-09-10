# Research examples

[Guide home](Home.md) | [First walkthrough](Getting-Started.md) | [Read the results](Reading-Results.md)

Complete the sample walkthrough first.
Run these examples from the repository root with the environment active.
Each command uses the same `artifacts/tutorial` directory.

## Compare two structures

```sh
optiondesk strategy iron_condor --out-dir artifacts/tutorial
optiondesk strategy straddle --out-dir artifacts/tutorial
optiondesk compare --out-dir artifacts/tutorial
```

In the dashboard, select each structure and inspect its payoff and legs.
Compare maximum loss, breakevens, net Greeks, and spread-cost estimates.
A model ranking does not establish which structure suits a person or has a trading edge.

## List and rank the playbook

```sh
optiondesk strategy --list
optiondesk strategy --recommend 0 --vol-view crush --out-dir artifacts/tutorial
```

The first command prints the 23 registered structures with their outlook tags, volatility view, and ownership requirement.
The second ranks candidates for a neutral outlook with an expected fall in implied volatility.
Outlooks run from -2 (strong bearish) to +2 (strong bullish).
Add `--owns-underlying` to include the covered call and the protective put, or `--direction-unknown` when a move is expected without a direction.
The score orders the playbook under the stated inputs. It is not a forecast.

## Compare two expiries

Import the second supplied sample:

```sh
optiondesk chain SYNTH --from-file examples/chain-synth-far.json --accept-data-rights --out-dir artifacts/tutorial
optiondesk greeks --snapshot artifacts/tutorial/chain_SYNTH_2026-11-07.json --out-dir artifacts/tutorial
optiondesk exposure --snapshot artifacts/tutorial/chain_SYNTH_2026-11-07.json --out-dir artifacts/tutorial
```

Build a calendar with explicit near and far snapshots:

```sh
optiondesk strategy calendar_spread --snapshot artifacts/tutorial/chain_SYNTH_2026-10-08.json --far-snapshot artifacts/tutorial/chain_SYNTH_2026-11-07.json --out-dir artifacts/tutorial
optiondesk compare --snapshot artifacts/tutorial/chain_SYNTH_2026-10-08.json --far-snapshot artifacts/tutorial/chain_SYNTH_2026-11-07.json --out-dir artifacts/tutorial
```

With a far snapshot on disk, `compare` also builds the calendar put spread, both diagonals, and both ratio diagonals.
The walkthrough directory then holds 21 plans for the near expiry.

Select the near expiry in the dashboard.
The surviving far leg uses a model value at the near expiry.
Read the time-spread assumptions and scan boundaries beside the result.

## Save charts for a report

Write the supplied sample as PNG charts:

```sh
optiondesk plots SYNTH --snapshot artifacts/tutorial/chain_SYNTH_2026-10-08.json --out-dir artifacts/tutorial
```

The command prints the output paths.
Keep the source and model labels with any chart you share.

## Open and mark a paper position

These commands change the local paper ledger. They place no brokerage order.

```sh
optiondesk forward open --plan artifacts/tutorial/strategy_SYNTH_iron_condor_2026-10-08.json --thesis "Synthetic walkthrough" --out-dir artifacts/tutorial
optiondesk forward status --out-dir artifacts/tutorial
optiondesk forward mark --out-dir artifacts/tutorial
```

Save the position ID from the open result.
A mark against the same sample chain demonstrates the workflow only.
A useful forward test needs a later independent snapshot.
The open result records the entry value from mid quotes and a note that says so.
A mark against the same chain reports a profit of 0.0 and an underlying move of 0.0. It shows the workflow and nothing else.

To close the paper record, replace `POSITION_ID` and the example settlement value:

```sh
optiondesk forward close --id POSITION_ID --price 100 --out-dir artifacts/tutorial
```

`--price` is the underlying settlement price for this action.
Use a synthetic value only for a synthetic paper exercise.

## Simulate a real underlying locally

This workflow needs permitted underlying price history and an enabled provider.
The chain sample cannot supply that history.

After local provider setup, run:

```sh
optiondesk simulate SPY --horizon 30 --out-dir artifacts/research
```

Read `converged`, R-hat, effective sample size, and degradation before quoting the fan or tail estimates.
Saved plans in that directory can receive simulated payoff distributions.

## Backtest a structure locally

With the same provider access, run:

```sh
optiondesk backtest SPY iron_condor --holding-days 30 --entry-every 5 --period 5y --out-dir artifacts/research
```

Read the benchmark, cost omissions, overlapping-window treatment, and uncertainty measures with the result.
The backtest uses historical underlying closes and modeled option premiums.
It does not reconstruct historical option-chain fills.

## Refresh a complete provider demo

```sh
./run.sh --symbols SPY --no-open
```

The runner writes to its demo directory and serves its dashboard.
Use `./run.sh --help` for directory, expiry-window, and stage controls.
Read [Installation](Installation.md#local-provider-demo) for the provider acknowledgment.

## Before interpreting uncertainty

For simulation, check the requested horizon against each structure's expiry. The current callback uses intrinsic payoff and omits a surviving leg's time value. The truncated ESS estimate can overstate mixing quality. Finite sample means of unbounded payoffs do not establish finite expectations under Student-t log returns.

For backtests, report block length and the sign-flip symmetry assumption. Block boundaries can lose dependence. If a block covers the whole sample, the bootstrap interval has no resampling variation and cannot support a conclusion. See the [algorithm limits](Algorithm.md#numerical-and-inference-limits).

Next: [Read the dashboard](Dashboard.md) or [troubleshoot a result](Troubleshooting.md).
