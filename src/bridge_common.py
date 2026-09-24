"""Encode/decode the local Anthropic-format bridge URL for a Modules entry that only has an
OpenAI-format base URL (e.g. OpenRouter). Stdlib only, like modules.py: this file is imported both
by modules.py (which must stay dependency-free) and by anthropic_bridge.py (the FastAPI endpoint
that actually forwards the translated request), so the target never needs to be stored server-side —
it round-trips through the URL itself.
"""
import base64
import json

BRIDGE_PREFIX = "codebone-bridge"


def encode_target(base_url: str, model: str) -> str:
    raw = json.dumps({"base_url": base_url, "model": model}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_target(token: str) -> dict:
    padding = "=" * (-len(token) % 4)
    raw = base64.urlsafe_b64decode(token + padding)
    return json.loads(raw.decode("utf-8"))


def bridge_path(base_url: str, model: str) -> str:
    return f"/{BRIDGE_PREFIX}/{encode_target(base_url, model)}"
