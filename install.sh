#!/bin/bash
# codebone Installer — Minimal, robust, local-first setup for macOS.
set -euo pipefail

# Safety: ensure this exact install.sh is the latest from git origin/main
_CURRENT_COMMIT=$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --short HEAD 2>/dev/null || echo "")
_ORIGIN_COMMIT=$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --short origin/main 2>/dev/null || echo "")
if [[ -n "$_CURRENT_COMMIT" && -n "$_ORIGIN_COMMIT" && "$_CURRENT_COMMIT" != "$_ORIGIN_COMMIT" ]]; then
  echo "⚠️  Warning: Your local install.sh ($CURRENT_COMMIT) is behind origin/main ($_ORIGIN_COMMIT)."
  echo "   Please run: git fetch origin && git reset --hard origin/main"
  echo "   Then re-run: ./install.sh"
  echo ""
fi

COMMIT=$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --short HEAD 2>/dev/null || echo "latest")
echo "🦴 Installing codebone ($COMMIT) — The Semantic Local-Server..."

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Error: codebone is designed specifically for macOS (Metal / Menu Bar)." >&2
  exit 1
fi

echo "0/5 ── Preflight system dependency check ──────────────────────────────"
echo ""
echo "   Checking every required tool and auto-installing anything missing."
echo ""

# ─── Helper ────────────────────────────────────────────────────────────────
ok()   { echo "   ✅  $*"; }
warn() { echo "   ⚠️   $*"; }
fix()  { echo "   🔄  $*"; }
fail() { echo "   ❌  $*" >&2; }

