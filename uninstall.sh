#!/bin/bash
# Removes everything install.sh set up: the .app, the login item, the MCP
# registration, and the installed source/venv. Leaves your sniffed map and
# settings in ~/Library/Application Support/PUG untouched unless -a/--all
# is passed.
set -euo pipefail

PUG_HOME="$HOME/Library/Application Support/PUG"
KEEP_DATA=1
if [[ "${1:-}" == "-a" || "${1:-}" == "--all" ]]; then
  KEEP_DATA=0
fi

echo "==> Quitting PUG"
osascript -e 'quit app "PUG"' >/dev/null 2>&1 || true
pkill -f "/PUG.app/" >/dev/null 2>&1 || true

echo "==> Removing login item"
launchctl unload "$HOME/Library/LaunchAgents/com.pug.app.plist" >/dev/null 2>&1 || true
rm -f "$HOME/Library/LaunchAgents/com.pug.app.plist"

if command -v claude >/dev/null 2>&1; then
  echo "==> Unregistering MCP server (Claude)"
  claude mcp remove pug >/dev/null 2>&1 || true
fi

GEMINI_MCP="$HOME/.gemini/config/mcp_config.json"
if [[ -f "$GEMINI_MCP" ]]; then
  python3 -c "
import json
p = '$GEMINI_MCP'
try:
    with open(p, 'r') as f:
        data = json.load(f)
    if 'pug' in data.get('mcpServers', {}):
        del data['mcpServers']['pug']
        with open(p, 'w') as f:
            json.dump(data, f, indent=2)
except Exception:
    pass
" >/dev/null 2>&1 || true
fi

echo "==> Removing the app"
rm -rf "/Applications/PUG.app" "$HOME/Applications/PUG.app"

echo "==> Removing installed source + venv"
rm -rf "$PUG_HOME/src" "$PUG_HOME/venv"

if [[ "$KEEP_DATA" -eq 0 ]]; then
  echo "==> Removing config, sniffed map, models, logs (--all)"
  rm -rf "$PUG_HOME"
  rm -rf "$HOME/Library/Logs/PUG"
else
  echo "==> Keeping config/map/models at: $PUG_HOME"
  echo "    (re-run with --all to remove those too)"
fi

echo "PUG uninstalled."
