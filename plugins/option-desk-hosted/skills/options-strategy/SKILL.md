---
name: options-strategy
description: "Build and plot an option structure from SYNTH or a permitted user-supplied option-chain snapshot. Use for iron condors, butterflies, spreads, breakevens, maximum gain or loss, quoted-spread friction, or payoff plots."
---

# Option strategy

Use the hosted Option Desk MCP. Do not run a local command or fetch market data.

For a synthetic example, call `option_strategy_plot` with `symbol="SYNTH"`. State that the result is a sample and not a market quote.

For a ticker such as SPY, require an attached CSV or JSON option chain. The user must name its source and confirm that they may send it. Validate unclear files before analysis. Call `option_strategy_from_snapshot` so the payoff PNG appears in the conversation.

Report the selected legs, assumptions, breakevens, maximum gain and loss when available, and quoted-spread limitations. Keep the source, capture time, expiry, private-research label, and no-trading warning visible.

For a report with diagnostics and several payoffs, call `option_report_plots` once with up to three distinct strategies. Do not split the report into parallel plot calls. If that tool is unavailable, report that the connection needs a tool refresh.

Use `strategy_records` for tables and expiration scenarios. These are the engine records used for the charts. Do not reconstruct legs from images. Use the returned units: no currency or contract multiplier is implied. Report `vega_per_vol_point` for a one-percentage-point IV change. Keep the patient-fill friction model separate from `natural_entry_cost`, which estimates full bid/ask crossing. Never claim that a successful tool call proves the images rendered.

Do not select a trade for the user. Do not recommend entry, exit, order, or position size. Option Desk cannot place or route orders.