# ─── 1. Homebrew ────────────────────────────────────────────────────────────
if [[ -x "/opt/homebrew/bin/brew" ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
  ok "Homebrew — $(/opt/homebrew/bin/brew --version | head -1)"
elif [[ -x "/usr/local/bin/brew" ]]; then
  eval "$(/usr/local/bin/brew shellenv)"
  ok "Homebrew — $(/usr/local/bin/brew --version | head -1)"
else
  warn "Homebrew not found. Auto-installing..."
  fix "Running Homebrew installer (needs internet, ~2 min)..."
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" 2>/dev/null || true
  if [[ -x "/opt/homebrew/bin/brew" ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
    ok "Homebrew installed — $(/opt/homebrew/bin/brew --version | head -1)"
  elif [[ -x "/usr/local/bin/brew" ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
    ok "Homebrew installed — $(/usr/local/bin/brew --version | head -1)"
  else
    warn "Homebrew could not be installed. Will attempt fallback installers."
  fi
fi

# ─── 2. Xcode Command Line Tools (clang, make, git) ────────────────────────
if xcode-select -p >/dev/null 2>&1 && command -v clang >/dev/null 2>&1; then
  ok "Xcode CLT — clang present"
else
  warn "Xcode Command Line Tools not found. Installing..."
  xcode-select --install 2>/dev/null || true
  sleep 2
  if xcode-select -p >/dev/null 2>&1; then
    ok "Xcode CLT installed."
  else
    warn "Xcode CLT installer launched. Click 'Install' if prompted, then re-run ./install.sh"
  fi
fi

# ─── 3. cmake (needed to compile llama-cpp-python with Metal) ──────────────
if command -v cmake >/dev/null 2>&1; then
  ok "cmake — $(cmake --version | head -1)"
else
  warn "cmake not found (needed for Metal/GPU acceleration). Installing..."
  if command -v brew >/dev/null 2>&1; then
    fix "brew install cmake"
    HOMEBREW_NO_AUTO_UPDATE=1 brew install cmake 2>/dev/null || true
  fi
  if command -v cmake >/dev/null 2>&1; then
    ok "cmake installed — $(cmake --version | head -1)"
  else
    warn "cmake not available. Metal GPU compilation skipped (FastFallbackProvider active)."
  fi
fi

# ─── 4. git ─────────────────────────────────────────────────────────────────
if command -v git >/dev/null 2>&1; then
  ok "git — $(git --version)"
else
  warn "git not found. Installing..."
  command -v brew >/dev/null 2>&1 && HOMEBREW_NO_AUTO_UPDATE=1 brew install git 2>/dev/null || true
  command -v git >/dev/null 2>&1 && ok "git installed." || warn "git could not be installed."
fi

# ─── 5. curl ────────────────────────────────────────────────────────────────
if command -v curl >/dev/null 2>&1; then
  ok "curl — $(curl --version | head -1 | awk '{print $1, $2}')"
else
  warn "curl not found. Installing..."
  command -v brew >/dev/null 2>&1 && HOMEBREW_NO_AUTO_UPDATE=1 brew install curl 2>/dev/null || true
  command -v curl >/dev/null 2>&1 && ok "curl installed." || warn "curl not available."
fi

# ─── 6. Python >= 3.10 ─────────────────────────────────────────────────────
find_python() {
  local candidates=(
    "${PYTHON:-}"
    "python3"
    "python3.14"
    "python3.13"
    "python3.12"
    "python3.11"
    "python3.10"
    "/opt/homebrew/bin/python3"
    "/opt/homebrew/bin/python3.13"
    "/opt/homebrew/bin/python3.12"
    "/opt/homebrew/bin/python3.11"
    "/usr/local/bin/python3"
    "$HOME/.local/bin/python3"
  )
  for p in "$HOME"/.local/share/uv/python/*/bin/python3; do
    [[ -x "$p" ]] && candidates+=("$p")
  done
  for candidate in "${candidates[@]}"; do
    [[ -z "$candidate" ]] && continue
    if command -v "$candidate" >/dev/null 2>&1; then
      local resolved
      resolved="$(command -v "$candidate")"
      if "$resolved" -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        echo "$resolved"
        return 0
      fi
    elif [[ -x "$candidate" ]]; then
      if "$candidate" -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

PYTHON_BIN="$(find_python || true)"

if [[ -z "$PYTHON_BIN" ]]; then
  warn "Python >= 3.10 not found (macOS system Python is 3.9 — incompatible)."

  # Attempt A: Homebrew python
  if command -v brew >/dev/null 2>&1; then
    fix "brew install python (this may take 1-2 minutes)..."
    HOMEBREW_NO_AUTO_UPDATE=1 brew install python 2>/dev/null || true
    if [[ -x "/opt/homebrew/bin/brew" ]]; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi
    PYTHON_BIN="$(find_python || true)"
  fi

  # Attempt B: uv standalone (rootless, no sudo needed)
  if [[ -z "$PYTHON_BIN" ]]; then
    fix "Installing Python 3.12 via Astral uv (rootless, no sudo needed)..."
    UV_BIN=""
    for cand in "uv" "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" "/opt/homebrew/bin/uv" "/usr/local/bin/uv"; do
      if command -v "$cand" >/dev/null 2>&1; then UV_BIN="$(command -v "$cand")"; break
      elif [[ -x "$cand" ]]; then UV_BIN="$cand"; break; fi
    done
    if [[ -z "$UV_BIN" ]]; then
      fix "Installing uv first..."
      curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 || true
      for cand in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        [[ -x "$cand" ]] && UV_BIN="$cand" && break
      done
    fi
    if [[ -n "$UV_BIN" ]]; then
      "$UV_BIN" python install 3.12 >/dev/null 2>&1 || true
      UV_PY="$("$UV_BIN" python find 3.12 2>/dev/null || "$UV_BIN" python find 2>/dev/null || true)"
      [[ -x "$UV_PY" ]] && PYTHON_BIN="$UV_PY"
    fi
  fi
fi

if [[ -z "$PYTHON_BIN" ]]; then
  fail "Could not automatically install Python >= 3.10."
  fail "Please run:  brew install python"
  fail "Or download: https://www.python.org/downloads/macos/"
  exit 1
fi

PY_VER="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
ok "Python $PY_VER — $PYTHON_BIN"

# ─── 7. pip (via the Python interpreter found above) ───────────────────────
if "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  ok "pip — $("$PYTHON_BIN" -m pip --version | awk '{print $1, $2}')"
else
  warn "pip not available for $PYTHON_BIN. Bootstrapping..."
  "$PYTHON_BIN" -m ensurepip --upgrade 2>/dev/null || \
    curl -sS https://bootstrap.pypa.io/get-pip.py | "$PYTHON_BIN" 2>/dev/null || true
  "$PYTHON_BIN" -m pip --version >/dev/null 2>&1 && ok "pip bootstrapped." || warn "pip unavailable — venv pip will be used."
fi

# ─── 8. Node.js / npx (optional — for MCP npm bridge) ──────────────────────
if command -v npx >/dev/null 2>&1; then
  ok "Node.js / npx — $(node --version 2>/dev/null || echo 'present') — MCP npm bridge available"
else
  warn "Node.js / npx not found (optional). Will use Python MCP bridge instead."
  if command -v brew >/dev/null 2>&1; then
    fix "brew install node (optional — for npx MCP bridge)..."
    HOMEBREW_NO_AUTO_UPDATE=1 brew install node 2>/dev/null || true
    command -v npx >/dev/null 2>&1 && ok "Node.js installed — npx MCP bridge active." || warn "Node.js not installed. Using Python MCP bridge."
  fi
fi

echo ""
echo "   ─── Preflight complete ────────────────────────────────────────────"
echo ""




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

# If an existing venv exists, ensure it actually runs Python >= 3.10
# This deletes any stale Python 3.9 venv left from a previous failed install.
if [[ -d "$APP_VENV" ]]; then
  EXISTING_PY_VER=""
  if [[ -x "$APP_VENV/bin/python3" ]]; then
    EXISTING_PY_VER=$("$APP_VENV/bin/python3" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "unknown")
  fi
  if [[ -z "$EXISTING_PY_VER" ]] || ! "$APP_VENV/bin/python3" -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    echo "    ⚠️ Existing venv uses Python $EXISTING_PY_VER (< 3.10). Wiping and re-creating..."
    rm -rf "$APP_VENV"
  else
    echo "    Existing venv OK (Python $EXISTING_PY_VER)."
  fi
fi

if [[ ! -d "$APP_VENV" ]]; then
  echo "    Creating venv with $PYTHON_BIN (Python $PY_VER)..."
  "$PYTHON_BIN" -m venv "$APP_VENV"
fi

# ===== HARD ASSERTION: venv must be Python >= 3.10 =====
VENV_PY_VER=$("$APP_VENV/bin/python3" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null || echo "ERROR")
if ! "$APP_VENV/bin/python3" -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  echo "" >&2
  echo "❌ FATAL: The virtual environment was created with Python $VENV_PY_VER." >&2
  echo "   pip with Python < 3.10 cannot install 'mcp', 'fastapi', or other required packages." >&2
  echo "   The interpreter used was: $PYTHON_BIN" >&2
  echo "   Detected venv Python:     $APP_VENV/bin/python3 = $VENV_PY_VER" >&2
  echo "" >&2
  echo "   Fix: Run 'brew install python' then re-run './install.sh'" >&2
  rm -rf "$APP_VENV"
  exit 1
fi
echo "   ✅ venv Python: $VENV_PY_VER — ready for pip install."
# ===========================================================

if [[ -e "$CODEBONE_HOME/venv" && ! -L "$CODEBONE_HOME/venv" ]]; then
  rm -rf "$CODEBONE_HOME/venv"
fi
ln -sfn "$APP_VENV" "$CODEBONE_HOME/venv"

# Ensure pip, wheel, setuptools are up to date
"$APP_VENV/bin/pip" install --quiet --upgrade pip wheel setuptools

echo "4/5 Installing dependencies with Apple Silicon Metal acceleration..."
export CMAKE_ARGS="-DGGML_METAL=on"

# Try installing all requirements; if full requirements fail, fallback to core dependencies
if ! "$APP_VENV/bin/pip" install --quiet -r "$RESOURCES/src/requirements.txt" 2>&1; then
  echo "    ⚠️ Full requirements install encountered an issue. Retrying core dependencies individually..."
  for dep in "fastapi>=0.110.0" "uvicorn>=0.29.0" "rumps>=0.4.0" "watchdog>=4.0.0" "pydantic>=2.6.0" "requests>=2.31.0" "mcp>=1.0.0,<2.0.0" "httpx>=0.27.0" "pathspec>=0.12.0" "pytest>=8.0.0"; do
    "$APP_VENV/bin/pip" install --quiet "$dep" 2>/dev/null || echo "    ⚠️ Could not install: $dep"
  done
  "$APP_VENV/bin/pip" install --quiet llama-cpp-python 2>/dev/null || {
    echo "    Note: llama-cpp-python native Metal compilation skipped. FastFallbackProvider will be active."
  }
fi

# ===== HARD ASSERTION: verify mcp is importable =====
if ! "$APP_VENV/bin/python3" -c 'import mcp' 2>/dev/null; then
  echo "    ⚠️ mcp not importable — forcing install of mcp>=1.0.0,<2.0.0..."
  "$APP_VENV/bin/pip" install 'mcp>=1.0.0,<2.0.0'
fi
# Verify all critical packages
MISSING_PKGS=()
for pkg in fastapi uvicorn rumps watchdog pydantic mcp httpx pathspec; do
  if ! "$APP_VENV/bin/python3" -c "import $pkg" 2>/dev/null; then
    MISSING_PKGS+=("$pkg")
    "$APP_VENV/bin/pip" install --quiet "$pkg" || true
  fi
done
if [[ ${#MISSING_PKGS[@]} -gt 0 ]]; then
  echo "   ⚠️ Force-installed missing packages: ${MISSING_PKGS[*]}"
else
  echo "   ✅ All dependencies verified and importable."
fi
# ====================================================

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
PYTHON_CONFIG="${PYTHON_BIN}-config"
if ! command -v "$PYTHON_CONFIG" >/dev/null 2>&1; then
  PYTHON_CONFIG="python3-config"
fi

PYTHON_CFLAGS=$("$PYTHON_CONFIG" --cflags 2>/dev/null || echo "")
PYTHON_LDFLAGS=$("$PYTHON_CONFIG" --ldflags --embed 2>/dev/null || "$PYTHON_CONFIG" --ldflags 2>/dev/null || echo "")

if command -v clang >/dev/null 2>&1 && [[ -n "$PYTHON_CFLAGS" && -n "$PYTHON_LDFLAGS" ]]; then
  if clang -O2 $PYTHON_CFLAGS -o "$MACOS/codebone" -x c - $PYTHON_LDFLAGS 2>/dev/null << 'EOF'
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
  then
    rm -rf "$MACOS/codebone.dSYM"
  else
    cat > "$MACOS/codebone" <<EOF
#!/bin/bash
DIR="\$(cd "\$(dirname "\$0")" && pwd)"
exec "\$DIR/../Resources/venv/bin/python3" "\$DIR/../Resources/src/codebone_main.py"
EOF
  fi
else
  cat > "$MACOS/codebone" <<EOF
#!/bin/bash
DIR="\$(cd "\$(dirname "\$0")" && pwd)"
exec "\$DIR/../Resources/venv/bin/python3" "\$DIR/../Resources/src/codebone_main.py"
EOF
fi
chmod +x "$MACOS/codebone"

# Clean up unwanted build / cache artifacts
rm -rf "$MACOS"/*.dSYM
find "$APP_BUNDLE" -name ".DS_Store" -delete 2>/dev/null || true
find "$APP_BUNDLE" -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Sanitize bundle symlinks (prevent Gatekeeper rejection if bundle is packaged or inspected)
find "$APP_BUNDLE" -type l | while IFS= read -r link; do
  if [[ -L "$link" ]]; then
    resolved=$("$PYTHON_BIN" -c "import os, sys; print(os.path.realpath(sys.argv[1]))" "$link" 2>/dev/null || true)
    if [[ -n "$resolved" ]]; then
      case "$resolved" in
        "$APP_BUNDLE"/*)
          ;;
        *)
          rm -f "$link"
          cp -L "$resolved" "$link"
          ;;
      esac
    fi
  fi
done

# Strip quarantine attributes and codesign bundle
xattr -cr "$APP_BUNDLE" 2>/dev/null || true
codesign --force --deep -s - "$APP_BUNDLE" 2>/dev/null || true

# Refresh LaunchServices database so icon and file size update immediately
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP_BUNDLE" >/dev/null 2>&1 || true
touch "$APP_BUNDLE"

# Register MCP for Claude CLI if installed
if command -v claude >/dev/null 2>&1; then
  echo "Wiring up codebone to Claude via MCP..."
  claude mcp remove pug >/dev/null 2>&1 || true
  if command -v npx > /dev/null 2>&1; then
    claude mcp add -s user codebone -- npx -y codebone-mcp 2>/dev/null || true
  else
    claude mcp add -s user codebone -- "$APP_VENV/bin/python3" -m codebone_mcp.server 2>/dev/null || true
  fi
fi

# Register with local MCP configuration if present (Gemini / Antigravity / other JSON-based configs)
for GEMINI_MCP in "$HOME/.gemini/config/mcp_config.json" "$HOME/.gemini/antigravity-ide/mcp_config.json"; do
  mkdir -p "$(dirname "$GEMINI_MCP")"
  if command -v npx > /dev/null 2>&1; then
    MCP_COMMAND="npx"
    MCP_ARGS='["-y", "codebone-mcp"]'
  else
    MCP_COMMAND="$APP_VENV/bin/python3"
    MCP_ARGS='["-m", "codebone_mcp.server"]'
  fi
  "$APP_VENV/bin/python3" -c "
import json, os
p = '$GEMINI_MCP'
try:
    with open(p, 'r') as f:
        data = json.load(f)
except Exception:
    data = {}
servers = data.setdefault('mcpServers', {})
servers.pop('pug', None)
entry = {
    'command': '$MCP_COMMAND',
    'args': $MCP_ARGS
}
if '$MCP_COMMAND' != 'npx':
    entry['env'] = {'CODEBONE_PORT': '8053'}
servers['codebone'] = entry
with open(p, 'w') as f:
    json.dump(data, f, indent=2)
" 2>/dev/null || true
done

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

# Health check: verify the server starts listening on localhost:8053
sleep 1.5
for i in {1..5}; do
  if curl -s -m 1 http://localhost:8053/codebone/status >/dev/null 2>&1 || curl -s -m 1 http://localhost:8053/pug/status >/dev/null 2>&1; then
    echo "🟢 codebone server is active and responding on http://localhost:8053"
    break
  fi
  sleep 0.5
done

