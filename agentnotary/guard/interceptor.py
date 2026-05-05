"""
agentnotary.guard.interceptor
==========================
Provider-specific request/response parsing for the guard proxy.

Each provider has its own request shape, response shape, and error shape.
This module extracts the metadata the policy engine needs (tool names, prompt
content, token counts) and synthesizes provider-shaped error responses when
guard blocks a call.
"""

from __future__ import annotations

from typing import Optional


def extract_anthropic_request(body: dict) -> dict:
    """
    Anthropic Messages API:
        { "model": "...", "messages": [...], "tools": [...], "system": "..." }
    """
    parts = []
    if "system" in body and isinstance(body["system"], str):
        parts.append(body["system"])
    for m in body.get("messages", []):
        c = m.get("content", "")
        if isinstance(c, str):
            parts.append(c)
        elif isinstance(c, list):
            for block in c:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))

    tools = []
    for t in body.get("tools", []):
        if isinstance(t, dict) and "name" in t:
            tools.append(t["name"])

    return {
        "prompt_text": "\n".join(parts),
        "tools_requested": tools,
        "model": body.get("model", "unknown"),
        "stream": bool(body.get("stream", False)),
    }


def extract_openai_request(body: dict) -> dict:
    """
    OpenAI Chat Completions:
        { "model": "...", "messages": [...], "tools": [...] }
    """
    parts = []
    for m in body.get("messages", []):
        c = m.get("content", "")
        if isinstance(c, str):
            parts.append(c)
        elif isinstance(c, list):
            for block in c:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))

    tools = []
    for t in body.get("tools", []):
        if isinstance(t, dict):
            fn = t.get("function", {})
            if "name" in fn:
                tools.append(fn["name"])

    # Legacy OpenAI 'functions' field: function defs have 'name' at top level
    for f in body.get("functions", []):
        if isinstance(f, dict) and "name" in f:
            tools.append(f["name"])

    return {
        "prompt_text": "\n".join(parts),
        "tools_requested": tools,
        "model": body.get("model", "unknown"),
        "stream": bool(body.get("stream", False)),
    }


def extract_anthropic_response(body: dict) -> dict:
    """Pull token counts and assistant text from an Anthropic response."""
    usage = body.get("usage", {}) or {}
    text = ""
    for block in body.get("content", []) or []:
        if isinstance(block, dict) and block.get("type") == "text":
            text += block.get("text", "")
    tool_calls = [
        block.get("name")
        for block in body.get("content", []) or []
        if isinstance(block, dict) and block.get("type") == "tool_use"
    ]
    return {
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "response_text": text,
        "tool_calls": tool_calls,
    }


def extract_openai_response(body: dict) -> dict:
    usage = body.get("usage", {}) or {}
    text = ""
    tool_calls = []
    for choice in body.get("choices", []) or []:
        msg = choice.get("message", {})
        if msg.get("content"):
            text += msg["content"]
        for tc in msg.get("tool_calls", []) or []:
            fn = tc.get("function", {})
            if fn.get("name"):
                tool_calls.append(fn["name"])
        # Legacy 'function_call' response field
        fc = msg.get("function_call")
        if isinstance(fc, dict) and fc.get("name"):
            tool_calls.append(fc["name"])
    return {
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "response_text": text,
        "tool_calls": tool_calls,
    }


# ── Synthesized error responses ───────────────────────────────────────


def anthropic_error(reason: str, status: int = 403) -> dict:
    """Anthropic-shaped error body so SDKs raise their normal exception."""
    return {
        "type": "error",
        "error": {
            "type": "permission_error",
            "message": f"[agentnotary guard] {reason}",
        },
    }


def openai_error(reason: str, status: int = 403) -> dict:
    """OpenAI-shaped error body."""
    return {
        "error": {
            "message": f"[agentnotary guard] {reason}",
            "type": "permission_error",
            "code": "agentbox_guard_blocked",
        },
    }


PROVIDERS = {
    "anthropic": {
        "request_extractor": extract_anthropic_request,
        "response_extractor": extract_anthropic_response,
        "error_body": anthropic_error,
        "default_url": "https://api.anthropic.com",
    },
    "openai": {
        "request_extractor": extract_openai_request,
        "response_extractor": extract_openai_response,
        "error_body": openai_error,
        "default_url": "https://api.openai.com",
    },
}


def estimate_tokens(text: str) -> int:
    """
    Rough token estimate: ~4 chars per token. Used for pre-flight cost projection
    when tiktoken is unavailable. Conservative — overestimates slightly.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_request_tokens(provider: str, body: dict) -> int:
    """Provider-aware token estimate for the request."""
    extractor = PROVIDERS.get(provider, {}).get("request_extractor")
    if not extractor:
        return 0
    extracted = extractor(body)
    return estimate_tokens(extracted.get("prompt_text", ""))


def get_default_url(provider: str) -> Optional[str]:
    return PROVIDERS.get(provider, {}).get("default_url")
