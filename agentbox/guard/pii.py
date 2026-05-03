"""
agentbox.guard.pii
==================
Lightweight regex-based PII detection. Works without external deps; an
optional `presidio-analyzer` integration provides NER-based detection.

Patterns are intentionally conservative to minimize false positives in
LLM prompts (which often contain code, numbers, and proper nouns).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# ── Built-in patterns ─────────────────────────────────────────────────
# Each entry: (label, compiled_regex)
PATTERNS = {
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "SSN": re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"),
    "CREDIT_CARD": re.compile(
        r"\b(?:4\d{3}|5[1-5]\d{2}|3[47]\d{2}|6(?:011|5\d{2}))[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"
    ),
    "PHONE_US": re.compile(
        r"\b(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"
    ),
    "IP_ADDRESS": re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ),
    "AWS_ACCESS_KEY": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "AWS_SECRET_KEY": re.compile(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])"),
}


@dataclass
class PIIMatch:
    pattern: str
    matched: str
    start: int
    end: int


def detect(text: str, patterns: Optional[list] = None) -> list:
    """
    Return all PII matches in `text`. If `patterns` is None, runs every
    built-in pattern; otherwise only the named patterns.
    """
    if not text:
        return []
    active = patterns if patterns else list(PATTERNS.keys())
    out = []
    for name in active:
        regex = PATTERNS.get(name)
        if regex is None:
            continue
        for m in regex.finditer(text):
            out.append(PIIMatch(
                pattern=name,
                matched=m.group(0),
                start=m.start(),
                end=m.end(),
            ))
    return out


def redact(text: str, matches: list) -> str:
    """Replace each match with [REDACTED-{LABEL}]. Idempotent and order-independent."""
    if not matches:
        return text
    # Sort descending so earlier replacements don't shift later indices
    for m in sorted(matches, key=lambda x: x.start, reverse=True):
        text = text[: m.start] + f"[REDACTED-{m.pattern}]" + text[m.end:]
    return text


def has_pii(text: str, patterns: Optional[list] = None) -> bool:
    """Fast check: any PII present?"""
    return bool(detect(text, patterns))
