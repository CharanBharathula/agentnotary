# scripts/

Helper scripts for demos and reproducibility.

## `demo.sh`

A 60-second end-to-end demo of AgentNotary. Spawns a tempdir, runs every
major command, and tears down on exit. Designed for terminal recording.

```bash
bash scripts/demo.sh                # interactive (press any key to advance)
bash scripts/demo.sh --no-pause     # straight-through (for non-interactive recording)
```

Recording with [asciinema](https://asciinema.org/):
```bash
asciinema rec -c 'bash scripts/demo.sh --no-pause' demo.cast
asciinema upload demo.cast
```

Recording with [t-rec](https://github.com/sassman/t-rec-rs) (creates a GIF):
```bash
t-rec --output agentnotary-demo bash scripts/demo.sh --no-pause
```

Recording with [vhs](https://github.com/charmbracelet/vhs) (creates a GIF from a tape file):
```bash
# vhs reads a tape script; see vhs/agentnotary.tape (TODO).
vhs vhs/agentnotary.tape
```

## `runaway_agent.py`

A toy agent that calls the Anthropic API in an infinite loop. Designed
to demonstrate that `agentnotary guard` blocks it before the cost cap is
breached.

```bash
agentnotary guard run -- python scripts/runaway_agent.py
```

Requires `pip install anthropic` and `ANTHROPIC_API_KEY` in env.
