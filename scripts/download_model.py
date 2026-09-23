#!/usr/bin/env python3
"""Downloader for the default codebone GGUF model (Qwen2.5-Coder-0.5B-Instruct).

Downloads the model file from Hugging Face into codebone's models directory.
Uses standard library urllib so it runs with zero extra dependencies.
"""
import argparse
import os
import sys
import time
import urllib.request
from pathlib import Path

MODEL_NAME = "qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF/resolve/main/"
    + MODEL_NAME
)
MODELS_DIR = Path.home() / "Library" / "Application Support" / "codebone" / "models"
MODEL_DEST = MODELS_DIR / MODEL_NAME
MIN_EXPECTED_SIZE = 300 * 1024 * 1024  # ~390 MB


def is_model_installed() -> bool:
    return MODEL_DEST.exists() and MODEL_DEST.stat().st_size >= MIN_EXPECTED_SIZE


def download_model(force: bool = False) -> bool:
    if is_model_installed() and not force:
        print(f"codebone model already present: {MODEL_DEST}")
        return True

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = MODEL_DEST.with_suffix(".tmp")

    print(f"Downloading {MODEL_NAME} (~390 MB) to:")
    print(f"  {MODEL_DEST}")
    print("This is a one-time download for local Metal-accelerated AI mapping.\n")

    start_time = time.time()

    def report_hook(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            percent = min(100.0, (downloaded / total_size) * 100)
            mb_down = downloaded / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)
            elapsed = time.time() - start_time
            speed = mb_down / elapsed if elapsed > 0 else 0
            bar_len = 30
            filled = int(bar_len * percent / 100)
            bar = "#" * filled + "-" * (bar_len - filled)
            sys.stdout.write(
                f"\r[{bar}] {percent:5.1f}% ({mb_down:5.1f}/{mb_total:5.1f} MB) {speed:4.1f} MB/s"
            )
            sys.stdout.flush()

    try:
        urllib.request.urlretrieve(MODEL_URL, temp_file, reporthook=report_hook)
        print("\nDownload complete. Finalizing model file...")
        os.replace(temp_file, MODEL_DEST)
        print(f"Ready: {MODEL_DEST}")
        return True
    except KeyboardInterrupt:
        print("\nDownload canceled.")
        if temp_file.exists():
            temp_file.unlink(missing_ok=True)
        return False
    except Exception as exc:
        print(f"\nDownload failed: {exc}", file=sys.stderr)
        if temp_file.exists():
            temp_file.unlink(missing_ok=True)
        return False


def main():
    parser = argparse.ArgumentParser(description="Download codebone base GGUF model")
    parser.add_argument(
        "--check", action="store_true", help="Check if model is already downloaded"
    )
    parser.add_argument(
        "--force", action="store_true", help="Force re-download even if present"
    )
    args = parser.parse_args()

    if args.check:
        if is_model_installed():
            print("INSTALLED")
            sys.exit(0)
        else:
            print("MISSING")
            sys.exit(1)

    success = download_model(force=args.force)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
