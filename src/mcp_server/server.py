"""Model Context Protocol (MCP) Server for Software Engineering Agent.

Exposes security-contained repository exploration, code reading, and search tools
via the official MCP Python SDK v2 (MCPServer).
"""

import argparse
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
        title="CodeForgeX",
        description="Deterministic AI-Agent Evaluation & Software Engineering Tools over Model Context Protocol",
        instructions=(
            "Software engineering tools for inspecting, analyzing, modifying, and "
            "verifying codebases within a deterministic sandbox environment."
        ),
        website_url="https://github.com/kirubeshvarman28/CodeForgeX",
        version="0.1.0",
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
                policy=policy,
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

    @server.custom_route(path="/", methods=["GET"])
    async def handle_root(request: Any) -> Any:
        """Root landing endpoint providing health status and MCP endpoint information."""
        from starlette.responses import HTMLResponse, JSONResponse

        accept = request.headers.get("accept", "")
        payload = {
            "name": "CodeForgeX MCP Server",
            "status": "online",
            "version": "0.1.0",
            "mcp_endpoint": "/mcp",
            "transport": "streamable-http",
            "docs": "https://github.com/kirubeshvarman28/CodeForgeX",
            "smithery_verification": "69dde62346c27143101b851dd010b4611127f550d3cc0e71bc510f774d791f0f",
            "smithery_url": "https://smithery.ai/servers/kirubeshvarman28/codeforgex",
            "tools_count": 8,
            "tools": [
                "list_files",
                "read_file",
                "search_code",
                "run_tests",
                "get_test_output",
                "apply_patch",
                "get_git_diff",
                "get_repository_status",
            ],
        }
        if "text/html" in accept:
            html = """<!DOCTYPE html>
<html>
<head>
    <title>CodeForgeX MCP Server</title>
    <meta name="smithery-verification" content="69dde62346c27143101b851dd010b4611127f550d3cc0e71bc510f774d791f0f">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 32px; max-width: 600px; width: 100%; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
        .badge { display: inline-block; background: #10b981; color: #0f172a; font-weight: bold; font-size: 12px; padding: 4px 10px; border-radius: 9999px; text-transform: uppercase; margin-bottom: 16px; }
        h1 { margin: 0 0 8px 0; font-size: 24px; }
        p { color: #94a3b8; font-size: 14px; line-height: 1.5; margin: 0 0 20px 0; }
        .endpoint-box { background: #0f172a; border: 1px solid #475569; border-radius: 8px; padding: 12px 16px; font-family: monospace; font-size: 14px; color: #38bdf8; margin-bottom: 20px; word-break: break-all; }
        .tools-list { list-style: none; padding: 0; margin: 0 0 20px 0; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        .tools-list li { background: #0f172a; padding: 8px 12px; border-radius: 6px; font-family: monospace; font-size: 12px; border: 1px solid #334155; color: #cbd5e1; }
        a { color: #38bdf8; text-decoration: none; font-size: 14px; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="card">
        <span class="badge">&#9679; Online &amp; Ready</span>
        <h1>CodeForgeX MCP Server</h1>
        <p>Deterministic AI-Agent Evaluation &amp; Software Engineering Tools over Model Context Protocol.</p>
        <div style="font-size: 12px; color: #94a3b8; margin-bottom: 6px;">MCP Streamable HTTP Endpoint:</div>
        <div class="endpoint-box">/mcp</div>
        <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">Active Tools (8):</div>
        <ul class="tools-list">
            <li>&#10003; list_files</li>
            <li>&#10003; read_file</li>
            <li>&#10003; search_code</li>
            <li>&#10003; run_tests</li>
            <li>&#10003; get_test_output</li>
            <li>&#10003; apply_patch</li>
            <li>&#10003; get_git_diff</li>
            <li>&#10003; get_repository_status</li>
        </ul>
        <div style="display: flex; gap: 16px; margin-top: 12px; flex-wrap: wrap;">
            <a href="https://github.com/kirubeshvarman28/CodeForgeX" target="_blank">GitHub Repository &rarr;</a>
            <a href="https://smithery.ai/servers/kirubeshvarman28/codeforgex" target="_blank">Smithery Registry &rarr;</a>
        </div>
    </div>
</body>
</html>"""

            return HTMLResponse(content=html, status_code=200)
        return JSONResponse(content=payload, status_code=200)

    @server.custom_route(path="/health", methods=["GET"])
    async def handle_health(request: Any) -> Any:
        """Healthcheck route returning service status."""
        from starlette.responses import JSONResponse
        return JSONResponse({"status": "healthy", "service": "codeforgex-mcp"}, status_code=200)

    return server



async def _run_server_main(
    repo_root: Optional[str] = None,
    transport: str = "stdio",
    host: str = "0.0.0.0",
    port: int = 8000,
):
    """Main asynchronous entry point to launch MCP server over stdio or HTTP/SSE."""
    server = create_mcp_server(repo_root=repo_root)
    if transport == "streamable-http":
        print(f"[CodeForgeX] Starting Streamable HTTP server on http://{host}:{port}/mcp ...")
        await server.run_streamable_http_async(host=host, port=port)
    elif transport == "sse":
        print(f"[CodeForgeX] Starting SSE server on http://{host}:{port}/sse ...")
        await server.run_sse_async(host=host, port=port)
    else:
        await server.run_stdio_async()


def main():
    """Synchronous entry point for the CLI / module execution."""
    parser = argparse.ArgumentParser(description="CodeForgeX MCP Software Engineering Server")
    parser.add_argument(
        "--repo-root",
        "-r",
        type=str,
        default=None,
        help="Repository root directory to bound tool operations (defaults to REPO_ROOT env var or current directory)",
    )
    parser.add_argument(
        "--transport",
        "-t",
        type=str,
        choices=["stdio", "streamable-http", "sse"],
        default=os.environ.get("MCP_TRANSPORT", "stdio"),
        help="MCP transport protocol (stdio, streamable-http, or sse; default: stdio)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=os.environ.get("HOST", "0.0.0.0"),
        help="Host interface to bind HTTP/SSE server (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="Port to bind HTTP/SSE server (default: 8000 or $PORT)",
    )
    args, _ = parser.parse_known_args()
    try:
        asyncio.run(
            _run_server_main(
                repo_root=args.repo_root,
                transport=args.transport,
                host=args.host,
                port=args.port,
            )
        )
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
