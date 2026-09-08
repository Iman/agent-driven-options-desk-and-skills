# Install skills in your agent

[Guide home](Home.md) | [Full installation reference](../../INSTALL.md) | [First prompts](Agent-Workflows.md)

Choose your product, then choose an installation method.
A skill contains instructions. Option Desk calculations also require the local tools or the hosted MCP connection.
The terminal commands below use macOS or Linux shell syntax.

## Choose your platform

| Product | Install instructions | Connect calculation tools |
|---|---|---|
| [Codex](#codex) | `npx`, manual copy, shell installer, or plugin | Local `optiondesk-mcp`, or the separate hosted plugin. |
| [Claude Code](#claude-code) | `npx`, manual copy, shell installer, or plugin | Local `optiondesk-mcp`, or the separate hosted plugin. |
| [ChatGPT](#chatgpt) | Upload a hosted skill in an eligible workspace | Connect the hosted MCP app separately. |
| [Claude chat](#claude-chat) | Upload a hosted skill ZIP | Add the hosted custom connector separately. |

The `npx` and shell routes install files on your computer.
They do not upload skills to your ChatGPT or Claude chat account.

## Choose the correct skill edition

| Edition | Source folder | Skills | Intended tools |
|---|---|---|---|
| Local | `shell/skills/` | `desk-setup`, `options-greeks`, `options-positioning`, `options-strategy`, `options-simulation`, `options-backtest` | Local CLI or local MCP server. |
| Hosted | `openai-skills/` | `option-data-import`, `options-greeks`, `options-positioning`, `options-strategy` | Hosted Option Desk MCP. |

Several names occur in both editions, but their tool instructions differ.
Select one edition for a session.
The commands below use an explicit source folder to avoid installing the wrong edition.

## Codex

### Install through npx

Requirements: Node.js and npm, which supplies `npx`.

List the local skills:

```sh
npx skills add https://github.com/Iman/agent-driven-options-desk-and-skills/tree/main/shell/skills --list
```

Install one skill for your user account:

```sh
npx skills add https://github.com/Iman/agent-driven-options-desk-and-skills/tree/main/shell/skills --agent codex --skill options-greeks --global
```

Install all six local skills:

```sh
npx skills add https://github.com/Iman/agent-driven-options-desk-and-skills/tree/main/shell/skills --agent codex --skill '*' --global
```

For project scope, run the command in your project and omit `--global`.
Use `--copy` if you need copied files instead of symbolic links.
Inspect the installer summary before accepting it.
These flags come from the [skills CLI](https://github.com/vercel-labs/skills).

### Copy a skill manually

Clone the repository if you do not already have it:

```sh
git clone https://github.com/Iman/agent-driven-options-desk-and-skills.git
cd agent-driven-options-desk-and-skills
```

For a first installation of one skill:

```sh
mkdir -p "$HOME/.agents/skills"
cp -Rn shell/skills/options-greeks "$HOME/.agents/skills/"
cp -n DISCLAIMER.md "$HOME/.agents/skills/options-greeks/DISCLAIMER.md"
```

`-n` preserves existing files. It does not update an older installation.
To install another skill, replace `options-greeks` with a local skill name from the table.
For project scope, use `.agents/skills` inside the target project instead of `$HOME/.agents/skills`.

Codex discovers repository and user skills from these locations.
This checkout already links `.agents/skills` to `shell/skills`.
OpenAI documents the [local discovery paths](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills).

### Use the shell installer

From the checkout, run:

```sh
./install.sh --skills-only --dry-run
./install.sh --skills-only
```

This installs all six local skills into both `~/.agents/skills` and `~/.claude/skills`.
It preserves skill directories that it does not own.
Run `./install.sh` without `--skills-only` to install the calculation tools as well.

### Use the plugin

After installing the local tools:

```sh
codex plugin marketplace add Iman/agent-driven-options-desk-and-skills
codex plugin add option-desk@option-desk
```

Choose this as an alternative to standalone copies of the same skills.
See [plugin installation](../../INSTALL.md#4-codex-plugin).

### Connect and check local tools

If you used standalone skills, install the tools and register MCP:

```sh
./install.sh --no-skills --no-mcp
codex mcp add optiondesk -- optiondesk-mcp
optiondesk doctor
```

The executable must be on PATH. The [full installer guide](../../INSTALL.md#1-full-local-installer) explains the command directory.
Restart Codex and check that `options-greeks` appears in the skills selector.
Ask it to use `options-greeks` with the supplied sample.
A detected skill without working tools cannot calculate fresh results.

## Claude Code

### Install through npx

Install one local skill for your user account:

```sh
npx skills add https://github.com/Iman/agent-driven-options-desk-and-skills/tree/main/shell/skills --agent claude-code --skill options-greeks --global
```

For all six:

```sh
npx skills add https://github.com/Iman/agent-driven-options-desk-and-skills/tree/main/shell/skills --agent claude-code --skill '*' --global
```

Omit `--global` for the current project.
You can select both local agents in one command:

```sh
npx skills add https://github.com/Iman/agent-driven-options-desk-and-skills/tree/main/shell/skills --agent codex claude-code --skill '*' --global
```

### Copy a skill manually

From the repository checkout:

```sh
mkdir -p "$HOME/.claude/skills"
cp -Rn shell/skills/options-greeks "$HOME/.claude/skills/"
cp -n DISCLAIMER.md "$HOME/.claude/skills/options-greeks/DISCLAIMER.md"
```

For project scope, use `.claude/skills` inside the target project.
This checkout already links `.claude/skills` to `shell/skills`.
The [Claude Code skill guide](https://code.claude.com/docs/en/skills) describes personal and project discovery.

### Use the shell installer

From the checkout:

```sh
./install.sh --skills-only
```

This installs skills for both Claude Code and Codex.
Use `./install.sh` for tools, skills, and attempted MCP registration together.

### Use the plugin

Inside Claude Code:

```text
/plugin marketplace add Iman/agent-driven-options-desk-and-skills
/plugin install option-desk@option-desk
```

The plugin also includes commands and reviewer agents.
Install the local tools before using it.
See [plugin installation](../../INSTALL.md#3-claude-code-plugin).

### Connect and check local tools

For standalone skills with the tools on PATH:

```sh
claude mcp add optiondesk -s user -- optiondesk-mcp
optiondesk doctor
```

Restart Claude Code.
Enter `/options-greeks` for a standalone skill, or select its namespaced entry when using the plugin.
Run the [first local prompt](Agent-Workflows.md#first-local-prompt).

## Prepare individual browser skill ZIPs

ChatGPT and Claude chat use the hosted edition.

For a download without Git:

1. Open the [repository](https://github.com/Iman/agent-driven-options-desk-and-skills).
2. Select **Code > Download ZIP**.
3. Extract the downloaded repository archive.
4. Open its `openai-skills` folder.
5. Compress the selected skill folder, such as `options-greeks`, into its own ZIP.

For a terminal workflow, create one ZIP per skill from the repository checkout:

```sh
mkdir -p dist/browser-skills
python3 -m zipfile -c dist/browser-skills/option-data-import.zip openai-skills/option-data-import
python3 -m zipfile -c dist/browser-skills/options-greeks.zip openai-skills/options-greeks
python3 -m zipfile -c dist/browser-skills/options-positioning.zip openai-skills/options-positioning
python3 -m zipfile -c dist/browser-skills/options-strategy.zip openai-skills/options-strategy
```

Each ZIP contains one skill directory with its `SKILL.md` and any supporting files.
Upload one skill at a time.
For a graphical workflow, open `openai-skills` and compress the selected skill folder using your file manager.

The existing `dist/skills/*.zip` archives contain local skills, whose instructions expect local tools.
The aggregate `dist/option-desk-skills.zip` is an attachment for the plugin submission portal.
Use the individual ZIPs above for personal browser uploads.

## ChatGPT

### Check account access

OpenAI currently documents Skills for eligible Business, Enterprise, Healthcare, and Edu workspaces.
Personal Free, Plus, or Pro access is not established by that documentation.
If the Skills page is absent, use a supported local agent or the [hosted dashboard](https://optiondesk.avidquant.com).
See [Skills in ChatGPT](https://help.openai.com/en/articles/20001066) for current availability and workspace permissions.

### Upload a hosted skill

1. Prepare the individual hosted ZIPs described above.
2. Open **Plugins** in the ChatGPT sidebar.
3. Select the **Skills** tab.
4. Select **Create**, then **Upload from your computer**.
5. Select `options-greeks.zip` from `dist/browser-skills`.
6. Complete the scan and any review shown by ChatGPT.
7. Repeat for the other hosted skills you need.

Uploading a skill does not connect its MCP server.

### Connect the hosted tools

Where your account permits custom MCP apps:

1. Enable developer mode through the account or workspace controls available to your role.
2. Open **Settings > Apps > Create**, or **Workspace settings > Apps > Create**.
3. Enter the name **Option Desk** and the MCP URL below.
4. Complete the authentication choice shown by the connection form.
5. Select **Scan Tools**, then **Create** after a successful scan.
6. Start a chat and select the new app.

```text
https://optiondesk.avidquant.com/mcp
```

Full MCP access depends on workspace plan and role. Pro has a narrower read/fetch path.
See [developer mode and MCP apps](https://help.openai.com/en/articles/12584461) for current restrictions.
A local stdio declaration or a shell skill installation does not connect ChatGPT to this endpoint.

## Claude chat

### Upload a hosted skill

1. Prepare the individual hosted ZIPs described above.
2. Enable **Code execution and file creation** in **Settings > Capabilities**.
3. Open **Customize > Skills**.
4. Select **+**, then **Create skill**, then **Upload a skill**.
5. Upload `options-greeks.zip` from `dist/browser-skills`.
6. Enable the skill in the list.
7. Repeat for the other hosted skills you need.

Claude documents skills for Free, Pro, Max, Team, and Enterprise plans.
Organization settings can restrict uploads.
See [Use skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude).

### Connect the hosted tools

For an individual account with custom connectors:

1. Open **Customize > Connectors**.
2. Select **+**, then **Add custom connector**.
3. Enter **Option Desk** and `https://optiondesk.avidquant.com/mcp`.
4. Complete **Add** and any connection prompt.
5. Enable the connector for the conversation.

Team and Enterprise owners first add the connector through **Organization settings > Connectors**.
Members then connect to that approved entry.
See [custom remote MCP connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp).

## Check a browser installation

Start with a sample that needs no uploaded data:

```text
Use the Option Desk hosted tools to show the SYNTH Greek ladder plot.
Identify the source as synthetic. Explain the units and any unavailable results.
```

Expected: a tool call produces a plot and identifies synthetic input.
A prose response alone does not demonstrate a working MCP connection.
For a workflow with your own data, use [the import guide](Importing-Data.md).

## Update or remove a skill

For installations managed by the skills CLI:

```sh
npx skills list --global
npx skills update --global
npx skills remove options-greeks --agent codex --global
```

Replace `codex` with `claude-code` for that agent.
Omit `--global` for project installations.
Review the selected scope before confirming an update or removal.

For shell-managed installations, rerun the installer to update its owned skill folders.
For manual copies, keep a backup before replacing the selected skill directory.
For browser uploads, manage the skill through the product's Skills page and upload the revised individual ZIP.
Updating skill instructions does not update the hosted service or a workspace's approved tool definitions.

## If installation does not work

| Symptom | Check |
|---|---|
| `npx` is unavailable | Install Node.js with npm, or use the shell/manual route. |
| The wrong skill edition appears | Use the explicit `shell/skills` source for local agents and `openai-skills` for browser uploads. |
| Two copies of the same skill appear | Choose either the plugin or standalone installation for that edition. |
| The skill appears but calculations fail | Check the MCP connection and `optiondesk doctor` for local tools. |
| The shell installer skips a directory | It preserves directories that it did not install. Manage that copy through its original method. |
| ZIP upload fails | Check that the ZIP contains one skill folder and that the folder contains `SKILL.md`. |
| ChatGPT has no Skills or custom-app controls | Check the account plan and workspace permissions. |
| Claude chat has no upload control | Check code execution and the organization's skill permissions. |

Platform instructions checked against the linked official guides on September 9, 2026.
Account-specific upload and connection flows still require a check in that account.

The documented manual-copy and individual-ZIP commands were checked in temporary directories.
The shell skills-only install produced six skills in each destination.
The `npx` project install selected the local edition for both Codex and Claude Code.
These checks do not establish a completed upload into a personal browser account.
