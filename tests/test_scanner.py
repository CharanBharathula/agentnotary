"""Tests for the codebase agent scanner."""


import pytest

from agentbox.scanner import format_scan_results, scan_directory, scan_file

LANGCHAIN_SAMPLE = """\
from langchain.agents import AgentExecutor, create_react_agent
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o")
agent_executor = AgentExecutor(agent=agent, tools=tools)
"""

ANTHROPIC_SAMPLE = """\
import anthropic

client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    tools=[{"name": "search", "description": "Search the web"}],
    messages=[{"role": "user", "content": "Hello"}],
)
"""

CREWAI_SAMPLE = """\
from crewai import Agent, Crew, Task

researcher = Agent(
    role="Research Analyst",
    goal="Research topics",
    backstory="Expert researcher",
)
crew = Crew(agents=[researcher], tasks=[Task(description="Research AI")])
"""

PLAIN_PYTHON = """\
def add(a, b):
    return a + b

class Calculator:
    def multiply(self, x, y):
        return x * y
"""


@pytest.fixture
def code_dir(tmp_path):
    (tmp_path / "langchain_agent.py").write_text(LANGCHAIN_SAMPLE)
    (tmp_path / "anthropic_agent.py").write_text(ANTHROPIC_SAMPLE)
    (tmp_path / "crewai_agent.py").write_text(CREWAI_SAMPLE)
    (tmp_path / "plain.py").write_text(PLAIN_PYTHON)
    return tmp_path


def test_scan_file_detects_langchain(tmp_path):
    f = tmp_path / "agent.py"
    f.write_text(LANGCHAIN_SAMPLE)
    results = scan_file(str(f))
    frameworks = [r.framework for r in results]
    assert "langchain" in frameworks


def test_scan_file_detects_anthropic(tmp_path):
    f = tmp_path / "agent.py"
    f.write_text(ANTHROPIC_SAMPLE)
    results = scan_file(str(f))
    frameworks = [r.framework for r in results]
    assert "anthropic_sdk" in frameworks


def test_scan_file_detects_crewai(tmp_path):
    f = tmp_path / "agent.py"
    f.write_text(CREWAI_SAMPLE)
    results = scan_file(str(f))
    frameworks = [r.framework for r in results]
    assert "crewai" in frameworks


def test_scan_file_no_false_positive(tmp_path):
    f = tmp_path / "plain.py"
    f.write_text(PLAIN_PYTHON)
    results = scan_file(str(f))
    assert results == []


def test_scan_file_detects_tools(tmp_path):
    f = tmp_path / "agent.py"
    f.write_text(ANTHROPIC_SAMPLE)
    results = scan_file(str(f))
    assert any(r.has_tools for r in results)


def test_scan_directory_finds_all_agents(code_dir):
    agents, files_scanned = scan_directory(str(code_dir))
    assert files_scanned >= 4
    assert len(agents) >= 3


def test_scan_directory_skips_pycache(tmp_path):
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "agent.py").write_text(LANGCHAIN_SAMPLE)
    agents, _ = scan_directory(str(tmp_path))
    for a in agents:
        assert "__pycache__" not in a.filepath


def test_format_scan_results_structure(code_dir):
    agents, files_scanned = scan_directory(str(code_dir))
    report = format_scan_results(agents, files_scanned)
    assert "total_agents_found" in report
    assert "files_scanned" in report
    assert "ungoverned_agents" in report
    assert "frameworks" in report
    assert "agents" in report
    assert report["files_scanned"] == files_scanned
    assert report["total_agents_found"] == len(agents)


def test_format_scan_results_ungoverned_count(tmp_path):
    # Agent without guardrails
    (tmp_path / "agent.py").write_text(LANGCHAIN_SAMPLE)
    agents, files = scan_directory(str(tmp_path))
    report = format_scan_results(agents, files)
    ungoverned = [a for a in agents if not a.has_guardrails]
    assert report["ungoverned_agents"] == len(ungoverned)


def test_scan_file_extracts_model(tmp_path):
    f = tmp_path / "agent.py"
    f.write_text(ANTHROPIC_SAMPLE)
    results = scan_file(str(f))
    anthropic_results = [r for r in results if r.framework == "anthropic_sdk"]
    if anthropic_results:
        # Should have extracted a model name
        assert anthropic_results[0].model != ""
