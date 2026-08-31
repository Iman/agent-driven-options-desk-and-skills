# Installing

Eight ways in, depending on what you want and which runtime you use. Every
one of them has been run and verified; none is written from memory.

If you only want to try it, use the first. If you only want the skills and
not the tools, use the second, which needs no Python. If you use claude.ai
in the browser rather than a terminal, use the seventh. If you are in
Codex or ChatGPT, use the second or the fourth.

---

## 1. One command, everything (Claude Code, Codex, Gemini CLI)

```
./install.sh
```

Creates a virtualenv at `~/.optiondesk`, installs the MIT shell with the
free data provider and the AGPL engine, links `optiondesk` and
`optiondesk-mcp` into `~/.local/bin`, copies the skills into both
`~/.claude/skills` and `~/.agents/skills` so Claude Code and Codex each
find them, registers the MCP server with every agent runtime CLI it finds,
then offers an optional prompt for provider keys and runs a verification.

Each installed skill also receives a copy of `DISCLAIMER.md`, because the
skills point at it and a skill installed on its own has no repository root
to find it in.

Re-running is safe. It never overwrites a file it did not create: a skill
directory or a binary it does not recognise is left alone with a warning.

Flags:

| flag | effect |
|---|---|
| `--dry-run` | print the plan, change nothing |
| `--no-engine` | MIT shell only, no AGPL component, Greeks unavailable |
| `--skills-only` | just the markdown skills, no Python at all |
| `--no-mcp` | leave every runtime config untouched |
| `--no-keys` | skip the optional key prompt |
| `--prefix DIR` | install somewhere other than `~/.optiondesk` |
| `--bin-dir DIR` | put the two commands somewhere other than `~/.local/bin` |
| `--skills-dir DIR` | Claude skills somewhere other than `~/.claude/skills` |
| `--agents-skills-dir DIR` | Codex and ChatGPT skills somewhere other than `~/.agents/skills` |
| `--no-skills` | Python only, no skills |
| `--repo NAME` `--ref REF` | install from a different repository or branch |
| `--yes`, `-y` | do not prompt |
| `--version`, `--help` | print and exit |
| `--uninstall` | remove exactly what it created, and nothing else |

## 2. Skills only, through the skills CLI

```
npx skills add Iman/agent-driven-options-desk-and-skills
```

Installs the five skills and nothing else, with no Python involved. Add
`--list` to see them first, or `--skill options-greeks options-strategy` to
take a subset.

The CLI finds them through `.claude-plugin/marketplace.json`, which this
repository generates, so the skills stay in `shell/skills` where the rest
of the build expects them.

It detects which agents you have installed and asks where to put them.
Claude Code reads `.claude/skills/`; universal agents share
`.agents/skills/`. Asking an agent to run the command for you is the case
that goes wrong: the CLI then runs non-interactively and may install only
to `.agents/skills/`, which Claude Code does not read. Name the agent when
that happens:

```
npx skills add Iman/agent-driven-options-desk-and-skills -a claude-code
```

One caveat worth knowing. This path gives you the skills as knowledge, not
the tools they describe, the same as option 6 below. An agent holding them
can explain the desk and its conventions and cannot run anything until the
CLI is installed too.

## 3. As a Claude Code plugin, which also brings the commands and agents

```
/plugin marketplace add /path/to/option-desk
/plugin install option-desk@option-desk
```

Or, once published, `/plugin marketplace add Iman/agent-driven-options-desk-and-skills`.

That gives you the five skills, six commands (`/desk-open`, `/desk-risk`,
`/desk-test`, `/desk-mark`, plus `/desk-watch` and `/desk-complete` which
are shaped for loops), two agents (an adversarial risk reviewer and a data
auditor) and the MCP server declaration, in one step.

The plugin's MCP entry names the bare command `optiondesk-mcp`, so it
resolves through your PATH. `install.sh` creates that binary in
`~/.local/bin`, but it does not edit your shell profile: if that
directory is not already on PATH it warns and leaves it to you. A plugin
install on its own creates no binary at all, since nothing in the plugin
runs the installer. The skills, commands and agents work regardless;
only the tools need the binary.

The plugin directory is generated. Edit `shell/skills`, `.claude/commands`
or `.claude/agents`, then run `python3 scripts/refresh.py` to rebuild it
along with everything else generated, or `python3 scripts/package.py` for
the installable forms alone.

## 4. In Codex or ChatGPT, as a plugin

```
codex plugin marketplace add Iman/agent-driven-options-desk-and-skills
codex plugin add option-desk@option-desk
```

