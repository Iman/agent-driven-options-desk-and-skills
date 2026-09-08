# Architecture and artifacts

[Guide home](Home.md) | [API inventory](../INVENTORY.md) | [Development](Development.md) | [Master algorithm](Algorithm.md)

## Detailed reference and preserved content

The earlier long-form documentation remains available here in full:

| Preserved page | Includes |
|---|---|
| [Project reference](Reference-README.md) | Original architecture, seven diagrams, mathematics, providers, asset classes, extension points, audit findings, screenshots, examples, and licensing discussion. |
| [Earlier FAQ](Reference-FAQ.md) | Original questions, explanations, measurements, and research caveats. |
| [Earlier installation guide](Reference-INSTALL.md) | Previous setup routes and their recorded verification notes. |

These pages preserve revision `9626273`, immediately before the guide rewrite.
They retain historical claims as historical material. Use [skill installation](Skill-Installation.md) for current setup steps.
The [preservation manifest](../reference-preservation.json) records source hashes and diagram counts.

Read the original [design rationale](Reference-README.md#architecture), [data flow](Reference-README.md#how-data-flows),
[artifact contracts](Reference-README.md#artifacts-and-contracts), [extension guide](Reference-README.md#extending-it),
and [engineering verification notes](Reference-README.md#what-has-been-verified).

## Calculation path

```mermaid
flowchart LR
    file["Permitted snapshot"] --> cli["CLI commands"]
    provider["Enabled provider"] --> cli
    agent["Agent with skills"] --> mcp["Local MCP server"]
    mcp --> cli
    cli --> bridge["Engine adapter"]
    bridge --> engine["Analytics engine"]
    engine --> cli
    cli --> artifacts["Validated JSON artifacts"]
    artifacts --> dashboard["Local dashboard"]
    artifacts --> reader["Agent or other reader"]
```

## Packages

| Package | Responsibility | Source |
|---|---|---|
| Engine | Pricing, Greeks, strategies, exposure, simulation, and backtest mathematics | `engine/src/optiondesk_engine/` |
| Shell | Providers, import, commands, validation, files, plots, MCP, and dashboard | `shell/src/optiondesk/` |
| Optional agent package | LangChain bindings and a bounded LangGraph workflow | `agent/src/optiondesk_agent/` |

The shell reaches the engine through `engine_bridge.py`.
All packages use the repository license.
The hosted service is a separate deployment with its own connection and data policy.

## Artifact flow

```mermaid
flowchart TD
    snapshot["Chain snapshot"] --> greeks["Greek ladder"]
    snapshot --> exposure["Positioning"]
    snapshot --> plan["Strategy plans"]
    far["Far-expiry snapshot"] --> plan
    plan --> comparison["Comparison"]
    plan --> ledger["Paper ledger"]
    later["Later snapshot"] --> ledger
    history["Underlying price history"] --> simulation["Simulation"]
    history --> backtest["Backtest"]
    plan --> simulation
```

Simulation and backtests require price history.
A chain snapshot does not replace that input.

## Contracts

| Schema | Filename pattern | Contents |
|---|---|---|
| `chain_snapshot` | `chain_*.json` | Contracts, quotes, IV sources, and input provenance. |
| `greeks_ladder` | `greeks_*.json` | Sensitivities, units, and skip counts. |
| `exposure` | `exposure_*.json` | Gamma exposure, walls, flip, ratios, and smile. |
| `strategy_plan` | `strategy_*.json` | Legs, payoff, probabilities, Greeks, and friction. |
| `strategy_comparison` | `comparison_*.json` | Ranked plans and comparison assumptions. |
| `simulation` | `simulation_*.json` | Posterior, diagnostics, fan, and tail risk. |
| `backtest` | `backtest_*.json` | Trades, statistics, uncertainty, and benchmark. |
| `forward_ledger` | `forward_ledger.json` | Paper positions, marks, and settlements. |

The `meta` block records generation time, tool, versions, source, quality flags, notes, and policy statements.
Each producer validates its artifact before writing it.
The dashboard reads those artifacts.

## File locations and replacement

The normal artifact directory is `~/TradingDesk/option-desk`.
`--out-dir` selects another directory for a command.
`OPTIONDESK_ARTIFACTS` selects the default directory for a process.
The demo runner uses `~/TradingDesk/option-desk-demo` unless configured otherwise.

When a named artifact changes, the outgoing version moves under `archive/<date>/`.
The current filename remains stable for readers.
`OPTIONDESK_ARCHIVE=0` disables that archival behavior.
The project does not prune your archive automatically.

## Sources of documentation

Local skills live in `shell/skills/`.
The generated runtime files and plugin copies come from those sources.
Claude command and reviewer sources live in `.claude/commands/` and `.claude/agents/`.
Hosted skills live in `openai-skills/`.

Use the [capabilities catalogue](../CAPABILITIES.md) for interfaces and the [generated inventory](../INVENTORY.md) for source symbols.
Use [Loops](../../LOOPS.md) for the bounded graph and recurring workflows.

## Current design diagrams

These diagrams describe the source reviewed at revision `79e8d7f`.
The [PlantUML gallery](../diagrams/README.md) provides editable sources, SVGs, and PNGs.
The [preserved project reference](Reference-README.md) retains the earlier Mermaid diagrams and recorded measurements.
Original PlantUML editions remain accessible through the gallery's revision link.

### Packages and runtime boundaries

```mermaid
flowchart TB
    clients["Local agents and terminal users"] --> mcp["Local stdio MCP: 12 tools"]
    clients --> cli["CLI command handlers"]
    optional["Optional LangChain / LangGraph package"] --> cli
    mcp --> cli
    cli --> inputs["Permitted imports / enabled providers"]
    cli --> bridge["engine_bridge: sole shell-to-engine import"]
    bridge --> engine["Engine: pricing, 16 Greeks, 23 structures,<br/>exposure, simulation, backtests"]
    cli --> validation["8 artifact schemas"]
    cli --> writer["Archive and atomic artifact writer"]
    writer --> disk["Local JSON artifacts"]
    disk --> dashboard["Local dashboard and readers"]
    browser["Browser clients"] --> hosted["Remote MCP: separate deployment"]
    hosted --> subset["Documented hosted subset:<br/>SYNTH sample or permitted uploaded chain"]
```

The hosted implementation is outside this repository.
Its skill and plugin bundles are in this repository.
A browser skill upload and an MCP connection are separate setup steps.

### Artifacts between commands

```mermaid
flowchart LR
    input["Permitted import or enabled provider"] --> chain["Chain snapshot"]
    chain --> greeks["Greek ladder"]
    chain --> exposure["Positioning"]
    chain --> strategy["Strategy plans"]
    far["Far-expiry snapshot"] --> strategy
    strategy --> compare["Comparison"]
    strategy --> forward["Paper ledger"]
    later["Later chain"] --> forward
    strategy --> sim["Simulation and structure outcomes"]
    history["Underlying history"] --> sim
    history --> bt["Backtest"]
    greeks --> dash["Dashboard"]
    exposure --> dash
    compare --> dash
    sim --> dash
    bt --> dash
    forward --> dash
```

### One MCP request from agent to disk

```mermaid
sequenceDiagram
    participant A as Agent
    participant M as Local MCP
    participant C as Chain command
    participant P as Snapshot parser
    participant D as Artifact directory
    A->>M: Snapshot text/data and rights acknowledgement
    M->>C: Validated tool arguments
    C->>P: Parse and normalize supplied snapshot
    alt Missing rights, source, spot or invalid fields
        P-->>C: Validation error
        C-->>M: Failure
        M-->>A: Tool error, prior artifact preserved
    else Valid permitted input
        P-->>C: Normalized snapshot with provenance
        C->>C: Validate chain_snapshot schema
        C->>D: Archive previous file, atomic replacement
        C-->>M: Summary and quality flags
        M-->>A: Structured result
    end
```

This sequence describes the import route without historical market counts.
Imported IV remains user-supplied. The provider route has separate access checks and IV provenance.

### Structure outlook map

```mermaid
flowchart TB
    registry["PLAYBOOK: 23 structures"] --> direction["Five directional outlook tags: -2 through +2"]
    registry --> volatility["Volatility view: crush, expand, any"]
    registry --> ownership["Underlying ownership requirement"]
    direction --> filter["Filter and score candidates against stated inputs"]
    volatility --> filter
    ownership --> filter
    filter --> build["Build from available contracts"]
    build --> check["Payoff, missing inputs, friction and rankability"]
    check --> output["Research comparison with assumptions"]
```

The [complete outlook diagram](../diagrams/04_structures_by_outlook.svg) shows every registered membership.
A structure can have several outlook tags. These tags do not establish a forecast or a recommendation.

### Skills and generated runtime instructions

```mermaid
flowchart TB
    local["shell/skills: 6 local skills"] --> gen["gen_runtime_docs.py"]
    parsers["CLI argparse parsers"] --> gen
    gen --> agents["AGENTS.md"]
    gen --> gemini["GEMINI.md"]
    local --> claude["Claude Code skill discovery"]
    local --> package["scripts/package.py"]
    hosted["openai-skills: 4 hosted skills"] --> package
    package --> lp["Local plugin bundle"]
    package --> hp["Hosted plugin bundle"]
    gen --> tests["Generated-file and packaging checks"]
    package --> tests
```

### Provider resolution

```mermaid
flowchart LR
    need["Requested capability / explicit provider"] --> reg["Registry"]
    reg --> single["Chains, rates, dividends: Yahoo"]
    reg --> fallback["History, quotes: Yahoo then Alpha Vantage"]
    single --> gate["Access mode, rights, key and dependency checks"]
    fallback --> gate
    gate -->|"available"| chosen["Chosen provider and skipped reasons"]
    gate -->|"none permitted"| error["ProviderUnavailable"]
    upload["Permitted uploaded snapshot"] --> parse["Import validation without provider resolution"]
```

Demo mode refuses external providers. Yahoo requires local-use acknowledgement.
An explicit provider is strict by default. Its failure does not silently select a substitute.
Alpha Vantage supplies history and quotes, not option chains.

### License boundaries

```mermaid
flowchart LR
    nc["Permitted noncommercial uses<br/>subject to the full licence"] --> work["Option Desk source<br/>PolyForm Noncommercial 1.0.0"]
    commercial["Commercial use<br/>separate written agreement"] --> work
    third["Third-party components<br/>their own terms"] -.-> work
    data["Market data<br/>separate provider and user rights"] -.-> work
```

[LICENSE](../../LICENSE) is the controlling text.
[LICENSES.md](../../LICENSES.md), [THIRD-PARTY.md](../../THIRD-PARTY.md), and [DISCLAIMER.md](../../DISCLAIMER.md) explain the separate boundaries.

## Hosted and local access

![Local and hosted connection boundaries](../diagrams/08_hosted_boundary.png)

## Test layers and coverage

![Unit, BDD, integration and validation layers](../diagrams/09_testing_layers.png)

The [testing guide](../TESTING.md) gives the commands and defines the 80% per-package unit line-coverage gate.

## Bounded agent workflow

![Bounded LangGraph workflow](../diagrams/10_bounded_workflow.png)

Planning and calculation nodes are deterministic. A supplied model can write the final summary.
Completion means the required artifacts exist. It does not establish that a trading thesis is correct.

## Research loops and prompts

![Watch and completion loops](../diagrams/11_research_loops.png)

The loop commands contain instructions for a host agent. They are distinct from the Python graph's artifact-completion checks.

![Prompt assembly and model boundary](../diagrams/12_prompt_assembly.png)

Prompt rules constrain the requested answer. The repository does not prove that every model will follow them.

## Backtest and forward test

![Historical backtest workflow](../diagrams/13_backtest_workflow.png)

![Forward paper-test lifecycle](../diagrams/14_forward_paper_lifecycle.png)

Backtests use model premiums and historical underlying moves.
Forward tests record entry plans and later paper marks.
The close command uses intrinsic settlement and does not enforce expiry or snapshot freshness.
Check the date and price before interpreting a settlement. See the [paper workflow](Examples.md#open-and-mark-a-paper-position).
