# Changelog

All notable changes to codebone will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Uninstall from inside the app** (menu bar > Settings > Uninstall codebone...). One module (`src/uninstall.py`) removes the app, application data and models, logs, caches, preferences, login items, and codebone's entries in the Claude Code, Claude Desktop, Cursor and Gemini configs (other servers and settings are left alone); it also runs `brew uninstall` / `npm uninstall -g` when those installed it. Project folders are never touched. `./uninstall.sh --dry-run | --yes` is the terminal fallback. The separate "Uninstall codebone.app" is gone.
- **Context that navigates**: `cb()` now returns layout, domains, key entities and a one-line summary per file (about 1,500 tokens for a 56-file project of 125,000 tokens of source); `cb(query="several words")` ranks files by name, entities and summary and lists linked files; `codebone_graph(file=...)` shows which files are connected through shared tables, routes or events. MCP tool descriptions are much shorter.
- Model status (download progress, "no model, using heuristics") is shown in the graph page and in `/codebone/status`; the graph page refreshes when the index revision changes instead of polling the whole graph.

### Changed
- One install recipe (`scripts/build_bundle.sh`) behind the DMG, ZIP/Homebrew and `install.sh`: bundled Python 3.13.15, packages pinned in `requirements.lock`, native launcher, and the pinned base model (exact Hugging Face revision + SHA-256) bundled in the app and linked on first launch.
- Per-project MCP files (`.cursor`, `.gemini`, `.agents`) are no longer written into indexed folders; global client configs are only touched for installed clients and no longer pin a port.
- Scans are incremental and cooperative: one lock per file instead of per scan, unreadable folders never wipe the index, files over 1 MB, binaries and secret-like files (`.env`, keys, `credentials*`) are skipped, deletions and moves reach the index, one rolling snapshot per project.

### Fixed
- **Live Graph never finished loading** on real projects: layout cost was O(edges x nodes) per tick and per frame, and the regex fallback linked nearly every file to every domain. The layout is now spatial-grid based, drawing happens only when something changes, and file names or summaries can no longer inject HTML or script into the page.
- **Local API hardening**: foreign `Host` headers (DNS rebinding) and cross-origin requests are refused, export never overwrites files, docs pages are gone, feedback and payloads are size-limited.
- **Switching projects** no longer serves or skips against the previous project's index; a damaged index database is moved aside instead of crashing the app on every start.
- Model output is grounded in the code (no invented tables, routes or events), prompts fit the context window, and rows written by the regex fallback are re-analysed once the model is available.
- Menu updates from background threads now hop to the main thread; the idle stats timer no longer recomputes the graph; a second app instance exits instead of sharing the database.
- The update installer extracts with `ditto` (keeps symlinks), refuses unsafe archive paths and swaps the bundle with rollback.
- Test runs no longer touch the developer's real configuration or MCP client configs.

## [1.2.2] - 2026-09-23

### Added
- **Multi-Client MCP Auto-Registration**: Full out-of-the-box auto-patching for Gemini / Antigravity IDE (`~/.gemini/config/mcp_config.json`, `~/.gemini/antigravity-ide/mcp_config.json`, and `<project>/.agents/mcp_config.json`) alongside Claude Desktop and Cursor.
- **Initial-Days Visual Setup "Ping"**: Interactive pulsing beacon banner in the Live Graph UI and dedicated menu item in the macOS menu bar popover for the first 7 days, providing one-click direct access to `#mcp-setup`.
- **Intelligent Bundle Venv & Permissions Resolver**: Auto-creates Application Support venv symlink and ensures execute permissions on bundled python binaries for seamless DMG drag-and-drop installations.

## [1.2.1] - 2026-09-23

### Added
- **In-App Auto-Updater**: Direct one-click update checking, background package download, signature verification, atomic app bundle replacement, and graceful restart via **Settings ➔ Check for Updates...**.
- **Recent Projects History (Verlauf)**: One-click project switching directly from the main menu, automatically remembering up to 10 previously scanned codebases with active state indicators.
- **Full Disk Access Guidance & Automation**: Automatic TCC probing to register codebone with macOS System Settings, accompanied by a guided setup dialog and **Reveal in Finder** action for effortless drag-and-drop.
- **Comprehensive SF Symbol Icons**: Crisp Apple SF Symbol vector icons across the entire menu hierarchy (main menu, settings submenu, and model picker).

### Changed
- Streamlined release packaging to remove redundant asset duplicates, providing two clear, fast downloads: `codebone-macos-arm64.dmg` and `codebone-macos-arm64.zip`.

## [1.2.0] - 2026-09-23

