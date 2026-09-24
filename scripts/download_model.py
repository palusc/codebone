#!/usr/bin/env python3
"""Installs the pinned base GGUF model (Qwen2.5-Coder-0.5B-Instruct Q4_K_M).

Thin CLI over src/model_fetch.py so the app, install.sh and the DMG build all use one implementation.
  download_model.py                 -> ensure it exists in ~/Library/Application Support/codebone/models
  download_model.py --dest DIR      -> download into DIR (used when building the .app bundle)
  download_model.py --check         -> exit 0 if the installed model matches the pinned checksum
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import model_fetch  # noqa: E402
from src.config import BASE_MODEL_FILE, BASE_MODEL_PATH  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Install the pinned codebone base model")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dest", help="directory to download the model into (default: Application Support)")
    args = ap.parse_args()

    dest = Path(args.dest) / BASE_MODEL_FILE if args.dest else Path(BASE_MODEL_PATH)
    if args.check:
        ok = model_fetch.is_valid(dest)
        print("INSTALLED" if ok else "MISSING")
        sys.exit(0 if ok else 1)

    last = [-1]

    def bar(pct):
        if pct != last[0] and pct % 5 == 0:  # the hook fires per 8 KB block; print every 5 %
            last[0] = pct
            print(f"  {BASE_MODEL_FILE}: {pct}%", flush=True)

    try:
        if args.dest:  # bundle build: never symlink, always a real file
            if not model_fetch.is_valid(dest):
                model_fetch.download(dest, bar)
            result = "ready"
        else:
            result = model_fetch.install(dest, bar)
    except Exception as exc:
        print(f"\nModel install failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"\nModel {result}: {dest}")


if __name__ == "__main__":
    main()
