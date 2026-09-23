import sys
from pathlib import Path

# Add bundled or local venv site-packages if running inside macOS app bundle
resources_dir = Path(__file__).resolve().parent.parent
venv_dir = resources_dir / "venv"
if venv_dir.exists():
    for sp in venv_dir.glob("lib/python*/site-packages"):
        if str(sp) not in sys.path:
            import site
            site.addsitedir(str(sp))

# Ensure root package directory is in sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.app import main

if __name__ == "__main__":
    main()

