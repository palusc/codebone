# Windows desktop application (2.0)

The native Windows x64 application runs the same indexing service, SQLite graph,
HTTP API and Python MCP tools as the macOS app. Its desktop shell uses Tk for
settings and Win32 notification-area integration through pystray. macOS keeps its
existing Cocoa menu-bar app and Metal backend.

## Install and run

The Windows 2.0 binaries are unsigned. SmartScreen may block their launch and
show an unknown publisher. Only proceed if you obtained the file from this
repository's official release and trust it. Compare its SHA-256 with the release
checksum; this confirms the downloaded file matches the release, not publisher
identity. Do not disable SmartScreen globally. A trusted signing identity is
required for signed releases; new signed apps can still receive reputation warnings.

Use `codebone-windows-x64-setup.exe` for a per-user installation (no administrator
rights required), or extract `codebone-windows-x64.zip` and run `codebone.exe`.
The installer offers desktop and login-startup shortcuts as optional tasks.
Closing the settings window keeps the tray icon and local API running. Use the
tray's Quit command to stop them before replacing or uninstalling the app.

Projects, GitHub repository cloning (Git for Windows recommended), scanning,
pause/resume/cancel, map-agent settings, graph UI and scan import/export are
available in the desktop window. The built-in pinned model runs on CPU; the
Settings tab also supports a GGUF file, a local model endpoint or a cloud provider.
Cloud mode sends relevant source to the configured provider. Fallback mode
performs deterministic analysis without a model.

The installed app includes its Python runtime, model and dependencies. Data and
logs live under `%LOCALAPPDATA%\codebone`, separately from installed program files.
Provider API keys are encrypted with Windows DPAPI for the current user and
excluded from the JSON configuration. Uninstalling retains data and projects.
Windows update checks open the release page; replace a portable install after
quitting, or run the new installer. In-place macOS bundle updating is not used on
Windows.

## Coding agents

The Coding agents tab displays a portable MCP configuration and can explicitly
register the bridge with Cursor or Claude Desktop. Existing JSON settings are
preserved and backed up; malformed settings are rejected. Other clients can use
the displayed command directly. The installed bridge is
`%LOCALAPPDATA%\Programs\codebone\cbone.exe` and needs no system Python.
Portable users can point their client directly to the adjacent MCP executable.
`CODEBONE_MCP` overrides npm bridge discovery for a portable or custom install;
`CODEBONE_PYTHON` continues to support source installations.

## Native build and validation

Build on Windows x64 with Python 3.12, MSVC C++ tools, Inno Setup 6 and PowerShell 7:

```powershell
./scripts/build_windows.ps1
```

The script installs pinned dependencies, builds llama.cpp for CPU without native
CPU tuning, verifies the model checksum, packages windowed and console executables,
and creates the installer, portable ZIP and SHA-256 files. There is no Linux
cross-build substitution for this native build.

The Windows workflow exercises real HTTP indexing/query behavior, encrypted
credential round trips, the packaged tray/settings window, CPU model generation,
MCP stdio protocol, and installer/uninstaller. Release publication requires those
checks and the macOS build to pass. The initial Windows binaries are not
Authenticode-signed; a publisher signing certificate is not configured. Do not
claim signing or native validation until the corresponding runner has completed.

The Windows shell does not currently expose the macOS-specific coding-model
routing controls or Full Disk Access controls. Architecture context through MCP
works independently of those integrations.
