# Install Option Desk

[README](README.md) · [User guide](docs/wiki/Home.md) · [First walkthrough](docs/wiki/Getting-Started.md) · [Troubleshooting](docs/wiki/Troubleshooting.md)

Eight ways in cover local tools, skills, plugins, and hosted connections.
Choose where you want calculations to run.
The [sample walkthrough](docs/wiki/Getting-Started.md) is the shortest route to a local dashboard without a data-provider account.

| Route | Includes | Requires |
|---|---|---|
| Full installer | CLI, engine, skills, dashboard, and MCP registration attempts | macOS or Linux, Python 3.11 or later |
| Manual checkout | CLI, engine, dashboard, and MCP executable | Python 3.11 or later and Git |
| Local plugin | Skills and MCP declaration; Claude Code commands and reviewers where supported | Local tools installed separately |
| Skills CLI | Skill instructions | A supported agent; tools for calculations |
| Hosted connection | Remote snapshot analysis and plots | Compatible account and connection configuration |
| Docker | Containerized CLI and dashboard | Docker and an artifact mount |

## 1. Full local installer

From a checkout:

```sh
./install.sh --dry-run
./install.sh
optiondesk doctor
```

Without a checkout:

```sh
curl -fsSL https://raw.githubusercontent.com/Iman/agent-driven-options-desk-and-skills/main/install.sh -o /tmp/optiondesk-install.sh
bash /tmp/optiondesk-install.sh
```

The installer creates a virtual environment under `~/.optiondesk`.
It links `optiondesk` and `optiondesk-mcp` under `~/.local/bin`.
It copies local skills to `~/.claude/skills` and `~/.agents/skills` and attempts registration with runtime CLIs it finds.

If the command directory is absent from PATH, add it for the current terminal:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Restart the agent after installation.
Read the installer output for any manual MCP registration step.

### Installer controls

| Flag | Purpose |
|---|---|
| `--dry-run` | Print the planned actions. |
| `--no-engine` | Install the shell without the analytics engine. |
| `--skills-only` | Install skill files without Python packages. |
| `--no-mcp` | Omit runtime MCP registration. |
| `--no-keys` | Omit the optional provider-key prompt. |
| `--accept-yahoo-terms` | Explicitly acknowledge local personal use after reading the linked terms. |
| `--prefix DIR` | Choose the installation directory. |
| `--bin-dir DIR` | Choose the command-link directory. |
| `--skills-dir DIR` | Choose the Claude skill directory. |
| `--agents-skills-dir DIR` | Choose the shared agent skill directory. |
| `--no-skills` | Omit skill installation. |
| `--repo NAME` and `--ref REF` | Choose the source repository and revision. |
| `--yes` | Disable interactive prompts. This is not a data-rights acknowledgment. |
| `--uninstall` | Remove the installation's recorded files. |
| `--help` | Show the current controls and terms link. |

The current installer includes an Apple silicon architecture check and native wheel repair.
If an existing installation reports an incompatible wheel architecture, rerun the installer and inspect the doctor output.

## 2. Manual checkout

```sh
git clone https://github.com/Iman/agent-driven-options-desk-and-skills.git
cd agent-driven-options-desk-and-skills
python3 -m venv .venv
```

Activate the environment on macOS or Linux:

