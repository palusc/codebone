<div align="center">

# 🦴 codebone

### Real-time codebase knowledge graph for your macOS menu bar.
**Stop dumping dozens of files into your prompt. Let the dog sniff it.** 🐾

<br>

[![macOS](https://img.shields.io/badge/platform-macOS-black?logo=apple&style=flat-square)](#)
[![Metal GPU](https://img.shields.io/badge/inference-Apple%20Silicon%20Metal-purple?style=flat-square)](#)
[![MCP](https://img.shields.io/badge/protocol-MCP%20Native-blue?style=flat-square)](#)
[![Version 1.2.0](https://img.shields.io/badge/version-1.2.0-informational?style=flat-square)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Local Only](https://img.shields.io/badge/privacy-100%25%20local-success?style=flat-square)](#-privacy--security)

</div>

---

## 📉 Why codebone?

AI assistants typically read 10–20 files just to understand your architecture — burning thousands of tokens on boilerplate before writing a single line of code.

<p align="center">
  <img src="resources/token-savings.svg" width="540" alt="Token overhead: Raw File Dump ~25k tokens, Vector RAG ~14k tokens, codebone ~2k tokens">
</p>

codebone runs in your macOS menu bar, watches every file save, and delivers a live architectural snapshot directly to Claude, Cursor, or Gemini via MCP.

---

## 🚀 Download & Install

### [⬇️ Download](https://github.com/palusc/codebone/releases/download/v1.2.0/codebone-macos-arm64.dmg)

Drag `codebone.app` to `/Applications` — done. A 🦴 appears in your menu bar.

Click it → **Select Project Folder...** to start your first scan.

> 💾 ~650 MB total (~390 MB model + ~260 MB venv). Requires macOS 13+ on Apple Silicon.

<details>
<summary><b>Homebrew / Build from Source</b></summary>

<br>

**Homebrew:**
```bash
brew tap palusc/codebone
brew install codebone
```

**Build from source:**
```bash
git clone https://github.com/palusc/codebone.git
cd codebone
./install.sh
```

</details>

---

## 🐾 How It Works

1. **Sniff** — Watches your repo on every `Cmd + S` with battery-aware debouncing.
2. **Think** — Apple Silicon Metal GPU extracts domains, models, routes, and events in `< 1s`.
3. **Map** — Builds a Semantic System Graph linking files by shared business logic — not just imports.
4. **Serve** — Streams precise architectural context to your AI via **MCP** or **curl**.

---

## 💬 Usage with AI Assistants

Prompt naturally:
> *"Implement authentication middleware for billing routes. Use codebone."*

The model calls `codebone_context()` and receives the exact schemas, routes, and relationships it needs — no file dumping required.

<details>
<summary><b>⚙️ Claude Desktop & Cursor Configuration</b></summary>

<br>

codebone auto-registers during `./install.sh`. For manual setup, add to `claude_desktop_config.json` or `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "codebone": {
      "command": "npx",
      "args": ["-y", "codebone-mcp"]
    }
  }
}
```

That's it — no Python paths, no manual configuration.

<details>
<summary>Manual path (if npx isn't available)</summary>

```json
{
  "mcpServers": {
    "codebone": {
      "command": "/Users/YOUR_USERNAME/Library/Application Support/codebone/venv/bin/python3",
      "args": ["-m", "codebone_mcp.server"],
      "env": { "CODEBONE_PORT": "8053" }
    }
  }
}
```

Replace `YOUR_USERNAME` with the output of `whoami`.

</details>

</details>

<details>
<summary><b>📋 Sample Context Payload</b></summary>

<br>

```markdown
# codebone — Codebase Architecture
Project: /Users/you/my_project | Files: 142 | Updated: 2026-09-23

## Business Domains
- Authentication & Identity (12 files: auth/router.py, auth/jwt.py, models/user.py …)
- Payment & Billing (8 files: billing/stripe.py, billing/webhook.py, models/invoice.py …)
- Order Fulfillment (15 files: orders/service.py, events/order_created.py …)

## Focused query: codebone_context(domain="billing")
→ Returns only billing files, models (Invoice, Subscription),
  routes (POST /checkout/session), and events (InvoicePaid, PaymentFailed).
```

</details>

<details>
<summary><b>🌐 Direct curl / Terminal</b></summary>

<br>

```bash
# Full architectural context
curl http://localhost:8053/codebone/context

# Filter by domain, file, or entity
curl 'http://localhost:8053/codebone/context?domain=billing'
curl 'http://localhost:8053/codebone/context?file=payments'
curl 'http://localhost:8053/codebone/context?query=InvoiceCreated'
```

</details>

---

## 🗺️ Live Graph UI

```bash
open http://localhost:8053/codebone/graph/ui
```

Interactive node-link diagram of your codebase. Dark glassmorphism theme, real-time search (`/`), click-to-inspect drawer, and live sync on every file save.

---

## 🧠 Brain Options

| Provider | Description |
|---|---|
| **Built-in (Qwen 0.5B)** *(default)* | Metal GPU-accelerated. Zero cost, zero cloud. |
| **Local URL** | Ollama, LM Studio, or any OpenAI-compatible endpoint. |
| **Cloud BYOK** | Your own API key — OpenAI (`GPT-6`) or Anthropic (`Claude Sonnet 5`). |
| **Custom .gguf** | Any local GGUF model via file dialog (e.g. Qwen 7B, Llama 3). |

🦴 ➔ **Settings** ➔ **Model** to switch at any time.

---

## 🔄 Smart Scan Adoption

Renamed, moved, or branched your project? **Never re-scan from scratch.**

SHA-256 fingerprinting reuses unchanged files instantly. Only modified files are re-sniffed.

🦴 ➔ **Adopt / Link Existing Scan...**

---

## 🔒 Privacy & Security

- **100% Localhost** — Binds to `127.0.0.1:8053` only. Zero cloud, zero telemetry.
- **Prompt Injection Defense** — Untrusted code is isolated with escaped XML wrappers and strict anti-jailbreak directives.
- **Symlink Jail** — Symlinks cannot escape the project root into sensitive system paths.
- **Full Disk Access Helper** — Pre-flight TCC check with 1-click System Settings shortcut.
- **Battery-Aware** — 0.5s debounce on AC, 15s on battery.

---

## 🗑️ Uninstall

<details>
<summary><b>How to completely remove codebone</b></summary>

<br>

**Option A — Uninstaller App (recommended):**
Double-click `Uninstall codebone.app` → **Clean All Data**. Removes all processes, databases, models, logs, and MCP entries. Then drag `codebone.app` to the Trash.

**Option B — Terminal:**
```bash
./uninstall.sh           # full wipe
./uninstall.sh --keep-data  # keep databases & model for fast reinstall
```

</details>

---


<div align="center">

Released under the [MIT License](LICENSE).

</div>