Both verified against codex-cli 0.149.1 on a real install, not read off a
documentation page: the first registers the marketplace, `codex plugin
list` then shows `option-desk@option-desk`, and the second installs it into
`~/.codex/plugins/cache/`. An earlier draft of this file claimed there was
no `codex plugin add` command, on the strength of a docs page that does not
mention it. The binary has it, and the binary is the authority.

The bundle carries two manifests over one set of files. Codex and ChatGPT
read `.codex-plugin/plugin.json`, Claude Code reads
`.claude-plugin/plugin.json`, and both point at the same five skills. The
six commands and two agents in it are Claude-only, so what Codex gets from
this path is the five skills plus the MCP server declaration.

Codex also finds the skills with no plugin at all, because it scans
`.agents/skills` in a repository and `~/.agents/skills` for your user. This
repository symlinks the former to `shell/skills`, so cloning it is enough,
and option 2 above installs to the latter.

### What ChatGPT on the web cannot do

The MCP server here is a local stdio process. Codex on your machine can run
it. ChatGPT in a browser or on a phone cannot: it has no way to execute a
binary on your computer. Reaching that would need a hosted Streamable HTTP
MCP service with authentication and per-user credentials, which does not
exist here and is not planned in this repository.

So in browser ChatGPT the five skills work as knowledge and instructions,
the same as options 2 and 6, and they say so themselves: each one now
carries an execution route telling the agent to prefer the MCP tool, fall
back to the command line, and if neither is available to state plainly that
no fresh figures can be produced rather than inventing them.

## 5. From a checkout, by hand

```
python -m venv .venv && . .venv/bin/activate
pip install -e "shell[yahoo,dev]" -e engine
optiondesk doctor
```

Add `-e agent` for the LangChain bindings, which are optional and pull in
`langchain-core`.

## 6. Skills only, no Python

```
./install.sh --skills-only
```

Or copy them yourself: the skills are plain directories of markdown under
`shell/skills`, and they work in `~/.claude/skills` (personal) or a
project's `.claude/skills`.

An agent with the skills but not the tools can explain the desk, the
conventions and the reporting rules. It cannot run anything, because the
commands the skills describe are not there. Using them as domain knowledge
without the automation is a legitimate choice.

## 7. claude.ai, in the browser

Upload the zips from `dist/skills/`:

```
python3 scripts/package.py     # builds them
```

Then in claude.ai, Settings, Capabilities, Skills, upload a zip. There is
one per skill, plus `dist/option-desk-skills.zip` with all five.

Two things to know before you do. Custom skills on claude.ai are per user:
each person on a team uploads their own, and an admin cannot distribute
them centrally. And the runtime there has no access to your machine, so the
skills work as knowledge and instructions rather than as tools, the same
as options 2 and 6.

## 8. MCP only, without skills

If you want the tools in a runtime and nothing else:

```
claude mcp add optiondesk -- /abs/path/to/.venv/bin/optiondesk-mcp
codex  mcp add optiondesk -- /abs/path/to/.venv/bin/optiondesk-mcp
gemini mcp add -s user optiondesk /abs/path/to/.venv/bin/optiondesk-mcp
```

Ten tools, typed schemas, no prose. This is the right choice when the
runtime already has its own conventions and you want capability, not
guidance.

---

## Verifying an install

```
optiondesk doctor
```

Reports the shell version, whether the AGPL engine is present, which
providers can answer, which optional keys are configured (never their
values), and where artifacts are written.

Then the shortest useful run:

```
optiondesk chain SPY
optiondesk greeks --band 0.06
optiondesk dashboard
```

## Provider keys

Optional. Everything works with none: chains, Greeks, positioning,
structures, simulation and backtests all run on free sources.

```
optiondesk keys list                 # what is needed, what is set, masked
optiondesk keys set alphavantage     # prompts with hidden input
optiondesk keys unset alphavantage   # remove one
optiondesk keys path                 # where they are stored
```

Keys live in `~/.optiondesk/config.env`, outside any repository, readable
only by you. Resolution order is a command line flag, then the
environment, then `.env` in the working directory, then that file. They are
never printed in full, never logged, and never written into an artifact.

## Uninstalling

```
./install.sh --uninstall
```

Removes the virtualenv and source it created, the two symlinks if they
still point into that virtualenv, the skills it marked as its own, and the
MCP registrations under its own server name. It leaves your artifacts, any
skill it did not install, and any binary it did not create.

For the plugin: `/plugin uninstall option-desk@option-desk`.

## Requirements

Python 3.11 or newer. Everything else is optional: `yfinance` for the free
data provider, `fastapi` and `uvicorn` for the richer dashboard server
(there is a standard library fallback), `jsonschema` for full schema
validation (there is a built-in subset validator), `langchain-core` only if
you want the agent bindings.

The engine itself has no dependencies outside the standard library and no
network access at all.
