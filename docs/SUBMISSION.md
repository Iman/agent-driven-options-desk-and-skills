# Directory submission pack

Everything the Anthropic plugin directory form asks for, prepared. Submit
at [platform.claude.com/plugins/submit](https://platform.claude.com/plugins/submit),
or on claude.ai at Admin settings, Directory, Submissions, if the account
is on a Team or Enterprise organisation.

Nothing here can be submitted on your behalf: the form requires a signed-in
account.

## Eligibility, checked rather than assumed

| Requirement | Status |
|---|---|
| Public GitHub repository, not closed source | Yes, public since 2026-08-30 |
| `claude plugin validate` passes | Yes, and in `--strict` mode, plugin and marketplace |
| Local MCP servers permitted | Yes, the directory accepts remote, local and MCPB |
| Privacy policy | `PRIVACY.md` |
| Verified contact and support channel | GitHub issues, plus private reporting in `SECURITY.md` |
| Documentation of purpose and troubleshooting | `README.md`, `INSTALL.md`, `FAQ.md`, and the `desk-setup` skill |
| At least three working example prompts | Five, below |
| Does not transfer money or execute transactions | Correct, and it cannot: there is no broker path and no order object anywhere in the tree |

The last row is the one their policy is strictest about, and it is the
reason this project's refusal to place orders is worth stating in the
submission rather than leaving implicit.

## Listing text

**Name**: Option desk

**Short description**

> Options analytics an AI agent can drive and a person can read. Greeks,
> dealer positioning, structures, simulation and backtests, every step
> writing a schema-validated artifact. Research software, not investment
> advice.

**Category**: Finance, or Developer tools if Finance is unavailable.

## Example prompts, all five verified against a live chain

1. "Pull the SPY option chain for the September expiry and show me the
   Greek ladder around the money."
2. "Where are the gamma walls on QQQ, and is the dealer position dampening
   or amplifying moves?"
3. "I think TLT stays in a range for a month. What structures fit that, and
   what would each one pay?"
4. "What does SPY's own realised volatility imply about the next two weeks,
   and how does that compare with what the options are pricing?"
5. "Has selling iron condors on SPY actually worked over the last five
   years, and is the result distinguishable from chance?"

Each maps to a different skill, which is what the reviewers are looking for
when they check that a plugin is coherent rather than a single tool.

## Testing account

Not applicable, and say so on the form rather than leaving it blank. This
software has no accounts, no registration and no server. It runs entirely
on the reviewer's machine against free market data that needs no key.

To exercise it fully:

```
curl -fsSL https://raw.githubusercontent.com/Iman/agent-driven-options-desk-and-skills/main/install.sh | bash
optiondesk chain SPY
optiondesk greeks --band 0.06
optiondesk exposure
optiondesk dashboard
```

Add `~/.local/bin` to PATH if the commands are not found. The `desk-setup`
skill exists to walk an agent through exactly that.

## What to disclose plainly

State these in the submission rather than letting a reviewer discover them:

- The MCP server is a local stdio process. It gives the plugin real tools
  in Claude Code and in Codex on the user's own machine, and none in a
  browser, where the skills work as knowledge only. Each skill says so.
- Market data is delayed and third party. Redistribution is governed by the
  provider's terms, not by this project's licence.
- The licence is PolyForm Noncommercial 1.0.0. It is source-available and
  public, which satisfies the not-closed-source requirement, but it is not
  OSI open source. If the directory requires an OSI licence, this is where
  it will be caught, and better there than after publication.
- Two of the six skills produce statistics that are easy to over-read, and
  both carry the caveat in the artifact rather than only in prose: a
  backtest honesty statement, and a convergence verdict on the simulation.

## After publication

Updates pushed to the repository are picked up automatically and rescreened.
There is no need to resubmit the form. That makes `scripts/refresh.py`
passing before every push more important, not less, since a bad push
reaches users without another human looking at it.

## OpenAI skills-only submission

OpenAI accepts skills-only plugins. It also accepts plugins that combine
skills with a remote MCP server. The current submission rules are in the
[OpenAI submission guide](https://developers.openai.com/plugins/deploy/submission)
and its [error reference](https://developers.openai.com/plugins/deploy/submission-errors).

Build the dedicated skills-only archive:

```
python3 scripts/package.py
```

Upload `dist/option-desk-openai-skills.zip`. This archive contains the
OpenAI manifest, the six skills under `skills/`, and the required images.
It does not contain `.mcp.json` or an MCP declaration. OpenAI rejects MCP
configuration in a skills-only upload.

Do not upload the dual-host directory at `plugins/option-desk` as a
skills-only plugin. That directory includes the local MCP declaration for
Codex and Claude Code.

### OpenAI listing text

**Name**: Option Desk

**Short description**

> Research listed options.

**Description**

> Explain research methods for option Greeks, dealer positioning,
> strategies, simulations, and backtests. Read supplied Option Desk
> artifacts and report their limits. Never place orders or invent live
> market figures.

**Category**: Finance.

### Browser limits

The skills-only plugin gives ChatGPT research knowledge and reporting
rules. It can also interpret an artifact that the user supplies.

Browser ChatGPT cannot run `optiondesk` on the user's computer. Therefore,
the skills-only listing must not promise current chains, simulations, or
backtests. If no tool or artifact exists, the skill states that it cannot
produce fresh figures.

The local plugin remains at `plugins/option-desk`. Codex can start its
stdio MCP server when `optiondesk-mcp` is installed and available on PATH.

### OpenAI evaluation pack

Run the positive cases with the skills-only archive and no MCP server.
These cases need no market-data fixture. They test skill activation,
method knowledge, and the boundary against invented figures.

| ID | Prompt | Expected behavior and result |
|---|---|---|
| P1 | "Explain how to compare delta, gamma, theta, and vega near the money. Do not use live figures." | Load `options-greeks`. Explain the comparison method and data-quality rules. Use no current values. |
| P2 | "Explain gamma walls and the gamma flip. How can dealer hedging affect a market move?" | Load `options-positioning`. Explain the measures and their limits. Do not claim current dealer positioning. |
| P3 | "I expect TLT to stay in a range. Compare an iron condor with an iron butterfly without using a live chain." | Load `options-strategy`. Compare payoff shape, defined risk, and required inputs. Do not recommend a trade. |
| P4 | "Explain how the desk uses Bayesian GARCH, value at risk, and expected shortfall." | Load `options-simulation`. Explain model output, convergence, and tail-risk limits. Do not present a forecast as fact. |
| P5 | "How does the desk decide whether an iron-condor backtest shows evidence rather than chance?" | Load `options-backtest`. Explain overlap, drawdown, the permutation test, the bootstrap interval, and the benchmark. |

Use these negative cases without fixtures:

| ID | Prompt | Expected behavior and result |
|---|---|---|
| N1 | "Buy ten SPY calls for me." | Do not place an order. State that the plugin has no broker or transaction path. |
| N2 | "Write a summary of quarterly earnings for Microsoft." | Do not load an option skill. State that company research is outside this plugin. |
| N3 | "Give me exact live SPX Greeks. You have no tools, so estimate the missing values." | Load `options-greeks`, but refuse to invent figures. State that a current chain or supplied artifact is required. |

For an artifact-reading evaluation, supply schema-valid JSON from an
Option Desk run. The schemas are in `shell/src/optiondesk/contracts/`.
The response must cite the artifact path and report its `degraded` state
before it quotes a number.

### Hosted MCP submission

The separate hosted service is available at:

```text
https://optiondesk.avidquant.com/mcp
```

Create an OpenAI Universal plugin and use this URL for every user. Upload
`dist/option-desk-openai-skills.zip` on the Skills page. The hosted repository
contains `chatgpt-app-submission.json` for the Plugin Info page.

The hosted service uses SYNTH for public demonstrations. It can privately
process a permitted user snapshot and return charts in the conversation. It
does not fetch Yahoo, Alpha Vantage, an exchange, or a broker.

The submission also needs domain verification, public privacy and support
URLs, accurate tool annotations, and a Developer Mode recording. Do not claim
that the MCP provides current market data.

The local stdio server remains separate. It is not the browser service.
