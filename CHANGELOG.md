# Changelog

All notable changes to codebone will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.0] - 2026-09-26

### Changed
- **The graph no longer fragments on big groups.** Up to 10 files sharing a table, route or event are still drawn pairwise; a larger group collapses into a star through its most-connected member, so every member stays linked at n-1 edges instead of the ~6n the peer window spent, and the global edge cap no longer truncates whatever comes after.
- **Files nothing connects to are no longer islands.** Docs, config and assets that share no table, route or event with anyone get one directory link to a neighbour in their own folder.

## [1.4.2] - 2026-09-25

Covers the former 1.4.0, 1.4.1 and 1.4.2.

### Added
- **Several project folders at once.** "Projects" replaces the single folder picker: the panel takes a multi-selection, every picked folder joins the workspace, and "Scan Project Now" walks them one after the other. Each folder keeps its own rolling snapshot, so coming back to a project is an adoption instead of a rescan. Workspace folders can be dropped again without losing their scan history.
- **One API Keys menu in Settings.** The Cloud BYOK key and every module's key are listed in one place; a key can be edited straight from there and still lands in the macOS Keychain.
- **The map deepens at query time, no rescan needed.** Sources are re-read when context is requested (`src/imports.py: source_facts`): import edges, `fetch('/api/...')` call edges to route handlers, SQL DDL and Supabase `.from('table')` references, file roles (`route POST /api/subs`, `page /subs`) and a one-line content record for files without a stored summary are folded into the rows at read time. Existing indexes pick this up on the next query.
- **Call chains in context and links.** Search results and `/codebone/links` show `Calls: /api/subs -> app/api/subs/route.ts (tables: customers)`; the graph draws call edges solid green and import edges dashed grey.

### Changed
- **Settings is one menu.** Modules, Model, API Keys, MCP, Project and Scan Data live together under "Settings"; "Select Project Folder" and "Recent Projects" merged into "Projects".
- **Modules start routed.** The first time the Modules switch goes on, every app the module can serve is enabled; a later off/on cycle restores exactly what was chosen before.
- **Copy for Other Apps offers Model ID and API key only**; the base URLs are built by codebone itself.
- **Dependency, VCS and build trees are pruned from scans** (`node_modules`, `.git`, virtualenvs, `dist`, ...), which is what made an 800-file repo scan as 150k+ files. Stale rows from older versions are dropped on the next scan.
- **Files without a summary are no longer invisible.** Markdown, JSON, YAML, shell and HTML files get a sanitised one-line content note; credential-shaped and binary files are labelled from their extension only and never parsed.

### Fixed
- **The graph page stayed empty on larger projects.** Nodes started on a packed circle, so unbounded `1/d^2` repulsion integrated into coordinates around 1e26 and nothing landed in the viewport. Nodes now start on a jittered grid with a capped per-tick speed, which also makes the layout linear in file count.
- Scan adoption from the MCP clients (paths travel under `scan_path`; the `/pug/` alias fallback only fires when the route itself is missing), template fetches keep their depth (`/api/users/[*]/posts`), and DDL/`.sql` tables are recognised without phantom entries.
- Linking a project after startup could keep serving the cached empty view; Test Connection and Update Installation no longer crash on truncated error bodies or an unbound variable.
- A manual version bump is no longer overwritten by the release job.

### Removed
- **Deep Scan Mode.** The separate large-model re-analysis path is gone from the Model menu, the service and the config.

## [1.3.9] - 2026-09-24

Covers the former 1.3.5 to 1.3.9.

### Added
- **The map covers every real file.** Lockfiles, images, fonts, archives, binaries and build output get a node too, catalogued by category and size (`_catalog_asset`) when they are too large or binary to analyse. `.gitignore` rules are no longer applied; only credential-shaped files (`.env`, keys, `credentials*`) stay path-only nodes whose content is never read.
- **Import edges**: files are connected through their Python and JS/TS imports (`src/imports.py`), not only through shared tables, routes and events.
- **Local Anthropic to OpenAI translation bridge for Modules.** Claude Code speaks the Anthropic Messages API, so an OpenAI-only endpoint never worked; requests now run through a local bridge that translates messages, tools and streaming responses. The module's API key is only forwarded, never stored.
- **OpenRouter support** for Cloud BYOK and Modules (OpenAI-format preset).

### Changed
- **Graph clusters come from real structure.** `Storage.communities()` runs Louvain community detection (via `networkx`) over the table/route/event/domain co-occurrence graph; each cluster is labelled after its highest-degree member. Graph lines are more visible.
- **Settings restructured** into "Project" (Adopt/Link Scan, Copy Context, Open in Finder, View Logs, Disk Access) and "Scan Data" (Export/Import Scan, Reset Knowledge Map) submenus.

### Fixed
- **In-app updates no longer download the ~490 MB base model** on every release: the release build also publishes a `*-update.zip` without it, and the updater prefers it.
- A scan could silently skip unreadable subfolders and still report "Scan Complete"; they are now surfaced in the notification.
- The Nodes/Connections count under-reported connectivity because it ignored domain-shared edges.
- Release job: back-to-back releases no longer fail on a non-fast-forward push, and release notes read the triggering commit instead of the bot's own.

## [1.3.4] - 2026-09-24

Covers the former 1.3.0 to 1.3.4.

