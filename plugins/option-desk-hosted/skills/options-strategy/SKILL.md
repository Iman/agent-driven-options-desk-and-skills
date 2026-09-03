---
name: options-strategy
description: "Build and plot an option structure from SYNTH or a permitted user-supplied option-chain snapshot. Use for iron condors, butterflies, spreads, breakevens, maximum gain or loss, quoted-spread friction, or payoff plots."
---

# Option strategy

Use the hosted Option Desk MCP. Do not run a local command or fetch market data.

For a synthetic example, call `option_strategy_plot` with `symbol="SYNTH"`. State that the result is a sample and not a market quote.

For a ticker such as SPY, require an attached CSV or JSON option chain. The user must name its source and confirm that they may send it. Validate unclear files before analysis. Call `option_strategy_from_snapshot` so the payoff PNG appears in the conversation.

Report the selected legs, assumptions, breakevens, maximum gain and loss when available, and quoted-spread limitations. Keep the source, capture time, expiry, private-research label, and no-trading warning visible.

Do not select a trade for the user. Do not recommend entry, exit, order, or position size. Option Desk cannot place or route orders.
