# Changelog

All notable changes to codebone will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.1] - 2026-09-23

### Added
- **Multi-Client MCP Auto-Registration**: Full out-of-the-box auto-patching for Gemini / Antigravity IDE (`~/.gemini/config/mcp_config.json`, `~/.gemini/antigravity-ide/mcp_config.json`, and `<project>/.agents/mcp_config.json`) alongside Claude Desktop and Cursor.
- **Initial-Days Visual Setup "Ping"**: Interactive pulsing beacon banner in the Live Graph UI and dedicated menu item in the macOS menu bar popover for the first 7 days, providing one-click direct access to `#mcp-setup`.
- **Intelligent Bundle Venv & Permissions Resolver**: Auto-creates Application Support venv symlink and ensures execute permissions on bundled python binaries for seamless DMG drag-and-drop installations.
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
