"""
AgentNotary Scanner
================
Discovers AI agents in a codebase — finds shadow agents across frameworks.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DiscoveredAgent:
    filepath: str
    framework: str
    agent_type: str  # chat, chain, crew, tool_calling, custom
    model: str = "unknown"
    line_number: int = 0
    has_tools: bool = False
    has_guardrails: bool = False
    has_memory: bool = False
    confidence: str = "high"  # high, medium, low


# Patterns to detect agent usage across frameworks
DETECTION_PATTERNS = {
    "langchain": [
        (r"from langchain.*import.*Agent", "agent_import"),
        (r"from langchain.*import.*Chain", "chain_import"),
        (r"AgentExecutor", "agent_executor"),
        (r"create_react_agent|create_openai_tools_agent", "agent_factory"),
        (r"ChatOpenAI|ChatAnthropic|ChatGoogleGenerativeAI", "chat_model"),
        (r"ConversationBufferMemory|ConversationSummaryMemory", "memory"),
    ],
    "crewai": [
        (r"from crewai import", "crewai_import"),
        (r"Agent\(.*role=", "crewai_agent"),
        (r"Crew\(", "crewai_crew"),
        (r"Task\(", "crewai_task"),
    ],
    "autogen": [
        (r"from autogen import|import autogen", "autogen_import"),
        (r"AssistantAgent|UserProxyAgent|ConversableAgent", "autogen_agent"),
        (r"GroupChat\(", "autogen_groupchat"),
    ],
    "openai_sdk": [
        (r"openai\.OpenAI|from openai import", "openai_import"),
        (r"client\.chat\.completions\.create", "openai_chat"),
        (r"tools=\[|functions=\[", "openai_tools"),
        (r"type.*function", "openai_function_call"),
    ],
    "anthropic_sdk": [
        (r"anthropic\.Anthropic|from anthropic import", "anthropic_import"),
        (r"client\.messages\.create|\.messages\.create", "anthropic_chat"),
        (r"tools=\[", "anthropic_tools"),
    ],
    "llamaindex": [
        (r"from llama_index|from llamaindex", "llamaindex_import"),
        (r"QueryEngine|ChatEngine", "llamaindex_engine"),
        (r"AgentRunner|ReActAgent", "llamaindex_agent"),
    ],
    "dspy": [
        (r"import dspy|from dspy", "dspy_import"),
        (r"dspy\.Predict|dspy\.ChainOfThought", "dspy_module"),
    ],
}

TOOL_PATTERNS = [
    r"@tool|Tool\(|BaseTool|StructuredTool",
    r"tools=\[|tools:\s*\[",
    r"function_call|tool_choice",
    r"mcp.*server|MCPServer|mcp_servers",
]

GUARDRAIL_PATTERNS = [
    r"guardrail|safety|content_filter|moderation",
    r"max_iterations|max_tokens|rate_limit",
    r"human_approval|requires_approval|human_in_loop",
    r"NeMoGuardrails|guardrails_ai",
]

MEMORY_PATTERNS = [
    r"memory|conversation_history|chat_history",
    r"ConversationBuffer|ChatMessageHistory",
    r"VectorStore|ChromaDB|Pinecone|Weaviate",
    r"redis.*cache|MemoryStore",
]


def scan_file(filepath: str) -> list:
    """Scan a single file for agent usage."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return []

    lines = content.split("\n")
    discovered = []

    for framework, patterns in DETECTION_PATTERNS.items():
        matches = []
        for pattern, pattern_type in patterns:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line):
                    matches.append((i, pattern_type))

        if len(matches) >= 2:  # Need at least 2 pattern matches for confidence
            # Detect model
            model = "unknown"
            model_patterns = [
                (r'model["\s]*[:=]\s*["\']([^"\']+)', None),
                (r'model_name["\s]*[:=]\s*["\']([^"\']+)', None),
            ]
            for mp, _ in model_patterns:
                m = re.search(mp, content)
                if m:
                    model = m.group(1)
                    break

            has_tools = any(re.search(p, content) for p in TOOL_PATTERNS)
            has_guardrails = any(re.search(p, content) for p in GUARDRAIL_PATTERNS)
            has_memory = any(re.search(p, content) for p in MEMORY_PATTERNS)

            confidence = "high" if len(matches) >= 3 else "medium"

            discovered.append(DiscoveredAgent(
                filepath=filepath,
                framework=framework,
                agent_type="tool_calling" if has_tools else "chat",
                model=model,
                line_number=matches[0][0],
                has_tools=has_tools,
                has_guardrails=has_guardrails,
                has_memory=has_memory,
                confidence=confidence,
            ))

    return discovered


def scan_directory(root_dir: str, extensions: set = None) -> list:
    """Scan an entire directory for AI agents."""
    if extensions is None:
        extensions = {".py", ".ts", ".js", ".tsx", ".jsx", ".mjs"}

    skip_dirs = {
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        "env", ".env", "dist", "build", ".agentnotary",
    }

    all_discovered = []
    files_scanned = 0

    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]

        for filename in filenames:
            if Path(filename).suffix in extensions:
                filepath = os.path.join(dirpath, filename)
                files_scanned += 1
                agents = scan_file(filepath)
                all_discovered.extend(agents)

    return all_discovered, files_scanned


def format_scan_results(agents: list, files_scanned: int) -> dict:
    """Format scan results into a structured report."""
    frameworks = {}
    for a in agents:
        frameworks.setdefault(a.framework, []).append(a)

    ungoverned = [a for a in agents if not a.has_guardrails]

    return {
        "total_agents_found": len(agents),
        "files_scanned": files_scanned,
        "frameworks": {k: len(v) for k, v in frameworks.items()},
        "ungoverned_agents": len(ungoverned),
        "agents_with_tools": sum(1 for a in agents if a.has_tools),
        "agents_with_memory": sum(1 for a in agents if a.has_memory),
        "agents_with_guardrails": sum(1 for a in agents if a.has_guardrails),
        "agents": [
            {
                "file": a.filepath,
                "line": a.line_number,
                "framework": a.framework,
                "model": a.model,
                "tools": a.has_tools,
                "guardrails": a.has_guardrails,
                "memory": a.has_memory,
                "confidence": a.confidence,
            }
            for a in agents
        ],
    }
