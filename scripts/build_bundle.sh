#!/bin/bash
# build_bundle.sh — builds the complete, self-contained codebone.app.
#
# This is the ONE recipe behind every install path: build_dmg.sh (DMG/ZIP/Homebrew) and install.sh (terminal)
# both call it, so they produce the same app: same Python, same pinned packages, same model, same launcher.
#
# Usage: scripts/build_bundle.sh <output_dir>     ->  <output_dir>/codebone.app
# Needs: curl, clang (Xcode CLT), network. llama-cpp-python is built from source with Metal (pip fetches cmake itself;
# the published prebuilt Metal wheel is corrupt, so it is not used).
set -euo pipefail

# ── Pins (change here, nowhere else) ────────────────────────────────────────
PBS_TAG="20260901"
PBS_PY="3.13.15"
PBS_SHA256="b9054a9d3d54f4cb5573d44907fddb29874b08909bde73f29f2868cf872223ee"
# Python packages are pinned in requirements.lock; the model URL/checksum live in src/config.py.

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:?usage: build_bundle.sh <output_dir>}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$REPO_DIR/src/__init__.py")"
PY_MM="${PBS_PY%.*}"
APP="$OUT_DIR/codebone.app"
RES="$APP/Contents/Resources"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

for tool in curl clang rsync shasum; do
  command -v "$tool" >/dev/null 2>&1 || { echo "❌ '$tool' is required (xcode-select --install)" >&2; exit 1; }
done
[[ "$(uname -m)" == "arm64" ]] || { echo "❌ codebone bundles are Apple Silicon (arm64) only" >&2; exit 1; }

echo "🦴 Building codebone v${VERSION} (Python ${PBS_PY}, pinned deps + model)"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$RES/src"

echo "   [1/7] Portable Python ${PBS_PY}..."
TARBALL="$WORK/python.tar.gz"
curl -fsSL -o "$TARBALL" "https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/cpython-${PBS_PY}+${PBS_TAG}-aarch64-apple-darwin-install_only.tar.gz"
[[ "$(shasum -a 256 "$TARBALL" | awk '{print $1}')" == "$PBS_SHA256" ]] || { echo "❌ Python archive checksum mismatch" >&2; exit 1; }
tar -xzf "$TARBALL" -C "$WORK"
mv "$WORK/python" "$RES/venv"

echo "   [2/7] Sources and icons..."
# Not shipped: tests, the benchmark, the Homebrew formula, build output, caches and OS files
SKIP_RE='^(tests|benchmark|Formula|dist|build|venv|\.venv|\.git|\.pytest_cache)/|(^|/)(__pycache__|\.DS_Store)(/|$)'
if git -C "$REPO_DIR" rev-parse --git-dir >/dev/null 2>&1; then
  # Only files git tracks or would track (respects .gitignore): stray local files never end up in a release
  git -C "$REPO_DIR" ls-files -z --cached --others --exclude-standard | grep -z -v -E "$SKIP_RE" \
    | rsync -a --from0 --files-from=- "$REPO_DIR/" "$RES/src/" || [[ $? -eq 23 || $? -eq 24 ]]
else
  rsync -a --exclude .git --exclude __pycache__ --exclude venv --exclude .venv --exclude dist --exclude build \
    --exclude benchmark --exclude tests --exclude Formula --exclude .pytest_cache --exclude .DS_Store "$REPO_DIR/" "$RES/src/"
fi
cp "$REPO_DIR/resources/AppIcon.icns" "$REPO_DIR/resources/bone_active.png" "$REPO_DIR/resources/bone_inactive.png" "$RES/"

echo "   [3/7] Pinned dependencies (llama-cpp-python Metal build takes a few minutes)..."
export CMAKE_ARGS="-DGGML_METAL=on"
"$RES/venv/bin/python3" -m pip install --quiet --no-cache-dir -r "$REPO_DIR/requirements.txt" -c "$REPO_DIR/requirements.lock"
# relative to sys.prefix so the bundle survives being moved or copied
echo "import sys, os; sys.path.append(os.path.join(sys.prefix, '..', 'src'))" > "$RES/venv/lib/python${PY_MM}/site-packages/codebone.pth"

echo "   [4/7] Info.plist and native launcher..."
cat > "$APP/Contents/Info.plist" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleName</key><string>codebone</string>
<key>CFBundleDisplayName</key><string>codebone</string>
<key>CFBundleIdentifier</key><string>com.codebone.app</string>
<key>CFBundleVersion</key><string>${VERSION}</string>
<key>CFBundleShortVersionString</key><string>${VERSION}</string>
<key>CFBundleExecutable</key><string>codebone</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>LSUIElement</key><true/>
<key>NSHighResolutionCapable</key><true/>
<key>NSDocumentsFolderUsageDescription</key><string>codebone requires access to your Documents folder to index code repositories located there.</string>
<key>NSDesktopFolderUsageDescription</key><string>codebone requires access to your Desktop folder to index code repositories located there.</string>
<key>NSDownloadsFolderUsageDescription</key><string>codebone requires access to your Downloads folder to index code repositories located there.</string>
<key>NSRemovableVolumesUsageDescription</key><string>codebone requires access to external volumes to index code repositories stored on external drives.</string>
</dict></plist>
PLISTEOF
# Python must run inside the bundle's main executable or macOS won't attach the menu-bar icon.
clang -O2 -arch arm64 -I"$RES/venv/include/python${PY_MM}" "$REPO_DIR/scripts/launcher.c" -L"$RES/venv/lib" -lpython${PY_MM} \
  -Wl,-rpath,@executable_path/../Resources/venv/lib -o "$APP/Contents/MacOS/codebone"

echo "   [5/7] Base model (pinned revision + SHA-256)..."
# cached between builds (verified by SHA-256 each time), so rebuilding does not re-download 490 MB
CACHE="$HOME/Library/Caches/codebone-build"
"$RES/venv/bin/python3" "$REPO_DIR/scripts/download_model.py" --dest "$CACHE"
mkdir -p "$RES/models"
cp "$CACHE"/*.gguf "$RES/models/"

echo "   [6/7] Smoke tests..."
if otool -L "$RES/venv/bin/python3" "$APP/Contents/MacOS/codebone" | grep -q /opt/homebrew; then echo "❌ bundle links Homebrew" >&2; exit 1; fi
"$RES/venv/bin/python3" -m pip check >/dev/null
cd "$WORK"  # so `import src` resolves to the bundle, not the repo checkout
"$RES/venv/bin/python3" - <<PYEOF
import fastapi, uvicorn, mcp, rumps, watchdog, httpx, pathspec, llama_cpp
import src, src.service, src.server, src.updater, codebone_mcp.server
assert src.__version__ == "${VERSION}", src.__version__
assert src.updater.CURRENT_VERSION == "${VERSION}", src.updater.CURRENT_VERSION
from src import model_fetch
assert model_fetch.is_valid(model_fetch.BUNDLED_MODEL), "bundled model missing or corrupt"
PYEOF

echo "   [7/7] Precompile and sign..."
"$RES/venv/bin/python3" -m compileall -q -j 0 "$RES/venv/lib" "$RES/src" >/dev/null || true
xattr -cr "$APP" 2>/dev/null || true
codesign --force --deep -s - "$APP"
echo "✅ $APP (v${VERSION})"
