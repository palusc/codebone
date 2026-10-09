# Changelog

All notable changes to codebone will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Official milestone releases are clean numbers (`1.0`, `1.5`, `1.6`, `1.7`, `1.8`).
Iterative updates and development drops within each release series use letter releases (`.a`, `.b`).

---

## [Unreleased]

---

## [1.7] - 2026-10-09
*Official Milestone Full Release*

### 🚀 Core & Hybrid Scan Engine
- **True Hybrid Architecture**: Combines deterministic multi-language structural static scanning (Python, TS/JS, Go, Rust, Ruby, PHP, Java, C/C++) with local and BYOK LLM semantic synthesis for deep symbol, dependency, and architecture indexing.
- **Cancelable & Resumable Scanning**: Enhanced scan management with instant `Cancel Scan` and `Pause Scanning`/`Resume Scanning` controls with live ETA calculation and active phase indicators.
- **Per-Project Auto-Scan Toggle**: Added `Auto-Scan on Save` setting directly in each project's menu (`ON` by default), allowing developers to easily disable automatic scanning on file saves for mass-editing sessions.
- **Terminology Standardization**: Standardized all UI labels, menus, alerts, and notifications from "Index / Indexing" to "Scan / Scanning / Scanned" throughout the app and graph dashboard.

### 🧠 Architecture Intelligence & Project TL;DR
- **Re-architected Project TL;DR**: Completely redesigned whole-project executive summaries. Structured prompt format prevents prompt echo/leakage with small local models (Qwen 0.5B).
- **Automated Architecture Breakdown**: TL;DRs now automatically append **💻 Tech Stack & Scale** (e.g. `Python, Shell, JavaScript (80 files)`), **🏛️ Key Domains** (e.g. `Testing, Authentication & Identity, Core`), and **📊 Entities** (`models, routes, events`).
- **Interactive TL;DR Dialog**: Added **Copy TLDR** (1-click markdown copy to macOS clipboard with notification) and **Open Map** (direct shortcut into the visual architecture graph).
- **Unified Info & TLDR Access**: Grouped `Info...` and `TLDR...` in the same section of the project menu, and added a **View TLDR** button directly inside the Project Info dialog.

### 🤖 Coding Agent Integration & Model Sync
- **1-Click Model Synchronization**: Automatically detects if a Cloud BYOK key (OpenAI, Claude, OpenRouter) is already configured in Map Agent and offers 1-click sync into Coding Agents without re-entering credentials.
- **Expanded Coding Presets**: Added Claude (Anthropic), OpenAI, OpenRouter, and Local Server (Ollama) presets alongside MiMo V2.6 Pro.
- **Dedicated Agent Routing**: Clear, individual routing switches for Claude Code, Cursor, Codex, Antigravity/Gemini, and opencode with resilient verification.
- **Categorized API Keys Settings**: Explicitly partitioned into `Map Agent (Cloud BYOK)` and `Coding Agent Models` for centralized credential management.

### 🖥️ macOS UI & Menu Hierarchy
- **Flattened Menu Hierarchy**: Eliminated Cocoa submenu overlap and stuck floating tooltips by replacing deeply nested submenus with accessible direct menus.
- **Mirrored Agent Menus**: Map Agent (`Used for maps, scanning & TLDRs` • `Active: [Model]`) and Coding Agent (`Used for Claude Code, Cursor & Codex` • `Active: [Model]`) now share identical, intuitive layouts and status lines.
- **Direct Recent Project Navigation**: The three most recently scanned projects are full menus in the main bar, complete with Info, TLDR, Scan, Auto-Scan, and Open Map.

### 🛡️ Stability, Auto-Updater & Resilience
- **Clean Network Error Handling**: Replaced raw Python socket/URL errors with clear, user-friendly messages (`"Could not connect to GitHub. Please check your internet connection and try again."`).
- **Milestone Version Ordering**: Updated in-app auto-updater (`src/updater.py`) to recognize clean milestone releases (`1.7`) as succeeding iterative letter patches (`1.7a < 1.7b < 1.7c < 1.7`).
- **Startup Crash Protection**: Fixed Cocoa menu item registration and added automated startup regression suites to ensure 100% launch reliability.

---

## [1.7a] - 2026-10-09
*Hybrid Engine & Flattened UI Preview*

### Added
- **True Hybrid Architecture Preview**: Multi-language structural static scanning with local & BYOK LLM semantic synthesis.
- **Resilient Agent Routing & Verification**: Non-intrusive diagnostic warnings for transient connection failures without disabling user preferences.
- **Enhanced Codex Integration**: Dual injection of `OPENAI_BASE_URL` and `OPENAI_API_BASE` in Codex config for broader CLI compatibility.
- **Thermal Profile & System Specs**: Battery-aware debouncing and passive thermal cooling guidelines documented.

---

## [1.6a] - 2026-10-08
*Release Automation & Milestone Consolidation*

### Added
- **Release Workflow Automation**: Release pipeline gated to explicit tags (`v*`) or manual triggers with automated artifact verification.
- **Letter-Based Auto-Updater**: Native comparison in `src/updater.py` with SHA256 checksum validation.

---

## [1.5b] - 2026-09-26
*Ranked Search, 2-Step Offers & Project TLDR*

### Added
- **Architectural Project TLDR**: `codebone_tldr` tool synthesizing concise architectural executive summaries of indexed codebases via MCP and HTTP API.
- **Ranked Search & Smart Filters**: `cb(query=...)` searches symbol names, comments, and summaries with confidence scoring; smart domain and asset filters.
- **2-Step Context Offer**: Initial call returns lightweight ranked offer with confidence and token estimate; `whisper=true` expands the full context.

