# option-desk plugin

Built by `scripts/package.py` from `shell/skills`, `.claude/commands` and `.claude/agents`. It carries both `.codex-plugin` and `.claude-plugin` manifests. Do not edit here: edit the sources and rebuild, or the next build will discard your changes.

The MCP server entry expects `optiondesk-mcp` on PATH, which `install.sh` puts there. The five skills work in ChatGPT and Codex; the commands and agents are Claude-only. Without the local binary, the skills remain instructions and cannot produce fresh market numbers. ChatGPT web also needs a hosted HTTP MCP connector to execute the tools; this bundle provides only local stdio MCP.
