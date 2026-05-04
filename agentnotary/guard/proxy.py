"""
agentnotary.guard.proxy
====================
Local HTTP reverse proxy that wraps an agent's LLM provider calls.

The proxy listens on 127.0.0.1:<random_port> and exposes per-provider paths:
    /anthropic/v1/messages    -> https://api.anthropic.com/v1/messages
    /openai/v1/chat/completions -> https://api.openai.com/v1/chat/completions

Before forwarding each request:
    - parse the body to extract prompt + tools + model
    - run PolicyEngine.pre_flight()
    - if blocked: return a synthetic provider-shaped error so the SDK raises naturally
    - if redacted: forward the rewritten body
    - if allowed: forward as-is

After receiving each response:
    - parse usage / token counts
    - call PolicyEngine.post_flight()
    - record into the SessionRecorder
    - return the response unchanged
"""

from __future__ import annotations

import json
import socket
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

import aiohttp
from aiohttp import web

from agentnotary.guard.interceptor import PROVIDERS, get_default_url
from agentnotary.guard.policies import CallMeta, PolicyEngine
from agentnotary.manifest import AgentManifest
from agentnotary.pricing import estimate_cost, estimate_input_cost
from agentnotary.recorder import SessionRecorder


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_app(manifest: AgentManifest, recorder: SessionRecorder,
             policy: PolicyEngine, *, on_block=None) -> web.Application:
    """
    Build the aiohttp application.

    on_block: optional callback(violation) invoked whenever a request is blocked,
              so the runner can decide to terminate the agent subprocess.
    """
    app = web.Application(client_max_size=64 * 1024 * 1024)
    app["manifest"] = manifest
    app["recorder"] = recorder
    app["policy"] = policy
    app["on_block"] = on_block
    app["client_session"] = None  # lazily initialized

    app.router.add_route("*", "/{provider}/{path:.*}", _handle_request)
    app.on_cleanup.append(_close_client)
    return app


async def _close_client(app):
    if app.get("client_session") is not None:
        await app["client_session"].close()


async def _get_client(app) -> aiohttp.ClientSession:
    if app["client_session"] is None:
        app["client_session"] = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=300)
        )
    return app["client_session"]


def _normalize_provider(p: str) -> str:
    return p.lower()


