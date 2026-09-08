# Troubleshooting

[Guide home](Home.md) | [Installation](Installation.md) | [First walkthrough](Getting-Started.md)

Start with the local health report:

```sh
optiondesk doctor
```

## Installation and connection

| Symptom | Check | Next action |
|---|---|---|
| `optiondesk: command not found` | Is the virtual environment active, or is `~/.local/bin` on PATH? | Activate the environment or use the PATH step in [Installation](Installation.md). |
| Engine unavailable | Does the doctor report the analytics engine? | In the checkout environment, run `python -m pip install -e ./engine`. |
| Plugin appears but calculations fail | Can the agent start `optiondesk-mcp`? | Install the local tools and restart the agent. |
| Skills appear but no tools exist | Was only the skills CLI used? | Install the local tools or connect the hosted service. |
| Duplicate tool names | Are both local and hosted Option Desk enabled? | Keep the connection intended for this session. |
| Apple silicon wheel error | Does the error report incompatible architectures? | Rerun the current installer from the checkout, then run the doctor. |

## Empty dashboard or browser error

The dashboard reads a directory. It does not fetch data or create missing analytics.
Use the same directory for calculations and the dashboard:

```sh
optiondesk expiries --out-dir artifacts/tutorial
optiondesk dashboard --out-dir artifacts/tutorial
```

The first command lists saved artifacts without a provider request.
Choose the correct underlying and expiry in the page.
Open the localhost URL on the computer that runs the server.

If the port is occupied, choose another port:

```sh
optiondesk dashboard --out-dir artifacts/tutorial --port 8788
```

Then open `http://127.0.0.1:8788`.

## Data and charts

| Symptom | Meaning or check | Next action |
|---|---|---|
| Provider unavailable | Dependency, credentials, terms acknowledgment, or access can be missing. | Read the provider reason in the doctor output, or use the supplied sample. |
| Chain mostly lacks IV | Quotes can be absent or insufficient to identify volatility. | Read counts, quote sources, and degradation. Obtain a usable snapshot. |
| Smile wings are missing | The available chain cannot establish the requested wing values. | Inspect strike coverage and missing-IV counts. |
| Date or spot looks stale | Generation time can differ from the input capture time. | Check the source timestamp. Refresh only through a permitted source. |
| Simulation or backtest is absent | A chain does not contain underlying price history. | Run the separate history workflow locally. |
| Paper mark unavailable | A required leg can lack a usable later quote. | Inspect the mark result and obtain the missing snapshot. |

Zero quotes do not establish a particular market session or recovery time.
Report the observed data quality without guessing the cause.

## Simulation takes time

The sampler performs repeated passes over the return history.
It prints a workload estimate before the calculation.
Inspect the process and its output before deciding that it is stuck.
Runtime depends on the history and sampler settings.

If the result reports non-convergence, inspect its diagnostics.
Do not remove the warning or substitute an earlier favorable result.

## Ask for help

Open a [GitHub issue](https://github.com/Iman/agent-driven-options-desk-and-skills/issues) with the command, software version, operating system, and error text.
Use the supplied SYNTH example to reproduce the problem when possible.
Remove credentials, account details, private upload links, and personal paths from the report.
Use [the security policy](../../SECURITY.md) for sensitive reports.

Next: [Return to the walkthrough](Getting-Started.md).
