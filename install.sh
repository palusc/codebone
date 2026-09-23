#!/bin/bash
# codebone Installer — Minimal, robust, local-first setup for macOS.
set -euo pipefail

echo "🦴 Installing codebone (The Semantic Local-Server)..."

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Error: codebone is designed specifically for macOS (Metal / Menu Bar)." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 not found. Please install Python 3.10+ (e.g. via 'brew install python')." >&2
  exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODEBONE_HOME="$HOME/Library/Application Support/codebone"
APP_NAME="codebone.app"

TARGET_DIR="/Applications"
if [[ ! -w "$TARGET_DIR" ]]; then
  TARGET_DIR="$HOME/Applications"
fi
mkdir -p "$TARGET_DIR"

# Terminate any previously running instances (both codebone and legacy CodeBone/PUG)
pkill -f "/codebone.app/" >/dev/null 2>&1 || true
pkill -f "/CodeBone.app/" >/dev/null 2>&1 || true
pkill -f "codebone_main.py" >/dev/null 2>&1 || true
pkill -f "/PUG.app/" >/dev/null 2>&1 || true
pkill -f "pug_main.py" >/dev/null 2>&1 || true
sleep 0.5

# Clean up legacy CodeBone.app / PUG.app and login items
rm -rf "$TARGET_DIR/CodeBone.app" "/Applications/CodeBone.app" "$HOME/Applications/CodeBone.app"
rm -rf "$TARGET_DIR/PUG.app" "/Applications/PUG.app" "$HOME/Applications/PUG.app"
launchctl unload "$HOME/Library/LaunchAgents/com.pug.app.plist" >/dev/null 2>&1 || true
rm -f "$HOME/Library/LaunchAgents/com.pug.app.plist"

echo "1/5 Preparing Application Support directories at $CODEBONE_HOME..."
mkdir -p "$CODEBONE_HOME/models"
mkdir -p "$HOME/Library/Logs/codebone"

# Migrate legacy database if found
if [[ -f "$CODEBONE_HOME/pug.sqlite3" && ! -f "$CODEBONE_HOME/codebone.sqlite3" ]]; then
  mv "$CODEBONE_HOME/pug.sqlite3" "$CODEBONE_HOME/codebone.sqlite3" 2>/dev/null || true
fi
if [[ -d "$HOME/Library/Application Support/PUG/models" && ! -f "$CODEBONE_HOME/models/qwen2.5-coder-0.5b-instruct-q4_k_m.gguf" ]]; then
  if [[ -f "$HOME/Library/Application Support/PUG/models/qwen2.5-coder-0.5b-instruct-q4_k_m.gguf" ]]; then
    cp "$HOME/Library/Application Support/PUG/models/qwen2.5-coder-0.5b-instruct-q4_k_m.gguf" "$CODEBONE_HOME/models/" 2>/dev/null || true
  fi
fi

echo "2/5 Creating self-contained macOS Application bundle at $TARGET_DIR/$APP_NAME..."
APP_BUNDLE="$TARGET_DIR/$APP_NAME"
CONTENTS="$APP_BUNDLE/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"

mkdir -p "$MACOS" "$RESOURCES"

# Sync source code into App Bundle Resources
mkdir -p "$RESOURCES/src"
rsync -a --delete \
  --exclude ".git" \
  --exclude "__pycache__" \
  --exclude ".venv" \
  --exclude "venv" \
  --exclude "dist" \
  --exclude "build" \
  "$REPO_DIR/" "$RESOURCES/src/"

# Copy AppIcon and status bar icons
if [[ -f "$REPO_DIR/resources/AppIcon.icns" ]]; then
  cp "$REPO_DIR/resources/AppIcon.icns" "$RESOURCES/"
fi
rm -f "$RESOURCES/bone_idle"* "$RESOURCES/bone_inactive@2x.png"
for icon in bone_active.png bone_inactive.png; do
  if [[ -f "$REPO_DIR/resources/$icon" ]]; then
    cp "$REPO_DIR/resources/$icon" "$RESOURCES/"
  fi
done

# Symlinks for Application Support
if [[ -e "$CODEBONE_HOME/src" && ! -L "$CODEBONE_HOME/src" ]]; then
  rm -rf "$CODEBONE_HOME/src"
fi
ln -sfn "$RESOURCES/src" "$CODEBONE_HOME/src"

echo "3/5 Configuring Python virtual environment inside App Bundle..."
APP_VENV="$RESOURCES/venv"
if [[ ! -d "$APP_VENV" ]]; then
  python3 -m venv "$APP_VENV"
fi
if [[ -e "$CODEBONE_HOME/venv" && ! -L "$CODEBONE_HOME/venv" ]]; then
  rm -rf "$CODEBONE_HOME/venv"
fi
ln -sfn "$APP_VENV" "$CODEBONE_HOME/venv"

# Ensure pip & wheel are up to date
"$APP_VENV/bin/pip" install --quiet --upgrade pip wheel

echo "4/5 Installing dependencies with Apple Silicon Metal acceleration..."
export CMAKE_ARGS="-DGGML_METAL=on"
"$APP_VENV/bin/pip" install --quiet -r "$RESOURCES/src/requirements.txt"

