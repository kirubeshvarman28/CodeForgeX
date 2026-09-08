"""Unit tests for the MCP Server initialization, tool dispatch, resources, and prompts."""

import json
import pytest
from pathlib import Path
from mcp_server.server import create_mcp_server


@pytest.fixture
def dummy_repo(tmp_path: Path) -> Path:
    """Create a temporary dummy repository structure for server integration."""
    repo = tmp_path / "server_test_repo"
    repo.mkdir()

    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (repo / "README.md").write_text("# Calc Project\n", encoding="utf-8")

    return repo


@pytest.mark.anyio
async def test_mcp_server_lists_tools(dummy_repo: Path):
    """Verify MCPServer registers expected tools with schemas and descriptions."""
    server = create_mcp_server(dummy_repo)
    tools = await server.list_tools()

    tool_names = [t.name for t in tools]
    assert "list_files" in tool_names
    assert "read_file" in tool_names
    assert "search_code" in tool_names

    # Check descriptions
    list_tool = next(t for t in tools if t.name == "list_files")
    assert "List files" in list_tool.description


@pytest.mark.anyio
async def test_mcp_server_call_list_files(dummy_repo: Path):
    """Verify calling list_files via server.call_tool returns valid structured output."""
    server = create_mcp_server(dummy_repo)
    result = await server.call_tool("list_files", {"directory": "", "recursive": True})

    assert not result.is_error
    assert len(result.content) > 0
    payload = json.loads(result.content[0].text)

    assert "entries" in payload
    paths = [e["path"] for e in payload["entries"]]
    assert "src/calc.py" in paths
    assert "README.md" in paths


@pytest.mark.anyio
async def test_mcp_server_call_read_file(dummy_repo: Path):
    """Verify calling read_file via server.call_tool returns content and line metadata."""
    server = create_mcp_server(dummy_repo)
    result = await server.call_tool("read_file", {"path": "src/calc.py", "start_line": 1, "end_line": 2})

    assert not result.is_error
    payload = json.loads(result.content[0].text)

    assert payload["path"] == "src/calc.py"
    assert "def add(a, b):" in payload["content"]
    assert payload["start_line"] == 1
    assert payload["end_line"] == 2


@pytest.mark.anyio
async def test_mcp_server_call_search_code(dummy_repo: Path):
    """Verify calling search_code via server.call_tool returns matches."""
    server = create_mcp_server(dummy_repo)
    result = await server.call_tool("search_code", {"query": "def add"})

    assert not result.is_error
    payload = json.loads(result.content[0].text)

    assert payload["total_matches"] == 1
    assert payload["matches"][0]["path"] == "src/calc.py"
    assert payload["matches"][0]["line_number"] == 1


@pytest.mark.anyio
async def test_mcp_server_blocks_traversal_gracefully(dummy_repo: Path):
    """Verify security errors return structured error JSON without crashing the server."""
    server = create_mcp_server(dummy_repo)
    result = await server.call_tool("read_file", {"path": "../../passwords.txt"})

    # The tool caught the PathTraversalError and returned formatted error JSON
    assert not result.is_error
    payload = json.loads(result.content[0].text)
    assert "error" in payload
    assert "Security violation" in payload["error"]


@pytest.mark.anyio
async def test_mcp_server_resources_and_prompts(dummy_repo: Path):
    """Verify MCPServer exposes registered resources and prompts."""
    server = create_mcp_server(dummy_repo)

    resources = await server.list_resources()
    resource_uris = [str(r.uri) for r in resources]
    assert "repo://overview" in resource_uris

    prompts = await server.list_prompts()
    prompt_names = [p.name for p in prompts]
    assert "explore_repository_prompt" in prompt_names
