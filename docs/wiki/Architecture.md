# Architecture and artifacts

[Guide home](Home.md) | [API inventory](../INVENTORY.md) | [Development](Development.md)

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

## Restored design diagrams

The seven diagrams below come from that preserved README edition.
The package diagram uses lighter backgrounds for readable labels. The archive retains its original styling.
They are reference diagrams, not fresh test or market measurements.
The request sequence uses the recorded August 30, 2026 sample counts.
The provider drawing is schematic: Alpha Vantage supplies history and quotes, not option chains.

### Packages and runtime boundaries

```mermaid
flowchart TB
    subgraph clients["Ways in"]
        claude["Claude Code<br/>reads SKILL.md"]
        codex["Codex<br/>reads .agents/skills"]
        gemini["Gemini CLI<br/>reads GEMINI.md"]
        human["A person<br/>types commands"]
    end

    mcp["MCP server<br/>stdio, standard library only<br/>12 tools"]
    cli["CLI<br/>optiondesk chain, greeks, exposure, plots,<br/>strategy, compare, simulate,<br/>backtest, forward"]

    subgraph shell["shell"]
        providers["Provider registry<br/>resolve by capability,<br/>not by vendor"]
        contracts["JSON contracts<br/>8 schemas + validator"]
        artifacts["Artifact writer<br/>atomic, provenance,<br/>degraded and notes"]
        bridge["engine_bridge<br/>THE ONLY IMPORT<br/>OF THE ENGINE"]
    end

    subgraph engine["engine &nbsp;(the numbers)"]
        pricing["pricing<br/>Black-Scholes-Merton,<br/>16 Greeks, implied vol"]
        strategies["strategies<br/>payoff, playbook,<br/>outlook, friction"]
        analytics["analytics<br/>gamma exposure, walls,<br/>max pain, smile, ranking"]
        simulation["simulation<br/>GARCH-t by MCMC,<br/>paths, VaR and ES"]
        backtest["backtest<br/>runner, statistics,<br/>forward marking"]
    end

    yahoo[("Yahoo<br/>free, delayed")]
    disk[("Artifact directory<br/>~/TradingDesk/option-desk")]
    dash["Dashboard<br/>FastAPI or stdlib,<br/>ECharts vendored"]

    claude --> mcp
    codex --> mcp
    gemini --> mcp
    human --> cli
    mcp --> cli
    cli --> providers
    cli --> bridge
    providers --> yahoo
    bridge --> pricing
    bridge --> strategies
    bridge --> analytics
    bridge --> simulation
    bridge --> backtest
    cli --> contracts
    contracts --> artifacts
    artifacts --> disk
    disk --> dash

    style engine fill:#f4edff,stroke:#7c3aed,color:#1f2328
    style shell fill:#eaf2ff,stroke:#2f6feb,color:#1f2328
    style bridge fill:#fff4e5,stroke:#b45309,color:#1f2328
```

### Artifacts between commands

```mermaid
flowchart LR
    provider[("Provider")] -->|quotes| chain["chain<br/><i>chain_SYM_EXPIRY.json</i>"]
    provider -->|daily closes| sim["simulate<br/><i>simulation_SYM_Nd.json</i>"]
    provider -->|daily closes| bt["backtest<br/><i>backtest_SYM_STRAT.json</i>"]

    chain --> greeks["greeks<br/><i>greeks_SYM_EXPIRY.json</i>"]
    chain --> exposure["exposure<br/><i>exposure_SYM_EXPIRY.json</i>"]
    chain --> strategy["strategy<br/><i>strategy_SYM_NAME_EXPIRY.json</i>"]
    strategy --> compare["compare<br/><i>comparison_SYM_EXPIRY.json</i>"]
    strategy --> forward["forward<br/><i>forward_ledger.json</i>"]
    chain --> forward
    strategy --> sim

    greeks --> dash["dashboard"]
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
    participant M as MCP server
    participant C as CLI command
    participant P as Provider
    participant E as Engine
    participant D as Disk

    A->>M: tools/call option_chain_snapshot {symbol: SPY}
    M->>C: chain.run(args)
    C->>P: resolve(option_chain) then fetch
    P-->>C: 607 contracts, spot, listed expiries
    C->>E: implied_vol per contract (via bridge)
    E-->>C: 595 solved, 12 refused as unidentified
    C->>C: validate against chain_snapshot schema
    C->>D: atomic write, tmp then replace
    C-->>M: {artifact, contracts, with_iv, degraded, notes}
    M-->>A: JSON summary
```

### Structure outlook map

```mermaid
flowchart LR
    sb["-2<br/>strong bearish"] --- mb["-1<br/>mild bearish"] --- n["0<br/>neutral"] --- mu["+1<br/>mild bullish"] --- su["+2<br/>strong bullish"]

    sb -.-> lp["long put<br/>protective put"]
    mb -.-> bps["bear put spread"]
    n -.-> ic["iron condor<br/>iron butterfly<br/>butterfly<br/>cash-secured put"]
    mu -.-> bcs["bull call spread<br/>covered call"]
    su -.-> lc["long call<br/>straddle, strangle"]
```

### Skills and generated runtime instructions

```mermaid
flowchart TB
    skill["shell/skills/*/SKILL.md<br/>one source of truth"]
    gen["shell/tools/gen_runtime_docs.py"]
    agents["AGENTS.md<br/>rules and commands<br/>for Codex"]
    gemini["GEMINI.md<br/>for Gemini CLI"]
    claude["Claude Code reads<br/>SKILL.md directly"]
    mcpserver["optiondesk-mcp<br/>typed tool schemas"]

    skill --> gen
    gen --> agents
    gen --> gemini
    skill --> claude
    skill -. "same capabilities" .-> mcpserver
    mcpserver --> claude
    mcpserver --> agents
    mcpserver --> gemini
```

### Provider resolution

```mermaid
flowchart LR
    need["A command needs<br/>option_chain"] --> reg{"Registry<br/>priority order"}
    reg -->|"key present"| paid["Alpha Vantage<br/>key required, history and quotes"]
    reg -->|"local acknowledgement"| yahoo["Yahoo<br/>local personal research<br/>delayed"]
    reg -->|"nothing can answer"| err["ProviderUnavailable<br/>naming every candidate<br/>and why each was skipped"]
    paid --> art["artifact records<br/>provider_used"]
    yahoo --> art
```

### License boundaries

```mermaid
flowchart LR
    free["Noncommercial use<br/>study, research, hobby,<br/>charities, schools, government"]
    work["option desk<br/>engine, shell, agent, skills"]
    paid["Commercial use<br/>funds, products, paid research,<br/>fundraising on the back of it"]

    free -->|"no permission needed"| work
    paid -.->|"written agreement first"| work
```
