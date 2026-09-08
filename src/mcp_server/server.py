"""Model Context Protocol (MCP) Server for Software Engineering Agent.

Exposes security-contained repository exploration, code reading, and search tools
via the official MCP Python SDK v2 (MCPServer).
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from mcp.server.mcpserver import MCPServer
from mcp_server.security.sandbox import PathTraversalError, SecuritySandboxError
from mcp_server.tools.filesystem import list_files_impl, read_file_impl
from mcp_server.tools.search import search_code_impl


def create_mcp_server(repo_root: Optional[Path | str] = None) -> MCPServer:
    """Create and configure an MCPServer instance bounded to the given repository root.

    Args:
        repo_root: Root directory that bounds all tool operations. If None,
                   reads from REPO_ROOT env var or defaults to current working directory.

    Returns:
        Configured MCPServer ready to run over stdio or SSE.
    """
    if repo_root is None:
        env_root = os.environ.get("REPO_ROOT") or os.environ.get("WORKSPACE_ROOT")
        resolved_root = Path(env_root).resolve() if env_root else Path.cwd().resolve()
    else:
        resolved_root = Path(repo_root).resolve()

    server = MCPServer(
        name="software-engineering-server",
        version="0.1.0",
        instructions=(
            "Software engineering tools for inspecting, analyzing, and modifying "
            "codebases within a deterministic sandbox environment."
        ),
    )

    @server.tool()
    def list_files(
        directory: str = "",
        recursive: bool = True,
        max_depth: int = 10,
    ) -> str:
        """List files and directories in the repository.

        Args:
            directory: Relative subfolder inside the repository (empty string for root).
            recursive: Whether to list recursively through child directories (default: True).
            max_depth: Maximum directory recursion depth (default: 10).

        Returns:
            JSON string containing total_entries and a structured list of files with sizes.
        """
        try:
            result = list_files_impl(
                repo_root=resolved_root,
                directory=directory,
                recursive=recursive,
                max_depth=max_depth,
            )
            return json.dumps(result, indent=2)
        except (PathTraversalError, FileNotFoundError, NotADirectoryError, SecuritySandboxError) as err:
            return json.dumps({"error": str(err), "success": False})
        except Exception as err:
            return json.dumps({"error": f"Unexpected error: {err}", "success": False})

    @server.tool()
    def read_file(
        path: str,
        start_line: int = 1,
        end_line: Optional[int] = None,
    ) -> str:
        """Read text content from a file inside the repository with line windowing.

        Args:
            path: Relative path to the file inside the repository.
            start_line: 1-indexed starting line number (default: 1).
            end_line: 1-indexed ending line number (default: None, reads up to 1000 lines).

        Returns:
            JSON string containing path, line numbers, content, and truncation status.
        """
        try:
            result = read_file_impl(
                repo_root=resolved_root,
                path=path,
                start_line=start_line,
                end_line=end_line,
            )
            return json.dumps(result, indent=2)
        except (PathTraversalError, FileNotFoundError, IsADirectoryError, ValueError, SecuritySandboxError) as err:
            return json.dumps({"error": str(err), "success": False})
        except Exception as err:
            return json.dumps({"error": f"Unexpected error: {err}", "success": False})

    @server.tool()
    def search_code(
        query: str,
        path: str = "",
        is_regex: bool = False,
        case_sensitive: bool = False,
        max_results: int = 50,
    ) -> str:
        """Search for literal text or regular expressions across repository files.

        Args:
            query: The substring or regex to search for.
            path: Optional relative directory or file to constrain search scope.
            is_regex: Whether query is a regular expression (default: False).
            case_sensitive: Whether match should be case-sensitive (default: False).
            max_results: Maximum matching lines to return (default: 50).

        Returns:
            JSON string with matched lines, line numbers, and file paths.
        """
        try:
            result = search_code_impl(
                repo_root=resolved_root,
                query=query,
                path=path,
                is_regex=is_regex,
                case_sensitive=case_sensitive,
                max_results=max_results,
            )
            return json.dumps(result, indent=2)
        except (PathTraversalError, FileNotFoundError, ValueError, SecuritySandboxError) as err:
            return json.dumps({"error": str(err), "success": False})
        except Exception as err:
            return json.dumps({"error": f"Unexpected error: {err}", "success": False})

    @server.resource(uri="repo://overview")
    def get_repo_overview() -> str:
        """Resource providing high-level repository metadata and bounded root location."""
        return json.dumps({
            "bounded_root": str(resolved_root),
            "available_tools": ["list_files", "read_file", "search_code"],
            "status": "ready",
        }, indent=2)

    @server.prompt()
    def explore_repository_prompt(objective: str) -> str:
        """Prompt template guiding an agent to explore a repository systematically."""
        return (
            f"You are investigating a codebase with the following objective:\n'{objective}'\n\n"
            "Workflow:\n"
            "1. Use `list_files` to discover the top-level modules and directory structure.\n"
            "2. Use `search_code` to locate key function/class definitions relevant to the objective.\n"
            "3. Use `read_file` to inspect the relevant files and understand current logic before modifying anything."
        )

    return server


async def _run_server_main():
    """Main asynchronous entry point to launch MCP server over stdio."""
    server = create_mcp_server()
    await server.run_stdio_async()


def main():
    """Synchronous entry point for the CLI / module execution."""
    try:
        asyncio.run(_run_server_main())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
