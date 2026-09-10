# Your first options dashboard

[Guide home](Home.md) | [Installation](Installation.md) | [Troubleshooting](Troubleshooting.md)

This walkthrough uses supplied synthetic data. It needs no provider account or market-data request after installation.
The values demonstrate the workflow. They describe no listed security.

## 1. Get the repository

Install Python 3.11 or later and Git first.
Run these commands in a terminal:

```sh
git clone https://github.com/Iman/agent-driven-options-desk-and-skills.git
cd agent-driven-options-desk-and-skills
python3 -m venv .venv
```

On macOS or Linux, activate the environment:

```sh
. .venv/bin/activate
```

On Windows PowerShell, activate it with:

```powershell
.venv\Scripts\Activate.ps1
```

Install the local packages:

```sh
python -m pip install -e ./engine -e ./shell
optiondesk doctor
```

Expected: the doctor reports an available analytics engine.
A missing external provider does not prevent this file-based walkthrough.

## 2. Import the sample

Run all following commands from the repository root, in the same terminal.

```sh
optiondesk chain SYNTH --from-file examples/chain-synth.json --accept-data-rights --out-dir artifacts/tutorial
```

The sample declares its source inside the file.
The acknowledgment applies to this supplied teaching sample.

Expected: the command writes `artifacts/tutorial/chain_SYNTH_2026-10-08.json`.
The summary reports 62 contracts. Read `degraded`, its reason, and the source before the results.
For this sample, `degraded` is false and `provider_used` reads `user snapshot`, because the file carries its own rate, dividend yield, and source label.

## 3. Calculate the desk

```sh
optiondesk greeks --out-dir artifacts/tutorial
optiondesk exposure --out-dir artifacts/tutorial
optiondesk strategy iron_condor --out-dir artifacts/tutorial
optiondesk compare --out-dir artifacts/tutorial
```

Expected: the directory contains the chain, Greek ladder, positioning, strategy plans, and comparison artifacts.
`compare` builds the available structures from the saved chain.
It writes a plan for every structure it can build, so the `strategy` command above is optional. It shows how to build one structure at a time.
Two-expiry structures require a second chain, covered in [Examples](Examples.md#compare-two-expiries).

## 4. Open the dashboard

```sh
optiondesk dashboard --out-dir artifacts/tutorial
```

Open [the local dashboard](http://127.0.0.1:8787) in the browser on the same computer.
Select **SYNTH** and **2026-10-08**.

Without the `dashboard` extra, the command serves the page from Python's standard library and prints a note that says so.
Install `-e './shell[dashboard]'` for the FastAPI server. The walkthrough page is the same either way.

Read the comparison, positioning, payoff, and Greek ladder panels.
Simulation and backtest panels need separate history-based calculations. A chain alone cannot populate them.

Press `Ctrl+C` in the terminal to stop the dashboard.
Your artifacts remain in `artifacts/tutorial`.

## 5. Continue with one task

| Next task | Guide |
|---|---|
| Understand the charts | [Dashboard tour](Dashboard.md) |
| Ask an agent to use these files | [Agent workflows](Agent-Workflows.md) |
| Replace the sample with your own export | [Import your data](Importing-Data.md) |
| Compare spreads or track a paper position | [Examples](Examples.md) |

The sample fixes its valuation date and time to expiry for repeatable teaching.
Its dates are labels for that scenario, not a claim of current data.
See [sample provenance](../../examples/README.md) before reusing its inputs.
