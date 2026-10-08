# Changelog

All notable changes to codebone will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Official release downloads on GitHub are the base `.a` versions (`1.0a`, `1.1a`, `1.2a`, `1.3a`, `1.4a`, `1.5a`, `1.6a`).
Incremental updates within each series are documented as distinct letter releases (`.b`, `.c`, `.d`, ...).

---

## [Unreleased]

### Changed
- **Cleaner project navigation**: The three most recently scanned projects are full project menus directly in the main menu. `Projects` lists only the remaining folders, so no project is duplicated; every project menu contains Index, TLDR, map statistics, Finder and removal actions.
- **Clear model roles**: Settings now separates codebone's **Map Model** from the optional **Coding Agent** model. MCP setup and common support destinations moved into **Help & Quick Links**.
- **Safer recent-history cleanup**: Clear Recent Projects now explains that it only removes recent shortcuts and leaves workspace projects, saved maps and source folders untouched.

---

## [1.6a] - 2026-10-08
*Official release download on GitHub*

### Added
- **Release workflow automation & letter versioning**: Release pipeline gated to explicit tags (`v*`) or manual triggers to prevent automated release spam on main; letter-based version comparison in native in-app auto-updater (`src/updater.py`).
- **Milestone consolidation**: Streamlined release hierarchy into full generations with granular `.b`, `.c`, `.d` interim tracking.

---

## [1.5d] - 2026-09-26

### Added
- **Project TLDR via MCP, API and Projects menu**: `codebone_tldr` and `/codebone/tldr` now explain an entire indexed project—its purpose, responsibilities and main architecture—instead of summarizing individual documents or source files. The active project is the default; another workspace project can be selected by name.

---

## [1.5c] - 2026-09-26

### Changed
- **`cb(query=...)` answers in two steps**: The first call returns a short offer: best file with line, confidence (high / medium / low), related files and tests, and the token size of the full answer. `whisper=true` on the same call returns the full ranked answer. A small change usually needs only the offer. HTTP: `offer=true` on `/codebone/context`.

---

## [1.5b] - 2026-09-26

### Added
- **Ranked word and meaning search**: `cb(query=...)` searches symbol names, comments, code lines, file names and summaries; the best 8 come back with a score and matching lines (`L79: ...`). A symbol name in the query also lists where it is defined and every other file:line that references it. Same-named files in several places collapse into one entry.
- **Smart filters**: `domain` and `file` no longer hide hits when a query is given. They boost, and the result says how many hits are inside the domain and how many elsewhere. With no query, a domain that matches nothing lists the domains that exist.
- **Asset filtering**: Image, font and other asset files are hidden unless `assets=true`; a note says how many more matched.
- **One MCP tool for lookup**: `cb` now includes imports / imported by for each hit; `codebone_context` and `codebone_graph` are removed from the MCP server (the HTTP endpoints stay).
- **Index freshness indicator**: Shown on every result: time since the last update and how many files changed on disk since.

---

## [1.5a] - 2026-09-26
*Official release download on GitHub*

### Changed
- **The graph no longer fragments on big groups**: Up to 10 files sharing a table, route or event are still drawn pairwise; a larger group collapses into a star through its most-connected member, so every member stays linked at n-1 edges instead of the ~6n the peer window spent, and the global edge cap no longer truncates whatever comes after.
- **Files nothing connects to are no longer islands**: Docs, config and assets that share no table, route or event with anyone get one directory link to a neighbour in their own folder.

---

## [1.4c] - 2026-09-25

### Added
- **Multi-folder project workspace**: "Projects" replaces the single folder picker; multiple folders join the workspace and "Scan Project Now" walks them sequentially with rolling snapshots.
- **Unified Settings**: Modules, Model, API Keys, MCP, Project and Scan Data unified into one Settings menu.

### Changed
- **Pruned scan trees**: `node_modules`, `.git`, virtualenvs and `dist` are pruned from indexing.
- **Graph spatial layout**: Jittered-grid initialization with capped per-tick speed preventing empty graph viewports.

