<div align="center">

# 🦴 codebone

### Real-time codebase knowledge graph for your macOS menu bar.
**Deliver clean architectural context without bloating your prompt tokens.**

<br>

[![macOS](https://img.shields.io/badge/platform-macOS-black?logo=apple&style=flat-square)](#)
[![Metal GPU](https://img.shields.io/badge/inference-Apple%20Silicon%20Metal-purple?style=flat-square)](#)
[![MCP](https://img.shields.io/badge/protocol-MCP%20Native-blue?style=flat-square)](#)
[![Version 1.2.0](https://img.shields.io/badge/version-1.2.0-informational?style=flat-square)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Local Only](https://img.shields.io/badge/privacy-100%25%20local-success?style=flat-square)](#-privacy--security)

<br>


*Never dump dozens of raw files into your prompt just to explain your architecture. Let the dog sniff it.* 🐾

</div>

---

## 📉 Token Savings

When asking AI assistants (Claude, Cursor, Gemini, Codex) to build a feature, they typically read 10 to 20 files just to discover schemas, routes, and events. That burns thousands of tokens on boilerplate before writing any code.

<p align="center">
  <img src="resources/token-savings.svg" width="560" alt="Token overhead per query: Raw File Dump ~25,000 tokens, Vector RAG Search ~14,000 tokens, codebone Live Graph ~2,000 tokens">
</p>

---

## 🐾 How It Works

codebone runs silently in your macOS menu bar and updates on every file save (`Cmd + S`):

1. **Sniff**: Watches repository files in real time with battery-aware debouncing.
2. **Think**: Apple Silicon Metal GPU extracts business domains, models, routes, and events in `<1s`.
3. **Map**: Synthesizes a relational Semantic System Graph linking files across overarching business capabilities.
4. **Serve**: Delivers instant architectural context to AI assistants via **MCP** or **curl**.

> 💡 **Beyond Code Imports:** Static parsers only see explicit `import` statements. codebone connects files through shared business logic (e.g. `billing.py` and `user_notification.py` via *Payment Processing*) even when no direct code import exists.

---

## 🚀 Installation & Quick Start

### Option A: Native Drag-and-Drop DMG (Recommended)
Download the latest pre-compiled **`codebone-macos-arm64.dmg`** from [GitHub Releases](https://github.com/palusc/codebone/releases) and drag `codebone.app` to your `/Applications` folder.

### Option B: Homebrew
```bash
brew tap palusc/codebone
brew install codebone
```

### Option C: Build from Source
```bash
git clone https://github.com/palusc/codebone.git
cd codebone
./install.sh
```

A bone icon **🦴** appears in your macOS menu bar. Click it ➔ **Select Project Folder...** to begin.

> 💾 **Lightweight:** Requires **~650 MB disk space** total (~390 MB model + ~260 MB venv) and **< 1 GB RAM**.

---

## ⚡ Built for 24/7 Background Operation

codebone runs continuously in the background without getting in your way:

* **0.5B Model by Default**: Fast (`< 1s`), tiny (~390 MB RAM), and completely silent. Your Mac's fans stay off and your battery is preserved. codebone indexes structure; your frontier model (Claude Sonnet 4.5, GPT-4.1) writes the code.
* **Apple Silicon Metal GPU**: Zero CPU overhead. Runs entirely on unified memory via Metal shaders.
* **Smart Scan Adoption**: SHA-256 fingerprinting recognizes moved or renamed files instantly. You never have to re-scan a project from scratch after renaming a directory or switching branches.
* **100% Localhost**: Binds strictly to `127.0.0.1:8053` (with automatic incremental fallback to `8054+` if occupied). Zero cloud, zero telemetry, zero tokens leaving your machine.

---

## 🔄 Smart Scan Adoption

Renamed, moved, or branched a project folder? **Never re-scan from scratch.**

codebone matches identical files via SHA-256 (0-cost instant reuse), sniffs only modified files, and reconciles the architecture automatically.

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
curl http://localhost:8053/codebone/scans

# Adopt a scan for a moved or renamed project
curl -X POST http://localhost:8053/codebone/scans/adopt \
     -H "Content-Type: application/json" \
     -d '{"scan_id": "my_app_1790102978", "project_path": "/Users/you/Desktop/my_app_renamed"}'
```

</details>

---

## 💬 Usage with AI Assistants

Prompt your AI model naturally:
> *"Implement authentication middleware for billing routes. Use codebone."*

The model detects `codebone`, calls `codebone_context()`, and immediately receives the exact database models, routes, and dependency graph.

<details>
<summary><b>⚙️ Cursor & Claude Desktop Configuration (Click to expand)</b></summary>

<br>

codebone auto-registers with Claude CLI during `./install.sh`. To configure **Claude Desktop** or **Cursor**, add this block to your MCP config (`claude_desktop_config.json` or `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "codebone": {
      "command": "/Users/YOUR_USERNAME/Library/Application Support/codebone/venv/bin/python3",
      "args": ["-m", "codebone_mcp.server"],
      "env": {
        "CODEBONE_PORT": "8053"
      }
    }
  }
}
```

> ⚠️ **Important:** Replace `YOUR_USERNAME` with your actual macOS username (run `whoami` in your terminal to find it).

</details>

<details>
<summary><b>📋 Sample Raw Context Payload returned to AI (Click to expand)</b></summary>

<br>

Here is an authentic sample of what `codebone_context()` passes to Claude, Cursor, or GPT:

```markdown
# codebone — High-Level Codebase Architecture
*Project: `/Users/username/Desktop/my_project` | Files indexed: 142 | Updated: 2026-09-23 12:30:15*

## 1. System Metrics & Architecture Summary
- **Indexed Files:** 142 source files
- **Business Domains:** 7 overarching domain categories
- **Database Models / Tables:** 19 total detected across modules
- **API Routes / Endpoints:** 28 total endpoints
- **Events & Logic Hooks:** 14 event triggers/handlers
- **Cross-Module Semantic Relationships:** 38 conceptual links

## 2. Business Domains & Systems
- **`Authentication & Identity`** (12 files: `auth/router.py`, `auth/jwt.py`, `models/user.py` *(+9 more)*)
- **`Payment & Billing`** (8 files: `billing/stripe.py`, `billing/webhook.py`, `models/invoice.py` *(+5 more)*)
- **`Order Fulfillment`** (15 files: `orders/service.py`, `events/order_created.py`, `models/order.py` *(+12 more)*)
- **`Notifications & Webhooks`** (6 files: `services/mailer.py`, `workers/push.py` *(+4 more)*)

---
## 💡 Level-of-Detail (LOD) — Token-Saving Deep Dive
To inspect lower-level entities, models, endpoints, and file summaries without wasting tokens on the full repository graph, call `codebone_context` with focused parameters:
- **By Domain:** `codebone_context(domain="Payment & Billing")`
- **By File/Module:** `codebone_context(file="stripe.py")`
- **By Entity/Keyword:** `codebone_context(query="InvoiceCreated")`
```

When the AI calls `codebone_context(domain="billing")` for deep implementation details, it receives a focused technical slice:

```markdown
# codebone — Filtered Context (`billing`)
Matching files: 8

## Matching Business Domains
- **Payment & Billing**

## Matching Database Models / Tables
- `Invoice`
- `Subscription`

## Matching API Routes / Endpoints
- `POST /api/v1/checkout/session`
- `POST /api/v1/billing/webhook`

## Matching Events & Logic Hooks
- `InvoicePaid`
- `PaymentFailed`

### `billing/stripe.py` *(Payment & Billing)*
Integrates Stripe checkout sessions, webhooks, and subscription syncing.
**Routes:** `POST /api/v1/checkout/session`
**Tables:** `Invoice`, `Subscription`
```

</details>

<details>
<summary><b>🌐 Direct Curl / Terminal Option (Click to expand)</b></summary>

<br>

Fetch the live architectural context directly from your terminal:

```bash
curl http://localhost:8053/codebone/context
```

Returns Markdown structured specifically for LLMs:
* **Business Domains & Systems**: High-level architectural capabilities grouping related modules.
* **Entities**: Database models, ORM tables, API routes, and event emitters.
* **Semantic System Graph**: Cross-module business relationships beyond rigid code imports.
* **Recent Changes**: Chronological log of recent file modifications and their logical purpose.

**Level-of-Detail (LOD) filtering** — Reduce token usage further on large repos:

```bash
# Only files in the "billing" domain
curl 'http://localhost:8053/codebone/context?domain=billing'

# Files matching a specific path
curl 'http://localhost:8053/codebone/context?file=payments'

# Files touching a specific table, route, or event
curl 'http://localhost:8053/codebone/context?query=InvoiceCreated'
```

Or via the MCP tool: `codebone_context(domain="billing")` — the AI only loads the relevant slice.

*(Note: `/pug/...` endpoints are also supported for backwards compatibility).*

</details>

---

## 🗺️ Live Graph UI

Visualize your Semantic System Graph as an interactive node-link diagram in any browser:

```bash
open http://localhost:8053/codebone/graph/ui
```

Or click the Knowledge Graph card in the macOS menu bar. The interface features:
- **De-Neonified Dark Glassmorphism**: Elegant slate background (`#0a0d14` to `#151d2f`) with a blueprint dot-matrix grid and harmonious color palette (no blinding neon cyan).
- **Live Telemetry HUD**: Shows active project name, path, live status (🟢 *Watching* / 🔵 *Sniffing*), and active AI provider.
- **Interactive Metric Filter Pills**: Filter and highlight nodes in real time by category:
  - 🌐 **Domains** (`#8b5cf6` Iris/Purple)
  - 📁 **Files** (`#10b981` Emerald Green)
  - ⚡ **Routes** (`#0ea5e9` Sky Azure)
  - 🗄️ **Tables / Models** (`#f59e0b` Warm Amber)
  - 📡 **Events** (`#f43f5e` Rose Coral)
  - 🔗 **Relations / Edges**
- **Live Search (`/` Shortcut)**: Instantly search filenames, database tables, HTTP routes, or business concepts. Non-matching nodes fade to 10% opacity while matches remain illuminated.
- **Instant Hover Tooltips**: Hover over any node to inspect its category, name, and a 1-sentence AI architecture preview.
- **Rich Slide-out Inspector Drawer**: Click any node to open the glassmorphism sidebar:
  - **🧠 Architectural Purpose**: Full AI summary explaining the module's logical role and data flow.
  - **Discovered Entities**: Categorized chips for database models (`🗄️`), HTTP endpoints (`⚡`), events (`📡`), and domains (`🌐`).
  - **Interactive Connection Jumping**: Lists all linked files with the connecting entity. Clicking any connected item smoothly pans and centers that node on the canvas.
- **Viewport Controls**: Floating buttons in the bottom-right corner for Zoom In (`+`), Zoom Out (`−`), Fit View (`⛶`), and Center (`◎`).
- **In-App Feedback & Bug Reporting**: Built-in glassmorphism modal accessible via the **Feedback** button in the HUD to report issues or request features without leaving the interface.
- **Auto-Refresh**: Live updates synchronize in real time when you save files in your editor (`Cmd + S`).

---

## 🦴 Native macOS Menu Bar Experience

codebone integrates seamlessly into macOS:
- **Native Apple SF Symbols**: Every menu item, submenu, and setting features pixel-perfect Apple vector icons (`14pt` standard size with regular weight) that adapt automatically to Dark and Light modes.
- **Interactive Header Card**:
  - Branded logo and live status dot (Green = Watching, Blue = Sniffing, Gray = Idle).
  - Clickable project folder link with native `folder` symbol revealing the repo in Finder.
  - Interactive Knowledge Graph HUD card displaying live node and connection counts.
- **Fast Model Switcher**: Seamlessly toggle between local GGUF models, Ollama/LM Studio, and cloud providers.
- **Built-in Feedback & Bug Reports**: 1-click dialog directly in the menu bar with auto-bundled diagnostics and sensitive credential redaction.
- **One-Click Settings**: Full Disk Access helper, snapshot export/import, log viewer, and cache reset directly accessible from the menu.

---

## 💬 Built-in Feedback & Bug Reporting

Report bugs, request features, or share suggestions directly inside the tool:

* **From macOS Menu Bar**: Click 🦴 ➔ **Feedback & Bug Report...** (`exclamationmark.bubble` icon).
* **From Live Graph Web UI**: Click the **Feedback** button in the top HUD.
* **Auto-Diagnostics**: Automatically attaches OS version, codebone version, active provider, file/node count, and recent diagnostic logs.
* **Security & Privacy**: Sensitive API keys and tokens (`sk-...`, `bearer ...`, `api_key=...`) are automatically redacted before saving.
* **Offline-Capable & GitHub 1-Click**: Stored locally in `~/Library/Application Support/codebone/feedback.jsonl` with an optional 1-click pre-filled GitHub Issue link.

---

## 🧠 Brain Options

Click the bone icon 🦴 ➔ **Settings** ➔ **Model**:

| Provider | Description |
|---|---|
| **Built-in (Qwen 0.5B)** *(default)* | Apple Silicon Metal GPU-accelerated. Zero cost, zero cloud, instant setup. |
| **Local URL** | Connect to local Ollama (`http://localhost:11434/api/generate`) or LM Studio. |
| **Cloud BYOK** | Use your own API key for OpenAI (`GPT-4.1`) or Anthropic (`Claude Sonnet 4.5`). |
| **Custom .gguf** | Load any local GGUF model file (e.g. Qwen 7B, Llama 3) via native file dialog. |

---

## 🔬 Deep Scan Mode (Advanced)

The default 0.5B brain is tuned for speed, not depth. If your architecture is dense enough that the fast pass misses relationships, **Deep Scan Mode** re-runs a full project sniff through a larger local model you supply (e.g. **Qwen2.5-Coder 7B**) for a more thorough one-off pass, then automatically switches back to the fast 0.5B brain for everyday saves.

Click 🦴 ➔ **Settings** ➔ **Model** ➔ **Deep Scan Mode (7B)...** and point it at a `.gguf` file.

> ⚠️ **Know what you're doing before you turn this on.** A 7B model needs far more RAM, disk, and time than the built-in 0.5B brain, and re-sniffing a large repo can take minutes instead of seconds. It's opt-in and off by default — recommended only if you're comfortable managing local GGUF models yourself.

---

## 🔒 Privacy & Security

* **100% Localhost**: Binds strictly to `127.0.0.1:8053` (with automatic port conflict probing to `8054+`). Zero external network exposure, zero telemetry.
* **Apple Silicon Metal Acceleration**: Runs directly on Apple Silicon GPU / Neural Engine (`-DGGML_METAL=on`). Minimal CPU impact, silent fans.
* **macOS Full Disk Access (TCC)**: Pre-flight permission verification for protected directories (`~/Desktop`, `~/Documents`, `~/Downloads`, and external drives). Includes a 1-click helper in the menu bar opening macOS System Settings directly to *Privacy & Security > Full Disk Access*.
* **Symlink Jail / Sandboxing**: Prevents repository symlinks from escaping the project root into sensitive system directories (`~/.ssh`, `/etc/passwd`). Out-of-tree symlinks are automatically rejected by the sniffer.
* **Prompt Injection & Jailbreak Defense**:
  - Untrusted code is isolated using `<untrusted_source_code file="...">` with closing XML tags escaped (`&lt;/untrusted_source_code&gt;`) to prevent delimiter breakout.
  - Strict anti-jailbreak system directives instruct the model to treat untrusted code as passive data and ignore embedded instructions, role changes, or `SYSTEM OVERRIDE` commands.
  - Entity and summary sanitization strips injection payloads, control characters, and XSS HTML/JS links (`javascript:`, `data:`).
* **Path Traversal Protection**: Scan adoption and export endpoints strictly reject traversal attempts (`..`, `/`, `\`).
* **Battery-Aware Throttling**: Auto-detects power source via macOS `pmset -g batt`: fast **0.5s** debounce on AC power, and **15.0s** throttling on battery to preserve MacBook battery health.

---

## 🗑️ Complete Uninstallation

codebone provides a dedicated standalone uninstaller program so you can clean all traces with 1 click:

### Option A: Standalone Uninstaller App (Recommended)
1. Double-click **`Uninstall codebone.app`** in your `/Applications` folder (or click 🦴 ➔ **Settings** ➔ **Uninstall codebone...**).
2. Click **"Clean All Data"**. It will:
   - Terminate all background processes and watchers.
   - Wipe all semantic knowledge maps, SQLite databases, and cached AI models (`~/Library/Application Support/codebone`).
   - Remove all diagnostic logs (`~/Library/Logs/codebone`).
   - Clean MCP server registrations from Claude Desktop, Cursor, and Gemini.
   - Remove LaunchAgents.
3. Once cleaned, simply drag **`codebone.app`** into the Trash (or click **"Move to Trash"** in the dialog to do it automatically). Everything is gone for good.

### Option B: Terminal CLI
```bash
# Complete uninstallation (removes all apps, databases, models, logs, and MCP configs):
./uninstall.sh

# Optional: keep databases and models for fast reinstall:
./uninstall.sh --keep-data
```

---

<div align="center">

Released under the [MIT License](LICENSE).

</div>
