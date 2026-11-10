# option-desk-hosted plugin

It declares one remote MCP server, `https://optiondesk.avidquant.com/mcp`, and carries the four skills that match it. The service serves the SYNTH sample and privately processes option-chain snapshots the user is permitted to send; it fetches no market data and places no orders. Its privacy policy and terms are at https://optiondesk.avidquant.com/legal/privacy and https://optiondesk.avidquant.com/legal/terms.

For the local desk, with its own data pulls, simulation, backtests, commands and agents, install `option-desk` instead. Do not install both: they expose tools with the same names.

Install in Claude Code:

```
/plugin install option-desk-hosted --marketplace Iman/agent-driven-options-desk-and-skills
```

Built by `scripts/package.py` from `openai-skills`. Do not edit here: edit the sources and rebuild.