```sh
. .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install the packages:

```sh
python -m pip install -e ./engine -e ./shell
optiondesk doctor
```

Imported snapshots and the local dashboard need no provider extra.
For local Yahoo access, install `./shell[yahoo]` and complete the provider acknowledgment.
For development, use [the development guide](docs/wiki/Development.md).

Next: [run the supplied sample](docs/wiki/Getting-Started.md#2-import-the-sample).

## 3. Claude Code plugin

Install the local tools first, then run these commands inside Claude Code:

```text
/plugin marketplace add Iman/agent-driven-options-desk-and-skills
/plugin install option-desk@option-desk
```

The plugin includes six skills, six commands, two reviewer agents, and an MCP declaration.
The declaration starts `optiondesk-mcp` from PATH.
The plugin does not run the tool installer.
See [agent workflows](docs/wiki/Agent-Workflows.md) and the [official Claude Code instructions](https://code.claude.com/docs/en/discover-plugins).

## 4. Codex plugin

After installing the local tools, run:

```sh
codex plugin marketplace add Iman/agent-driven-options-desk-and-skills
codex plugin add option-desk@option-desk
```

The repository also exposes local skills through `.agents/skills`.
The plugin and MCP executable supply different parts of the workflow.
See [the OpenAI packaging guide](https://developers.openai.com/plugins/build/plugins) for marketplace details.

## 5. Skills only

```sh
npx skills add Iman/agent-driven-options-desk-and-skills --list
npx skills add Iman/agent-driven-options-desk-and-skills
```

Select the skills and agent when prompted.
To name Claude Code explicitly:

```sh
npx skills add Iman/agent-driven-options-desk-and-skills -a claude-code
```

These commands install instructions. Calculations need separately installed CLI or MCP tools.
See the [skills CLI documentation](https://www.skills.sh/docs/cli) for its current controls.

## 6. Hosted service and browser agents

The separate hosted endpoint is:

```text
https://optiondesk.avidquant.com/mcp
```

Connect it through the custom MCP or plugin setup available to your runtime and workspace.
Start with: `Show the SYNTH Greek ladder plot. Identify the data source.`

The hosted service provides a synthetic sample and permitted private snapshot analysis.
It supports Greeks, positioning, and strategy plots.
It does not fetch live market data or expose the local history-based workflow.
Read the [hosted workflow guide](docs/wiki/Agent-Workflows.md#browser-agents-and-the-hosted-service) and [privacy policy](https://optiondesk.avidquant.com/legal/privacy).

For runtimes that support this repository's hosted plugin, select `option-desk-hosted` from the same marketplace.
Do not enable it beside the local plugin in the same session: they expose overlapping tool names.
Directory review status is not a guarantee of account-level availability.

Skills ZIP files are instruction packages, not running MCP servers.
Maintainer upload and directory-submission instructions are in [docs/SUBMISSION.md](docs/SUBMISSION.md).

## 7. MCP without a plugin

The installed executable serves the local protocol over stdio.
Twelve tools expose typed inputs for chain import, analytics, plots, history workflows, and status.

For a full installer setup with the executable on PATH:

```sh
claude mcp add optiondesk -- optiondesk-mcp
codex mcp add optiondesk -- optiondesk-mcp
```

For a manual virtual environment, use the absolute path to its `optiondesk-mcp` executable.
Restart the agent and run its MCP connection check.

## 8. Docker

The container supplies the CLI and dashboard. Host agents need their own skill installation and MCP connection.
Mount both the input file directory and the artifact directory.

From a clone containing the supplied examples:

```sh
mkdir -p artifacts/tutorial
docker run --rm -v "$PWD/examples:/inputs:ro" -v "$PWD/artifacts/tutorial:/artifacts" ghcr.io/iman/agent-driven-options-desk-and-skills chain SYNTH --from-file /inputs/chain-synth.json --accept-data-rights
docker run --rm -v "$PWD/artifacts/tutorial:/artifacts" ghcr.io/iman/agent-driven-options-desk-and-skills greeks
docker run --rm -v "$PWD/artifacts/tutorial:/artifacts" ghcr.io/iman/agent-driven-options-desk-and-skills exposure
docker run --rm -v "$PWD/artifacts/tutorial:/artifacts" ghcr.io/iman/agent-driven-options-desk-and-skills compare
docker run --rm -p 127.0.0.1:8787:8787 -v "$PWD/artifacts/tutorial:/artifacts" ghcr.io/iman/agent-driven-options-desk-and-skills dashboard --host 0.0.0.0
```

Open `http://127.0.0.1:8787` on the host.
The current source requires a persistent artifact mount for writing commands.
The published container image is a separate release; its contents need not match an unpublished checkout.

## Provider setup

The supplied sample and permitted local file imports need no API key.
External-provider access depends on dependencies, credentials, and the provider's terms.

```sh
optiondesk doctor
optiondesk keys list
```

To configure an Alpha Vantage key through hidden input:

```sh
optiondesk keys set alphavantage
```

Yahoo requires a local personal-use acknowledgment.
Read the terms linked by `./install.sh --help` before using `--accept-yahoo-terms`.
Neither a key nor an acknowledgment grants hosting or redistribution rights.

Use `./run.sh --symbols SPY --dry-run` to inspect the complete local provider demo.
Use [the sample walkthrough](docs/wiki/Getting-Started.md) when no provider is available.

## Remove an installation

From a checkout, use the same custom paths as the original installation:

```sh
./install.sh --uninstall
```

Review the reported removals.
Your research artifacts are separate from the installed commands and skills.
