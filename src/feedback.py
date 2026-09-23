"""Built-in feedback & bug report recorder for codebone."""
import json
import logging
import platform
import re
import time
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional

from .config import CONFIG_DIR
from .logging_setup import LOG_FILE

logger = logging.getLogger("codebone.feedback")
FEEDBACK_FILE = CONFIG_DIR / "feedback.jsonl"
GITHUB_REPO_URL = "https://github.com/palusc/codebone/issues/new"
APP_VERSION = "1.2.0"


def _sanitize_log_line(line: str) -> str:
    """Removes API keys, bearer tokens, or sensitive credentials from logs before reporting."""
    # Redact common token patterns (sk-..., bearer ..., key=...)
    redacted = re.sub(r"(sk-[a-zA-Z0-9_\-]{20,})", "sk-***REDACTED***", line)
    redacted = re.sub(r"(bearer\s+[a-zA-Z0-9_\-\.]{20,})", "bearer ***REDACTED***", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"(api[_-]?key[\"'\s:=]+)[a-zA-Z0-9_\-]{16,}", r"\1***REDACTED***", redacted, flags=re.IGNORECASE)
    return redacted


def get_recent_log_snippet(max_lines: int = 40) -> str:
    """Extracts recent log entries with sensitive token redaction."""
    if not LOG_FILE.exists():
        return "No local log file found."
    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = lines[-max_lines:] if len(lines) > max_lines else lines
        return "\n".join(_sanitize_log_line(l) for l in tail)
    except Exception as exc:
        return f"Could not read log file: {exc}"


def build_system_diagnostics(extra_info: Optional[dict] = None) -> Dict[str, str]:
    """Collects anonymous hardware and environment details to speed up bug triage."""
    mac_ver = platform.mac_ver()[0] or platform.system()
    diag = {
        "app_version": APP_VERSION,
        "os": f"macOS {mac_ver}",
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
    }
    if extra_info:
        for k, v in extra_info.items():
            if v is not None:
                diag[k] = str(v)
    return diag


def generate_github_issue_url(
    feedback_type: str,
    title: str,
    description: str,
    diagnostics: Dict[str, str],
    log_snippet: Optional[str] = None,
) -> str:
    """Builds a pre-filled GitHub issue URL with Markdown formatting."""
    issue_type = feedback_type.capitalize()
    issue_title = f"[{issue_type}] {title}" if title else f"[{issue_type}] Bug / Feedback Report"

    body_lines = [
        "### Description",
        description or "*(No description provided)*",
        "",
        "### System Diagnostics",
        f"- **Version:** `{diagnostics.get('app_version', APP_VERSION)}`",
        f"- **OS:** `{diagnostics.get('os', 'macOS')}` ({diagnostics.get('architecture', 'arm64')})",
        f"- **Python:** `{diagnostics.get('python_version', '')}`",
    ]

    for k, v in diagnostics.items():
        if k not in ("app_version", "os", "architecture", "python_version"):
            body_lines.append(f"- **{k.replace('_', ' ').title()}:** `{v}`")

    if log_snippet:
        body_lines.extend([
            "",
            "<details>",
            "<summary><b>Recent Diagnostic Logs (Click to expand)</b></summary>",
            "",
            "```log",
            log_snippet,
            "```",
            "",
            "</details>",
        ])

    body = "\n".join(body_lines)
    params = {
        "title": issue_title,
        "body": body,
    }
    return f"{GITHUB_REPO_URL}?{urllib.parse.urlencode(params)}"


def record_feedback(
    feedback_type: str = "bug",
    title: str = "",
    description: str = "",
    include_logs: bool = True,
    email: Optional[str] = None,
    extra_diagnostics: Optional[dict] = None,
) -> dict:
    """Records feedback locally to feedback.jsonl and returns response with GitHub link."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    f_type = feedback_type.lower() if feedback_type in ("bug", "feedback", "feature") else "bug"
    diag = build_system_diagnostics(extra_diagnostics)

    log_snippet = get_recent_log_snippet(40) if include_logs else None
    github_url = generate_github_issue_url(f_type, title, description, diag, log_snippet)

    entry = {
        "id": f"fb_{int(time.time() * 1000)}",
        "timestamp": time.time(),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "type": f_type,
        "title": title.strip() or f"{f_type.capitalize()} Report",
        "description": description.strip(),
        "email": email.strip() if email else None,
        "diagnostics": diag,
        "log_snippet": log_snippet,
        "github_url": github_url,
    }

    try:
        with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        logger.info("Recorded %s feedback locally (ID: %s)", f_type, entry["id"])
    except Exception as exc:
        logger.error("Failed to write to feedback.jsonl: %s", exc)

    return {
        "status": "success",
        "id": entry["id"],
        "message": "Feedback recorded successfully",
        "github_url": github_url,
        "diagnostics": diag,
    }


def list_recent_feedback(limit: int = 15) -> List[dict]:
    """Retrieves recent locally recorded feedback items."""
    if not FEEDBACK_FILE.exists():
        return []
    items: List[dict] = []
    try:
        lines = FEEDBACK_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
                if len(items) >= limit:
                    break
            except Exception:
                continue
    except Exception as exc:
        logger.error("Error reading feedback file: %s", exc)
    return items
