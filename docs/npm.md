# xcbone

The terminal and MCP launcher for **codebone**, the local codebase architecture app
for macOS and Windows.

```bash
npx -y xcbone
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
      "args": ["-y", "xcbone"]
    }
  }
}
```

Call `cb()` for an overview, `cb(query="billing")` for focused architectural
context, or `codebone_tldr()` for a compact project summary.

## Supported desktop apps

- **macOS:** macOS 13+ on Apple Silicon, with the built-in model using Metal.
- **Windows:** Windows 10/11 x64, with a tray app, settings and CPU model support.

cbone requires Node.js 18 or later. The installed desktop app includes the Python
runtime and MCP server. Windows portable installs can set `CODEBONE_MCP` to the
full path of `cbone.exe`. Source installs can set `CODEBONE_PYTHON` to their Python
interpreter. `CODEBONE_PORT` selects an explicit running local instance.

## Names

**xcbone** is the npm package and a terminal command. **cbone** is also available
as a terminal alias. **codebone** is the desktop app. The previous npm package
was called `codebone-mcp`; new configurations should use `xcbone`.

[Website](https://codeb.one) · [Source](https://github.com/palusc/codebone) ·
[Downloads](https://github.com/palusc/codebone/releases/latest) ·
[Issues](https://github.com/palusc/codebone/issues)

MIT licensed.
