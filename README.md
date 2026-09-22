<div align="center">

# 🦴 PUG

### Real-time codebase knowledge graph for your macOS menu bar.
**Deliver clean architectural context without bloating your prompt tokens.**

<br>

[![macOS](https://img.shields.io/badge/platform-macOS-black?logo=apple&style=flat-square)](#)
[![Metal GPU](https://img.shields.io/badge/inference-Apple%20Silicon%20Metal-purple?style=flat-square)](#)
[![MCP](https://img.shields.io/badge/protocol-MCP%20Native-blue?style=flat-square)](#)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Local Only](https://img.shields.io/badge/privacy-100%25%20local-success?style=flat-square)](#-privacy--security)

<br>

*Never dump dozens of raw files into your prompt just to explain your architecture. Let the dog sniff it.* 🐾

</div>

---

## 📉 Token Savings

When asking AI assistants (Claude, Cursor, Gemini, Codex) to build a feature, they typically read 10 to 20 files just to discover your database schema, endpoints, and event handlers. That burns thousands of tokens on boilerplate, imports, and noise before writing any code.

```text
Prompt Token Overhead per Architectural Query:

Raw File Dump     [████████████████████████████████████████] ~25,000 tokens  (100% — Slow & expensive)
Vector RAG Search [██████████████████████                  ] ~14,000 tokens  ( 56% — High noise)
PUG Live Graph    [███                                     ]  ~2,000 tokens  (  8% — ~80% savings ⚡)
```

---

## 🐾 How It Works

PUG runs quietly in your macOS menu bar.

```text
       [ Project Folder ]
              │
              ▼
    👃 File Watcher (Instant debounce on save)
              │
              ▼
    🧠 Local AI Brain (Apple Silicon Metal GPU / Qwen2.5-Coder)
              │
              ▼
    🗺️  SQLite Graph (Tables, Endpoints, Events & Connections)
              │
              ├── 🔗 Native MCP (Claude, Cursor, Gemini, Codex)
              └── 🌐 Localhost API (curl http://127.0.0.1:3000/pug/context)
```

1. **Sniff**: Watches your repository files in real time with battery-aware debouncing.
2. **Think**: Local Apple Silicon Metal-accelerated AI extracts models, routes, and events in <1s.
3. **Map**: Maintains a lightweight relational graph in local SQLite (`~/Library/Application Support/PUG`).
4. **Serve**: Delivers instant distilled architecture context to AI models via **MCP** or **curl**.

---

## 🚀 Quick Start

One command sets up the environment, downloads the local Metal model (with live progress), creates `PUG.app`, and launches it:

```bash
git clone https://github.com/palusc/pug.git
cd pug
./install.sh
```

A bone icon **🦴** appears in your macOS menu bar. Click it ➔ **Select Project Folder...** and pick your repo.

> 💾 **Lightweight Footprint:** Only requires **~650 MB disk space** total (~390 MB model + ~260 MB virtualenv) and **< 1 GB RAM** on Apple Silicon.

---

## 💬 Usage with AI Assistants

Prompt your AI model naturally:
> *"Implement authentication middleware for billing routes. Use PUG."*

The model detects `PUG`, calls `pug_context()`, and immediately receives the exact database models, routes, and dependency graph.

<details>
<summary><b>⚙️ Cursor & Claude Desktop Configuration (Click to expand)</b></summary>

<br>

PUG auto-registers with Claude CLI during `./install.sh`. To use it in **Claude Desktop** or **Cursor**, add this block to your MCP config (`claude_desktop_config.json` or `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "pug": {
      "command": "/Users/YOUR_USERNAME/Library/Application Support/PUG/venv/bin/python3",
      "args": ["/Users/YOUR_USERNAME/Library/Application Support/PUG/src/pug_mcp/server.py"]
    }
  }
}
```

</details>

<details>
<summary><b>🌐 Direct Curl / Zero-Config Option (Click to expand)</b></summary>

<br>

You can also fetch the live architectural context directly from terminal or any chat tool:

```bash
curl http://localhost:3000/pug/context
```

Returns Markdown structured specifically for LLMs:
* **Entities**: Database models, ORM tables, API routes, and event emitters.
* **Graph**: Cross-file dependency links (who calls which table/endpoint).
* **Recent Changes**: Chronological log of recent file modifications and their logical purpose.

</details>

---

## 🧠 Brain Options

Click the bone icon 🦴 ➔ **More...** ➔ **Brain Selection**:

| Provider | Description |
|---|---|
| **Built-in (Qwen 0.8B)** *(default)* | Apple Silicon Metal GPU-accelerated. Zero cost, zero cloud, instant setup. |
| **Local URL** | Connect to local Ollama (`http://localhost:11434/api/generate`) or LM Studio. |
| **Cloud BYOK** | Use your own API key for OpenAI (`gpt-4o-mini`) or Anthropic (`claude-3-5-haiku`). |
| **Custom .gguf** | Load any local GGUF model file (e.g. Qwen 7B, Llama 3) via native file dialog. |

---

## 🔒 Privacy & Security

* **100% Localhost**: Binds strictly to `127.0.0.1:3000`. No external network exposure, zero telemetry.
* **Metal Acceleration**: Runs on Apple Silicon GPU / Apple Neural Engine (`-DGGML_METAL=on`). Minimal CPU impact.
* **Battery-Aware**: Detects MacBook battery power and increases debounce intervals to conserve energy.

---

## 🗑️ Uninstall

<details>
<summary><b>Uninstall commands</b></summary>

<br>

```bash
# Removes PUG.app, login items, and environment (keeps model for instant reinstall):
./uninstall.sh

# Completely wipes everything from disk, including the ~390 MB local LLM model:
./uninstall.sh --all
```

</details>

---

<div align="center">

Released under the [MIT License](LICENSE).

</div>
