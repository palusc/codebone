# Changelog

All notable changes to codebone will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Official milestone releases are clean numbers (`1.0`, `1.1`, `1.2`, `1.3`, `1.4`, `1.5`, `1.6`, `1.7`).
Development preview snapshots leading up to each milestone use letter releases (`.a`, `.b`, `.c`).

---

## [Unreleased]

---

## [1.7] - 2026-10-09
*Official Milestone Full Release (Current)*

### 🎯 Milestone Goal
Establish true hybrid scanning combining deterministic multi-language AST analysis with local and cloud LLM synthesis, eliminate macOS menu bar overlapping artifacts, and centralize coding agent routing for external tools (Claude Code, Cursor, Codex, Gemini/Antigravity).

### Added
- **True Hybrid Scan Engine**: Combines deterministic static multi-language AST scanning (Python, TS/JS, Go, Rust, Ruby, PHP, Java, C/C++) with local and BYOK LLM semantics for in-depth symbol, dependency, and architecture indexing.
- **1-Click Model Synchronization**: Automatic detection of configured Cloud BYOK keys in Map Agent with 1-click adoption into Coding Agents. (1.7a)
- **Expanded Coding Presets**: Ready-to-use presets for Claude (Anthropic), OpenAI, OpenRouter, and Local Server (Ollama) alongside MiMo V2.6 Pro. (1.7a)
- **Dedicated Agent Routing**: Explicit routing toggles for Claude Code, Cursor, Codex, Gemini/Antigravity, and opencode. (1.7a)
- **Categorized API Key Management**: Clean separation into Map Agent (Cloud BYOK) and Coding Agent Models. (1.7a)
- **Re-architected Project TL;DR**: Completely redesigned prompt-free project summaries for small local models, featuring automatic sections for Tech Stack & Scale, Key Domains, and Entities. (1.7b)
- **Interactive TL;DR Dialog**: Integrated 1-click Copy TLDR to clipboard with native macOS notifications and direct Open Map shortcut. (1.7b)
- **Cancelable & Resumable Scanning**: Advanced scan controls with instant Cancel Scan as well as Pause/Resume Scanning including live ETA calculation and phase indicators. (1.7c)
- **Per-Project Auto-Scan Toggle**: New Auto-Scan on Save switch directly in each project menu (ON by default) to temporarily pause automatic re-scanning during bulk file operations. (1.7c)

### Changed
- **Flattened Menu Hierarchy**: Eliminated nested Cocoa submenus and lingering tooltips for a sleek, responsive macOS menu bar experience.
- **Unified Terminology**: Standardized all user-facing strings and dialogs from "Index / Indexing" to "Scan / Scanning / Scanned".
- **Mirrored Agent Menus**: Map Agent and Coding Agent now share an identical, intuitive menu structure with live status rows.
- **Quick-Access Projects**: The 3 most recently scanned projects are now direct one-click entries in the main menu bar.

### Fixed
- **Menu Bar Startup Crash Fix**: Resolved missing menu instantiations and missing `time` import after menu flattening; guarded with automated regression tests.
- **Resilient Agent Routing**: Transient connection errors no longer automatically uncheck or reset user agent selections.
- **User-Friendly Network Errors**: Clear, actionable error messaging in the auto-updater when network connection is offline.

---

## [1.7c] - 2026-10-09
*Pre-Release*

### Added
- **Per-Project Auto-Scan Toggle**: Toggle `Auto-Scan on Save` directly within each project menu (ON by default) to control file-save scans per repository. (1.7c)
- **Cancelable Scan Controls**: Pause, resume, and instant cancel controls for active scans with live ETA displays in the menu bar. (1.7c)

### Changed
- **Terminology Standardization**: Consistent rename across all menu items, dialogs, and notifications from "Index" to "Scan". (1.7c)

---

## [1.7b] - 2026-10-09
*Pre-Release*

### Added
- **Architecture Highlights in TL;DR**: Structured output of Tech Stack, Key Domains, and Entities in the Project TL;DR dialog. (1.7b)
- **Copy TLDR & Map Shortcuts**: Interactive buttons in the TL;DR dialog for 1-click clipboard copy and direct graph navigation. (1.7b)