async def _handle_request(request: web.Request) -> web.Response:
    provider = _normalize_provider(request.match_info["provider"])
    path = request.match_info["path"]

    spec = PROVIDERS.get(provider)
    if not spec:
        return web.json_response(
            {"error": {"message": f"[agentnotary guard] Unknown provider: {provider}"}},
            status=404,
        )

    upstream_url = f"{get_default_url(provider)}/{path}"
    request_body_bytes = await request.read()

    # Parse body for inspection. Non-JSON bodies pass through unchecked.
    try:
        body = json.loads(request_body_bytes) if request_body_bytes else {}
    except json.JSONDecodeError:
        body = {}

    extractor = spec["request_extractor"]
    extracted = extractor(body) if body else {}

    streaming_requested = extracted.get("stream", False)
    if streaming_requested:
        # v0.2 explicit limitation
        sys.stderr.write(
            "[agentnotary guard] WARNING: streaming response requested. v0.2 enforces "
            "policy on the request only; per-token cost limits during the stream are "
            "best-effort. Streaming support lands in v0.2.1.\n"
        )

    # ── Pre-flight policy check ─────────────────────────────────
    policy: PolicyEngine = request.app["policy"]
    recorder: SessionRecorder = request.app["recorder"]
    manifest: AgentManifest = request.app["manifest"]

    projected_input = len(extracted.get("prompt_text", "")) // 4 if extracted else 0
    projected_cost = None
    if extracted:
        projected_cost = estimate_input_cost(
            manifest.effective_provider,
            extracted.get("model", manifest.effective_model),
            projected_input,
        )

    call_meta = CallMeta(
        provider=manifest.effective_provider,
        model=extracted.get("model", manifest.effective_model) if extracted else manifest.effective_model,
        prompt_text=extracted.get("prompt_text", "") if extracted else "",
        tools_requested=extracted.get("tools_requested", []) if extracted else [],
        projected_input_tokens=projected_input,
    )

    decision = policy.pre_flight(call_meta, projected_cost_usd=projected_cost)

    if not decision.allowed:
        block = decision.block_violation()
        if block:
            # Record the block, optionally signal the runner to terminate.
            recorder.record_guardrail(
                guardrail_name=block.rule,
                triggered_by=call_meta.prompt_text[:120],
                action_taken=f"blocked: {block.detail}",
            )
            on_block = request.app.get("on_block")
            if on_block:
                on_block(block)
            err_body = spec["error_body"](block.detail)
            return web.json_response(err_body, status=403)

    # Apply redactions if the policy modified the request
    if decision.redacted_prompt is not None:
        body = _apply_redaction(body, provider, decision.redacted_prompt)
        request_body_bytes = json.dumps(body).encode("utf-8")

    # ── Forward to upstream provider ─────────────────────────────
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length")}

    client = await _get_client(request.app)
    t0 = time.time()
    try:
        async with client.request(
            request.method,
            upstream_url,
            data=request_body_bytes if request_body_bytes else None,
            headers=headers,
            params=request.query,
        ) as upstream:
            response_body = await upstream.read()
            response_headers = {k: v for k, v in upstream.headers.items()
                                if k.lower() not in ("content-encoding", "transfer-encoding",
                                                      "content-length", "connection")}
            status = upstream.status
    except aiohttp.ClientError as e:
        recorder.record_error(error=str(e), context=f"upstream {upstream_url}")
        return web.json_response(
            {"error": {"message": f"[agentnotary guard] Upstream error: {e}"}},
            status=502,
        )
    duration_ms = int((time.time() - t0) * 1000)

    # ── Post-flight: parse response, accumulate cost ─────────────
    if status == 200 and not streaming_requested:
        try:
            response_json = json.loads(response_body)
        except json.JSONDecodeError:
            response_json = {}

        resp_data = spec["response_extractor"](response_json) if response_json else {}
        in_tok = resp_data.get("input_tokens", 0)
        out_tok = resp_data.get("output_tokens", 0)
        cost = estimate_cost(
            manifest.effective_provider,
            extracted.get("model", manifest.effective_model) if extracted else manifest.effective_model,
            in_tok, out_tok,
        )
        policy.post_flight(input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost)

        recorder.record_llm_call(
            prompt=call_meta.prompt_text,
            response=resp_data.get("response_text", ""),
            duration_ms=duration_ms,
            cost_usd=cost or 0.0,
            tokens=in_tok + out_tok,
        )
        for tn in resp_data.get("tool_calls", []):
            recorder.record_tool_call(tool_name=tn, args={}, result="<deferred>")

        # Outbound PII check
        outbound_violation = policy.post_flight_response_pii(resp_data.get("response_text", ""))
        if outbound_violation and outbound_violation.action == "block":
            recorder.record_guardrail(
                guardrail_name=outbound_violation.rule,
                triggered_by="response",
                action_taken=f"flagged: {outbound_violation.detail}",
            )

    return web.Response(body=response_body, status=status, headers=response_headers)


def _apply_redaction(body: dict, provider: str, redacted_text: str) -> dict:
    """
    Replace the user-side prompt content with the redacted version.

    For both Anthropic and OpenAI, we replace the content of the last user message
    with the redacted text. Multi-turn redaction is best-effort in v0.2.
    """
    if provider == "anthropic":
        msgs = body.get("messages", [])
        if msgs:
            for m in reversed(msgs):
                if m.get("role") == "user":
                    m["content"] = redacted_text
                    break
    elif provider == "openai":
        msgs = body.get("messages", [])
        if msgs:
            for m in reversed(msgs):
                if m.get("role") == "user":
                    m["content"] = redacted_text
                    break
    return body


# ── Server lifecycle ─────────────────────────────────────────────────


@asynccontextmanager
async def run_proxy(manifest: AgentManifest, recorder: SessionRecorder,
                    policy: PolicyEngine, *, on_block=None,
                    port: Optional[int] = None):
    """
    Async context manager that starts the proxy and yields its base URL.

    Usage:
        async with run_proxy(manifest, recorder, policy) as base_url:
            # base_url like "http://127.0.0.1:54123"
            ...
    """
    if port is None:
        port = find_free_port()

    app = make_app(manifest, recorder, policy, on_block=on_block)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()

    base_url = f"http://127.0.0.1:{port}"
    try:
        yield base_url
    finally:
        await runner.cleanup()
