# Read the dashboard

[Guide home](Home.md) | [First walkthrough](Getting-Started.md) | [Complete gallery](../SCREENSHOTS.md)

The dashboard shows artifacts already saved on disk.
Opening or refreshing the page does not retrieve new market data.

## Open the correct directory

```sh
optiondesk dashboard --out-dir artifacts/tutorial
```

Open `http://127.0.0.1:8787` on the same computer.
Select the underlying and expiry at the top of the page.
Keep the input source, date, and quality messages visible while interpreting a result.

## Follow the panels

| Panel | Question it answers | Read with it |
|---|---|---|
| Pipeline | Which calculations produced this page? | The artifact inputs and missing stages. |
| Structure comparison | How do the saved structures rank under this model? | The score definition, costs, and excluded cases. |
| Composite support | Where do the model, simulation, and backtest agree? | Component weights and disagreements. |
| Time spreads | What changes when legs use different expiries? | Surviving-leg valuation and scan boundaries. |
| Positioning | Where does assumed dealer gamma concentrate? | Open interest, missing contracts, and sign convention. |
| Volatility | How does IV vary by strike and expiry? | Data coverage and unavailable wings. |
| Structures | What is the shape of this plan's payoff? | Leg quantities, breakevens, stock legs, and loss limits. |
| Ladder | How sensitive is each usable contract? | Units and skipped-contract counts. |
| Condor search | How do saved condors differ? | The selected strikes and the search coverage. |
| Simulation | What distribution does the fitted model produce? | Source history and convergence diagnostics. |
| Backtest | What happened in the modeled historical exercise? | Benchmark, overlap treatment, and cost omissions. |

## Inspect a structure

![Synthetic structure payoff and leg table](../screenshots/dashboard-structures.png)

Choose a structure in the selector.
Read the leg table before the headline payoff.
Inspect where the payoff crosses zero and whether any gain or loss is unbounded.

## Compare positioning and volatility

![Synthetic positioning panels](../screenshots/dashboard-positioning.png)

Gamma exposure is conditional on assumed dealer holdings.
Open interest is an input to that calculation, not proof of who owns a position.

![Synthetic volatility panels](../screenshots/dashboard-volatility.png)

A missing wing value means the available data cannot establish that point.
It does not mean that volatility is zero.

## Compare model and history

![Simulation from synthetic teaching history](../screenshots/dashboard-simulation.png)

Read the convergence result before the predictive fan.
The simulation uses history rather than the chain's implied volatility.

![Backtest from synthetic teaching history](../screenshots/dashboard-backtest.png)

These public screenshots use synthetic history.
Their outcomes do not measure a strategy's market performance.
[Capture provenance](../SCREENSHOT-PROVENANCE.md) identifies the inputs and source revision.

## Missing panels

An imported chain can support Greeks, positioning, and structures.
Simulation and backtest panels need their own saved results.
Time spreads need another expiry for the same underlying.

Use [Examples](Examples.md) to create the missing artifacts.
Use [Troubleshooting](Troubleshooting.md) if existing files do not appear.

Next: [Understand the result fields](Reading-Results.md).