---

## [1.4b] - 2026-09-25

### Fixed
- **Scan adoption from MCP clients**: Paths travel under `scan_path`; the `/pug/` alias fallback only fires when the route itself is missing.
- **Template route depths**: Template fetches keep their depth (`/api/users/[*]/posts`), and DDL/`.sql` tables are recognised without phantom entries.
- **Error tolerance**: Linking a project after startup serves refreshed view; Test Connection and Update Installation tolerate truncated error bodies.

---

## [1.4a] - 2026-09-25
*Official release download on GitHub*

### Added
- **Dynamic map deepening at query time**: Sources are re-read when context is requested (`src/imports.py: source_facts`): import edges, `fetch('/api/...')` call edges to route handlers, SQL DDL and Supabase `.from('table')` references, file roles (`route POST /api/subs`, `page /subs`) and a one-line content record for files without a stored summary are folded into the rows at read time. Existing indexes pick this up on the next query.
- **Call chains in context and links**: Search results and `/codebone/links` show `Calls: /api/subs -> app/api/subs/route.ts (tables: customers)`; the graph draws call edges solid green and import edges dashed grey.

---

## [1.3j] - 2026-09-24

### Added
- **Import graph edges**: Files connected through Python and JS/TS imports (`src/imports.py`) in addition to shared entities.

---

## [1.3i] - 2026-09-24

### Added
- **Local translation bridge**: Direct Anthropic ↔ OpenAI message translation bridge allowing Claude Code to speak to any OpenAI-compatible module.

---

## [1.3h] - 2026-09-24

### Added
- **OpenRouter integration**: Native support for OpenRouter across Cloud BYOK and Modules presets.

---

## [1.3g] - 2026-09-24

### Added
- **Graph Community Clustering**: `Storage.communities()` runs Louvain modularity-based community detection (via `networkx`) over the co-occurrence graph; clusters are labelled after their highest-degree structural hub.

---

## [1.3f] - 2026-09-24

### Changed
- **Lightweight delta updates**: Published `*-update.zip` strips the ~490 MB base model, saving bandwidth and disk writes on code updates.
- **Full file coverage**: Assets, lockfiles, images, binaries and archives catalogued with size and extension tags.

### Fixed
- **Connectivity reporting**: Fix under-reported node and connection counts by including domain-shared edges.

---

## [1.3e] - 2026-09-24

### Changed
- **Grouped Settings**: Model moved into Settings, submenus for "Project" and "Scan Data", release race condition fixes.

---

## [1.3d] - 2026-09-24

### Added
- **Modules switch row**: Dedicated master on/off switch row in the menu bar instead of nested checkboxes.

---

## [1.3c] - 2026-09-24

### Fixed
- **Routing stabilization**: Fix modules getting stuck routing Claude Code/opencode off their normal API.
- **Curated release notes**: Human-curated changelog sections used in release notifications.

---

## [1.3b] - 2026-09-24

### Added
- **Relaunch detection**: Launching an already running instance brings its menu forward instead of exiting silently.
- **Release CI automation**: GitHub Actions release pipeline building signed DMGs and updating Homebrew formulas.

---

## [1.3a] - 2026-09-24
*Official release download on GitHub*

### Added
- **Modules model library**: Model APIs (preset for MiMo V2.6 Pro, or any Anthropic- or OpenAI-format endpoint) with per-app routing switches. Claude Code and opencode are configured directly with keys stored in macOS Keychain.
- **Reliable indexing & compact context**: Incremental cooperative scans with per-file locks; hardened local API with DNS rebinding protection and CORS guards.
- **In-app Uninstaller**: Settings > Uninstall codebone... cleanly removes application, data, models, logs, caches, preferences, login items and MCP client entries.

---

## [1.2i] - 2026-09-23

### Added
- **Native Mach-O launcher**: Native launcher binary ensuring menu bar icon visibility and macOS Gatekeeper compatibility.
- **Reopen handler**: Application reopen handler support.

