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
    🗺️  Semantic System Graph (Domains, Tables, Endpoints, Events & Logic)
              │
              ├── 🔗 Native MCP (Claude, Cursor, Gemini, Codex)
              └── 🌐 Localhost API (curl http://127.0.0.1:3000/pug/context)
```

1. **Sniff**: Watches your repository files in real time with battery-aware debouncing.
2. **Think**: Local Apple Silicon Metal-accelerated AI extracts business domains, models, routes, and events in <1s.
3. **Map**: Synthesizes a relational Semantic System Graph linking files across overarching business capabilities in local SQLite (`~/Library/Application Support/PUG`).
4. **Serve**: Delivers instant distilled architecture context to AI models via **MCP** or **curl**.

> 💡 **Semantic System Graph:** PUG maps connections far beyond rigid code imports. Static parsers only see explicit `import` statements. PUG recognizes how files are logically intertwined through your overarching system architecture and business logic — connecting e.g. `billing.py` and `user_notification.py` through *Payment Processing* even when they never directly import each other.

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
* **Business Domains & Systems**: High-level architectural capabilities grouping related modules.
* **Entities**: Database models, ORM tables, API routes, and event emitters.
* **Semantic System Graph**: Cross-module business relationships beyond rigid code imports.
* **Recent Changes**: Chronological log of recent file modifications and their logical purpose.

</details>

---

## ⚡ Smart Scan Adoption

Renamed, moved, or branched a project folder? **Never re-scan from scratch.**

PUG recognizes moved files via SHA-256 fingerprinting (0-cost instant reuse), sniffs only modified files, and uses the AI to reconcile overarching business domains.

* **Menu Bar:** Click 🦴 ➔ **Adopt / Link Existing Scan...** (or select a renamed folder for auto-detection).
* **Backup & Share:** Click 🦴 ➔ **More...** ➔ **Export / Import Scan Snapshot (.sqlite3)**.

<details>
<summary><b>⚙️ How Smart Adoption Works (Click to expand)</b></summary>

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

## 🧠 Brain Options

Click the bone icon 🦴 ➔ **More...** ➔ **Brain Selection**:

| Provider | Description |
|---|---|
| **Built-in (Qwen 0.8B)** *(default)* | Apple Silicon Metal GPU-accelerated. Zero cost, zero cloud, instant setup. |
| **Local URL** | Connect to local Ollama (`http://localhost:11434/api/generate`) or LM Studio. |
| **Cloud BYOK** | Use your own API key for OpenAI (`gpt-4o-mini`) or Anthropic (`claude-3-5-haiku`). |
| **Custom .gguf** | Load any local GGUF model file (e.g. Qwen 7B, Llama 3) via native file dialog. |

---

## 💡 Built for 24/7 Background Operation

PUG is designed to run silently 24/7 in your menu bar on every file save (`Cmd + S`):

* **⚡ Ultra-Lightweight (0.8B default):** Heavy 7B+ models spin up fans and drain MacBook battery. Qwen 0.8B extracts routes, tables, and events in `< 1s` using only ~390 MB RAM. PUG indexes structure; your frontier model (Claude 3.5 Sonnet, GPT-4o) writes the code.
* **🍏 Apple Silicon First:** Unified memory allows zero-copy, zero-stutter inference on Metal GPU without taxing the CPU.
* **🎛️ Modular Brains:** Need deeper parsing on complex meta-programming? Switch to Ollama, LM Studio, custom GGUF, or Cloud BYOK in 1 click.

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
