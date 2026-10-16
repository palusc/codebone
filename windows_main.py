"""PyInstaller entry point for the Windows desktop executable."""
import os
import sys

# Windowed PyInstaller executables have no console streams. Libraries such as
# uvicorn still inspect isatty(); provide harmless streams before importing them.
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

from src.windows_app import main

if __name__ == '__main__':
    main()