### Fixed
- **Menu Bar Startup Crash**: Resolved `AttributeError` and missing `time` import preventing the menu bar app from launching. (1.7b)
- **Menu Item Registration**: Restored `open_map_item`, `documentation_item`, `feedback_item`, `check_updates_item`, and `uninstall_item`. (1.7b)

---

## [1.7a] - 2026-10-09
*Pre-Release*

### Added
- **Hybrid Architecture Preview**: Initial integration of multi-language AST scanning with LLM semantic synthesis. (1.7a)
- **Resilient Agent Routing**: Non-blocking connection warnings without silently reverting user choices. (1.7a)
- **Codex Dual Injection**: Export both `OPENAI_BASE_URL` and `OPENAI_API_BASE` for broader CLI tool compatibility. (1.7a)
- **Thermal & Battery Guidelines**: Documented battery-aware debouncing and whisper-quiet CPU throttling budgets. (1.7a)

### Changed
- **macOS Menu Flattening**: Flattened deep submenu trees to avoid Cocoa clipping and overlapping artifacts. (1.7a)

---

## [1.6] - 2026-10-08
*Official Milestone Release*

### 🎯 Milestone Goal
Full automation of the release pipeline via GitHub Actions, native in-app auto-updater with robust version comparison, and automated Homebrew distribution.

### Added
- **GitHub Actions Release Pipeline**: Automated workflow building signed macOS DMGs and ZIP archives on version tag pushes (`v*`).
- **Native In-App Auto-Updater**: Robust version comparison logic in `src/updater.py` supporting milestones and letter pre-releases (`1.6a < 1.6b < 1.6`). (1.6a)
- **Checksum Validation**: Automated generation and verification of SHA-256 checksums for all release artifacts. (1.6a)
- **Homebrew Formula Sync**: Automated updates of download URL and SHA-256 checksum in `Formula/codebone.rb`. (1.6b)
- **Release CI Automation**: GitHub Actions workflow creating signed DMG files and uploading release assets. (1.6b)

### Changed
- **Release Gating**: Decoupled regular `main` branch pushes from releases; releases are triggered strictly by explicit version tags.
- **Standardized Versioning**: Consolidated release hierarchy into clean milestone generations with transparent preview stages.

### Fixed
- **Release Race Conditions**: Eliminated race conditions when simultaneously building DMGs and updating the repository.

---

## [1.6b] - 2026-10-08
*Pre-Release*

### Added
- **Release CI Automation**: GitHub Actions workflow creating signed DMG files and uploading release assets. (1.6b)
- **Homebrew Formula Sync**: Automated updates of `Formula/codebone.rb` with generated SHA-256 checksums. (1.6b)

---

## [1.6a] - 2026-10-08
*Pre-Release*

### Added
- **Release Workflow Automation**: Tag-gated CI releases (`v*`) preventing accidental release creation on `main`. (1.6a)
- **Letter-Based Auto-Updater**: Native version comparison in `src/updater.py` supporting letter pre-releases with SHA-256 validation. (1.6a)

---

## [1.5] - 2026-09-26
*Official Milestone Release*

### 🎯 Milestone Goal
Scalable graph performance for large repositories via star topologies, ranked semantic search, and automated architectural summaries via MCP.

### Added
- **Standalone File Linking**: Unlinked configuration and documentation files bind to neighboring directories to eliminate orphan nodes. (1.5a)
- **Star Topology in Graph**: Large entity clusters collapse into star topologies around central hubs, conserving edge budgets. (1.5a)
- **Ranked Search**: `cb(query=...)` searches symbol names, comments, and code lines with confidence scoring (`high` / `medium` / `low`). (1.5b)
- **2-Step Context Offer Protocol**: Two-stage context delivery; initial query returns matches overview, `whisper=true` expands full token context. (1.5b)
- **Smart Filtering & Freshness Indicator**: Domain and asset filtering (`assets=true`) plus real-time graph freshness indicators. (1.5b)
- **Architectural Project TL;DR**: `codebone_tldr` MCP tool and `/codebone/tldr` HTTP endpoint for concise codebase summaries. (1.5c)

