# AgentNotary 90-second demo — VHS tape
#
# Record:
#   vhs vhs/agentnotary.tape
#   → produces agentnotary-demo.gif and agentnotary-demo.mp4
#
# Install vhs (one-time):
#   brew install vhs                      # macOS
#   choco install vhs                     # Windows
#   winget install charmbracelet.vhs      # Windows alternative
#   go install github.com/charmbracelet/vhs@latest    # any platform with Go

Output agentnotary-demo.gif
Output agentnotary-demo.mp4
Output agentnotary-demo.webm

Set Theme "Catppuccin Mocha"
Set FontSize 14
Set Width 1280
Set Height 720
Set Padding 20
Set TypingSpeed 45ms
Set PlaybackSpeed 1.0

# ── Hero ────────────────────────────────────────────────────────────
Type "# AgentNotary — notarize, govern, and audit AI agents"
Sleep 1500ms
Enter
Sleep 600ms
Type "pip install agentnotary"
Sleep 600ms
Enter
Sleep 1500ms

# ── 1. init ─────────────────────────────────────────────────────────
Type "agentnotary init refund-bot && cd refund-bot"
Sleep 400ms
Enter
Sleep 2500ms

# ── 2. doctor (the new viral one) ──────────────────────────────────
Type "agentnotary doctor"
Sleep 400ms
Enter
Sleep 4000ms

# ── 3. seal ─────────────────────────────────────────────────────────
Type "agentnotary seal"
Sleep 400ms
Enter
Sleep 3500ms

# ── 4. score (badge URL = social proof loop) ───────────────────────
Type "agentnotary score"
Sleep 400ms
Enter
Sleep 4500ms

# ── 5. attack (OWASP fuzzer) ───────────────────────────────────────
Type "agentnotary attack --suite owasp-llm-top10 --dry-run"
Sleep 400ms
Enter
Sleep 4500ms

# ── 6. compliance (EU AI Act) ──────────────────────────────────────
Type "agentnotary compliance --standard eu-ai-act --output ./docs"
Sleep 400ms
Enter
Sleep 3000ms

# ── 7. bom (CycloneDX) ─────────────────────────────────────────────
Type "agentnotary bom --format cyclonedx"
Sleep 400ms
Enter
Sleep 2000ms

# ── 8. drift (the killer feature for HN) ───────────────────────────
Type "agentnotary drift"
Sleep 400ms
Enter
Sleep 3000ms

# ── 9. bench (Pareto) ──────────────────────────────────────────────
Type "agentnotary bench --dry-run"
Sleep 400ms
Enter
Sleep 4500ms

# ── Outro ──────────────────────────────────────────────────────────
Type "# pip install agentnotary"
Sleep 1500ms
Enter
Type "# https://github.com/CharanBharathula/agentnotary"
Sleep 2500ms
Enter
Sleep 1500ms
