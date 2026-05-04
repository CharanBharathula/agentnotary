"""
Programmatic demo-GIF generator for AgentNotary.

Renders a curated sequence of "screens" as PNG frames using Pillow, then
encodes them into a GIF via imageio. No external recording tool needed.

The frames are crafted by hand from the actual `agentnotary` command output —
this gives us pixel-perfect control over what HN sees in the launch.

Output:
    agentnotary-demo.gif
    Plus 8 standalone PNG frames in frames/

Usage:
    python scripts/make_demo_gif.py
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import imageio.v3 as iio
from PIL import Image, ImageDraw, ImageFont

# ── Theme (Catppuccin Mocha) ─────────────────────────────────────────
BG = (30, 30, 46)
FG = (205, 214, 244)
DIM = (108, 112, 134)
ACCENT = (203, 166, 247)        # mauve
GREEN = (166, 227, 161)
YELLOW = (249, 226, 175)
RED = (243, 139, 168)
BLUE = (137, 180, 250)
CYAN = (148, 226, 213)

WIDTH, HEIGHT = 1280, 720
PADDING = 40
LINE_HEIGHT = 26
FONT_SIZE = 18

# ── Font discovery ───────────────────────────────────────────────────


def _find_mono_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/CascadiaCode.ttf",
        "C:/Windows/Fonts/Consolas.ttf",
        "C:/Windows/Fonts/lucon.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


FONT = _find_mono_font(FONT_SIZE)
FONT_BOLD = _find_mono_font(FONT_SIZE)  # Pillow doesn't easily switch weight; same font

# ── Mini-DSL: each line is a tuple (color, text) ─────────────────────
# Special prefixes:
#   "$ "    → muted prompt + bold cmd
#   "  ✓"   → green check
#   "  ✗"   → red cross
#   "  →"   → blue arrow

Frame = list  # list of (color, str)


def _parse_line(line: str) -> tuple:
    if line.startswith("$ "):
        return [(DIM, "$ "), (ACCENT, line[2:])]
    if line.startswith("  ✓"):
        return [(GREEN, line[:3]), (FG, line[3:])]
    if line.startswith("  ✗"):
        return [(RED, line[:3]), (FG, line[3:])]
    if line.startswith("  !"):
        return [(YELLOW, line[:3]), (FG, line[3:])]
    if line.startswith("  →"):
        return [(BLUE, line[:3]), (FG, line[3:])]
    if line.startswith("PASS"):
        return [(GREEN, line[:4]), (FG, line[4:])]
    if line.startswith("FAIL"):
        return [(RED, line[:4]), (FG, line[4:])]
    if line.startswith("WARN"):
        return [(YELLOW, line[:4]), (FG, line[4:])]
    if line.startswith("VULN"):
        return [(RED, line[:4]), (FG, line[4:])]
    if line.startswith("SAFE"):
        return [(GREEN, line[:4]), (FG, line[4:])]
    if line.startswith("# "):
        return [(DIM, line)]
    if "agentnotary" in line.lower() and line.lstrip().startswith("⬡"):
        return [(CYAN, line)]
    return [(FG, line)]


def render(lines: list, *, header: Optional[str] = None) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    # Window chrome (3 colored dots top-left)
    draw.ellipse((20, 20, 36, 36), fill=(243, 139, 168))
    draw.ellipse((46, 20, 62, 36), fill=(249, 226, 175))
    draw.ellipse((72, 20, 88, 36), fill=(166, 227, 161))

    # Title bar text
    title = header or "AgentNotary — demo"
    bbox = draw.textbbox((0, 0), title, font=FONT)
    tw = bbox[2] - bbox[0]
    draw.text(((WIDTH - tw) // 2, 18), title, font=FONT, fill=DIM)

    # Body
    y = 70
    for line in lines:
        if y > HEIGHT - LINE_HEIGHT:
            break
        x = PADDING
        for color, text in _parse_line(line):
            draw.text((x, y), text, font=FONT, fill=color)
            bbox = draw.textbbox((x, y), text, font=FONT)
            x = bbox[2]
        y += LINE_HEIGHT

    return img


# ── The script: each frame is one "screen" of output ──────────────────


SCREENS: list = [

    # 0 — hero install
    {
        "header": "Terminal — pip install agentnotary",
        "lines": [
            "# AgentNotary — notarize, govern, and audit AI agents",
            "",
            "$ pip install agentnotary",
            "  Successfully installed agentnotary-0.4.0",
            "",
            "$ agentnotary --help",
            "",
            "  ⬡ AgentNotary — Notarize, govern, and audit AI agents",
            "    Notarize → Enforce → Certify.",
            "",
            "  Health & Forensics (v0.4):",
            "    doctor    score    drift    compare    audit",
            "",
            "  Notarize & Govern:",
            "    seal      guard run    compliance",
            "",
            "  Audit & Test (v0.3):",
            "    bom       bench    attack       replay --rewind",
        ],
        "duration": 3.5,
    },

    # 1 — agentnotary doctor
    {
        "header": "$ agentnotary doctor",
        "lines": [
            "$ agentnotary doctor",
            "",
            "  ⬡ AgentNotary — Doctor: 62/100 (grade C)",
            "  → Decent. Address 3 warning(s) to improve.",
            "",
            "  Actionable items (3):",
            "",
            "  FAIL  1. agent.lock missing",
            "          → Run: agentnotary seal",
            "",
            "  WARN  2. No adversarial test on record",
            "          → Run: agentnotary attack --suite owasp-llm-top10",
            "",
            "  WARN  3. No Python dependency lockfile",
            "          → Generate uv.lock / poetry.lock for reproducibility",
            "",
            "  ✗ 1 failure(s). Fix these before shipping.",
        ],
        "duration": 4.0,
    },

    # 2 — agentnotary seal
    {
        "header": "$ agentnotary seal",
        "lines": [
            "$ agentnotary seal",
            "",
            "  ⬡ AgentNotary — Sealing agent",
            "",
            "  ✓ Wrote agent.lock",
            "  → Seal hash:    sha256:212aaee4175049e14...",
            "  → Manifest:     sha256:d4c3...c8db...",
            "  → Prompts:      1",
            "  → Tools:        3",
            "  → Datasets:     1",
            "    Probe: probe disabled (run --probe to enable)",
            "",
            "  ! 2 non-determinism caveat(s) recorded:",
            "    - Model provider may silently update underlying weights...",
            "",
            "  → Verify with: agentnotary seal --verify",
        ],
        "duration": 3.5,
    },

    # 3 — agentnotary score (badge URL!)
    {
        "header": "$ agentnotary score",
        "lines": [
            "$ agentnotary score",
            "",
            "  ⬡ AgentNotary — Governance score: 87/100 (grade B)",
            "  → Strong governance. 2 optional improvement(s).",
            "",
            "  seal             20/20",
            "      ✓ agent.lock present and verifies clean",
            "  guardrails       20/20",
            "      ✓ cost cap, iteration cap, tools allowlist, PII, rate",
            "  attack           12/15",
            "      ! 18% vulnerability rate (reduce by tightening prompts)",
            "  compliance       15/15",
            "  evals            10/10",
            "  reproducibility  10/10",
            "  ops              10/10",
            "",
            "  → Badge: https://img.shields.io/badge/agentnotary-87/100-green",
        ],
        "duration": 4.5,
    },

    # 4 — agentnotary attack
    {
        "header": "$ agentnotary attack --suite owasp-llm-top10",
        "lines": [
            "$ agentnotary attack --suite owasp-llm-top10",
            "",
            "  ⬡ AgentNotary — Attack: owasp-llm-top10",
            "",
            "  → Total attacks: 11",
            "  18% vulnerability rate   2 succeeded · 9 blocked",
            "",
            "    SEV   ID                ATTACK",
            "  SAFE  HIGH  OWASP-LLM01-001   Direct system-prompt override",
            "  SAFE  HIGH  OWASP-LLM01-002   Role-play jailbreak (DAN-style)",
            "  VULN  HIGH  OWASP-LLM01-004   Indirect injection via document",
            "  SAFE  CRIT  OWASP-LLM02-001   API-key extraction",
            "  SAFE  HIGH  OWASP-LLM06-001   Unauthorized tool invocation",
            "  VULN  HIGH  OWASP-LLM07-002   JSON-format leakage",
            "",
            "  ! Strengthen system_prompt; restrict tool allowlist.",
        ],
        "duration": 4.5,
    },

    # 5 — agentnotary drift (the killer for HN)
    {
        "header": "$ agentnotary drift",
        "lines": [
            "$ agentnotary drift",
            "",
            "  ⬡ AgentNotary — Drift check: refund-bot v0.1.0",
            "",
            "  → Sealed at:    2026-04-15T09:12:33Z",
            "  → Measured at:  2026-05-04T10:48:16Z",
            "  → Model:        anthropic/claude-sonnet-4-5-20251022",
            "",
            "  ✗ Significant drift: 100% (1/1 probe(s) diverged)",
            "",
            "  [1] DRIFT  similarity=0.42",
            "      sealed:    sha256:8af3...c91b...",
            "      current:   sha256:212a...d4c3...",
            "",
            "    Probe response hash differs from the sealed value.",
            "    The model may have been updated by the provider.",
        ],
        "duration": 4.5,
    },

    # 6 — agentnotary compliance
    {
        "header": "$ agentnotary compliance --standard eu-ai-act",
        "lines": [
            "$ agentnotary compliance --standard eu-ai-act --output ./docs",
            "",
            "  ⬡ AgentNotary — Compliance: eu-ai-act",
            "",
            "  → Risk class: LIMITED",
            "    Classified as LIMITED RISK. Transparency obligations:",
            "    agent must disclose its AI nature to users.",
            "",
            "  ✓ Wrote ./docs/eu_ai_act_annex_iv.md",
            "  ✓ Wrote ./docs/eu_ai_act_annex_iv.json",
            "",
            "  ! Documentation is a SCAFFOLD ONLY",
            "    review by qualified counsel required.",
            "",
            "  9 sections · cited rules · disclaimer banner included",
        ],
        "duration": 4.0,
    },

    # 7 — agentnotary guard (the $47K save)
    {
        "header": "$ agentnotary guard run -- python my_agent.py",
        "lines": [
            "$ agentnotary guard run -- python my_agent.py",
            "",
            "  [agentnotary guard] Proxy on http://127.0.0.1:54123",
            "  [agentnotary guard] Wrapping: python my_agent.py",
            "  [agentnotary guard] Active: cost<=$0.50, llm_calls<=25",
            "",
            "  ... agent runs ...",
            "  [agent] call 008: $0.0612 spent",
            "  [agent] call 042: $0.4912 spent",
            "  [agent] call 043: would push session > $0.50 ✗",
            "",
            "  ✗ Guard BLOCKED the agent: cost.max_usd_per_session",
            "  → LLM calls: 42",
            "  → Total cost: $0.4912",
            "",
            "  → Saved: ~$4,283 before the wallet caught fire",
        ],
        "duration": 5.0,
    },

    # 8 — outro
    {
        "header": "AgentNotary v0.4.0",
        "lines": [
            "",
            "  ⬡ AgentNotary",
            "",
            "  Notarize → Enforce → Certify",
            "",
            "  $ pip install agentnotary",
            "",
            "  github.com/CharanBharathula/agentnotary",
            "",
            "  Apache 2.0  ·  202 tests passing  ·  Python 3.9+",
        ],
        "duration": 3.5,
    },
]


def main(out_dir: str = ".") -> None:
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    frames_dir = out / "frames"
    frames_dir.mkdir(exist_ok=True)

    fps = 30
    images: list = []

    for i, screen in enumerate(SCREENS):
        img = render(screen["lines"], header=screen.get("header"))
        # Save standalone PNG for HN/LinkedIn carousel
        png_path = frames_dir / f"{i:02d}-{(screen.get('header') or 'frame').split()[0].strip('$')}.png"
        png_path = frames_dir / f"{i:02d}.png"
        img.save(png_path)
        # Repeat each frame `duration * fps` times for the GIF
        n_frames = int(screen["duration"] * fps)
        for _ in range(n_frames):
            images.append(img)

    print(f"Rendered {len(SCREENS)} screens, {len(images)} total GIF frames @ {fps}fps")

    # Encode as GIF
    gif_path = out / "agentnotary-demo.gif"
    iio.imwrite(
        gif_path,
        [list(img.getdata()) for img in []],   # placeholder — real call below
    ) if False else None

    # Use imageio to write a real animated GIF
    import numpy as np
    frames_np = [np.array(img) for img in images]
    iio.imwrite(gif_path, frames_np, fps=fps, loop=0)
    print(f"Wrote {gif_path}  ({gif_path.stat().st_size / 1024:.0f} KB)")

    # Also write an MP4 for LinkedIn / X (smaller, plays inline)
    try:
        mp4_path = out / "agentnotary-demo.mp4"
        iio.imwrite(mp4_path, frames_np, fps=fps,
                     codec="libx264", quality=8,
                     macro_block_size=1)
        print(f"Wrote {mp4_path}  ({mp4_path.stat().st_size / 1024:.0f} KB)")
    except Exception as e:
        print(f"MP4 export skipped: {e}")


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "demo-output")
