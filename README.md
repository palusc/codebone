<div align="center">

# 🦴 PUG

### Real-time codebase knowledge graph for your macOS menu bar.
**Deliver clean architectural context without bloating your prompt tokens.**

<br>

[![macOS](https://img.shields.io/badge/platform-macOS-black?logo=apple&style=flat-square)](#)
[![Metal GPU](https://img.shields.io/badge/inference-Apple%20Silicon%20Metal-purple?style=flat-square)](#)
[![MCP](https://img.shields.io/badge/protocol-MCP%20Native-blue?style=flat-square)](#)
[![Version 1.0.0](https://img.shields.io/badge/version-1.0.0-informational?style=flat-square)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Local Only](https://img.shields.io/badge/privacy-100%25%20local-success?style=flat-square)](#-privacy--security)

<br>

*Never dump dozens of raw files into your prompt just to explain your architecture. Let the dog sniff it.* 🐾

</div>

---

## 📉 Token Savings

When asking AI assistants (Claude, Cursor, Gemini, Codex) to build a feature, they typically read 10 to 20 files just to discover schemas, routes, and events. That burns thousands of tokens on boilerplate before writing any code.

```text
Prompt Token Overhead per Architectural Query:

Raw File Dump     [████████████████████████████████████████] ~25,000 tokens  (100% — Slow & expensive)
Vector RAG Search [██████████████████████                  ] ~14,000 tokens  ( 56% — High noise)
PUG Live Graph    [███                                     ]  ~2,000 tokens  (  8% — ~80% savings ⚡)
```

---

## 🐾 How It Works

PUG runs silently in your macOS menu bar and updates on every file save (`Cmd + S`):

```text
       [ Project Folder ]
              │
              ▼
    👃 File Watcher (Instant debounce on save)
              │
              ▼
    🧠 Local Metal GPU (Qwen2.5-Coder 0.8B)
              │
              ▼
    🗺️  Semantic System Graph (Domains, Tables, Endpoints, Events & Logic)
              │
              ├── 🔗 Native MCP (Claude, Cursor, Gemini, Codex)
              └── 🌐 Localhost API (curl http://127.0.0.1:3000/pug/context)
```

1. **Sniff**: Watches repository files in real time with battery-aware debouncing.
2. **Think**: Apple Silicon Metal GPU extracts business domains, models, routes, and events in `<1s`.
3. **Map**: Synthesizes a relational Semantic System Graph linking files across overarching business capabilities.
4. **Serve**: Delivers instant architectural context to AI assistants via **MCP** or **curl**.

> 💡 **Beyond Code Imports:** Static parsers only see explicit `import` statements. PUG connects files through shared business logic (e.g. `billing.py` and `user_notification.py` via *Payment Processing*) even when no direct code import exists.

---

## 🚀 Quick Start

```bash
git clone https://github.com/palusc/pug.git
cd pug
./install.sh
```

A bone icon **🦴** appears in your macOS menu bar. Click it ➔ **Select Project Folder...** to begin.

> 💾 **Lightweight:** Requires **~650 MB disk space** total (~390 MB model + ~260 MB venv) and **< 1 GB RAM**.

---

## ⚡ Built for 24/7 Background Operation

PUG runs continuously in the background without getting in your way:

* **0.8B Model by Default**: Fast (`< 1s`), tiny (~390 MB RAM), and completely silent. Your Mac's fans stay off and your battery is preserved. PUG indexes structure; your frontier model (Claude 3.5 Sonnet, GPT-4o) writes the code.
* **Apple Silicon Metal GPU**: Zero CPU overhead. Runs entirely on unified memory via Metal shaders.
* **Smart Scan Adoption**: SHA-256 fingerprinting recognizes moved or renamed files instantly. You never have to re-scan a project from scratch after renaming a directory or switching branches.
* **100% Localhost**: Binds strictly to `127.0.0.1:3000`. Zero cloud, zero telemetry, zero tokens leaving your machine.

---

## 🔄 Smart Scan Adoption

Renamed, moved, or branched a project folder? **Never re-scan from scratch.**

PUG matches identical files via SHA-256 (0-cost instant reuse), sniffs only modified files, and reconciles the architecture automatically.

* **Menu Bar**: Click 🦴 ➔ **Adopt / Link Existing Scan...** (or pick a renamed folder for auto-detection).
* **Snapshots**: Click 🦴 ➔ **More...** ➔ **Export / Import Scan Snapshot (.sqlite3)**.

<details>
<summary><b>⚙️ Adoption Architecture & API Details (Click to expand)</b></summary>

<br>

```text
[Target Project Folder] ◀── Compare ──▶ [Existing Codebase Scan]
          │
          ├── ⚡ Content Hash Match (SHA-256): 0-cost instant reuse (zero LLM latency)
          ├── 🔄 Moved / Renamed Files: auto-detected by hash & re-linked in database
          ├── 🧠 Modified / New Files: only the diff is sniffed by the AI brain
          └── 🗺️ AI Architecture Pass: LLM reconciles overarching business domains
```

```bash
# List all saved codebase scans
curl http://localhost:3000/pug/scans

# Adopt a scan for a moved or renamed project
curl -X POST http://localhost:3000/pug/scans/adopt \
     -H "Content-Type: application/json" \
     -d '{"scan_id": "my_app_1790102978", "project_path": "/Users/you/Desktop/my_app_renamed"}'
```

</details>

---

## 💬 Usage with AI Assistants

Prompt your AI model naturally:
> *"Implement authentication middleware for billing routes. Use PUG."*

The model detects `PUG`, calls `pug_context()`, and immediately receives the exact database models, routes, and dependency graph.

<details>
<summary><b>⚙️ Cursor & Claude Desktop Configuration (Click to expand)</b></summary>

<br>

PUG auto-registers with Claude CLI during `./install.sh`. To configure **Claude Desktop** or **Cursor**, add this block to your MCP config (`claude_desktop_config.json` or `.cursor/mcp.json`):

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
<summary><b>🌐 Direct Curl / Terminal Option (Click to expand)</b></summary>

<br>

Fetch the live architectural context directly from your terminal:

```bash
curl http://localhost:3000/pug/context
```

Returns Markdown structured specifically for LLMs:
* **Business Domains & Systems**: High-level architectural capabilities grouping related modules.
* **Entities**: Database models, ORM tables, API routes, and event emitters.
* **Semantic System Graph**: Cross-module business relationships beyond rigid code imports.
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
* **Metal Acceleration**: Runs on Apple Silicon GPU / Neural Engine (`-DGGML_METAL=on`). Minimal CPU impact.
* **Battery-Aware**: Detects MacBook battery power and increases debounce intervals to conserve energy.

---

## 🗑️ Uninstall

<details>
<summary><b>Uninstall commands (Click to expand)</b></summary>

<br>

```bash
# Standard uninstall (removes app & environment, keeps ~390 MB model for fast reinstall):
./uninstall.sh

# Full cleanup (completely wipes all ~650 MB: app, database, logs, and local model):
./uninstall.sh --all
```

> ℹ️ *Note: Models and index data reside in `~/Library/Application Support/PUG/`, completely separated from your project repositories.*

</details>

---

<div align="center">

Released under the [MIT License](LICENSE).

</div>
