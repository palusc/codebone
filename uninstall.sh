#!/usr/bin/env bash
# ==============================================================================
# codebone — Complete System Uninstaller (CLI)
# ==============================================================================
# Removes everything codebone set up:
# • Background processes & daemons
# • Application bundles (/Applications/codebone.app, Uninstall codebone.app)
# • LaunchAgents login items
# • MCP registrations (Claude Desktop, Cursor, Gemini, Claude CLI)
# • Application Support databases, maps, scans, models, and logs (with --all / -a)
# ==============================================================================
set -euo pipefail

CODEBONE_HOME="$HOME/Library/Application Support/codebone"
LEGACY_CODEBONE_HOME="$HOME/Library/Application Support/CodeBone"
LEGACY_PUG_HOME="$HOME/Library/Application Support/PUG"

KEEP_DATA=0
if [[ "${1:-}" == "--keep-data" ]]; then
  KEEP_DATA=1
fi

echo "🦴 Uninstalling codebone..."

echo "1/6 Stopping all codebone processes..."
pkill -9 -f "/codebone.app/" >/dev/null 2>&1 || true
pkill -9 -f "codebone_main.py" >/dev/null 2>&1 || true
pkill -9 -f "/CodeBone.app/" >/dev/null 2>&1 || true
pkill -9 -f "/PUG.app/" >/dev/null 2>&1 || true
pkill -9 -f "pug_main.py" >/dev/null 2>&1 || true

echo "2/6 Removing LaunchAgents..."
launchctl unload "$HOME/Library/LaunchAgents/com.codebone.app.plist" >/dev/null 2>&1 || true
rm -f "$HOME/Library/LaunchAgents/com.codebone.app.plist"
launchctl unload "$HOME/Library/LaunchAgents/com.pug.app.plist" >/dev/null 2>&1 || true
rm -f "$HOME/Library/LaunchAgents/com.pug.app.plist"

echo "3/6 Cleaning MCP registrations (Claude Desktop, Cursor, Gemini)..."
/usr/bin/python3 - << 'PYEOF'
import json
from pathlib import Path

targets = [
    Path.home() / 'Library' / 'Application Support' / 'Claude' / 'claude_desktop_config.json',
    Path.home() / '.cursor' / 'mcp.json',
    Path.home() / '.gemini' / 'config' / 'mcp_config.json',
]

for t in targets:
    if t.exists():
        try:
            with open(t, 'r', encoding='utf-8') as f:
                data = json.load(f)
            servers = data.get('mcpServers', {})
            modified = False
            for k in ['codebone', 'pug']:
                if k in servers:
                    del servers[k]
                    modified = True
            if modified:
                with open(t, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
        except Exception:
            pass
PYEOF

if command -v claude >/dev/null 2>&1; then
  claude mcp remove codebone >/dev/null 2>&1 || true
  claude mcp remove pug >/dev/null 2>&1 || true
fi

echo "4/6 Removing application bundles..."
for app_path in \
  "/Applications/codebone.app" \
  "$HOME/Applications/codebone.app" \
  "/Applications/Uninstall codebone.app" \
  "$HOME/Applications/Uninstall codebone.app" \
  "/Applications/CodeBone.app" \
  "$HOME/Applications/CodeBone.app" \
  "/Applications/PUG.app" \
  "$HOME/Applications/PUG.app"; do
  if [[ -e "$app_path" ]]; then
    /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -u "$app_path" >/dev/null 2>&1 || true
    rm -rf "$app_path"
  fi
done

echo "5/6 Removing caches and preferences..."
rm -rf "$HOME/Library/Caches/com.codebone.app"
rm -rf "$HOME/Library/Caches/com.pug.app"
rm -rf "$HOME/Library/Saved Application State/com.codebone.app.savedState"
rm -f "$HOME/Library/Preferences/com.codebone.app.plist"

if [[ "$KEEP_DATA" -eq 0 ]]; then
  echo "6/6 Removing all databases, models, scans, and logs..."
  rm -rf "$CODEBONE_HOME"
  rm -rf "$LEGACY_CODEBONE_HOME"
  rm -rf "$LEGACY_PUG_HOME"
  rm -rf "$HOME/Library/Logs/codebone"
  rm -rf "$HOME/Library/Logs/CodeBone"
  rm -rf "$HOME/Library/Logs/PUG"
else
  echo "6/6 Keeping database/models at $CODEBONE_HOME (pass without --keep-data to remove)"
fi

echo ""
echo "✨ codebone has been completely uninstalled from this Mac."
