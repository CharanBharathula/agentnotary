"""
agentnotary.bom
============
Software Bill of Materials (SBOM) generator for AI agents.

Outputs:
  - CycloneDX 1.6 (OWASP standard, widely supported by GRC tools)
  - SPDX 2.3 (Linux Foundation standard)

The BOM enumerates every component that defines an agent's behavior:
models, prompts, tools, MCP servers, datasets, and Python dependencies —
each with cryptographic hashes from `agent.lock` when available.

Public API:
    generate_bom(base_dir, format) -> dict
    write_bom(base_dir, format, output_path) -> Path
"""

from agentnotary.bom.generator import (
    SUPPORTED_BOM_FORMATS,
    generate_bom,
    write_bom,
)

__all__ = ["SUPPORTED_BOM_FORMATS", "generate_bom", "write_bom"]