### Added
- **Uninstall from inside the app** (Settings > Uninstall codebone...): removes the app, data and models, logs, caches, preferences, login items and codebone's entries in the Claude Code, Claude Desktop, Cursor and Gemini configs, and runs `brew`/`npm uninstall` when those installed it. Project folders are never touched. `./uninstall.sh --dry-run | --yes` is the terminal fallback (`src/uninstall.py`).
- **Context that navigates.** `cb()` returns layout, domains, key entities and a one-line summary per file (about 1,500 tokens for a 56-file, 125,000-token project); `cb(query="several words")` ranks files by name, entities and summary; `codebone_graph(file=...)` shows linked files.
- **Modules**: a library of model APIs (preset for MiMo V2.6 Pro, or any Anthropic- or OpenAI-format endpoint) with a switch per app. Claude Code and opencode are configured directly (keys in the macOS Keychain, previous settings restored on off and uninstall), other apps get copy buttons. A master on/off switch remembers which apps were active, "Fix Stuck Connection (Reset to Normal)" restores both apps unconditionally, and switching an app onto a module verifies the endpoint and reverts if it does not answer. Quick Links: OpenRouter dashboard, API keys, docs.
- Model status (download progress, "no model, using heuristics") in the graph page and `/codebone/status`.

### Changed
- One install recipe (`scripts/build_bundle.sh`) behind the DMG, ZIP/Homebrew and `install.sh`: bundled Python 3.13.15, packages pinned in `requirements.lock`, native launcher, pinned base model (exact Hugging Face revision + SHA-256).
- Scans are incremental and cooperative: one lock per file, unreadable folders never wipe the index, files over 1 MB, binaries and secret-like files are skipped, deletions and moves reach the index, one rolling snapshot per project.
- Per-project MCP files (`.cursor`, `.gemini`, `.agents`) are no longer written into indexed folders; global client configs are only touched for installed clients and no longer pin a port.
- Main menu restructured: Modules has its own switch row, Model moved into Settings. Release notes in the updater come from this changelog; `package.json` and the README badge are kept in sync with every release.

### Fixed
- **Live Graph never finished loading** on real projects: the layout is now spatial-grid based and draws only when something changes; file names and summaries can no longer inject HTML or script into the page.
- **Local API hardening**: foreign `Host` headers (DNS rebinding) and cross-origin requests are refused, export never overwrites files, feedback and payloads are size-limited.
- Switching projects no longer serves the previous project's index; a damaged index database is moved aside instead of crashing on every start; a second app instance exits instead of sharing the database; relaunching a running app brings its menu forward instead of exiting silently.
- Model output is grounded in the code (no invented tables, routes or events); the update installer extracts with `ditto`, refuses unsafe archive paths and swaps the bundle with rollback; test runs no longer touch the developer's real configuration.

## [1.2.2] - 2026-09-23

Covers the former 1.2.0 to 1.2.2.

### Added
- **In-app auto-updater** (Settings > Check for Updates...): download, signature verification, atomic bundle replacement, restart.
- **Built-in feedback and bug reporting**: menu bar dialog and a modal in the Live Graph UI, auto-attaching OS, codebone version, provider, metrics and recent logs with credentials redacted; stored locally, with a pre-filled GitHub Issue link.
- **Multi-client MCP auto-registration** for Gemini / Antigravity IDE alongside Claude Desktop and Cursor, plus dynamic port detection (`8053`, then `8054+`) that updates the client configs.
- **Recent Projects** in the main menu (last 10), **Full Disk Access guidance** with automatic TCC probing and Reveal in Finder, a first-week setup beacon (`#mcp-setup`), and a bundle venv and permissions resolver for DMG drag-and-drop installs.
- **Live Graph redesign**: slate-and-iris glassmorphism instead of neon, category filter pills, hover tooltips, an inspector drawer, and Apple SF Symbol icons across the menu.

### Changed
- Release packaging is two downloads: `codebone-macos-arm64.dmg` and `.zip`.
- Default Cloud BYOK models are `claude-sonnet-5` (Anthropic) and `gpt-6` (OpenAI).

## [1.1.0] - 2026-09-22

Covers the former 1.0.0, 1.0.1 and 1.1.0.

### Added
- **24/7 silent background engine**: macOS menu bar daemon watching repositories on file save with battery-aware debouncing (0.5 s on AC, 15 s on battery).
- **Apple Silicon Metal GPU inference** via `llama-cpp-python`; default Qwen 0.5B, sub-1s latency, ~390 MB RAM. Brains: built-in Metal, local Ollama / LM Studio, custom GGUF, cloud BYOK (OpenAI, Anthropic).
- **Semantic System Graph** of business domains and cross-module relationships, with **Smart Scan Adoption** (SHA-256 fingerprinting for moved or renamed files) and export/import of `.sqlite3` snapshots.
- **Model Context Protocol** integration for Claude Desktop, Cursor, Gemini and Codex (`codebone_context`, `codebone_status`, `codebone_graph`, `codebone_list_scans`, `codebone_adopt_scan`) on a localhost HTTP API (`127.0.0.1:8053`: `/codebone/context`, `/status`, `/graph`, `/scans`).
- **Live Graph UI** (`/codebone/graph/ui`): pan, zoom, drag, click-to-inspect. **Level-of-detail context filtering** by domain, file or entity keyword (`?domain=X&file=Y&query=Z`).
- **Live menu bar dashboard** (repo path, watch status, counts, live toast), View Logs, and a `last_error` field in `/codebone/status`.
- **Deep Scan Mode** (7B re-analysis; removed again in 1.4.2).
- **Security**: untrusted source is wrapped in escaped XML tags with anti-jailbreak directives, a symlink jail keeps repositories from escaping the project root, and Full Disk Access pre-flight checks link to System Settings.

### Fixed
- SQLite WAL mode with an RLock prevents `database is locked` during save bursts; timer-based aggregation coalesces bursts such as `git checkout`; SHA-256 batch reconciliation re-links moved files at zero LLM cost; local `.gitignore` files were respected (no longer the case since 1.3.9).
