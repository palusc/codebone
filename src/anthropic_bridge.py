"""Translates Claude Code's Anthropic Messages API calls into OpenAI-compatible chat/completions calls
against a Modules entry that only has an OpenAI-format base URL (e.g. OpenRouter), and translates the
response back. Only reached for a module with no Anthropic-format URL of its own — see modules._url,
which points Claude Code's ANTHROPIC_BASE_URL at this bridge instead of the module's URL directly.

The API key never touches this file's config or logs: Claude Code sends it (via apiKeyHelper) in
x-api-key on every request, and it is forwarded straight through as a Bearer token to the target.
"""
import json
import logging
import uuid
from typing import AsyncIterator, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse, Response

from .bridge_common import decode_target

logger = logging.getLogger("codebone.anthropic_bridge")

_FINISH_TO_STOP = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use", "content_filter": "end_turn"}


def _known_openai_urls(config) -> set:
    """Only bridge to a URL that is actually one of the user's saved modules — the token round-trips
    through the URL unsigned, so this is what stops any local process from turning the bridge into an
    open relay to an arbitrary host."""
    return {m.get("openai_url") for m in (config.get("modules") or []) if isinstance(m, dict) and m.get("openai_url")}


def _convert_messages(system, messages) -> list:
    openai_messages = []
    if system:
        text = system if isinstance(system, str) else "\n".join(
            b.get("text", "") for b in system if isinstance(b, dict) and b.get("type") == "text")
        if text:
            openai_messages.append({"role": "system", "content": text})

    for msg in messages or []:
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(content, str):
            openai_messages.append({"role": role, "content": content})
            continue
        if not isinstance(content, list):
            continue

        text_parts, image_parts, tool_calls, tool_results = [], [], [], []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "image":
                src = block.get("source", {})
                if src.get("type") == "base64":
                    image_parts.append({"type": "image_url", "image_url": {
                        "url": f"data:{src.get('media_type', 'image/png')};base64,{src.get('data', '')}"}})
            elif btype == "tool_use":
                tool_calls.append({"id": block.get("id"), "type": "function",
                                   "function": {"name": block.get("name"), "arguments": json.dumps(block.get("input", {}))}})
            elif btype == "tool_result":
                rc = block.get("content")
                if isinstance(rc, list):
                    rtext = "\n".join(b.get("text", "") for b in rc if isinstance(b, dict) and b.get("type") == "text")
                else:
                    rtext = rc if isinstance(rc, str) else ""
                tool_results.append((block.get("tool_use_id"), rtext))

        # A tool_result message carries only results in Anthropic's shape; OpenAI wants each as its
        # own "tool" message, so it can never be merged with the user/assistant entry below.
        if tool_results:
            for tool_use_id, rtext in tool_results:
                openai_messages.append({"role": "tool", "tool_call_id": tool_use_id, "content": rtext})
            continue

        entry = {"role": role}
        if image_parts:
            entry["content"] = image_parts + ([{"type": "text", "text": "\n".join(text_parts)}] if text_parts else [])
        else:
            entry["content"] = "\n".join(text_parts)
        if tool_calls:
            entry["tool_calls"] = tool_calls
            entry["content"] = entry["content"] or None
        openai_messages.append(entry)
    return openai_messages


def _convert_tools(tools):
    if not tools:
        return None
    return [{"type": "function", "function": {"name": t.get("name"), "description": t.get("description", ""),
                                              "parameters": t.get("input_schema") or {"type": "object", "properties": {}}}}
            for t in tools]


def _convert_tool_choice(tc):
    if not tc:
        return None
    t = tc.get("type")
    if t == "any":
        return "required"
    if t == "none":
        return "none"
    if t == "tool":
        return {"type": "function", "function": {"name": tc.get("name")}}
    return "auto"


def anthropic_to_openai(body: dict, model: str) -> dict:
    payload = {
        "model": model,
        "messages": _convert_messages(body.get("system"), body.get("messages")),
        "max_tokens": body.get("max_tokens") or 1024,
        "stream": bool(body.get("stream")),
    }
    for key in ("temperature", "top_p"):
        if key in body:
            payload[key] = body[key]
    if body.get("stop_sequences"):
        payload["stop"] = body["stop_sequences"]
    tools = _convert_tools(body.get("tools"))
    if tools:
        payload["tools"] = tools
    tool_choice = _convert_tool_choice(body.get("tool_choice"))
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice
    return payload


