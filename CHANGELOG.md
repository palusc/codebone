# Changelog

All notable changes to PUG will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