### Added
- **Built-in Feedback & Bug Reporting**: Native menu bar dialog (🦴 ➔ **Feedback & Bug Report...**) and glassmorphic modal in the Live Graph UI. Auto-attaches OS version, codebone version, active provider, file/node metrics, and recent logs. Redacts sensitive credentials before saving. Stored locally; generates a pre-filled GitHub Issue link with one click.
- **Standalone Uninstaller App** (`Uninstall codebone.app`): Dedicated macOS app that terminates background processes, wipes all local databases, cached models, logs, and MCP registrations from Claude Desktop, Cursor, and Gemini, then prepares the main app for the Trash.
- **Dynamic Port Detection**: Defaults to port `8053` and automatically finds the next free port (`8054+`) if occupied, updating Claude Desktop & Cursor MCP configs transparently.
- **De-Neonified Live Graph**: Replaced high-contrast neon palette with a balanced slate-and-iris dark glassmorphism design. Added category filter pills, hover tooltips, and a slide-out inspector drawer.
- **Apple SF Symbols**: Native vector icons across all menu bar items, adapting automatically to dark and light modes.

### Changed
- Default Cloud BYOK models updated to `claude-sonnet-5` (Anthropic) and `gpt-6` / `gpt-6` (OpenAI).

## [1.1.0] - 2026-09-22

### Added
- **Deep Scan Mode** (🦴 **Settings → Model → Deep Scan Mode (7B)...**): One-off full re-analysis using a larger local GGUF model, then automatically switches back to the fast 0.5B built-in brain.
- **Live Menu Bar Dashboard**: Real-time embedded view showing repo path, watch status, file/domain/model/route/event counts, and a live sniff toast — replacing static status text.

## [1.0.1] - 2026-09-22

### Added
- **Live Graph UI** (`GET /codebone/graph/ui`): Interactive dark-mode node-link diagram of the Semantic System Graph. Auto-refreshes, supports pan/zoom/drag, and click-to-inspect sidebar.
- **Level-of-Detail (LOD) Context Filtering**: Slice context by domain, file path, or entity keyword via `/codebone/context?domain=X&file=Y&query=Z`. Reduces token payload on large repos.
- **View Logs** menu item: Opens the codebone log file directly in Console.app.
- **`last_error` field** in `/codebone/status` response for diagnostics.

### Fixed
- **SQLite WAL mode + RLock**: Prevents `database is locked` errors during heavy file-save bursts.
- **Burst / Batch processing**: Timer-based event aggregation coalesces rapid file events (e.g. `git checkout`) into efficient bulk operations.
- **Move/Rename detection**: SHA-256 batch reconciliation re-links moved files at zero LLM cost.
- **`.gitignore` respect**: Auto-parses local `.gitignore` files to skip `node_modules`, `.venv`, and similar directories.

## [1.0.0] - 2026-09-22

### Added
- **24/7 Silent Background Engine**: macOS menu bar daemon watching repositories on file save (`Cmd + S`) with battery-aware debouncing (0.5 s on AC, 15 s on battery).
- **Apple Silicon Metal GPU Inference**: GGUF inference via `llama-cpp-python` with Metal GPU acceleration. Default Qwen 0.5B model — sub-1s latency, ~390 MB RAM.
- **Semantic System Graph**: Identifies business domains and cross-module relationships beyond direct code imports.
- **Smart Scan Adoption**: SHA-256 fingerprinting for moved/renamed files and selective diff sniffing across folder moves and branches.
- **Scan Snapshot Management**: Export and import `.sqlite3` snapshots from the menu bar or REST API.
- **Native macOS Menu Bar App**: Status icon, folder picker, and quick actions.
- **Model Context Protocol (MCP)**: Integration for Claude Desktop, Cursor, Gemini, and Codex. Tools: `codebone_context`, `codebone_status`, `codebone_graph`, `codebone_list_scans`, `codebone_adopt_scan`.
- **Localhost HTTP API**: REST endpoints on `127.0.0.1:8053` — `/codebone/context`, `/codebone/status`, `/codebone/graph`, `/codebone/scans`.
- **Multi-Brain Support**: Built-in Metal GPU, local Ollama / LM Studio, custom GGUF, and cloud BYOK (OpenAI, Anthropic).
- **Prompt Injection Defense**: Untrusted source code wrapped in escaped XML tags with strict anti-jailbreak system directives.
- **Symlink Jail / Sandboxing**: Prevents repository symlinks from escaping the project root.
- **macOS Full Disk Access Helpers**: Pre-flight TCC permission checks with 1-click System Settings shortcut.
