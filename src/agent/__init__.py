"""Agent module for CodeForgeX.

Includes MCP Client layer, ReAct loop execution, planning, and evaluation telemetry.
"""

from agent.client import MCPClient, ToolCallRecord, ToolDefinition, ToolResult
from agent.loop import AgentExecutionLoop, AgentRunResult
from agent.planner import (
    AgentAction,
    BasePlanner,
    LLMPlanner,
    PlanStage,
    SystematicSWEPlanner,
    TrajectoryStep,
)

__all__ = [
    # Client
    "MCPClient",
    "ToolDefinition",
    "ToolCallRecord",
    "ToolResult",
    # Planning
    "PlanStage",
    "AgentAction",
    "TrajectoryStep",
    "BasePlanner",
    "SystematicSWEPlanner",
    "LLMPlanner",
    # Execution Loop
    "AgentExecutionLoop",
    "AgentRunResult",
]