### Changed
- **Consolidated MCP Tooling**: `cb` merges imports and cross-references; removed redundant individual tools.

### Fixed
- **Graph Fragmentation**: Resolved layout breaks and isolated clusters on large codebases.

---

## [1.5c] - 2026-09-26
*Pre-Release*

### Added
- **Architectural Project TL;DR via MCP & API**: Introduced `codebone_tldr` and `/codebone/tldr` for comprehensive architectural overviews of indexed codebases. (1.5c)

---

## [1.5b] - 2026-09-26
*Pre-Release*

### Added
- **Ranked Word and Meaning Search**: Precise searching across symbols, comments, and files with scoring (`cb(query=...)`). (1.5b)
- **2-Step Offer Protocol**: Lightweight match offers to conserve AI agent token budgets (`whisper=true` for full context). (1.5b)
- **Smart Filters**: Domain boosting and asset file filtering. (1.5b)

---

## [1.5a] - 2026-09-26
*Pre-Release*

### Changed
- **Graph Density Optimization**: Large file clusters collapse into star topologies around central structural hubs. (1.5a)
- **Neighbor Linking**: Automated linking of isolated config and docs files to adjacent directory peers. (1.5a)

---

## [1.4] - 2026-09-25
*Official Milestone Release*

### 🎯 Milestone Goal
Support for multi-folder project workspaces and deeper system graph analysis via dynamic call chains and SQL/route discovery.

### Added
- **Live Call Chains**: Visual call edges from frontend routes to backend handlers and Supabase/SQL tables (`Calls: /api/... -> ...`). (1.4a)
- **Dynamic Map Deepening**: Re-evaluation of imports, DDL tables, and file functions at query time (`source_facts`). (1.4a)
- **Multi-Folder Project Workspaces**: Support for multiple project folders in a shared workspace with sequential background scanning and rolling snapshots. (1.4b)
- **Unified Settings Window**: Centralized settings for modules, models, API keys, and workspace paths. (1.4b)

### Changed
- **Clean Scan Trees**: Automated pruning of `node_modules`, `.git`, virtualenvs, and build folders (`dist`).
- **Graph Layout Stability**: Jittered-grid initialization prevents empty viewports on opening the graph.

### Fixed
- **MCP Scan Adoption**: Stabilized path resolution under `scan_path` and preserved route depths.
- **Resilient Server Responses**: Connection tests robustly tolerate truncated error bodies.

---

## [1.4b] - 2026-09-25
*Pre-Release*

### Added
- **Multi-Folder Workspaces**: Support for multiple project folders with rolling snapshots. (1.4b)
- **Unified Settings**: Grouped modules, models, and API keys into a single settings menu. (1.4b)

### Fixed
- **Scan Adoption**: Fixed route depths and stabilized error handling during connection setup. (1.4b)

---

## [1.4a] - 2026-09-25
*Pre-Release*

### Added
- **Dynamic Map Deepening**: Dynamic loading of import edges and table references at query time. (1.4a)
- **Live Call Chains**: Visualizing call edges from endpoints to handlers in the graph. (1.4a)

---

## [1.3] - 2026-09-24
*Official Milestone Release*

### 🎯 Milestone Goal
Deliver a flexible model library with macOS Keychain security, multi-agent routing, and advanced graph community detection via Louvain modularity.

### Added
- **Module Model Library**: Support for arbitrary Anthropic and OpenAI compatible endpoints (including MiMo V2.6 Pro) with secure macOS Keychain storage. (1.3a)
- **In-App Uninstaller**: Clean removal of app, models, caches, preferences, and MCP registrations directly from Settings. (1.3a)
- **Import Graph Edges**: Cross-file static links for Python and TypeScript/JavaScript imports in the system graph. (1.3b)
- **Louvain Community Clustering**: Modularity-based community detection (`networkx`) over the co-occurrence graph with labels based on structural hubs. (1.3b)
- **Local Translation Bridge**: Translation between Anthropic and OpenAI message formats for seamless CLI agent connectivity. (1.3c)
- **OpenRouter Integration**: Native support for OpenRouter across all module and routing surfaces. (1.3c)
- **Lightweight Delta Updates**: Delta update ZIPs without base model files for minimal download sizes. (1.3c)

