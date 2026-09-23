"""py2app build script — `python setup.py py2app` produces codebone.app."""
from setuptools import setup

from src import __version__

APP = ["codebone_main.py"]
DATA_FILES = ["resources"]
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "LSUIElement": True,  # menu bar only, no Dock icon
        "CFBundleName": "codebone",
        "CFBundleDisplayName": "codebone",
        "CFBundleIdentifier": "com.codebone.app",
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "NSHumanReadableCopyright": "codebone",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
        "LSApplicationCategoryType": "public.app-category.developer-tools",
    },
    # llama_cpp and uvicorn's event-loop backends aren't always picked up by
    # py2app's static import scan — spell them out so the packaged .app
    # doesn't fail at runtime with an ImportError that never shows up in dev.
    "includes": [
        "llama_cpp",
        "uvicorn",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.lifespans.off",
        "anyio._backends._asyncio",
    ],
    "packages": ["src", "uvicorn", "fastapi", "starlette", "anyio", "h11"],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
