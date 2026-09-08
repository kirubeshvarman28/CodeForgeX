"""Asynchronous Model Context Protocol (MCP) Client.

Enables AI agents to discover tools, execute actions over stdio with an MCP server,
inspect resources, and collect execution telemetry for deterministic evaluation.
"""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import AsyncExitStack
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@dataclass
class ToolDefinition:
    """Represents a discovered MCP tool and its input schema."""

    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)

    def to_openai_tool(self) -> Dict[str, Any]:
        """Format definition for OpenAI / function-calling LLM APIs."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def to_anthropic_tool(self) -> Dict[str, Any]:
        """Format definition for Anthropic Claude tool calling."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def to_gemini_declaration(self) -> Dict[str, Any]:
        """Format definition for Google Gemini function declarations."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema,
        }


@dataclass
class ToolCallRecord:
    """Historical telemetry record of an executed tool call."""

    timestamp: float
    tool_name: str
    arguments: Dict[str, Any]
    latency_ms: float
    success: bool
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize record to dictionary."""
        return asdict(self)


@dataclass
class ToolResult:
    """Structured result returned from calling an MCP tool."""

    tool_name: str
    success: bool
    content: str
    data: Optional[Any] = None
    is_error: bool = False
    error: Optional[str] = None
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result to dictionary."""
        return asdict(self)

    @property
    def as_text(self) -> str:
        """Return human-readable text representation of the result or error."""
        if self.is_error or not self.success:
            return self.error or self.content or f"Tool '{self.tool_name}' failed."
        return self.content


class MCPClient:
    """Asynchronous client connecting to an MCP server over stdio.

    Features:
    - Automatic subprocess lifecycle management using AsyncExitStack
    - Tool discovery and format conversion for LLM APIs (OpenAI, Claude, Gemini)
    - Resilient tool calling with structured JSON unpacking and error detection
    - Resource reading and prompt retrieval
    - In-memory telemetry and tool call history for evaluation metrics
    """

    def __init__(
        self,
        repo_root: Path | str,
        server_command: Optional[str] = None,
        server_args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        """Initialize MCPClient.

        Args:
            repo_root: Bounded repository root directory for the server.
            server_command: Executable to run (defaults to sys.executable).
            server_args: Command-line arguments to pass (defaults to ['-m', 'mcp_server']).
            env: Optional environment variable overrides.
            timeout_seconds: Subprocess communication timeout in seconds.
        """
        self.repo_root = Path(repo_root).resolve()
        self.server_command = server_command or sys.executable
        self.server_args = server_args or ["-m", "mcp_server"]
        self.custom_env = env or {}
        self.timeout_seconds = timeout_seconds

        self._exit_stack: Optional[AsyncExitStack] = None
        self._session: Optional[ClientSession] = None
        self._server_info: Optional[Any] = None
        self._tools_cache: Optional[Dict[str, ToolDefinition]] = None
        self._call_history: List[ToolCallRecord] = []

    @property
    def is_connected(self) -> bool:
        """Check whether the client is currently connected to the server."""
        return self._session is not None

    @property
    def server_info(self) -> Optional[Any]:
        """Return metadata reported by the server during handshake."""
        return self._server_info

    @property
    def call_history(self) -> List[ToolCallRecord]:
        """Return a copy of all tool call telemetry records."""
        return list(self._call_history)

    @property
    def total_calls(self) -> int:
        """Return the total number of tool calls executed."""
        return len(self._call_history)

    @property
    def successful_calls(self) -> int:
        """Return the count of successful tool calls."""
        return sum(1 for rec in self._call_history if rec.success)

    @property
    def failed_calls(self) -> int:
        """Return the count of failed tool calls."""
        return sum(1 for rec in self._call_history if not rec.success)

    @property
    def total_latency_ms(self) -> float:
        """Return the cumulative latency of all tool calls in milliseconds."""
        return sum(rec.latency_ms for rec in self._call_history)

    def reset_history(self) -> None:
        """Clear the tool call history and reset metrics counters."""
        self._call_history.clear()

    def _build_env(self) -> Dict[str, str]:
        """Construct the subprocess environment with required paths and variables."""
        env = dict(os.environ)
        # Ensure project 'src' directory is in PYTHONPATH so -m mcp_server resolves
        src_path = Path(__file__).resolve().parent.parent
        existing_pythonpath = env.get("PYTHONPATH", "")
        if existing_pythonpath:
            env["PYTHONPATH"] = f"{src_path}{os.pathsep}{existing_pythonpath}"
        else:
            env["PYTHONPATH"] = str(src_path)

        # Pass target repository root to the server
        env["REPO_ROOT"] = str(self.repo_root)
        env["WORKSPACE_ROOT"] = str(self.repo_root)

        # Apply any user-supplied overrides
        env.update(self.custom_env)
        return env

    async def connect(self) -> None:
        """Connect to the MCP server over stdio and perform initialization."""
        if self.is_connected:
            return

        exit_stack = AsyncExitStack()
        try:
            params = StdioServerParameters(
                command=self.server_command,
                args=self.server_args,
                env=self._build_env(),
                cwd=str(self.repo_root),
            )

            read_stream, write_stream = await exit_stack.enter_async_context(
                stdio_client(params)
            )

            session = await exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )

            init_result = await session.initialize()
            self._session = session
            self._exit_stack = exit_stack
            self._server_info = init_result.server_info
            self._tools_cache = None
        except Exception:
            await exit_stack.aclose()
            self._session = None
            self._exit_stack = None
            raise

    async def disconnect(self) -> None:
        """Gracefully disconnect from the server and terminate subprocesses."""
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
            self._exit_stack = None
            self._session = None
            self._server_info = None
            self._tools_cache = None

    async def __aenter__(self) -> MCPClient:
        """Enter async context, connecting to the server."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context, disconnecting from the server."""
        await self.disconnect()

    def _ensure_connected(self) -> ClientSession:
        """Validate active connection or raise RuntimeError."""
        if self._session is None:
            raise RuntimeError(
                "MCPClient is not connected. Call 'await client.connect()' "
                "or use 'async with client:' before invoking operations."
            )
        return self._session

    async def list_tools(self, refresh: bool = False) -> List[ToolDefinition]:
        """Discover tools exposed by the MCP server.

        Args:
            refresh: If True, forces a live query to the server bypassing cache.

        Returns:
            List of ToolDefinition instances describing available tools.
        """
        session = self._ensure_connected()

        if self._tools_cache is not None and not refresh:
            return list(self._tools_cache.values())

        tools_result = await session.list_tools()
        tools_map: Dict[str, ToolDefinition] = {}

        for tool in tools_result.tools:
            schema = getattr(tool, "input_schema", None)
            if schema is None:
                schema = getattr(tool, "inputSchema", {})

            tools_map[tool.name] = ToolDefinition(
                name=tool.name,
                description=tool.description or "",
                input_schema=schema if isinstance(schema, dict) else {},
            )

        self._tools_cache = tools_map
        return list(tools_map.values())

    async def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Retrieve the definition for a specific tool by name."""
        tools = await self.list_tools()
        for tool in tools:
            if tool.name == name:
                return tool
        return None

    async def get_tools_for_llm(
        self, format: Literal["openai", "anthropic", "gemini"] = "openai"
    ) -> List[Dict[str, Any]]:
        """Format discovered tools for consumption by a target LLM API.

        Args:
            format: One of 'openai', 'anthropic', or 'gemini'.

        Returns:
            List of tool schema dictionaries.
        """
        tools = await self.list_tools()
        if format == "openai":
            return [t.to_openai_tool() for t in tools]
        elif format == "anthropic":
            return [t.to_anthropic_tool() for t in tools]
        elif format == "gemini":
            return [t.to_gemini_declaration() for t in tools]
        else:
            raise ValueError(f"Unsupported LLM tool format: {format}")

    async def call_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """Invoke a tool on the MCP server and record telemetry.

        Args:
            name: The name of the tool to invoke.
            arguments: Dictionary of keyword arguments to pass to the tool.

        Returns:
            Structured ToolResult containing output, parsed JSON, and status flags.
        """
        session = self._ensure_connected()
        args = arguments or {}

        start_time = time.perf_counter()
        raw_text = ""
        is_error = False
        parsed_data: Optional[Any] = None
        error_msg: Optional[str] = None
        success = True

        try:
            result = await session.call_tool(name=name, arguments=args)
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            # Extract text blocks
            if hasattr(result, "content") and result.content:
                text_parts = [
                    block.text
                    for block in result.content
                    if hasattr(block, "text") and block.text is not None
                ]
                raw_text = "\n".join(text_parts)
            else:
                raw_text = str(result)

            is_error = getattr(result, "is_error", False) or False

            # Check if result is JSON and unpack structured data
            if raw_text.strip():
                try:
                    parsed_data = json.loads(raw_text)
                    if isinstance(parsed_data, dict):
                        # Detect application-level error payloads
                        if parsed_data.get("success") is False:
                            success = False
                            error_msg = parsed_data.get("error") or "Operation unsuccessful"
                        elif parsed_data.get("status") == "failed":
                            success = False
                            error_msg = parsed_data.get("stderr") or "Command failed"
                        elif "error" in parsed_data and parsed_data["error"]:
                            success = False
                            error_msg = str(parsed_data["error"])
                except (json.JSONDecodeError, ValueError):
                    # Output is raw string / non-JSON, keep parsed_data as None
                    pass

            if is_error:
                success = False
                if not error_msg:
                    error_msg = raw_text.strip() or f"Tool '{name}' reported an error."

        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            is_error = True
            success = False
            error_msg = str(exc)
            raw_text = f"Exception during tool call '{name}': {exc}"

        tool_result = ToolResult(
            tool_name=name,
            success=success,
            content=raw_text,
            data=parsed_data,
            is_error=is_error,
            error=error_msg,
            latency_ms=round(latency_ms, 2),
        )

        # Record telemetry
        self._call_history.append(
            ToolCallRecord(
                timestamp=time.time(),
                tool_name=name,
                arguments=args,
                latency_ms=round(latency_ms, 2),
                success=success,
                error=error_msg,
            )
        )

        return tool_result

    async def read_resource(self, uri: str) -> str:
        """Read text content from a registered MCP resource.

        Args:
            uri: Target resource URI (e.g. 'repo://overview').

        Returns:
            Resource content as string.
        """
        session = self._ensure_connected()
        result = await session.read_resource(uri)
        if hasattr(result, "contents") and result.contents:
            texts = [
                c.text for c in result.contents if hasattr(c, "text") and c.text is not None
            ]
            return "\n".join(texts)
        return ""

    async def get_prompt(
        self, name: str, arguments: Optional[Dict[str, str]] = None
    ) -> str:
        """Retrieve the formatted text of a registered MCP prompt.

        Args:
            name: Name of the prompt.
            arguments: Template variables to supply.

        Returns:
            Rendered prompt text string.
        """
        session = self._ensure_connected()
        args = arguments or {}
        result = await session.get_prompt(name=name, arguments=args)
        if hasattr(result, "messages") and result.messages:
            texts = []
            for msg in result.messages:
                if hasattr(msg, "content"):
                    if hasattr(msg.content, "text"):
                        texts.append(msg.content.text)
                    else:
                        texts.append(str(msg.content))
            return "\n\n".join(texts)
        return ""
