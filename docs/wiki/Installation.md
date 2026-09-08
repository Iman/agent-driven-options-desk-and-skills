# Install Option Desk

[Guide home](Home.md) | [First walkthrough](Getting-Started.md)

Choose the calculation location first. A plugin or skill installation does not always install the local tools.

| You want | Install | Then do this |
|---|---|---|
| A local dashboard and CLI | [First walkthrough](Getting-Started.md) | Import the supplied sample. |
| Local tools connected to agents | Run `./install.sh` from a checkout | Run `optiondesk doctor`, then restart the agent. |
| Claude Code skills, commands, and reviewers | Install the tools, then the local plugin | [Claude Code instructions](Agent-Workflows.md#claude-code). |
| Codex skills and MCP tools | Install the tools, then the local plugin | [Codex instructions](Agent-Workflows.md#codex). |
| Tools in a browser agent | Connect the hosted MCP service | [Hosted instructions](Agent-Workflows.md#browser-agents-and-the-hosted-service). |
| Skill instructions alone | Use the skills CLI | Connect tools separately for calculations. |

## Full local installer

On macOS or Linux, run these commands from the repository root:

```sh
./install.sh --dry-run
./install.sh
```

The installer creates an environment under `~/.optiondesk` and command links under `~/.local/bin`.
It copies skills to the user skill directories and registers MCP with supported runtime CLIs it finds.
The installer can ask about provider access. Imported files need no provider acknowledgment.

If your terminal cannot find `optiondesk`, add the command directory for this terminal:

```sh
export PATH="$HOME/.local/bin:$PATH"
optiondesk doctor
```

Restart your agent after installation so it can discover the tools.
The [installation reference](../../INSTALL.md) covers custom paths, flags, Docker, and removal.

## Local provider demo

`run.sh` installs missing tools, selects expiries, runs the analytics, and opens the dashboard.
It uses external data and also creates a paper position.

Inspect its plan first:

```sh
./run.sh --symbols SPY --dry-run
```

If you have already acknowledged the provider terms, run:

```sh
./run.sh --symbols SPY
```

For an explicit acknowledgment, read the terms linked by `./run.sh --help`, then use its `--accept-yahoo-terms` flag.
The flag grants no public display or redistribution rights.
The default demo directory is `~/TradingDesk/option-desk-demo`.

For a shorter first run, omit the history calculations:

```sh
./run.sh --symbols SPY --no-simulation --no-backtests
```

## Skills only

```sh
npx skills add Iman/agent-driven-options-desk-and-skills --list
npx skills add Iman/agent-driven-options-desk-and-skills
```

Select the skills and agent in the install prompt.
Skills describe the workflows. They need the CLI or MCP tools to produce calculations.

Next: [Run the sample walkthrough](Getting-Started.md) or [connect your agent](Agent-Workflows.md).
