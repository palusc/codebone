#!/bin/bash
# PUG Installer — Minimal, robust, local-first setup for macOS.
set -euo pipefail

echo "🦴 Installing PUG (The Semantic Local-Server)..."

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Error: PUG is designed specifically for macOS (Metal / Menu Bar)." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 not found. Please install Python 3.10+ (e.g. via 'brew install python')." >&2
  exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PUG_HOME="$HOME/Library/Application Support/PUG"
APP_NAME="PUG.app"

TARGET_DIR="/Applications"
if [[ ! -w "$TARGET_DIR" ]]; then
  TARGET_DIR="$HOME/Applications"
fi
mkdir -p "$TARGET_DIR"

# Terminate any previously running instances
pkill -f "/PUG.app/" >/dev/null 2>&1 || true
pkill -f "pug_main.py" >/dev/null 2>&1 || true
sleep 0.5

echo "1/5 Preparing Application Support directories at $PUG_HOME..."
mkdir -p "$PUG_HOME/models"
mkdir -p "$HOME/Library/Logs/PUG"

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

# Backwards-compatible symlink for Application Support
if [[ -e "$PUG_HOME/src" && ! -L "$PUG_HOME/src" ]]; then
  rm -rf "$PUG_HOME/src"
fi
ln -sfn "$RESOURCES/src" "$PUG_HOME/src"

echo "3/5 Configuring Python virtual environment inside App Bundle..."
APP_VENV="$RESOURCES/venv"
if [[ ! -d "$APP_VENV" ]]; then
  python3 -m venv "$APP_VENV"
fi
if [[ -e "$PUG_HOME/venv" && ! -L "$PUG_HOME/venv" ]]; then
  rm -rf "$PUG_HOME/venv"
fi
ln -sfn "$APP_VENV" "$PUG_HOME/venv"

# Ensure pip & wheel are up to date
"$APP_VENV/bin/pip" install --quiet --upgrade pip wheel

echo "4/5 Installing dependencies with Apple Silicon Metal acceleration..."
export CMAKE_ARGS="-DGGML_METAL=on"
"$APP_VENV/bin/pip" install --quiet -r "$RESOURCES/src/requirements.txt"

# Link source dir into site-packages so pug_mcp and src imports work globally
"$APP_VENV/bin/python3" -c "import site; from pathlib import Path; p = Path(site.getsitepackages()[0]) / 'pug.pth'; p.write_text('$RESOURCES/src\n')"

echo "5/5 Checking local AI model (Qwen2.5-Coder)..."
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
    <string>PUG</string>
    <key>CFBundleDisplayName</key>
    <string>PUG</string>
    <key>CFBundleIdentifier</key>
    <string>com.pug.app</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleExecutable</key>
    <string>PUG</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIconName</key>
    <string>AppIcon</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

# Compile native Mach-O executable launcher embedding Python directly.
# This prevents PID/audit token mismatches that cause MenuBarAgent to reject status items on macOS.
PYTHON_CFLAGS=$(python3-config --cflags 2>/dev/null || echo "")
PYTHON_LDFLAGS=$(python3-config --ldflags --embed 2>/dev/null || python3-config --ldflags 2>/dev/null || echo "")

if command -v clang >/dev/null 2>&1 && [[ -n "$PYTHON_CFLAGS" && -n "$PYTHON_LDFLAGS" ]]; then
  clang -O2 -arch arm64 $PYTHON_CFLAGS -o "$MACOS/PUG" -x c - $PYTHON_LDFLAGS << 'EOF'
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
    snprintf(script, sizeof(script), "%s/../Resources/src/pug_main.py", dir);

    char *py_argv[] = { "PUG", script, NULL };
    return Py_BytesMain(2, py_argv);
}
EOF
else
  cat > "$MACOS/PUG" <<EOF
#!/bin/bash
DIR="\$(cd "\$(dirname "\$0")" && pwd)"
exec "\$DIR/../Resources/venv/bin/python3" "\$DIR/../Resources/src/pug_main.py"
EOF
fi
chmod +x "$MACOS/PUG"

# Refresh LaunchServices database so icon and file size update immediately
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP_BUNDLE" >/dev/null 2>&1 || true
touch "$APP_BUNDLE"

# Register MCP for Claude CLI if installed
if command -v claude >/dev/null 2>&1; then
  echo "Wiring up PUG to Claude via MCP..."
  claude mcp add -s user pug -- "$APP_VENV/bin/python3" "$RESOURCES/src/pug_mcp/server.py" 2>/dev/null || true
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
servers['pug'] = {
    'command': '$APP_VENV/bin/python3',
    'args': ['$RESOURCES/src/pug_mcp/server.py']
}
with open(p, 'w') as f:
    json.dump(data, f, indent=2)
" 2>/dev/null || true
fi

echo ""
echo "✨ PUG is installed successfully!"
echo "   App:    $APP_BUNDLE"
echo "   Server: http://localhost:3000"
echo "   Logs:   $HOME/Library/Logs/PUG/pug.log"
echo ""
echo "Starting PUG now..."
open "$APP_BUNDLE" || true
