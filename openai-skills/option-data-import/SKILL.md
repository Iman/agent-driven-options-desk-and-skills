---
name: option-data-import
description: "Validate, normalize, import, or delete an option-chain snapshot that the user is permitted to send. Use when a user attaches CSV or JSON data, asks how to format it, wants errors repaired, wants a private dashboard, or asks to delete that dashboard."
---

# Option data import

Use the hosted Option Desk MCP. Do not run a local command.

## Safety boundary

- Never fetch market data.
- Never ask for credentials, API keys, account numbers, positions, or names.
- Do not process an upload until the user confirms that they may send it.
- A user confirmation does not override the source provider's terms.
- The hosted service blocks Yahoo, yfinance, and personal Alpha Vantage data.
- Never invent a strike, quote, volatility, open-interest value, expiry, source, or rights statement.

## Workflow

1. If the format is unclear, call `option_snapshot_schema`.
2. Ask for the data source and rights confirmation if either is missing.
3. Call `option_validate_snapshot` before analysis.
4. Report each validation problem and the permitted repair. Ask for corrected data when a required value is missing.
5. Call `option_import_snapshot` only after the user also accepts storage for up to one hour.
6. Tell the user that the private dashboard URL is a bearer secret.
7. Use `option_delete_snapshot` when the user asks for early deletion.

For analysis that does not need a dashboard, use a plot or strategy tool. Those tools remove their temporary files before they respond.