# Link source dir into site-packages so codebone_mcp and src imports work globally
"$APP_VENV/bin/python3" -c "import site; from pathlib import Path; sp = Path(site.getsitepackages()[0]); (sp / 'pug.pth').unlink(missing_ok=True); (sp / 'codebone.pth').write_text('$RESOURCES/src\n')"

echo "5/5 Checking local AI model (Qwen2.5-Coder 0.5B)..."
if ! "$APP_VENV/bin/python3" "$RESOURCES/src/scripts/download_model.py" --check >/dev/null 2>&1; then
  echo "    Downloading base GGUF model (~390 MB) for local zero-impact mapping..."
  "$APP_VENV/bin/python3" "$RESOURCES/src/scripts/download_model.py" || {
    echo "    Warning: Model download could not complete. FastFallbackProvider will be active."
  }
else
  echo "    Base model already installed."
fi

# Info.plist with proper AppIcon and metadata
cat > "$CONTENTS/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleName</key>
    <string>codebone</string>
    <key>CFBundleDisplayName</key>
    <string>codebone</string>
    <key>CFBundleIdentifier</key>
    <string>com.codebone.app</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleExecutable</key>
    <string>codebone</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIconName</key>
    <string>AppIcon</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSDocumentsFolderUsageDescription</key>
    <string>codebone requires access to your Documents folder to index code repositories located there.</string>
    <key>NSDesktopFolderUsageDescription</key>
    <string>codebone requires access to your Desktop folder to index code repositories located there.</string>
    <key>NSDownloadsFolderUsageDescription</key>
    <string>codebone requires access to your Downloads folder to index code repositories located there.</string>
    <key>NSRemovableVolumesUsageDescription</key>
    <string>codebone requires access to external volumes to index code repositories stored on external drives.</string>
</dict>
</plist>
EOF

# Compile native Mach-O executable launcher embedding Python directly.
# This prevents PID/audit token mismatches that cause MenuBarAgent to reject status items on macOS.
PYTHON_CFLAGS=$(python3-config --cflags 2>/dev/null || echo "")
PYTHON_LDFLAGS=$(python3-config --ldflags --embed 2>/dev/null || python3-config --ldflags 2>/dev/null || echo "")

if command -v clang >/dev/null 2>&1 && [[ -n "$PYTHON_CFLAGS" && -n "$PYTHON_LDFLAGS" ]]; then
  clang -O2 $PYTHON_CFLAGS -o "$MACOS/codebone" -x c - $PYTHON_LDFLAGS << 'EOF'
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <mach-o/dyld.h>
#include <libgen.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char *argv[]) {
    char exe_path[PATH_MAX];
    uint32_t size = sizeof(exe_path);
    if (_NSGetExecutablePath(exe_path, &size) != 0) {
        return 1;
    }
    char *dir = dirname(exe_path);
    char script[PATH_MAX];
    snprintf(script, sizeof(script), "%s/../Resources/src/codebone_main.py", dir);

    char *py_argv[] = { "codebone", script, NULL };
    return Py_BytesMain(2, py_argv);
}
EOF
else
  cat > "$MACOS/codebone" <<EOF
#!/bin/bash
DIR="\$(cd "\$(dirname "\$0")" && pwd)"
exec "\$DIR/../Resources/venv/bin/python3" "\$DIR/../Resources/src/codebone_main.py"
EOF
fi
chmod +x "$MACOS/codebone"

# Refresh LaunchServices database so icon and file size update immediately
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP_BUNDLE" >/dev/null 2>&1 || true
touch "$APP_BUNDLE"

# Register MCP for Claude CLI if installed
if command -v claude >/dev/null 2>&1; then
  echo "Wiring up codebone to Claude via MCP..."
  claude mcp remove pug >/dev/null 2>&1 || true
  claude mcp add -s user codebone -- "$APP_VENV/bin/python3" "$RESOURCES/src/codebone_mcp/server.py" 2>/dev/null || true
fi

# Register with local MCP configuration if present
GEMINI_MCP="$HOME/.gemini/config/mcp_config.json"
if [[ -f "$GEMINI_MCP" ]]; then
  "$APP_VENV/bin/python3" -c "
import json
p = '$GEMINI_MCP'
try:
    with open(p, 'r') as f:
        data = json.load(f)
except Exception:
    data = {}
servers = data.setdefault('mcpServers', {})
servers.pop('pug', None)
servers['codebone'] = {
    'command': '$APP_VENV/bin/python3',
    'args': ['$RESOURCES/src/codebone_mcp/server.py'],
    'env': {'CODEBONE_PORT': '8053'}
}
with open(p, 'w') as f:
    json.dump(data, f, indent=2)
" 2>/dev/null || true
fi

# Build standalone Uninstaller application alongside codebone.app
if [[ -f "$REPO_DIR/scripts/build_uninstaller.sh" ]]; then
  "$REPO_DIR/scripts/build_uninstaller.sh" "$TARGET_DIR" >/dev/null 2>&1 || true
fi

echo ""
echo "✨ codebone is installed successfully!"
echo "   App:         $APP_BUNDLE"
echo "   Uninstaller: $TARGET_DIR/Uninstall codebone.app"
echo "   Server:      http://localhost:8053"
echo "   Logs:        $HOME/Library/Logs/codebone/codebone.log"
echo ""
echo "Starting codebone now..."
open "$APP_BUNDLE" || true