---

## [1.2h] - 2026-09-23

### Added
- **Direct `cb` tool shortcut**: Established concise MCP tool for LLM context queries and agent rules.

---

## [1.2g] - 2026-09-23

### Added
- **Robust installer preflight**: 8-point dependency check verifying Python >= 3.10, Homebrew, CLT, cmake, git, curl, Node.js with automated fallbacks.

---

## [1.2f] - 2026-09-23

### Added
- **Multi-client MCP auto-registration**: Automatic registration for Gemini / Antigravity IDE alongside Claude Desktop and Cursor.
- **Setup banner**: Initial-days setup ping banner.

---

## [1.2e] - 2026-09-23

### Added
- **Full Disk Access automation**: Automatic preflight check with direct link to macOS Privacy & Security preferences.

---

## [1.2d] - 2026-09-23

### Added
- **Recent Projects history**: 1-click project switching in the main menu; expanded README FAQ section.

---

## [1.2c] - 2026-09-23

### Fixed
- **Bundle code signing**: Resolved bundle symlinks and codesigned DMG/ZIP archives; NSOpenPanel runloop dismissal fix.

---

## [1.2b] - 2026-09-23

### Added
- **Zero-config MCP setup**: `codebone-mcp` npm package published for running the MCP bridge via `npx -y codebone-mcp`.

---

## [1.2a] - 2026-09-23
*Official release download on GitHub*

### Added
- **In-app auto-updater**: Automated check, download, codesign verification, atomic bundle swap and restart.
- **Built-in feedback & bug reporting**: Menu bar dialog and modal in Live Graph UI with automated credential redaction.
- **Live Graph UI redesign**: Slate-and-iris dark glassmorphism, category filter pills, hover tooltips, interactive inspector drawer.
- **Apple SF Symbols**: Native macOS icons throughout the menu bar and application controls.
- **macOS Full Disk Access**: TCC permission probing and system settings guidance.

---

## [1.1d] - 2026-09-22

### Fixed
- **Live Graph resilience**: Fix infinite loading spinner, add knowledge graph tile in header, prominent "Scan Project Now" button.

---

## [1.1c] - 2026-09-22

### Added
- **Tailscale-style popover header**: Toggle switch, status indicator dot, active model selector in Settings, and dedicated SF Symbols.

---

## [1.1b] - 2026-09-22

### Added
- **Native Cocoa menu bar**: 100% native AppKit interface with functional Settings, streamlined stats and clean header.

---

## [1.1a] - 2026-09-22
*Official release download on GitHub*

### Added
- **Qwen 0.5B unification**: Standardized local model architecture with sub-second inference and ~390 MB RAM footprint.
- **Project baseline overview**: Initial load time estimation and live ETA progress tracking for large codebases.

---

## [1.0d] - 2026-09-22

### Added
- **Deep Scan Mode**: Background 7B model re-analysis option and live menu bar dashboard.

---

## [1.0c] - 2026-09-22

### Changed
- **Rebranding**: Package, app bundle, MCP tools, strings, and LaunchAgent plists standardized from PUG to CodeBone.

---

## [1.0b] - 2026-09-22

### Fixed
- **Day-One Patch**: Live Graph UI, Level-of-Detail context filtering, batch burst protection, WAL+RLock, .gitignore respect, move detection.

---

## [1.0a] - 2026-09-22
*Official release download on GitHub*

### Added
- **24/7 background engine**: macOS menu bar assistant watching project files on save with battery-aware debouncing (0.5s AC, 15s battery).
- **Apple Silicon Metal GPU inference**: Local LLM inference via `llama-cpp-python` with Metal acceleration.
- **Semantic System Graph**: Real-time mapping of business domains and cross-module relationships.
- **Model Context Protocol**: MCP server for Claude Desktop, Cursor, Gemini and Codex.
- **Security & Sandboxing**: Untrusted source wrapped in isolated XML containers with anti-jailbreak directives.