---

## [1.5a] - 2026-09-26
*Graph Performance & Star Topology*

### Changed
- **Optimized Graph Density**: Large file groups sharing entities collapse into star topologies around central structural hubs, preventing edge budget exhaustion.
- **Neighbor Linking for Standalone Files**: Unconnected config and asset files link to nearest folder neighbours to eliminate isolated islands in the graph.

---

## [1.4b] - 2026-09-25
*Multi-Folder Workspace & Deepening Maps*

### Added
- **Multi-Folder Project Workspace**: Support for multiple project folders in workspace with sequential indexing and rolling snapshots.
- **Dynamic Map Deepening**: Call edges, import edges, SQL tables, and Supabase references folded into results at query time.
- **Unified Settings Window**: Consolidated modules, model configuration, API keys, and workspace management into a unified settings interface.

---

## [1.4a] - 2026-09-25
*Call Chains & Route Tracing*

### Added
- **Live Call Chains**: Visual call edges from API endpoints to backend route handlers and database tables.
- **Pruned Scan Trees**: Automatic exclusion of `node_modules`, `.git`, virtualenvs, and `dist` build folders.

---

## [1.3b] - 2026-09-24
*Graph Intelligence, Bridges & OpenRouter*

### Added
- **Import Graph Edges**: Cross-file dependency edges for Python and JS/TS imports.
- **Graph Community Clustering**: Louvain modularity clustering over co-occurrence graphs with structural hub labels.
- **Local Translation Bridge**: Anthropic ↔ OpenAI message translation bridge for multi-agent CLI interoperability.
- **OpenRouter Integration**: Native support for OpenRouter in Cloud BYOK and module presets.
- **Lightweight Delta Updates**: Delta update packages stripping base model files for instant bandwidth-friendly updates.

---

## [1.3a] - 2026-09-24
*Modules Library & Multi-Agent Routing*

### Added
- **Modules Model Library**: Pluggable models (MiMo V2.6 Pro, local/cloud endpoints) with per-app routing switches and macOS Keychain storage.
- **In-App Uninstaller**: Clean removal of application, models, caches, and LaunchAgent plists from Settings.
- **Relaunch Detection**: Smart single-instance management bringing existing menu forward.
- **Hardened Local API**: DNS rebinding protection and strict CORS guards.

---

## [1.2b] - 2026-09-23
*Multi-Client MCP Ecosystem & Native Launcher*

### Added
- **Zero-Config MCP Package**: `codebone-mcp` on npm allowing instant bridge invocation via `npx -y codebone-mcp`.
- **Multi-Client MCP Auto-Registration**: Automatic registration for Gemini / Antigravity IDE, Claude Desktop, and Cursor.
- **Native Mach-O Launcher**: Standalone binary ensuring instant menu bar icon visibility and Gatekeeper compatibility.
- **Concise `cb` MCP Tool**: Streamlined context query tool for LLM agent rules.
- **Automated Dependency Preflight**: 8-point system check (Python, Homebrew, CLT, cmake, git, Node.js).

---

## [1.2a] - 2026-09-23
*Live Graph UI, In-App Updater & macOS Integration*

### Added
- **Live Graph UI Redesign**: Slate-and-iris dark glassmorphism interface with category filter pills, tooltips, and interactive inspector drawer.
- **Native macOS Auto-Updater**: Automated update checking, downloading, codesign validation, and atomic bundle replacement.
- **SF Symbols & Full Disk Access Automation**: Native AppKit icons and automated privacy preflight checks.
- **Recent Projects History**: 1-click project switching directly in the main menu bar.

---

## [1.1b] - 2026-09-22
*Status Popover & Live Graph Polish*

### Added
- **Tailscale-Style Popover Header**: Master toggle switch, live status indicator dot, active model selector, and native symbols.
- **Live Graph Resilience**: Infinite loading spinner fixes and prominent "Scan Project Now" trigger.

---

## [1.1a] - 2026-09-22
*Apple Silicon Local Model & Native Cocoa Menu Bar*

### Added
- **Qwen 0.5B Architecture Unification**: Sub-second local inference with ~390 MB RAM footprint on Apple Silicon Metal.
- **Native Cocoa Menu Bar**: 100% native AppKit interface with settings, live stats, and ETA calculation.

---

## [1.0b] - 2026-09-22
*Deep Scan Mode & CodeBone Rebranding*

### Added
- **Deep Scan Mode**: Background 7B model re-analysis option with live menu bar progress reporting.
- **Brand Standardization**: Application bundle, CLI, MCP tools, and plists unified under the CodeBone name.
- **Day-One Performance Patch**: Level-of-detail filtering, WAL+RLock concurrency, and `.gitignore` respect.

---

## [1.0a] - 2026-09-22
*Initial Launch — Real-Time Architecture Intelligence*

### Added
- **24/7 Background Engine**: macOS menu bar assistant watching project files on save with battery-aware debouncing.
- **Apple Silicon Metal GPU Inference**: Local LLM inference via `llama-cpp-python` with Metal acceleration.
- **Semantic System Graph**: Real-time mapping of business domains and cross-module relationships.
- **Model Context Protocol (MCP)**: Native server for Claude Desktop, Cursor, Gemini, and Codex.
- **Secure Sandboxing**: Isolated XML container parsing with anti-jailbreak directives.
