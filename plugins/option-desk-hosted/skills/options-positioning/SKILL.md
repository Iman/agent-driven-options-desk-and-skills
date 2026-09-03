---
name: options-positioning
description: "Analyze dealer-gamma assumptions, gamma walls, gamma flip, max pain, open interest, volume, and volatility geometry from SYNTH or a permitted user option-chain snapshot."
---

# Option positioning

Use the hosted Option Desk MCP. Do not run a local command or fetch market data.

For `SYNTH`, call `option_positioning` for figures or `option_plots` for images. State that all figures and dealer signs are synthetic.

For a market ticker, require a user-supplied CSV or JSON chain. Require the source name and confirmation that the user may send it. Validate unclear files before analysis. Call `option_positioning` for the summary and `option_plots_from_snapshot` for images.

Dealer positions are not observed. Explain the assumed sign convention. Do not claim that a wall, gamma flip, or max-pain level predicts price. Never describe user data as live or verified. Do not recommend trades or orders.
