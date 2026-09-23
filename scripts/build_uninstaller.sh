#!/usr/bin/env bash
# ==============================================================================
# codebone — Standalone Uninstaller App Builder
# ==============================================================================
# Compiles a native macOS application bundle "Uninstall codebone.app"
# that safely kills all background daemons, cleans all local models/databases,
# removes MCP registrations, and either moves codebone.app to the Trash or
# reveals it in Finder for the user to drag to the bin.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_DIR="${1:-/Applications}"
APP_NAME="Uninstall codebone.app"
OUTPUT_APP="$TARGET_DIR/$APP_NAME"
RESOURCES_DIR="$ROOT_DIR/resources"

echo "🦴 Building $APP_NAME for $TARGET_DIR..."

TMP_OSA=$(mktemp /tmp/uninstaller_script.XXXXXX.applescript)

cat << 'APPLESCRIPT_EOF' > "$TMP_OSA"
-- codebone Uninstaller Application
set appTitle to "codebone Uninstaller"
set codeboneSystemApp to "/Applications/codebone.app"
set userHome to POSIX path of (path to home folder)
set codeboneUserApp to userHome & "Applications/codebone.app"

tell application "System Events"
    set frontmost of current application to true
end tell

activate
set userChoice to display dialog "Are you sure you want to completely uninstall codebone?

This will permanently remove:
• All background processes and file watchers
• Semantic knowledge graphs & databases (~/Library/Application Support/codebone)
• Downloaded AI models (~390 MB)
• All diagnostic logs (~/Library/Logs/codebone)
• MCP server registrations from Claude Desktop, Cursor, and Gemini
• Background LaunchAgents

After data cleanup, you only need to drag codebone.app into the Trash." with title appTitle buttons {"Cancel", "Clean All Data"} default button "Clean All Data" with icon caution

if button returned of userChoice is not "Clean All Data" then
    return
end if

-- Execute thorough cleanup
do shell script "/bin/bash -s << 'CLEANUP_EOF'
set -e
# 1. Stop all codebone processes
pkill -9 -f '/codebone.app/' 2>/dev/null || true
pkill -9 -f 'codebone_main.py' 2>/dev/null || true
pkill -9 -f '/CodeBone.app/' 2>/dev/null || true
pkill -9 -f '/PUG.app/' 2>/dev/null || true
pkill -9 -f 'pug_main.py' 2>/dev/null || true

# 2. Unload & remove LaunchAgents
launchctl unload \"$HOME/Library/LaunchAgents/com.codebone.app.plist\" 2>/dev/null || true
rm -f \"$HOME/Library/LaunchAgents/com.codebone.app.plist\"
launchctl unload \"$HOME/Library/LaunchAgents/com.pug.app.plist\" 2>/dev/null || true
rm -f \"$HOME/Library/LaunchAgents/com.pug.app.plist\"

# 3. Clean MCP registrations from Claude Desktop, Cursor, Gemini
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

# 4. Remove all Application Support directories
rm -rf \"$HOME/Library/Application Support/codebone\"
rm -rf \"$HOME/Library/Application Support/CodeBone\"
rm -rf \"$HOME/Library/Application Support/PUG\"

# 5. Remove all logs
rm -rf \"$HOME/Library/Logs/codebone\"
rm -rf \"$HOME/Library/Logs/CodeBone\"
rm -rf \"$HOME/Library/Logs/PUG\"

# 6. Remove caches, preferences, saved state
rm -rf \"$HOME/Library/Caches/com.codebone.app\"
rm -rf \"$HOME/Library/Caches/com.pug.app\"
rm -rf \"$HOME/Library/Saved Application State/com.codebone.app.savedState\"
rm -f \"$HOME/Library/Preferences/com.codebone.app.plist\"

# 7. Unregister from macOS LaunchServices
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -u \"/Applications/codebone.app\" 2>/dev/null || true
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -u \"$HOME/Applications/codebone.app\" 2>/dev/null || true
CLEANUP_EOF"

-- Prompt user for the final step
tell application "System Events"
    set frontmost of current application to true
end tell

activate
set finalDialog to display dialog "✓ All codebone data, models, logs, and configurations have been completely removed!

Now simply drag codebone.app into the Trash to finish." with title "Cleanup Complete" buttons {"Done", "Show in Finder", "Move to Trash"} default button "Move to Trash" with icon note

if button returned of finalDialog is "Move to Trash" then
    tell application "Finder"
        if exists POSIX file codeboneSystemApp then
            delete POSIX file codeboneSystemApp
        end if
        if exists POSIX file codeboneUserApp then
            delete POSIX file codeboneUserApp
        end if
    end tell
    display notification "codebone.app has been moved to the Trash." with title "Uninstallation Complete"
else if button returned of finalDialog is "Show in Finder" then
    tell application "Finder"
        activate
        if exists POSIX file codeboneSystemApp then
            reveal POSIX file codeboneSystemApp
        else if exists POSIX file codeboneUserApp then
            reveal POSIX file codeboneUserApp
        else
            open (POSIX file "/Applications")
        end if
    end tell
end if
APPLESCRIPT_EOF

# Remove previous uninstaller bundle if existing
rm -rf "$OUTPUT_APP"

# Compile AppleScript application
osacompile -o "$OUTPUT_APP" "$TMP_OSA"
rm -f "$TMP_OSA"

# Apply icon if available
if [[ -f "$RESOURCES_DIR/AppIcon.icns" ]]; then
    cp "$RESOURCES_DIR/AppIcon.icns" "$OUTPUT_APP/Contents/Resources/applet.icns"
fi

# Set friendly bundle names in Info.plist
PLIST="$OUTPUT_APP/Contents/Info.plist"
if [[ -f "$PLIST" ]]; then
    /usr/libexec/PlistBuddy -c "Set :CFBundleName 'Uninstall codebone'" "$PLIST" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :CFBundleName string 'Uninstall codebone'" "$PLIST" 2>/dev/null || true

    /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName 'Uninstall codebone'" "$PLIST" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string 'Uninstall codebone'" "$PLIST" 2>/dev/null || true
fi

echo "✨ Successfully built: $OUTPUT_APP"
