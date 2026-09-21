# Changelog

All notable changes to PUG will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-09-22 (Day-One Patch)

### Added
- **Live Graph UI** (`GET /pug/graph/ui`): Self-contained interactive dark-mode node-link diagram of the Semantic System Graph. Accessible via browser or via 🦴 **More... → View Live Graph...**. Auto-refreshes every 5 s. Pan/zoom/drag with click-to-inspect sidebar.
- **Level-of-Detail (LOD) Context Filtering** (`/pug/context?domain=X&file=Y&query=Z`): Slice the architectural context by business domain, file path substring, or entity keyword. Both HTTP and MCP `pug_context()` support the new params — reduces token payload on large repos.
- **View Logs** menu item: Opens the PUG log file directly in Console.app from 🦴 **More... → View Logs...**
- **`last_error` field** in `/pug/status` response for easier diagnostics.

### Changed
- `pug_context` MCP tool updated with `domain`, `file`, and `query` parameters.

### Fixed
- **SQLite WAL mode + RLock** (`storage.py`): Serialises concurrent write access to prevent `database is locked` errors during heavy file-save bursts.
- **Burst / Batch processing** (`watcher.py`, `service.py`): Replaced single-file event handling with a timer-based aggregation window that coalesces rapid file events (e.g. `git checkout`) into efficient bulk operations.
- **Move/Rename detection** (`service.py`): SHA-256 batch reconciliation re-links moved files instantly at zero LLM cost instead of unnecessarily re-sniffing unchanged content.
- **`.gitignore` respect** (`config.py`): Auto-parsed local `.gitignore` files protect against scanning `node_modules`, `.venv`, and similar dependency directories.

## [1.0.0] - 2026-09-22

### Added
- **24/7 Silent Background Engine**: Lightweight macOS menu bar daemon watching local codebase repositories on file save (`Cmd + S`) with battery-aware debouncing.
- **Apple Silicon Metal GPU Inference**: Native GGUF inference powered by `llama-cpp-python` with Metal GPU acceleration (`-DGGML_METAL=on`) running a default Qwen 0.8B model (< 1s latency, ~390 MB RAM footprint).
- **Semantic System Graph**: Automatically identifies business domains (e.g. Authentication, Billing, Orders) and cross-module relationships, linking files logically even without direct code import statements.
- **Smart Scan Adoption**: SHA-256 fingerprinting for moved or renamed files, selective diff sniffing for changed files, and local AI reconciliation across folder moves and project branches.
- **Scan Snapshot Management**: Export and import `.sqlite3` scan snapshots directly from the menu bar or REST API.
- **Native macOS Menu Bar App**: Clean status indicator (`bone_active.png` during active indexing, `bone_inactive.png` when idle) with folder picker and quick actions.
- **Model Context Protocol (MCP)**: Native integration for Claude Desktop, Cursor, Gemini, and Codex (`pug_context`, `pug_status`, `pug_graph`, `pug_list_scans`, `pug_adopt_scan`).
- **Localhost HTTP API**: Zero-configuration REST endpoints on `127.0.0.1:3000` (`/pug/context`, `/pug/status`, `/pug/graph`, `/pug/scans`).
- **Multi-Brain Support**: Built-in Metal GPU, local Ollama / LM Studio endpoints, custom local GGUF models, and cloud BYOK (OpenAI, Anthropic).
- **Graceful Lifecycle Management**: Clean Metal GPU buffer teardown on exit and automatic port rebinding.
