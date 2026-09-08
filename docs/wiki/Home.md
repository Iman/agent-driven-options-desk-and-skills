# Option Desk guide

Option Desk turns option-chain snapshots into Greeks, positioning charts, strategy comparisons, and a local dashboard.
Local tools also support simulation, backtesting, and a paper ledger.

## Start here

| What you want | Where to start | What you get |
|---|---|---|
| See the results first | [Dashboard tour](Dashboard.md) | Screenshots and a guide to each panel. |
| Try it without market data | [First walkthrough](Getting-Started.md) | A sample chain, calculations, and a dashboard on your computer. |
| Use your agent | [Agent workflows](Agent-Workflows.md) | Installation paths and prompts for local and hosted tools. |
| Analyze your own chain | [Import your data](Importing-Data.md) | Required fields, an example file, and error recovery. |
| Run a research workflow | [Examples](Examples.md) | Structures, two-expiry spreads, simulation, backtests, and paper positions. |
| Resolve an error | [Troubleshooting](Troubleshooting.md) | Checks for installation, data, charts, and model results. |

## Choose where the calculation runs

| | Local desk | Hosted service | Skills only |
|---|---|---|---|
| Requirements | Python and the installed tools | A supported browser or agent connection | An agent that reads skills |
| Input | Your files or an enabled provider | The hosted SYNTH sample or a permitted upload | Your question and available context |
| Calculates results | Yes | Yes, within the hosted tool set | Requires separately connected tools |
| Simulation and backtests | Yes, with price history | Not part of the hosted workflow | Requires local tools |
| Dashboard | Local artifact viewer | Separate hosted service | No dashboard by itself |

[Install the desk](Installation.md), then complete the [first walkthrough](Getting-Started.md).
The hosted and local SYNTH examples are separate teaching samples. Their numbers need not match.

## Understand and maintain the desk

- [Read the results](Reading-Results.md): units, missing data, model assumptions, and comparison limits.
- [Architecture](Architecture.md): packages, artifacts, and the calculation path.
- [Master algorithm](Algorithm.md): skills, loops, graph routing, prompts, backtests, and paper tests in one pseudocode reference.
- [Development](Development.md): checks, screenshots, and documentation maintenance.
- [Documentation map](Documentation-Map.md): guides and reference material.

Research software. No order placement. Results are not investment advice.
The software is free for noncommercial use under the [project license](../../LICENSES.md).
[Privacy](../../PRIVACY.md) and the [research disclaimer](../../DISCLAIMER.md) explain the boundaries.

Next: [Complete the first walkthrough](Getting-Started.md).

[Install skills by platform](Skill-Installation.md) · [Architecture and preserved reference](Architecture.md#detailed-reference-and-preserved-content)
