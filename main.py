"""codebone desktop entry point."""
import sys

if __name__ == "__main__":
    if sys.platform == "win32":
        from src.windows_app import main
    else:
        from src.app import main
    main()
