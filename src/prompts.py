"""Prompt and parser for PUG's semantic code analysis."""
import re
from typing import Dict, List, Tuple

SYSTEM_PROMPT = (
    "You are PUG. Analyze this code file. Identify database models and tables, "
    "API endpoints, events, and overarching business or system domains (e.g. 'Payment Processing', "
    "'User Authentication', 'Billing & Subscriptions', 'Notification Pipeline'). "
    "Summarize the logical purpose of the module in at most two sentences. Keep the response extremely brief.\n\n"
    "Format:\n"
    "TABLES: [comma-separated list of database tables/models, or 'none']\n"
    "ROUTES: [comma-separated list of HTTP methods and paths, or 'none']\n"
    "EVENTS: [comma-separated list of emitted or handled events, or 'none']\n"
    "DOMAINS: [comma-separated list of overarching business domains or system concepts, or 'none']\n"
    "FLOW: [at most two sentences describing the logical flow]"
)


def build_prompt(file_path: str, code: str) -> str:
    lines = code.splitlines()
    if len(lines) > 250:
        snippet = "\n".join(lines[:250]) + "\n... [truncated]"
    else:
        snippet = code

    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"File: {file_path}\n"
        "```\n"
        f"{snippet}\n"
        "```"
    )


def parse_analysis(raw_text: str) -> Tuple[List[str], List[str], List[str], List[str], str]:
    """Parse structured output from PUG's analysis into:
    (tables, routes, events, domains, summary_flow).
    """
    tables: List[str] = []
    routes: List[str] = []
    events: List[str] = []
    domains: List[str] = []
    summary: str = ""

    lines = raw_text.strip().splitlines()
    summary_lines = []

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        upper = line_clean.upper()
        if upper.startswith("TABELLEN:") or upper.startswith("TABLES:"):
            val = line_clean.split(":", 1)[1].strip()
            if val.lower() not in ("keine", "none", "n/a", "-", ""):
                tables = [item.strip(" `[]\"'") for item in val.split(",") if item.strip(" `[]\"'")]
        elif upper.startswith("ROUTEN:") or upper.startswith("ROUTES:") or upper.startswith("ENDPOINTS:"):
            val = line_clean.split(":", 1)[1].strip()
            if val.lower() not in ("keine", "none", "n/a", "-", ""):
                routes = [item.strip(" `[]\"'") for item in val.split(",") if item.strip(" `[]\"'")]
        elif upper.startswith("EVENTS:") or upper.startswith("EREIGNISSE:"):
            val = line_clean.split(":", 1)[1].strip()
            if val.lower() not in ("keine", "none", "n/a", "-", ""):
                events = [item.strip(" `[]\"'") for item in val.split(",") if item.strip(" `[]\"'")]
        elif upper.startswith("DOMAINS:") or upper.startswith("DOMÄNEN:") or upper.startswith("CONCEPTS:") or upper.startswith("SYSTEMS:"):
            val = line_clean.split(":", 1)[1].strip()
            if val.lower() not in ("keine", "none", "n/a", "-", ""):
                domains = [item.strip(" `[]\"'") for item in val.split(",") if item.strip(" `[]\"'")]
        elif upper.startswith("FLUSS:") or upper.startswith("FLOW:") or upper.startswith("SUMMARY:"):
            val = line_clean.split(":", 1)[1].strip()
            if val:
                summary_lines.append(val)
        else:
            summary_lines.append(line_clean)

    if summary_lines:
        summary = " ".join(summary_lines).strip()
    else:
        summary = raw_text.strip()

    # Clean any accidental wikilink brackets [[...]]
    summary = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", r"\1", summary)

    return tables, routes, events, domains, summary
