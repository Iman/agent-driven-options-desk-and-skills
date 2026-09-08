# Use Option Desk with an agent

[Guide home](Home.md) | [Installation](Installation.md) | [Examples](Examples.md)

For manual, shell, `npx`, or browser ZIP installation, start with [Install skills in your agent](Skill-Installation.md).

Install the local tools before the local plugin.
For a browser agent, use the separate hosted connection.

## Claude Code

Run these commands inside Claude Code:

```text
/plugin marketplace add Iman/agent-driven-options-desk-and-skills
/plugin install option-desk@option-desk
```

The local plugin includes skills, commands, two reviewer agents, and an MCP declaration.
The declaration starts `optiondesk-mcp`, which must be on the runtime's PATH.
See the [official plugin instructions](https://code.claude.com/docs/en/discover-plugins).

## Codex

Run these commands in a terminal:

```sh
codex plugin marketplace add Iman/agent-driven-options-desk-and-skills
codex plugin add option-desk@option-desk
```

Codex can also discover the repository's `.agents/skills` without a plugin.
The full local installer supplies the calculation tools.
The [OpenAI plugin guide](https://developers.openai.com/plugins/build/plugins) describes the package format and marketplace workflow.

## First local prompt

Open an agent session in the cloned repository, then ask:

```text
Use examples/chain-synth.json, the supplied synthetic teaching sample.
I can use this file for private analysis.
Save this walkthrough under artifacts/tutorial.
Validate the chain, calculate its Greeks and positioning, and build an iron condor.
State the source, valuation date, missing inputs, and degradation before the numbers.
Show the payoff and explain the limits of the model.
```

Expected: the agent uses the supplied file and reports synthetic input.
A response that calls this live market data is incorrect.

## Ask by task

| Task | Example prompt | Local skill |
|---|---|---|
| Setup | Install the tools and check why MCP is unavailable. | `desk-setup` |
| Contract risk | Show delta, gamma, theta, and vega from this saved chain. | `options-greeks` |
| Chain positioning | Show gamma walls and state the dealer-sign assumption. | `options-positioning` |
| Structure comparison | Compare an iron condor with a straddle from this chain. | `options-strategy` |
| Forward distribution | Simulate the underlying from permitted price history and report convergence. | `options-simulation` |
| Historical research | Backtest the structure and explain the benchmark and omitted costs. | `options-backtest` |

## Repeat a local workflow

The Claude Code plugin supplies these commands:

| Command | Purpose |
|---|---|
| `/desk-open SPY` | Retrieve a permitted chain, calculate positioning, and compare structures. |
| `/desk-risk SPY 30` | Simulate the underlying and review the risk assumptions. |
| `/desk-test SPY iron_condor` | Research a structure with backtest and forward-test workflows. |
| `/desk-mark` | Mark open paper positions against saved chains. |
| `/desk-watch SPY` | Report material changes since the previous run. |
| `/desk-complete SPY` | Work toward a defined set of complete artifacts. |

Provider commands require an enabled data source.
Use [Loops](../../LOOPS.md) for budgets, stop conditions, and scheduling limits.

## Browser agents and the hosted service

Follow the separate [ChatGPT steps](Skill-Installation.md#chatgpt) or [Claude chat steps](Skill-Installation.md#claude-chat).
They include individual skill uploads, account requirements, and the MCP connection.

The hosted MCP endpoint is:

```text
https://optiondesk.avidquant.com/mcp
```

Add it through your runtime's supported custom MCP or plugin setup.
Connection availability depends on your account and workspace configuration.
A directory submission does not establish that every user can install the listing.

Start without an upload:

```text
Show the SYNTH market chart and Greek ladder.
Identify the data as synthetic and explain what each chart measures.
```

Then try a structure:

```text
Show the payoff for a SYNTH iron condor.
Explain the legs, breakevens, maximum gain, and maximum loss.
```

For your own chain, attach only a permitted CSV or JSON file.
Name its source and state that you can send it for private analysis.
Ask for validation before calculations.

The hosted workflow supports snapshot analysis, Greeks, positioning, and strategy plots.
It does not fetch live chains or offer the local simulation and backtest workflow.
The [hosted privacy policy](https://optiondesk.avidquant.com/legal/privacy) governs uploads.

Use one local or hosted Option Desk connection per session to avoid duplicate tool names.

Next: [Import your data](Importing-Data.md) or [read the results](Reading-Results.md).
