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
from mcp_server.security.sandbox import (
    DEFAULT_SECURITY_POLICY,
    PathTraversalError,
    ProtectedResourceError,
    ResourceLimitExceededError,
    SecurityPolicy,
    SecuritySandboxError,
)
from mcp_server.tools.filesystem import list_files_impl, read_file_impl
from mcp_server.tools.git import get_git_diff_impl, get_repository_status_impl
from mcp_server.tools.patching import apply_patch_impl
from mcp_server.tools.search import search_code_impl
from mcp_server.tools.testing import (
    GLOBAL_TEST_STORE,
    TestRunStore,
    get_test_output_impl,
    run_tests_impl,
)


def create_mcp_server(
    repo_root: Optional[Path | str] = None,
    test_store: Optional[TestRunStore] = None,
    security_policy: Optional[SecurityPolicy] = None,
) -> MCPServer:
    """Create and configure an MCPServer instance bounded to the given repository root.

    Args:
        repo_root: Root directory that bounds all tool operations. If None,
                   reads from REPO_ROOT env var or defaults to current working directory.
        test_store: Optional custom TestRunStore for test execution records.
        security_policy: Optional custom SecurityPolicy.

    Returns:
        Configured MCPServer ready to run over stdio or SSE.
    """
    if repo_root is None:
        env_root = os.environ.get("REPO_ROOT") or os.environ.get("WORKSPACE_ROOT")
        resolved_root = Path(env_root).resolve() if env_root else Path.cwd().resolve()
    else:
        resolved_root = Path(repo_root).resolve()

    store = test_store if test_store is not None else GLOBAL_TEST_STORE
    policy = security_policy if security_policy is not None else DEFAULT_SECURITY_POLICY

    server = MCPServer(
        name="software-engineering-server",
        version="0.1.0",
        instructions=(
            "Software engineering tools for inspecting, analyzing, modifying, and "
            "verifying codebases within a deterministic sandbox environment."
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
                policy=policy,
            )
            return json.dumps(result, indent=2)
        except (PathTraversalError, FileNotFoundError, NotADirectoryError, ProtectedResourceError, SecuritySandboxError) as err:
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
                policy=policy,
            )
            return json.dumps(result, indent=2)
        except (PathTraversalError, FileNotFoundError, IsADirectoryError, ValueError, ProtectedResourceError, ResourceLimitExceededError, SecuritySandboxError) as err:
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
                policy=policy,
            )
            return json.dumps(result, indent=2)
        except (PathTraversalError, FileNotFoundError, ValueError, ProtectedResourceError, SecuritySandboxError) as err:
            return json.dumps({"error": str(err), "success": False})
        except Exception as err:
            return json.dumps({"error": f"Unexpected error: {err}", "success": False})

    @server.tool()
    def run_tests(
        test_target: str = "",
        timeout_seconds: int = 30,
    ) -> str:
        """Execute automated pytest tests within the repository sandbox.

        Args:
            test_target: Optional relative test file or test node (e.g. 'tests/test_math.py::test_add').
            timeout_seconds: Maximum time allowed before terminating process (default: 30s).

        Returns:
            JSON string with exit code, passed/failed counts, duration, and output summary.
        """
        try:
            result = run_tests_impl(
                repo_root=resolved_root,
                test_target=test_target,
                timeout_seconds=timeout_seconds,
                store=store,
            )
            return json.dumps(result, indent=2)
        except (PathTraversalError, FileNotFoundError, SecuritySandboxError) as err:
            return json.dumps({"error": str(err), "success": False})
        except Exception as err:
            return json.dumps({"error": f"Unexpected error: {err}", "success": False})

    @server.tool()
    def get_test_output(
        run_id: str = "",
        full: bool = False,
    ) -> str:
        """Retrieve test execution output and logs from a previous test run.

        Args:
            run_id: Specific test run identifier (empty string defaults to most recent run).
            full: If True, returns full untruncated stdout and stderr (default: False).

        Returns:
            JSON string containing logs, exit code, duration, and pass/fail counts.
        """
        try:
            result = get_test_output_impl(
                store=store,
                run_id=run_id if run_id.strip() else None,
                full=full,
            )
            return json.dumps(result, indent=2)
        except KeyError as err:
            return json.dumps({"error": str(err), "success": False})
        except Exception as err:
            return json.dumps({"error": f"Unexpected error: {err}", "success": False})

    @server.tool()
    def apply_patch(
        patch: str,
        file_path: str = "",
    ) -> str:
        """Atomically apply a unified diff patch to repository files.

        Args:
            patch: The unified diff content (e.g., standard 'diff --git' or '--- / +++' format).
            file_path: Optional relative target path if targeting a single file.

        Returns:
            JSON string with success status, list of changed files, and status message.
        """
        try:
            result = apply_patch_impl(
                repo_root=resolved_root,
                patch=patch,
                file_path=file_path.strip() if file_path.strip() else None,
                policy=policy,
            )
            return json.dumps(result, indent=2)
        except (PathTraversalError, ValueError, ProtectedResourceError, ResourceLimitExceededError, SecuritySandboxError) as err:
            return json.dumps({"error": str(err), "success": False})
        except Exception as err:
            return json.dumps({"error": f"Unexpected error: {err}", "success": False})

    @server.tool()
    def get_git_diff(
        path: str = "",
        cached: bool = False,
    ) -> str:
        """Retrieve the deterministic Git diff of changes made in the repository.

        Args:
            path: Optional relative file or directory path to scope the diff.
            cached: If True, inspects staged changes (git diff --cached) (default: False).

        Returns:
            JSON string containing diff string, has_changes boolean, and changed_files list.
        """
        try:
            result = get_git_diff_impl(
                repo_root=resolved_root,
                path=path,
                cached=cached,
            )
            return json.dumps(result, indent=2)
        except (PathTraversalError, RuntimeError, SecuritySandboxError) as err:
            return json.dumps({"error": str(err), "success": False})
        except Exception as err:
            return json.dumps({"error": f"Unexpected error: {err}", "success": False})

    @server.tool()
    def get_repository_status() -> str:
        """Inspect the current Git repository status (modified, staged, untracked files).

        Returns:
            JSON string with branch, clean flag, and lists of modified/staged/untracked files.
        """
        try:
            result = get_repository_status_impl(repo_root=resolved_root)
            return json.dumps(result, indent=2)
        except (RuntimeError, SecuritySandboxError) as err:
            return json.dumps({"error": str(err), "success": False})
        except Exception as err:
            return json.dumps({"error": f"Unexpected error: {err}", "success": False})

    @server.resource(uri="repo://overview")
    def get_repo_overview() -> str:
        """Resource providing high-level repository metadata and bounded root location."""
        return json.dumps({
            "bounded_root": str(resolved_root),
            "available_tools": [
                "list_files",
                "read_file",
                "search_code",
                "run_tests",
                "get_test_output",
                "apply_patch",
                "get_git_diff",
                "get_repository_status",
            ],
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
            "3. Use `read_file` to inspect the relevant files and understand current logic before modifying anything.\n"
            "4. Use `run_tests` to observe current test suite results and verify baseline behavior."
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
