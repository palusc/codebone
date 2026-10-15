"""GitHub Integration for CodeBone (Domain & Infrastructure).

Allows cloning and syncing remote GitHub repositories directly into CodeBone's
managed workspace, switching to them, and triggering automatic codebase analysis.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("codebone.github")

DEFAULT_PROJECTS_DIR = Path.home() / "CodeboneProjects"

GITHUB_URL_REGEX = re.compile(
    r"^(?:https?://github\.com/|git@github\.com:|github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:/.*)?$"
)


def parse_github_identifier(identifier: str) -> Tuple[str, str, str]:
    """Parses a GitHub repo identifier or URL into (owner, repo, clone_url).

    Supports:
    - https://github.com/palusc/codebone
    - https://github.com/palusc/codebone.git
    - git@github.com:palusc/codebone.git
    - github.com/palusc/codebone
    - palusc/codebone
    """
    cleaned = identifier.strip()
    match = GITHUB_URL_REGEX.match(cleaned)
    if not match:
        raise ValueError(
            f"Invalid GitHub repository identifier '{identifier}'. "
            "Please provide a format like 'owner/repo' or 'https://github.com/owner/repo'."
        )
    owner, repo = match.group(1), match.group(2)
    # Strip any trailing .git from repo name for local directory naming
    if repo.endswith(".git"):
        repo = repo[:-4]
    clone_url = f"https://github.com/{owner}/{repo}.git"
    return owner, repo, clone_url


def clone_github_repo(
    identifier: str,
    target_dir: Optional[Path] = None,
    branch: Optional[str] = None,
    depth: int = 1,
    token: Optional[str] = None,
) -> Path:
    """Clones a GitHub repository locally into target_dir (default: ~/CodeboneProjects/<repo>).

    If git clone fails (e.g. environment issue), falls back to downloading the repository zip archive.
    Returns the resolved Path of the cloned repository folder.
    """
    owner, repo, clone_url = parse_github_identifier(identifier)

    if target_dir is None:
        target_dir = DEFAULT_PROJECTS_DIR / repo

    target_dir = Path(target_dir).expanduser().resolve()

    if target_dir.exists():
        if (target_dir / ".git").exists():
            logger.info("Repo %s already exists at %s; pulling latest changes...", repo, target_dir)
            pull_github_repo(target_dir)
            return target_dir
        # Non-empty directory that is not a git repo
        if any(target_dir.iterdir()):
            raise FileExistsError(
                f"Destination folder '{target_dir}' already exists and is not an empty git repository."
            )

    target_dir.parent.mkdir(parents=True, exist_ok=True)

    auth_clone_url = clone_url
    auth_token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if auth_token and clone_url.startswith("https://"):
        auth_clone_url = f"https://x-access-token:{auth_token}@github.com/{owner}/{repo}.git"

    cmd = ["git", "clone"]
    if depth > 0:
        cmd += ["--depth", str(depth)]
    if branch:
        cmd += ["--branch", branch]
    cmd += [auth_clone_url, str(target_dir)]

    try:
        logger.info("Cloning %s into %s...", clone_url, target_dir)
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        return target_dir
    except (subprocess.CalledProcessError, subprocess.SubprocessError, FileNotFoundError) as exc:
        err_msg = getattr(exc, "stderr", str(exc))
        logger.warning("git clone failed (%s). Attempting ZIP fallback...", err_msg)
        return _download_and_extract_zip(owner, repo, target_dir, branch=branch, token=auth_token)


def pull_github_repo(repo_path: Path) -> bool:
    """Performs a fast-forward git pull on an existing cloned repository."""
    if not (repo_path / ".git").exists():
        return False
    try:
        subprocess.run(
            ["git", "-C", str(repo_path), "pull", "--ff-only"],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return True
    except Exception as exc:
        logger.warning("git pull on %s failed: %s", repo_path, exc)
        return False


def _download_and_extract_zip(
    owner: str,
    repo: str,
    target_dir: Path,
    branch: Optional[str] = None,
    token: Optional[str] = None,
) -> Path:
    """Fallback archive downloader when git is unavailable or cloning fails."""
    branch_name = branch or "main"
    zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch_name}.zip"

    req = urllib.request.Request(zip_url)
    if token:
        req.add_header("Authorization", f"token {token}")
    req.add_header("User-Agent", "CodeBone-Client")

    temp_zip = target_dir.parent / f"{repo}_temp.zip"
    try:
        try:
            with urllib.request.urlopen(req, timeout=60) as resp, open(temp_zip, "wb") as out_f:
                shutil.copyfileobj(resp, out_f)
        except urllib.error.HTTPError as http_err:
            if http_err.code == 404 and branch is None:
                # Retry with master
                master_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/master.zip"
                req_master = urllib.request.Request(master_url)
                if token:
                    req_master.add_header("Authorization", f"token {token}")
                req_master.add_header("User-Agent", "CodeBone-Client")
                with urllib.request.urlopen(req_master, timeout=60) as resp, open(temp_zip, "wb") as out_f:
                    shutil.copyfileobj(resp, out_f)
            else:
                raise

        target_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(temp_zip, "r") as zf:
            root_dirs = [n.split("/")[0] for n in zf.namelist() if "/" in n]
            common_root = root_dirs[0] if root_dirs else ""

            for member in zf.infolist():
                filename = member.filename
                if common_root and filename.startswith(common_root + "/"):
                    rel = filename[len(common_root) + 1 :]
                else:
                    rel = filename
                if not rel:
                    continue
                dest = target_dir / rel
                if member.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        return target_dir
    finally:
        if temp_zip.exists():
            try:
                temp_zip.unlink()
            except Exception:
                pass
