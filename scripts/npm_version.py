"""Map app release names to npm's required three-part SemVer."""
import re
import sys


def npm_version(app_version: str) -> str:
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?([a-z])?", app_version)
    if not match:
        raise ValueError(f"Unsupported app version: {app_version!r}")
    major, minor, patch, letter = match.groups()
    return f"{major}.{minor}.{patch or '0'}" + (f"-{letter}" if letter else "")


if __name__ == '__main__':
    print(npm_version(sys.argv[1]))
