---
name: options-greeks
description: "Calculate and plot option Greeks from the SYNTH sample or a permitted user-supplied option-chain snapshot. Use for delta, gamma, vega, theta, vanna, charm, Greek ladders, or Greek plots."
---

# Option Greeks

Use the hosted Option Desk MCP. Do not run a local command or fetch market data.

For `SYNTH`, call `option_plots` with `plot="greeks"`. State that the figures are synthetic sample data.

For a ticker such as SPY, require an attached CSV or JSON option chain. The user must name its source and confirm that they may send it. If the file needs correction, call `option_snapshot_schema` and `option_validate_snapshot`. Use `option_plots_from_snapshot` for charts.

Never ask for credentials, API keys, account numbers, or portfolio positions. Never describe user data as live or verified. Keep the source, capture time, expiry, private-research label, and no-trading warning visible.

Explain model inputs and limitations. Do not recommend a contract, entry, exit, order, or position size.
