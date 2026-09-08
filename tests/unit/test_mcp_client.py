"""Unit tests for the MCPClient layer and stdio communication."""

import os
from pathlib import Path

import pytest
from agent.client import MCPClient, ToolCallRecord, ToolDefinition, ToolResult


@pytest.mark.anyio
async def test_client_lifecycle_and_handshake():
    """Verify MCPClient connects over stdio, performs handshake, and disconnects cleanly."""
    root = Path(".").resolve()
    client = MCPClient(repo_root=root)

    assert not client.is_connected
    assert client.server_info is None

    async with client:
        assert client.is_connected
        assert client.server_info is not None
        assert client.server_info.name == "software-engineering-server"
        assert client.server_info.version == "0.1.0"

    assert not client.is_connected
    assert client.server_info is None


@pytest.mark.anyio
async def test_client_not_connected_raises():
    """Verify invoking operations before connection raises RuntimeError."""
    client = MCPClient(repo_root=Path(".").resolve())

    with pytest.raises(RuntimeError, match="MCPClient is not connected"):
        await client.list_tools()

    with pytest.raises(RuntimeError, match="MCPClient is not connected"):
        await client.call_tool("list_files", {})

    with pytest.raises(RuntimeError, match="MCPClient is not connected"):
        await client.read_resource("repo://overview")


@pytest.mark.anyio
async def test_client_tool_discovery_and_schema_conversion():
    """Verify discovery of all 8 MCP tools and schema transformation for LLMs."""
    async with MCPClient(repo_root=Path(".").resolve()) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}

        expected_tools = {
            "list_files",
            "read_file",
            "search_code",
            "run_tests",
            "get_test_output",
            "apply_patch",
            "get_git_diff",
            "get_repository_status",
        }
        assert expected_tools.issubset(tool_names)

        # Test single tool retrieval
        list_tool = await client.get_tool("list_files")
        assert list_tool is not None
        assert list_tool.name == "list_files"
        assert "directory" in list_tool.input_schema.get("properties", {})

        # Test OpenAI format
        openai_schema = list_tool.to_openai_tool()
        assert openai_schema["type"] == "function"
        assert openai_schema["function"]["name"] == "list_files"
        assert "parameters" in openai_schema["function"]

        # Test Anthropic format
        anthropic_schema = list_tool.to_anthropic_tool()
        assert anthropic_schema["name"] == "list_files"
        assert "input_schema" in anthropic_schema

        # Test Gemini format
        gemini_schema = list_tool.to_gemini_declaration()
        assert gemini_schema["name"] == "list_files"
        assert "parameters" in gemini_schema

        # Test bulk converter
        openai_tools = await client.get_tools_for_llm("openai")
        assert len(openai_tools) >= 8
        assert all(t["type"] == "function" for t in openai_tools)


@pytest.mark.anyio
async def test_client_tool_calling_filesystem_and_search():
    """Verify invoking filesystem and search tools unpacks structured JSON."""
    async with MCPClient(repo_root=Path(".").resolve()) as client:
        # 1. list_files
        list_res = await client.call_tool(
            "list_files", {"directory": "", "recursive": False}
        )
        assert list_res.success
        assert not list_res.is_error
        assert list_res.data is not None
        assert list_res.data["total_entries"] > 0
        assert any(e["path"] == "pyproject.toml" for e in list_res.data["entries"])

        # 2. read_file
        read_res = await client.call_tool(
            "read_file", {"path": "pyproject.toml", "start_line": 1, "end_line": 10}
        )
        assert read_res.success
        assert not read_res.is_error
        assert "mcp-software-engineering-agent" in read_res.content
        assert read_res.data["path"] == "pyproject.toml"

        # 3. search_code
        search_res = await client.call_tool(
            "search_code", {"query": "create_mcp_server", "path": "src"}
        )
        assert search_res.success
        assert not search_res.is_error
        assert search_res.data["total_matches"] > 0


@pytest.mark.anyio
async def test_client_tool_error_handling():
    """Verify application-level errors and invalid tools return clean ToolResults."""
    async with MCPClient(repo_root=Path(".").resolve()) as client:
        # Calling tool with invalid file
        read_err = await client.call_tool(
            "read_file", {"path": "completely_non_existent_file_xyz.py"}
        )
        assert not read_err.success
        assert read_err.error is not None
        assert "does not exist" in read_err.error.lower()

        # Calling non-existent tool
        unknown_err = await client.call_tool("non_existent_tool_123", {})
        assert not unknown_err.success
        assert unknown_err.error is not None
        assert "Unknown tool" in unknown_err.error


@pytest.mark.anyio
async def test_client_telemetry_tracking():
    """Verify MCPClient accurately logs tool calls, latency, and success counters."""
    async with MCPClient(repo_root=Path(".").resolve()) as client:
        assert client.total_calls == 0

        # Success call
        await client.call_tool("list_files", {"directory": "", "recursive": False})
        # Error call
        await client.call_tool("read_file", {"path": "missing_xyz.py"})
        # Another success call
        await client.call_tool("search_code", {"query": "pytest"})

        assert client.total_calls == 3
        assert client.successful_calls == 2
        assert client.failed_calls == 1
        assert client.total_latency_ms > 0

        history = client.call_history
        assert len(history) == 3
        assert history[0].tool_name == "list_files"
        assert history[0].success is True
        assert history[1].tool_name == "read_file"
        assert history[1].success is False

        # Reset history
        client.reset_history()
        assert client.total_calls == 0
        assert len(client.call_history) == 0


@pytest.mark.anyio
async def test_client_resources_and_prompts():
    """Verify reading MCP resources and retrieving prompt templates."""
    async with MCPClient(repo_root=Path(".").resolve()) as client:
        # Read resource
        overview_text = await client.read_resource("repo://overview")
        assert "bounded_root" in overview_text
        assert "available_tools" in overview_text

        # Retrieve prompt
        prompt_text = await client.get_prompt(
            "explore_repository_prompt", {"objective": "Investigate memory leak"}
        )
        assert "Investigate memory leak" in prompt_text
        assert "list_files" in prompt_text