### Changed
- **Quick-Toggle Module Row**: Dedicated toggle row in the menu bar for coding agents.
- **Hardened Local Server**: DNS rebinding protection and strict CORS guards on all localhost endpoints.

### Fixed
- **Routing Stability**: Fixed issues when toggling Claude Code and opencode.
- **Relaunch Detection**: Launching an already running instance brings the menu bar to focus instead of exiting silently.

---

## [1.3c] - 2026-09-24
*Pre-Release*

### Added
- **Translation Bridge & OpenRouter**: Anthropic ↔ OpenAI message translation and native OpenRouter support. (1.3c)
- **Lightweight Delta Updates**: Delta update packages without base models for fast downloads. (1.3c)

### Fixed
- **Routing Stability**: Reliable switching of coding agents to external APIs. (1.3c)

---

## [1.3b] - 2026-09-24
*Pre-Release*

### Added
- **Import Graph Edges**: Cross-file import edges for Python and JS/TS in the system graph. (1.3b)
- **Graph Community Clustering**: Louvain clustering for detecting cohesive architecture domains. (1.3b)

---

## [1.3a] - 2026-09-24
*Pre-Release*

### Added
- **Modules Model Library**: Pluggable models with routing toggles and secure macOS Keychain storage. (1.3a)
- **In-App Uninstaller**: Full uninstallation routine for application and user data. (1.3a)
- **Reliable Indexing**: Cooperative background scans with file-based locks. (1.3a)

---

## [1.2] - 2026-09-23
*Official Milestone Release*

### 🎯 Milestone Goal
Complete overhaul of the live graph interface to modern dark glassmorphism, zero-config MCP distribution via npm, and deeper macOS system integration.

### Added
- **Live Graph UI Redesign**: Modern slate-and-iris dark glassmorphism interface with category filter pills, hover tooltips, and interactive inspector drawer. (1.2a)
- **Native macOS Auto-Updater**: Fully automated download, signature verification, and atomic bundle swap with restart. (1.2a)
- **Recent Projects History**: Fast project switching directly in the main menu. (1.2a)
- **Zero-Config MCP Package**: Published `codebone-mcp` to npm for instant bridge usage via `npx -y codebone-mcp`. (1.2b)
- **Multi-Client MCP Auto-Registration**: Automated configuration for Gemini / Antigravity IDE, Claude Desktop, and Cursor. (1.2b)
- **Native Mach-O Launcher**: Standalone launcher binary for guaranteed menu bar visibility and Gatekeeper compliance. (1.2b)
- **Direct `cb` MCP Tool**: Streamlined lookup tool for integration into AI agent system prompts. (1.2b)

### Changed
- **Apple SF Symbols**: Used native AppKit symbol icons across the entire menu hierarchy.
- **Full Disk Access Automation**: Automated TCC permission checking with direct System Settings link.

### Fixed
- **Signature & Bundle Structure**: Fixed symlink issues in signed DMGs and NSOpenPanel runloop handling.

---

## [1.2b] - 2026-09-23
*Pre-Release*

### Added
- **Zero-Config MCP Package**: `codebone-mcp` on npm for instant startup without cloning. (1.2b)
- **Multi-Client MCP Registration**: Automated configuration for Antigravity, Claude, and Cursor. (1.2b)
- **Native Mach-O Launcher**: Standalone launcher for macOS AppKit menu bar icon. (1.2b)
- **Compact `cb` Tool**: Fast context access for LLM agents. (1.2b)

---

## [1.2a] - 2026-09-23
*Pre-Release*

### Added
- **Live Graph UI Redesign**: New dark glassmorphism design with interactive inspector drawer. (1.2a)
- **Native macOS Auto-Updater**: Background check and atomic bundle swap. (1.2a)
- **SF Symbols & Full Disk Access**: Native symbols and automated FDA preflight. (1.2a)
- **Recent Projects History**: 1-click project history in the main menu. (1.2a)