def openai_to_anthropic_response(resp: dict, model: str) -> dict:
    choice = (resp.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = []
    if msg.get("content"):
        content.append({"type": "text", "text": msg["content"]})
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except (ValueError, TypeError):
            args = {}
        content.append({"type": "tool_use", "id": tc.get("id") or f"toolu_{uuid.uuid4().hex[:12]}",
                        "name": fn.get("name"), "input": args})
    usage = resp.get("usage") or {}
    return {
        "id": resp.get("id") or f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content or [{"type": "text", "text": ""}],
        "stop_reason": _FINISH_TO_STOP.get(choice.get("finish_reason"), "end_turn"),
        "stop_sequence": None,
        "usage": {"input_tokens": usage.get("prompt_tokens", 0), "output_tokens": usage.get("completion_tokens", 0)},
    }


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")


async def stream_openai_as_anthropic(lines: AsyncIterator[str], model: str) -> AsyncIterator[bytes]:
    """Anthropic's streaming shape (message_start / content_block_* / message_delta / message_stop)
    rebuilt incrementally from OpenAI-style SSE chunks, since Claude Code speaks only the former."""
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    yield _sse("message_start", {"type": "message_start", "message": {
        "id": msg_id, "type": "message", "role": "assistant", "model": model,
        "content": [], "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0}}})

    next_index = 0
    text_index: Optional[int] = None
    tool_indices: dict = {}
    stop_reason = "end_turn"
    usage = {"input_tokens": 0, "output_tokens": 0}

    async for line in lines:
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except ValueError:
            continue
        if chunk.get("usage"):
            u = chunk["usage"]
            usage = {"input_tokens": u.get("prompt_tokens", 0), "output_tokens": u.get("completion_tokens", 0)}
        choice = (chunk.get("choices") or [{}])[0]
        delta = choice.get("delta") or {}

        if delta.get("content"):
            if text_index is None:
                text_index = next_index
                next_index += 1
                yield _sse("content_block_start", {"type": "content_block_start", "index": text_index,
                                                    "content_block": {"type": "text", "text": ""}})
            yield _sse("content_block_delta", {"type": "content_block_delta", "index": text_index,
                                               "delta": {"type": "text_delta", "text": delta["content"]}})

        for tc in delta.get("tool_calls") or []:
            idx = tc.get("index", 0)
            if idx not in tool_indices:
                anth_idx = next_index
                next_index += 1
                tool_indices[idx] = anth_idx
                fn = tc.get("function") or {}
                yield _sse("content_block_start", {"type": "content_block_start", "index": anth_idx,
                                                    "content_block": {"type": "tool_use",
                                                                       "id": tc.get("id") or f"toolu_{uuid.uuid4().hex[:12]}",
                                                                       "name": fn.get("name") or "", "input": {}}})
            anth_idx = tool_indices[idx]
            fragment = (tc.get("function") or {}).get("arguments")
            if fragment:
                yield _sse("content_block_delta", {"type": "content_block_delta", "index": anth_idx,
                                                   "delta": {"type": "input_json_delta", "partial_json": fragment}})

        finish = choice.get("finish_reason")
        if finish:
            stop_reason = _FINISH_TO_STOP.get(finish, "end_turn")

    if text_index is not None:
        yield _sse("content_block_stop", {"type": "content_block_stop", "index": text_index})
    for anth_idx in tool_indices.values():
        yield _sse("content_block_stop", {"type": "content_block_stop", "index": anth_idx})

    yield _sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                                 "usage": usage})
    yield _sse("message_stop", {"type": "message_stop"})


async def handle_bridge_request(token: str, request: Request, config) -> Response:
    try:
        target = decode_target(token)
    except Exception:
        raise HTTPException(status_code=404, detail="Unknown bridge target")
    base_url, model = target.get("base_url"), target.get("model")
    if not base_url or base_url not in _known_openai_urls(config):
        raise HTTPException(status_code=404, detail="Unknown bridge target")

    api_key = request.headers.get("x-api-key") or (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    body = await request.json()
    payload = anthropic_to_openai(body, model)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = base_url.rstrip("/") + "/chat/completions"

    if payload["stream"]:
        client = httpx.AsyncClient(timeout=120.0)
        upstream = await client.send(client.build_request("POST", url, json=payload, headers=headers), stream=True)
        if upstream.status_code >= 400:
            detail = await upstream.aread()
            await upstream.aclose()
            await client.aclose()
            return JSONResponse({"type": "error", "error": {"type": "api_error",
                                 "message": detail.decode("utf-8", "replace")[:2000]}}, status_code=upstream.status_code)

        async def body_iter():
            try:
                async for chunk in stream_openai_as_anthropic(upstream.aiter_lines(), model):
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        return StreamingResponse(body_iter(), media_type="text/event-stream")

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
    if resp.status_code >= 400:
        return JSONResponse({"type": "error", "error": {"type": "api_error", "message": resp.text[:2000]}},
                            status_code=resp.status_code)
    return JSONResponse(openai_to_anthropic_response(resp.json(), model))


def register(app: FastAPI, config) -> None:
    @app.post("/codebone-bridge/{token}/v1/messages")
    async def _bridge(token: str, request: Request):
        return await handle_bridge_request(token, request, config)
