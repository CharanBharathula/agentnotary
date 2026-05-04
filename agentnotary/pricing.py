"""
agentnotary.pricing
================
Static token-pricing table for the top providers/models.

Prices are USD per 1 million tokens, separate input/output. Used by
`agentnotary guard` to project per-call cost and enforce session caps.

This table is best-effort and updated on each AgentNotary release. For
production, override via `pricing_overrides` in the manifest (planned v0.2.1)
or use `agentnotary guard --pricing path/to/pricing.yaml`.
"""

from __future__ import annotations

from typing import Optional

# (provider, model_name_prefix) -> (input_per_1m_usd, output_per_1m_usd)
# Prefix matching: longest prefix wins.
PRICING: dict = {
    # ── Anthropic ─────────────────────────────────────────────────
    ("anthropic", "claude-opus-4-5"):     (15.00, 75.00),
    ("anthropic", "claude-opus-4"):       (15.00, 75.00),
    ("anthropic", "claude-sonnet-4-5"):    (3.00, 15.00),
    ("anthropic", "claude-sonnet-4"):      (3.00, 15.00),
    ("anthropic", "claude-haiku-4"):       (0.80,  4.00),
    ("anthropic", "claude-3-5-sonnet"):    (3.00, 15.00),
    ("anthropic", "claude-3-5-haiku"):     (1.00,  5.00),
    ("anthropic", "claude-3-opus"):       (15.00, 75.00),
    ("anthropic", "claude-"):              (3.00, 15.00),  # generic Claude fallback

    # ── OpenAI ────────────────────────────────────────────────────
    ("openai", "gpt-5"):                   (5.00, 20.00),
    ("openai", "gpt-4o-mini"):             (0.15,  0.60),
    ("openai", "gpt-4o"):                  (2.50, 10.00),
    ("openai", "gpt-4-turbo"):            (10.00, 30.00),
    ("openai", "gpt-4"):                  (30.00, 60.00),
    ("openai", "gpt-3.5"):                 (0.50,  1.50),
    ("openai", "o3-mini"):                 (1.10,  4.40),
    ("openai", "o3"):                     (10.00, 40.00),
    ("openai", "o1-mini"):                 (1.10,  4.40),
    ("openai", "o1"):                     (15.00, 60.00),
    ("openai", "gpt-"):                    (2.50, 10.00),  # generic GPT fallback

    # ── Google ────────────────────────────────────────────────────
    ("google", "gemini-2.5-pro"):          (1.25, 10.00),
    ("google", "gemini-2.5-flash"):        (0.30,  2.50),
    ("google", "gemini-1.5-pro"):          (1.25,  5.00),
    ("google", "gemini-1.5-flash"):        (0.075, 0.30),
    ("google", "gemini-"):                 (1.25,  5.00),  # generic fallback

    # ── Meta / Llama via various hosts ────────────────────────────
    ("local", "llama-3.3-70b"):            (0.59,  0.79),
    ("local", "llama-"):                   (0.50,  0.50),
}


def lookup_pricing(provider: str, model: str) -> Optional[tuple]:
    """
    Return (input_usd_per_million, output_usd_per_million) or None if unknown.
    Uses longest-prefix matching on the model name.
    """
    provider = (provider or "").lower()
    model = (model or "").lower()

    candidates = [
        (p, m) for (p, m) in PRICING
        if p == provider and model.startswith(m)
    ]
    if not candidates:
        return None

    # Longest prefix wins
    candidates.sort(key=lambda pm: len(pm[1]), reverse=True)
    return PRICING[candidates[0]]


def estimate_cost(provider: str, model: str,
                  input_tokens: int, output_tokens: int) -> Optional[float]:
    """Estimate the USD cost of a call. Returns None if pricing is unknown."""
    rate = lookup_pricing(provider, model)
    if rate is None:
        return None
    input_rate, output_rate = rate
    return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate


def estimate_input_cost(provider: str, model: str, input_tokens: int) -> Optional[float]:
    """Pre-flight cost estimate based only on input tokens (output unknown)."""
    rate = lookup_pricing(provider, model)
    if rate is None:
        return None
    return (input_tokens / 1_000_000) * rate[0]
