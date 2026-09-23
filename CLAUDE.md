# Claude Code Guidelines for codebone

## 🦴 Shortcut: `cb`
When the user types `cb` (e.g. `cb`, `cb: <task>`, `cb <query>`), this is the official shortcut for **codebone**:
1. Immediately call the MCP tool `cb()` (or `codebone_context()`) to inspect the project's live architectural context, business domains, database models, and API endpoints.
2. Use this semantic context instead of reading dozens of files manually.
3. If the query is about a specific domain (e.g. `cb: stripe billing`), call `cb(domain="billing")` or `cb(query="stripe")` for focused, token-saving context.
