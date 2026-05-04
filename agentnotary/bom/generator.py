"""
agentnotary.bom.generator
======================
SBOM generation for AI agents in CycloneDX 1.6 and SPDX 2.3 formats.

Reuses fingerprints from `agent.lock` when present; falls back to fresh
hashing otherwise.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agentnotary.manifest import AgentManifest, parse_manifest
from agentnotary.seal.lockfile import AgentLock, load_lock

SUPPORTED_BOM_FORMATS = ["cyclonedx", "spdx"]

CYCLONEDX_SPEC_VERSION = "1.6"
SPDX_VERSION = "SPDX-2.3"


# ── CycloneDX renderer ──────────────────────────────────────────────────


def _cyclonedx_component_for_model(manifest: AgentManifest, lock: Optional[AgentLock]) -> dict:
    provider = manifest.effective_provider
    name = manifest.effective_model
    pinned = (manifest.model_spec.pinned_version
              if manifest.model_spec and manifest.model_spec.pinned_version else name)

    purl = f"pkg:ai-model/{provider}/{name}@{pinned}"
    component = {
        "bom-ref": purl,
        "type": "machine-learning-model",
        "name": name,
        "version": pinned,
        "purl": purl,
        "supplier": {"name": provider},
        "description": f"LLM foundation model from {provider}",
    }
    if lock and lock.model.get("probe_response_hash"):
        component["hashes"] = [{
            "alg": "SHA-256",
            "content": lock.model["probe_response_hash"].replace("sha256:", ""),
        }]
        component.setdefault("properties", []).append({
            "name": "agentnotary:probe_response_hash_at",
            "value": lock.model.get("resolved_at", ""),
        })
    return component


def _cyclonedx_component_for_prompt(prompt_fp: dict) -> dict:
    name = Path(prompt_fp["path"]).name
    sha = (prompt_fp.get("sha256") or "").replace("sha256:", "")
    norm = (prompt_fp.get("normalized_sha256") or "").replace("sha256:", "")
    component = {
        "bom-ref": f"prompt:{name}",
        "type": "data",
        "name": name,
        "description": "Agent system prompt or supporting prompt asset",
        "properties": [
            {"name": "agentnotary:type", "value": "prompt"},
            {"name": "agentnotary:bytes", "value": str(prompt_fp.get("bytes", 0))},
        ],
    }
    if sha:
        component["hashes"] = [{"alg": "SHA-256", "content": sha}]
    if norm:
        component.setdefault("properties", []).append({
            "name": "agentnotary:normalized_sha256", "value": norm,
        })
    return component


def _cyclonedx_component_for_tool(tool_fp: dict) -> dict:
    name = tool_fp.get("name", "unnamed")
    ttype = tool_fp.get("type", "builtin")
    component = {
        "bom-ref": f"tool:{name}",
        "type": "library" if ttype != "api" else "application",
        "name": name,
        "description": f"Agent tool ({ttype})",
        "properties": [
            {"name": "agentnotary:tool_type", "value": ttype},
        ],
    }

    # Source-code hash for function tools
    if tool_fp.get("source_sha256"):
        component["hashes"] = [{
            "alg": "SHA-256",
            "content": tool_fp["source_sha256"].replace("sha256:", ""),
        }]

    # External endpoint for API tools
    if tool_fp.get("endpoint"):
        component["properties"].append({
            "name": "agentnotary:endpoint", "value": tool_fp["endpoint"],
        })
        component["externalReferences"] = [{
            "type": "advisories",
            "url": tool_fp["endpoint"],
        }]

    # MCP server package info
    if tool_fp.get("package"):
        pkg = tool_fp["package"]
        component["purl"] = f"pkg:npm/{pkg.lstrip('@')}"
        if tool_fp.get("pinned_sha"):
            component["properties"].append({
                "name": "agentnotary:pinned_sha", "value": tool_fp["pinned_sha"],
            })

    return component


def _cyclonedx_component_for_dataset(dataset_fp: dict) -> dict:
    name = Path(dataset_fp["path"]).name
    sha = (dataset_fp.get("sha256") or "").replace("sha256:", "")
    component = {
        "bom-ref": f"dataset:{name}",
        "type": "data",
        "name": name,
        "description": "Agent dataset (eval suite, blocklist, etc.)",
        "properties": [{"name": "agentnotary:type", "value": "dataset"}],
    }
    if sha:
        component["hashes"] = [{"alg": "SHA-256", "content": sha}]
    return component


def _cyclonedx_component_for_dependencies(dep_fp: dict) -> Optional[dict]:
    if not dep_fp.get("lockfile"):
        return None
    sha = (dep_fp.get("lockfile_sha256") or "").replace("sha256:", "")
    component = {
        "bom-ref": f"deps:{dep_fp['lockfile']}",
        "type": "library",
        "name": dep_fp["lockfile"],
        "description": f"Python dependency lockfile (Python {dep_fp.get('python', 'unknown')})",
        "properties": [
            {"name": "agentnotary:type", "value": "dependency-lockfile"},
            {"name": "agentnotary:python_version", "value": dep_fp.get("python", "unknown")},
        ],
    }
    if sha:
        component["hashes"] = [{"alg": "SHA-256", "content": sha}]
    return component


def _generate_cyclonedx(manifest: AgentManifest, lock: Optional[AgentLock]) -> dict:
    serial = f"urn:uuid:{uuid.uuid4()}"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    components = [_cyclonedx_component_for_model(manifest, lock)]

    if lock:
        for prompt in lock.prompts:
            components.append(_cyclonedx_component_for_prompt(prompt))
        for tool in lock.tools:
            components.append(_cyclonedx_component_for_tool(tool))
        for dataset in lock.datasets:
            components.append(_cyclonedx_component_for_dataset(dataset))
        deps_component = _cyclonedx_component_for_dependencies(lock.dependencies)
        if deps_component:
            components.append(deps_component)

    main_ref = f"agent:{manifest.name}@{manifest.version}"

    return {
        "bomFormat": "CycloneDX",
        "specVersion": CYCLONEDX_SPEC_VERSION,
        "serialNumber": serial,
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
            "tools": {
                "components": [{
                    "type": "application",
                    "name": "AgentNotary",
                    "version": _agentnotary_version(),
                    "purl": "pkg:pypi/agentnotary",
                }],
            },
            "component": {
                "bom-ref": main_ref,
                "type": "application",
                "name": manifest.name,
                "version": manifest.version,
                "description": manifest.description or "AI agent",
                "supplier": {"name": manifest.author or "unknown"},
                "licenses": [{"license": {"id": manifest.license or "Apache-2.0"}}],
            },
            "properties": [
                {"name": "agentnotary:framework", "value": manifest.framework},
                {"name": "agentnotary:risk_class",
                  "value": manifest.compliance.risk_class if manifest.compliance else "unknown"},
                {"name": "agentnotary:seal_hash",
                  "value": lock.seal_hash if lock else "unsealed"},
            ],
        },
        "components": components,
        "dependencies": [
            {
                "ref": main_ref,
                "dependsOn": [c["bom-ref"] for c in components],
            },
        ],
    }


# ── SPDX renderer ───────────────────────────────────────────────────────


def _spdx_id(text: str) -> str:
    """Convert any string to a valid SPDX element ID (alphanumeric + hyphen + dot)."""
    safe = "".join(c if c.isalnum() or c in ".-" else "-" for c in text)
    return f"SPDXRef-{safe}"


def _spdx_package(spdx_id: str, name: str, version: str = "NOASSERTION", *,
                  sha256: Optional[str] = None, supplier: str = "NOASSERTION",
                  description: Optional[str] = None) -> dict:
    pkg = {
        "SPDXID": spdx_id,
        "name": name,
        "versionInfo": version,
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "supplier": (f"Organization: {supplier}" if supplier and supplier != "NOASSERTION"
                     else "NOASSERTION"),
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": "NOASSERTION",
        "copyrightText": "NOASSERTION",
    }
    if sha256:
        pkg["checksums"] = [{"algorithm": "SHA256",
                              "checksumValue": sha256.replace("sha256:", "")}]
    if description:
        pkg["description"] = description
    return pkg


def _generate_spdx(manifest: AgentManifest, lock: Optional[AgentLock]) -> dict:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc_id = "SPDXRef-DOCUMENT"
    main_id = _spdx_id(f"agent-{manifest.name}-{manifest.version}")

    packages = [
        _spdx_package(
            main_id,
            manifest.name,
            manifest.version,
            description=manifest.description,
            supplier=manifest.author or "NOASSERTION",
        ),
        _spdx_package(
            _spdx_id(f"model-{manifest.effective_provider}-{manifest.effective_model}"),
            manifest.effective_model,
            (manifest.model_spec.pinned_version if manifest.model_spec
             and manifest.model_spec.pinned_version else "NOASSERTION"),
            sha256=(lock.model.get("probe_response_hash") if lock else None),
            supplier=manifest.effective_provider,
            description="LLM foundation model",
        ),
    ]

    relationships = [
        {"spdxElementId": doc_id, "relatedSpdxElement": main_id, "relationshipType": "DESCRIBES"},
    ]

    if lock:
        for prompt in lock.prompts:
            pid = _spdx_id(f"prompt-{Path(prompt['path']).name}")
            packages.append(_spdx_package(
                pid, Path(prompt["path"]).name, "NOASSERTION",
                sha256=prompt.get("sha256"),
                description="Agent prompt asset",
            ))
            relationships.append({
                "spdxElementId": main_id, "relatedSpdxElement": pid,
                "relationshipType": "CONTAINS",
            })

        for tool in lock.tools:
            tid = _spdx_id(f"tool-{tool.get('name', 'unnamed')}")
            packages.append(_spdx_package(
                tid, tool.get("name", "unnamed"), "NOASSERTION",
                sha256=tool.get("source_sha256"),
                description=f"Agent tool ({tool.get('type', 'builtin')})",
            ))
            relationships.append({
                "spdxElementId": main_id, "relatedSpdxElement": tid,
                "relationshipType": "DEPENDS_ON",
            })

        for dataset in lock.datasets:
            did = _spdx_id(f"dataset-{Path(dataset['path']).name}")
            packages.append(_spdx_package(
                did, Path(dataset["path"]).name, "NOASSERTION",
                sha256=dataset.get("sha256"),
                description="Agent dataset",
            ))
            relationships.append({
                "spdxElementId": main_id, "relatedSpdxElement": did,
                "relationshipType": "DEPENDS_ON",
            })

    return {
        "spdxVersion": SPDX_VERSION,
        "dataLicense": "CC0-1.0",
        "SPDXID": doc_id,
        "name": f"{manifest.name}-{manifest.version}-sbom",
        "documentNamespace": f"https://agentnotary.dev/sbom/{manifest.name}/{manifest.version}/{uuid.uuid4()}",
        "creationInfo": {
            "created": timestamp,
            "creators": [f"Tool: AgentNotary-{_agentnotary_version()}"],
            "licenseListVersion": "3.21",
        },
        "packages": packages,
        "relationships": relationships,
    }


def _agentnotary_version() -> str:
    try:
        from agentnotary import __version__
        return __version__
    except ImportError:
        return "unknown"


# ── Public API ─────────────────────────────────────────────────────────


def generate_bom(base_dir: str = ".", *, format: str = "cyclonedx") -> dict:
    """Generate an SBOM document as a dict."""
    if format not in SUPPORTED_BOM_FORMATS:
        raise ValueError(
            f"Unsupported BOM format '{format}'. Supported: {', '.join(SUPPORTED_BOM_FORMATS)}"
        )

    manifest = parse_manifest(base_dir)

    lock = None
    try:
        lock = load_lock(base_dir)
    except FileNotFoundError:
        pass

    if format == "cyclonedx":
        return _generate_cyclonedx(manifest, lock)
    return _generate_spdx(manifest, lock)


def write_bom(base_dir: str = ".", *, format: str = "cyclonedx",
              output_path: Optional[str] = None) -> Path:
    """Generate and write an SBOM to disk. Default filename matches the format."""
    bom = generate_bom(base_dir, format=format)
    if output_path is None:
        output_path = "agent.sbom.cdx.json" if format == "cyclonedx" else "agent.sbom.spdx.json"
    path = Path(output_path)
    path.write_text(json.dumps(bom, indent=2), encoding="utf-8")
    return path