---

## [1.1] - 2026-09-22
*Official Milestone Release*

### 🎯 Milestone Goal
Reduce memory footprint on Apple Silicon by standardizing on Qwen 0.5B and delivering a purely native macOS AppKit menu bar experience.

### Added
- **Qwen 0.5B Model Standardization**: Sub-second inference with Apple Silicon Metal acceleration using only ~390 MB RAM. (1.1a)
- **Native Cocoa Menu Bar**: 100% native AppKit user interface with status, settings, and live ETA calculation. (1.1a)
- **Project Baseline Overview**: Initial load time estimation and progress display for large codebases. (1.1a)
- **Tailscale-Style Popover Header**: Master toggle, status LED, model selector, and native icons in popover header. (1.1b)
- **Live Graph Resilience**: Quick fixes for graph loading animations. (1.1b)

### Changed
- **Enhanced Dashboard UX**: Prominent "Scan Project Now" button in the dashboard header.

### Fixed
- **Live Graph Resilience**: Resolved infinite loading spinners in the knowledge graph dashboard.

---

## [1.1b] - 2026-09-22
*Pre-Release*

### Added
- **Tailscale-Style Popover Header**: Master toggle switch and status LED in header. (1.1b)
- **Live Graph Resilience**: Prominent scan button and fixed loading animations. (1.1b)

---

## [1.1a] - 2026-09-22
*Pre-Release*

### Added
- **Qwen 0.5B Standardization**: Local lightweight model on Apple Silicon Metal. (1.1a)
- **Native Cocoa Menu Bar**: AppKit menu bar interface with live statistics. (1.1a)

---

## [1.0] - 2026-09-21
*Official Milestone Release*

### 🎯 Milestone Goal
Initial release of codebone as a 24/7 local macOS background assistant with Metal GPU inference and native MCP interface for AI coding tools.

### Added
- **24/7 Background Engine**: Menu bar assistant for continuous file watching with battery-friendly debouncing (0.5s AC, 15s battery). (1.0a)
- **Apple Silicon Metal GPU Inference**: Local model execution via `llama-cpp-python` with Metal hardware acceleration. (1.0a)
- **Semantic System Graph**: Real-time mapping of business domains, cross-links, and module dependencies. (1.0a)
- **Model Context Protocol (MCP)**: Native server for Claude Desktop, Cursor, Gemini, and Codex. (1.0a)
- **Security Sandboxing**: Source code encapsulation in isolated XML containers with anti-prompt-injection directives. (1.0a)
- **Deep Scan Mode**: Optional background deep analysis with 7B model and live menu bar dashboard. (1.0b)

### Changed
- **Brand Standardization**: Harmonized all bundles, LaunchAgent plists, CLI commands, and MCP names under "codebone".

### Fixed
- **Day-One Stability Patch**: Concurrency with WAL+RLock, Level-of-Detail filtering, move detection, and strict `.gitignore` compliance.

---

## [1.0b] - 2026-09-21
*Pre-Release*

### Added
- **Deep Scan Mode**: Optional background deep analysis with 7B model. (1.0b)
- **Brand Standardization**: Standardized all strings and plists to codebone. (1.0b)

### Fixed
- **Day-One Patch**: WAL+RLock concurrency, Level-of-Detail filtering, and `.gitignore` compliance. (1.0b)

---

## [1.0a] - 2026-09-21
*Pre-Release*

### Added
- **24/7 Background Engine**: File watching on save with battery-friendly debouncing. (1.0a)
- **Metal GPU Inference**: Local inference with Apple Silicon hardware acceleration. (1.0a)
- **Semantic System Graph**: Automated mapping of business domains. (1.0a)
- **Model Context Protocol (MCP)**: Native interface for Claude Desktop, Cursor, Gemini, and Codex. (1.0a)
- **Security Sandboxing**: Isolated XML containers for analyzed source code. (1.0a)
