#!/bin/bash
# Removes everything install.sh set up: the .app, the login item, the MCP
# registrations (Claude & Gemini), and the installed source/venv. Also thoroughly
# cleans up any legacy PUG artifacts. Leaves your sniffed map and settings in
# ~/Library/Application Support/CodeBone untouched unless -a/--all is passed.
set -euo pipefail

CODEBONE_HOME="$HOME/Library/Application Support/CodeBone"
LEGACY_PUG_HOME="$HOME/Library/Application Support/PUG"

KEEP_DATA=1
if [[ "${1:-}" == "-a" || "${1:-}" == "--all" ]]; then
  KEEP_DATA=0
fi

echo "==> Quitting CodeBone & PUG processes"
pkill -f "/CodeBone.app/" >/dev/null 2>&1 || true
pkill -f "codebone_main.py" >/dev/null 2>&1 || true
pkill -f "/PUG.app/" >/dev/null 2>&1 || true
pkill -f "pug_main.py" >/dev/null 2>&1 || true

echo "==> Removing login items"
launchctl unload "$HOME/Library/LaunchAgents/com.codebone.app.plist" >/dev/null 2>&1 || true
rm -f "$HOME/Library/LaunchAgents/com.codebone.app.plist"
launchctl unload "$HOME/Library/LaunchAgents/com.pug.app.plist" >/dev/null 2>&1 || true
rm -f "$HOME/Library/LaunchAgents/com.pug.app.plist"

if command -v claude >/dev/null 2>&1; then
  echo "==> Unregistering MCP servers (Claude)"
  claude mcp remove codebone >/dev/null 2>&1 || true
  claude mcp remove pug >/dev/null 2>&1 || true
fi

GEMINI_MCP="$HOME/.gemini/config/mcp_config.json"
if [[ -f "$GEMINI_MCP" ]]; then
  echo "==> Cleaning Gemini MCP registrations"
  python3 -c "
import json
p = '$GEMINI_MCP'
try:
    with open(p, 'r') as f:
        data = json.load(f)
    servers = data.get('mcpServers', {})
    changed = False
    for k in ['codebone', 'pug']:
        if k in servers:
            del servers[k]
            changed = True
    if changed:
        with open(p, 'w') as f:
            json.dump(data, f, indent=2)
except Exception:
    pass
" >/dev/null 2>&1 || true
fi

echo "==> Removing application bundles"
for app_path in "/Applications/CodeBone.app" "$HOME/Applications/CodeBone.app" "/Applications/PUG.app" "$HOME/Applications/PUG.app"; do
  if [[ -e "$app_path" ]]; then
    /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -u "$app_path" >/dev/null 2>&1 || true
    rm -rf "$app_path"
  fi
done

echo "==> Removing installed source + venv"
rm -rf "$CODEBONE_HOME/src" "$CODEBONE_HOME/venv"
rm -rf "$LEGACY_PUG_HOME/src" "$LEGACY_PUG_HOME/venv"

if [[ "$KEEP_DATA" -eq 0 ]]; then
  echo "==> Removing config, sniffed map, models, logs (--all)"
  rm -rf "$CODEBONE_HOME"
  rm -rf "$LEGACY_PUG_HOME"
  rm -rf "$HOME/Library/Logs/CodeBone"
  rm -rf "$HOME/Library/Logs/PUG"
else
  echo "==> Keeping config/map/models at: $CODEBONE_HOME"
  echo "    (re-run with --all to remove those too)"
fi

echo "✨ CodeBone completely uninstalled."
