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

## ⚡ Smart Scan Adoption & AI Reconciliation

Renamed a project folder, moved code to a new directory, or checked out a branch? **You never have to re-scan from scratch.**

PUG automatically saves persistent codebase snapshots in `~/Library/Application Support/PUG/scans/` and features an intelligent **Structural Reconciler**:

```
[Target Project Folder] ◀── Compare ──▶ [Existing Codebase Scan]
          │
          ├── ⚡ Content Hash Match (SHA-256): 0-cost instant reuse (zero LLM latency)
          ├── 🔄 Moved / Renamed Files: auto-detected by hash & re-linked in database
          ├── 🧠 Modified / New Files: only the diff is sniffed by the AI brain
          └── 🗺️ AI Architecture Pass: LLM reconciles overarching business domains
```

* **macOS Menu Bar:** Click 🦴 ➔ **Adopt / Link Existing Scan...** to select an existing scan or browse any `.sqlite3` snapshot. When choosing a renamed project folder via **Select Project Folder...**, PUG automatically recognizes matching project signatures and offers instant reconciliation.
* **Snapshot Management:** Click 🦴 ➔ **More...** ➔ **Export Scan Snapshot...** or **Import Scan File (.sqlite3)...** to share or back up scans across machines.
* **REST API:**
  ```bash
  # List all historical codebase scans and detected domains
  curl http://localhost:3000/pug/scans

  # Adopt a scan for a moved or renamed project
  curl -X POST http://localhost:3000/pug/scans/adopt \
       -H "Content-Type: application/json" \
       -d '{"scan_id": "my_app_1790102978", "project_path": "/Users/you/Desktop/my_app_renamed"}'
  ```
* **Native MCP Tools:**
  * `pug_context()`: Retrieve live architecture, business domains, and Semantic System Graph.
  * `pug_graph()`: Inspect cross-module conceptual and entity links.
  * `pug_list_scans()`: List all saved codebase scans and snapshots.
  * `pug_adopt_scan(scan_id_or_path, project_path)`: Adopt and reconcile an existing scan.

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

## 💡 Design Decisions

* **Why 0.8B by default?** PUG runs continuously in the background on every file save (`Cmd + S`). A heavy 7B+ model would spin up fans and drain MacBook battery. Qwen 0.8B extracts routes, tables, and events in `< 1s` using only ~390 MB of memory, leaving unified RAM free for Docker, your IDE, and browser tabs. PUG doesn't generate code — that is the job of your frontier model (Claude 3.5 Sonnet, GPT-4o). PUG only acts as an ultra-fast structural indexer (with one-click switching to Ollama, LM Studio, or Cloud in the menu if you ever need deeper parsing on complex meta-programming).
* **Why macOS Apple Silicon first?** Apple Silicon's unified memory architecture is uniquely suited for persistent background inference via Metal GPU with zero CPU stutter or PCIe bus transfer lag. While built natively for the macOS developer ecosystem today, headless cross-platform support is planned.

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
