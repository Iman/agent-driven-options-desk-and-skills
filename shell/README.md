# optiondesk

The Option Desk shell: option chain retrieval, schema-validated artifacts, a
command line, a local MCP server and a local dashboard. The pricing and
analytics live in [optiondesk-engine](https://pypi.org/project/optiondesk-engine/).
LangChain bindings are in [optiondesk-agent](https://pypi.org/project/optiondesk-agent/).

## Install

```sh
pip install "optiondesk[engine]"
```

Without the `engine` extra the shell installs, but it cannot compute Greeks,
strategies, simulations or backtests. `optiondesk doctor` reports this.
Two more extras are available:

- `yahoo` adds the Yahoo Finance chain provider (`yfinance`).
- `dashboard` adds the local dashboard server (`fastapi`, `uvicorn`).

## Commands

`optiondesk` has these subcommands: `chain`, `greeks`, `strategy`,
`exposure`, `plots`, `expiries`, `compare`, `simulate`, `backtest`,
`forward`, `keys`, `doctor` and `dashboard`. Run `optiondesk <command> --help`
for the options of each one.

`optiondesk-mcp` starts the MCP server over stdio. It serves 12 tools:
`option_snapshot_schema`, `option_chain_snapshot`, `option_greeks_ladder`,
`option_positioning`, `option_expiries`, `option_strategy_build`,
`option_strategy_compare`, `option_simulate`, `option_backtest`,
`option_forward_test`, `option_plots` and `option_desk_status`.

## Data

The desk uses data that you are permitted to use: a supported provider, or
an option chain snapshot that you supply. It does not invent a missing
market value.

## Project

Source, plugin, skills and documentation:
https://github.com/Iman/agent-driven-options-desk-and-skills

Licensed under the PolyForm Noncommercial License 1.0.0. Commercial use
needs a separate written agreement with the copyright holder.

This is research software. Its output is not investment advice.
