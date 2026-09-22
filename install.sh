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
SRC_DIR="$PUG_HOME/src"
VENV_DIR="$PUG_HOME/venv"
APP_NAME="PUG.app"

TARGET_DIR="/Applications"
if [[ ! -w "$TARGET_DIR" ]]; then
  TARGET_DIR="$HOME/Applications"
fi
mkdir -p "$TARGET_DIR"

echo "1/5 Setting up PUG directories at $PUG_HOME..."
mkdir -p "$PUG_HOME/models"
mkdir -p "$HOME/Library/Logs/PUG"
mkdir -p "$SRC_DIR"

# Sync current source to Application Support
rsync -a --delete \
  --exclude ".git" \
  --exclude "__pycache__" \
  --exclude ".venv" \
  --exclude "venv" \
  "$REPO_DIR/" "$SRC_DIR/"

echo "2/5 Configuring Python virtual environment..."
if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

# Ensure pip & wheel are up to date
"$VENV_DIR/bin/pip" install --quiet --upgrade pip wheel

echo "3/5 Installing dependencies with Apple Silicon Metal acceleration..."
# Ensure llama-cpp-python builds with Metal support on Apple Silicon
export CMAKE_ARGS="-DGGML_METAL=on"
"$VENV_DIR/bin/pip" install --quiet -r "$SRC_DIR/requirements.txt"

# Link source dir into site-packages so pug_mcp and src imports work globally
"$VENV_DIR/bin/python3" -c "import site; from pathlib import Path; p = Path(site.getsitepackages()[0]) / 'pug.pth'; p.write_text('$SRC_DIR\n')"

echo "4/5 Checking local AI model (Qwen2.5-Coder)..."
if ! "$VENV_DIR/bin/python3" "$SRC_DIR/scripts/download_model.py" --check >/dev/null 2>&1; then
  echo "    Downloading base GGUF model (~390 MB) for local zero-impact mapping..."
  "$VENV_DIR/bin/python3" "$SRC_DIR/scripts/download_model.py" || {
    echo "    Warning: Model download could not complete. FastFallbackProvider will be active."
  }
else
  echo "    Base model already installed."
fi

echo "5/5 Creating macOS Application bundle at $TARGET_DIR/$APP_NAME..."
APP_BUNDLE="$TARGET_DIR/$APP_NAME"
CONTENTS="$APP_BUNDLE/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"

mkdir -p "$MACOS" "$RESOURCES"

# Copy icons
if [[ -f "$SRC_DIR/resources/bone_idle.png" ]]; then
  cp "$SRC_DIR/resources/bone_idle.png" "$RESOURCES/"
fi
if [[ -f "$SRC_DIR/resources/bone_inactive.png" ]]; then
  cp "$SRC_DIR/resources/bone_inactive.png" "$RESOURCES/"
fi

# Info.plist
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
    <key>CFBundleExecutable</key>
    <string>PUG</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

# Launcher script
cat > "$MACOS/PUG" <<EOF
#!/bin/bash
exec "$VENV_DIR/bin/python3" "$SRC_DIR/pug_main.py"
EOF
chmod +x "$MACOS/PUG"

# Register MCP for Claude CLI if installed
if command -v claude >/dev/null 2>&1; then
  echo "Wiring up PUG to Claude via MCP..."
  claude mcp add -s user pug -- "$VENV_DIR/bin/python3" "$SRC_DIR/pug_mcp/server.py" 2>/dev/null || true
fi

# Register with local MCP configuration if present
GEMINI_MCP="$HOME/.gemini/config/mcp_config.json"
if [[ -f "$GEMINI_MCP" ]]; then
  "$VENV_DIR/bin/python3" -c "
import json
p = '$GEMINI_MCP'
try:
    with open(p, 'r') as f:
        data = json.load(f)
except Exception:
    data = {}
servers = data.setdefault('mcpServers', {})
servers['pug'] = {
    'command': '$VENV_DIR/bin/python3',
    'args': ['$SRC_DIR/pug_mcp/server.py']
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
