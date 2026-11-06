# igotaboner

The terminal and MCP launcher for **codebone**, the local codebase architecture app
for macOS.

```bash
npx -y igotaboner
```

Install and launch the [codebone desktop app](https://github.com/palusc/codebone/releases/latest)
first. The app builds the local architecture graph; cbone connects your coding
agent to it through MCP. The launcher does not download or replace the desktop app.

## Configure your coding agent

```json
{
  "mcpServers": {
    "codebone": {
      "command": "npx",
      "args": ["-y", "igotaboner"]
    }
  }
}
```

Call `cb()` for an overview, `cb(query="billing")` for focused architectural
context, or `codebone_tldr()` for a compact project summary.

## Supported desktop apps

- **macOS:** macOS 13+ on Apple Silicon, with the built-in model using Metal.

cbone requires Node.js 18 or later. The installed desktop app includes the Python
runtime and MCP server. Source installs can set `CODEBONE_PYTHON` to their Python interpreter. `CODEBONE_PORT` selects an explicit running local instance.

## Names

**igotaboner** is the npm package; it installs the terminal commands `codebone`, `cb` and `igotaboner`. **codebone** is the
desktop app. The previous npm package was called
`codebone-mcp`; new configurations should use `igotaboner`.

[Website](https://codeb.one) · [Source](https://github.com/palusc/codebone) ·
[Downloads](https://github.com/palusc/codebone/releases/latest) ·
[Issues](https://github.com/palusc/codebone/issues)

MIT licensed.
