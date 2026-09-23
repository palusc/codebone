# Changelog

All notable changes to codebone will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-09-23

### Added
- **Built-in Feedback & Bug Reporting**:
  - Native menu bar dialog (🦴 ➔ **Feedback & Bug Report...** with `exclamationmark.bubble` SF Symbol).
  - Glassmorphic feedback modal integrated directly into the Live Graph Web UI (`/codebone/graph/ui`).
  - Automated system diagnostics (macOS version, codebone version, active model provider, file and edge metrics).
  - Automatic sensitive credential scrubbing (`sk-...`, `Bearer`, `api_key`) from recent log diagnostics.
  - Offline local record storage in `~/Library/Application Support/codebone/feedback.jsonl`.
  - 1-click pre-filled GitHub Issue URL generation for seamless bug triage.
  - API endpoints: `POST /codebone/feedback` and `GET /codebone/feedback`.
- **Dynamic Port Collision Detection**: Defaults to uncontentious port `8053` and incrementally finds the next free port (`8054+`) if occupied, auto-patching Claude Desktop & Cursor MCP configs.
- **De-Neonified Live Graph Visual System**: Replaced high-contrast neon cyan with a balanced slate-and-iris dark glassmorphism design, node category pills, and instant hover previews.
- **Apple SF Symbols Integration**: Native vector icons across all menu bar items with dark/light mode adaptability.
- **Standalone Uninstaller Program (`Uninstall codebone.app`)**: Dedicated macOS application that safely halts background processes, purges all local databases, cached AI models, logs, and MCP registrations from Claude Desktop, Cursor, and Gemini, then prepares the app bundle for the Trash.

## [1.1.0] - 2026-09-22

### Added
- **Deep Scan Mode** (🦴 **More... → Brain Selection → Deep Scan Mode (7B)...**): One-off full re-analysis of the project using a larger local GGUF model you supply (e.g. Qwen 7B), then automatically switches back to the fast built-in 0.5B brain. Gated behind a confirmation dialog since it uses significantly more RAM/CPU/time.
- **Live Menu Bar Dashboard**: The dropdown now opens into an embedded live view (repo path, watch status, file/domain/model/route/event counts, and a toast for the file currently being sniffed) instead of static status text, refreshed every couple of seconds.
- **`resources/how-it-works.svg`**: Replaced the README's ASCII architecture diagram with an actual image.

### Changed
- Updated default Cloud BYOK model IDs (`claude-haiku-4-5`, `gpt-6-luna`) and the README's frontier-model references to current models.

## [1.0.1] - 2026-09-22 (Day-One Patch)

### Added
- **Live Graph UI** (`GET /pug/graph/ui`): Self-contained interactive dark-mode node-link diagram of the Semantic System Graph. Accessible via browser or via 🦴 **More... → View Live Graph...**. Auto-refreshes every 5 s. Pan/zoom/drag with click-to-inspect sidebar.
- **Level-of-Detail (LOD) Context Filtering** (`/pug/context?domain=X&file=Y&query=Z`): Slice the architectural context by business domain, file path substring, or entity keyword. Both HTTP and MCP `codebone_context()` support the new params — reduces token payload on large repos.
- **View Logs** menu item: Opens the codebone log file directly in Console.app from 🦴 **More... → View Logs...**
- **`last_error` field** in `/pug/status` response for easier diagnostics.

### Changed
- `codebone_context` MCP tool updated with `domain`, `file`, and `query` parameters.

### Fixed
- **SQLite WAL mode + RLock** (`storage.py`): Serialises concurrent write access to prevent `database is locked` errors during heavy file-save bursts.
- **Burst / Batch processing** (`watcher.py`, `service.py`): Replaced single-file event handling with a timer-based aggregation window that coalesces rapid file events (e.g. `git checkout`) into efficient bulk operations.
- **Move/Rename detection** (`service.py`): SHA-256 batch reconciliation re-links moved files instantly at zero LLM cost instead of unnecessarily re-sniffing unchanged content.
- **`.gitignore` respect** (`config.py`): Auto-parsed local `.gitignore` files protect against scanning `node_modules`, `.venv`, and similar dependency directories.

## [1.0.0] - 2026-09-22

### Added
- **24/7 Silent Background Engine**: Lightweight macOS menu bar daemon watching local codebase repositories on file save (`Cmd + S`) with battery-aware debouncing.
- **Apple Silicon Metal GPU Inference**: Native GGUF inference powered by `llama-cpp-python` with Metal GPU acceleration (`-DGGML_METAL=on`) running a default Qwen 0.5B model (< 1s latency, ~390 MB RAM footprint).
- **Semantic System Graph**: Automatically identifies business domains (e.g. Authentication, Billing, Orders) and cross-module relationships, linking files logically even without direct code import statements.
- **Smart Scan Adoption**: SHA-256 fingerprinting for moved or renamed files, selective diff sniffing for changed files, and local AI reconciliation across folder moves and project branches.
- **Scan Snapshot Management**: Export and import `.sqlite3` scan snapshots directly from the menu bar or REST API.
- **Native macOS Menu Bar App**: Clean status indicator (`bone_active.png` during active indexing, `bone_inactive.png` when idle) with folder picker and quick actions.
- **Model Context Protocol (MCP)**: Native integration for Claude Desktop, Cursor, Gemini, and Codex (`codebone_context`, `codebone_status`, `codebone_graph`, `codebone_list_scans`, `codebone_adopt_scan`).
- **Localhost HTTP API**: Zero-configuration REST endpoints on `127.0.0.1:3000` (`/pug/context`, `/pug/status`, `/pug/graph`, `/pug/scans`).
- **Multi-Brain Support**: Built-in Metal GPU, local Ollama / LM Studio endpoints, custom local GGUF models, and cloud BYOK (OpenAI, Anthropic).
- **Graceful Lifecycle Management**: Clean Metal GPU buffer teardown on exit and automatic port rebinding.
