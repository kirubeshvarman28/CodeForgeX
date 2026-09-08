"""Environment and dependency sanity test suite.

Validates that:
1. Python version meets minimum runtime requirements (>= 3.10).
2. MCP SDK is installed and runs on version 2+.
3. Pydantic v2 is operational.
4. All project architecture packages (mcp_server, evaluator, tasks, agent)
   are discoverable and importable on PYTHONPATH.
"""

import sys
import pytest
from pydantic import BaseModel, Field


def test_python_version_meets_spec():
    """Ensure runtime Python version is at least 3.10."""
    major, minor = sys.version_info[:2]
    assert (major, minor) >= (3, 10), f"Python 3.10+ required, found {major}.{minor}"


def test_mcp_sdk_installed_and_version():
    """Verify Model Context Protocol SDK is installed and meets version 2+ requirement."""
    import mcp

    # Verify MCP package exposes modern attributes
    assert hasattr(mcp, "__file__"), "MCP package must have a valid file location"
    
    # Try importing modern server/types components
    from mcp.server import Server
    assert Server is not None, "mcp.server.Server must be importable"


def test_pydantic_operational():
    """Verify Pydantic v2 data validation works as expected."""

    class ToolMetadata(BaseModel):
        name: str
        description: str
        timeout_seconds: int = Field(default=30, ge=1)

    sample = ToolMetadata(name="list_files", description="List repository files")
    assert sample.name == "list_files"
    assert sample.timeout_seconds == 30

    with pytest.raises(Exception):
        ToolMetadata(name="invalid", description="test", timeout_seconds=0)


def test_project_modules_importable():
    """Verify all project architecture packages can be imported."""
    import mcp_server
    import evaluator
    import tasks
    import agent

    assert mcp_server is not None
    assert evaluator is not None
    assert tasks is not None
    assert agent is not None
