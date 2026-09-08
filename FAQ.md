# Questions about Option Desk

[README](README.md) · [User guide](docs/wiki/Home.md) · [Troubleshooting](docs/wiki/Troubleshooting.md)

## Start and install

**What is the quickest way to try it?**

Use the [supplied sample walkthrough](docs/wiki/Getting-Started.md).
It includes the input file, commands, and expected dashboard result.
It needs no provider account after the local packages are installed.

**Do I need an API key?**

The synthetic sample and permitted file imports need no key.
Yahoo access needs its optional dependency and a local personal-use acknowledgment.
Other providers can require credentials.
Run `optiondesk doctor` to see which sources are available and why others are unavailable.

**I installed the plugin. Why are the tools missing?**

The local plugin includes an MCP declaration, but it does not install the executable that declaration starts.
Install the local desk and restart the agent.
See [Installation](INSTALL.md) and [Agent workflows](docs/wiki/Agent-Workflows.md).

**Can I use it from ChatGPT or another browser agent?**

Use the separate hosted MCP connection if your account and workspace support it.
The hosted service provides synthetic examples and permitted snapshot analysis.
It does not run a local process on your computer.
See [the hosted workflow](docs/wiki/Agent-Workflows.md#browser-agents-and-the-hosted-service).

**Does installing skills also install the engine?**

No. Skills are workflow instructions.
Calculations need the local tools or a connected hosted service.

## Inputs and missing results

**Why is my dashboard empty?**

The page reads the directory you select. It does not fetch data.
Use the same `--out-dir` for your calculation commands and the dashboard.
Then select the correct underlying and expiry.
[The troubleshooting guide](docs/wiki/Troubleshooting.md#empty-dashboard-or-browser-error) gives the exact checks.

**Can I use my own CSV or JSON?**

Yes. Include the underlying, spot, expiry, source, and contract rows.
The [import guide](docs/wiki/Importing-Data.md) explains the format and acknowledgment.
Use only data permitted for the chosen local or hosted use.

**Why did some contracts receive no Greeks?**

Those contracts lack a usable implied volatility.
Quotes can be absent, invalid, or insufficient to identify volatility.
Read the chain counts and the ladder's skip counts.
A supplied valid IV can still support a row whose bid and ask are zero.

**Why does the volatility smile have missing wings?**

The available strikes and usable IV values can be insufficient to establish the requested wing points.
Read the chain coverage and missing-IV counts.
A missing value is not a zero value.

**What does `degraded` mean?**

The artifact reports reduced quality or a missing required input.
Read its reason before the values.
`notes` records additional observations and assumptions, including when degradation is false.

**Why does a timestamp look old?**

The artifact-generation time and input capture time answer different questions.
Read both and identify the source.
The supplied SYNTH example deliberately freezes a teaching scenario.
It is never current market data.

## Read the research

**Are model premiums executable prices?**

No. Read the premium source, model assumptions, and spread-cost estimate.
A model value or delayed midpoint is not a verified fill.

**Does a high comparison score identify a good trade?**

The score orders structures under a printed model and assumptions.
It does not account for your circumstances or establish a trading edge.
Inspect the legs, maximum loss, costs, and model limitations.

**Why does maximum loss sometimes say `unlimited`?**

That label means the modeled loss is unbounded.
It is different from an unknown value and cannot be replaced with a finite risk denominator.

**Why do the chain probability and simulation probability disagree?**

The chain calculation uses implied volatility under its stated model.
The simulation uses the underlying's return history.
They condition on different information. Their difference alone does not establish an edge.

**Can I use a simulation with `converged: false`?**

Do not quote its posterior quantiles as reliable estimates.
Inspect R-hat, effective sample size, and the reason for non-convergence.
More draws can help, but they do not guarantee a valid model or convergence.

**Why does the simulation take time?**

The sampler repeatedly evaluates the return history.
It prints a workload estimate before the calculation.
Runtime depends on history length and sampler settings.
See [Troubleshooting](docs/wiki/Troubleshooting.md#simulation-takes-time).

**Does the backtest use historical option chains?**

It uses historical underlying closes and modeled option premiums.
Read its honesty statement for omitted spreads, slippage, assignment, and exercise effects.
Compare it with the benchmark over the same windows.

**Does the paper ledger place orders?**

No. It records local plans, later marks, and settlements.
It does not send brokerage orders or verify fills.

## Historical example

**The backtest says a structure made 47 percent per trade. Is that real?**

This question refers to an earlier SPY bull-call-spread run recorded at `2026-08-30T16:18:49+00:00`.
The [evidence file](docs/evidence.json) records the mean return on capital at risk as `0.4742067427205202`.
The benchmark returned about 1.6 percent per window in the same recorded example.

The two returns use different capital bases.
The structure's result used modeled premiums, not historical option fills.
These historical figures illustrate interpretation limits. They are not current results or performance claims for the supplied SYNTH example.

## Scope and policies

**Which underlyings can I analyze?**

Use a compatible permitted option-chain snapshot or a provider that supports the underlying.
Availability varies by provider and date.
The pricing model's exercise assumptions remain relevant for every contract.
See [Reading results](docs/wiki/Reading-Results.md).

**Can I use it commercially?**

The repository uses PolyForm Noncommercial 1.0.0.
Commercial use requires a separate written agreement.
Read [LICENSES.md](LICENSES.md) for the project terms.

**Where does my data go?**

Direct local CLI imports produce local files.
A hosted upload is processed by the separate hosted service.
An agent can include tool results in its own conversation context.
Read [Privacy](PRIVACY.md) for the relevant boundaries and hosted-policy links.

**Where do I report an error?**

Use a [GitHub issue](https://github.com/Iman/agent-driven-options-desk-and-skills/issues) with a synthetic reproduction when possible.
Use [Security](SECURITY.md) for sensitive reports.
