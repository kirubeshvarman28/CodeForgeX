"""ReAct Execution Loop for Autonomous Software Engineering Agent.

Executes the Observe -> Reason -> Act -> Reflect cycle, managing iteration limits,
tool execution through MCPClient, failure circuit breakers, and final diff extraction.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from agent.client import MCPClient, ToolCallRecord
from agent.planner import BasePlanner, PlanStage, TrajectoryStep


@dataclass
class AgentRunResult:
    """Final summary of an agent execution trial."""

    task_id: str
    success: bool
    completed: bool
    iterations: int
    final_patch: str
    tool_calls_count: int
    failed_calls_count: int
    duration_seconds: float
    termination_reason: str
    trajectory: List[TrajectoryStep] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize run result to dictionary."""
        return {
            "task_id": self.task_id,
            "success": self.success,
            "completed": self.completed,
            "iterations": self.iterations,
            "final_patch": self.final_patch,
            "tool_calls_count": self.tool_calls_count,
            "failed_calls_count": self.failed_calls_count,
            "duration_seconds": round(self.duration_seconds, 2),
            "termination_reason": self.termination_reason,
            "trajectory": [step.to_dict() for step in self.trajectory],
        }


class AgentExecutionLoop:
    """Orchestrates autonomous ReAct iterations using an MCPClient and a BasePlanner."""

    def __init__(
        self,
        client: MCPClient,
        planner: BasePlanner,
        max_iterations: int = 15,
        max_consecutive_failures: int = 3,
        timeout_seconds: float = 300.0,
    ) -> None:
        """Initialize AgentExecutionLoop.

        Args:
            client: Connected or connectable MCPClient.
            planner: Reasoning engine (SystematicSWEPlanner or LLMPlanner).
            max_iterations: Hard cap on total ReAct iterations.
            max_consecutive_failures: Circuit breaker threshold for consecutive tool errors.
            timeout_seconds: Maximum wall-clock time in seconds for the entire run.
        """
        self.client = client
        self.planner = planner
        self.max_iterations = max_iterations
        self.max_consecutive_failures = max_consecutive_failures
        self.timeout_seconds = timeout_seconds

    def _infer_stage(self, tool_name: Optional[str], called_tools: List[str]) -> PlanStage:
        """Infer the Software Engineering stage based on tool intent and history."""
        if not tool_name:
            return PlanStage.EXPLORE

        if tool_name in ("list_files", "get_repository_status"):
            return PlanStage.EXPLORE
        elif tool_name in ("read_file", "search_code"):
            return PlanStage.ANALYZE
        elif tool_name == "apply_patch":
            return PlanStage.PATCH
        elif tool_name == "run_tests":
            # If a patch was applied earlier, running tests represents verification
            if "apply_patch" in called_tools:
                return PlanStage.VERIFY
            return PlanStage.REPRODUCE
        elif tool_name == "get_git_diff":
            return PlanStage.VERIFY

        return PlanStage.EXPLORE

    async def run(self, objective: str, task_id: str = "unknown") -> AgentRunResult:
        """Execute the autonomous ReAct cycle to achieve the given objective.

        Args:
            objective: High-level task description and instructions.
            task_id: Identifier for the benchmark task.

        Returns:
            AgentRunResult capturing outcome, trajectory, patch, and metrics.
        """
        start_time = time.time()
        trajectory: List[TrajectoryStep] = []
        consecutive_failures = 0
        success = False
        completed = False
        termination_reason = "Max iterations reached"

        # Manage connection lifecycle if not already connected
        should_disconnect = False
        if not self.client.is_connected:
            await self.client.connect()
            should_disconnect = True

        try:
            tools = await self.client.list_tools()

            for iteration in range(1, self.max_iterations + 1):
                # 1. Check timeout guard
                elapsed = time.time() - start_time
                if elapsed > self.timeout_seconds:
                    termination_reason = f"Timeout exceeded ({elapsed:.1f}s > {self.timeout_seconds}s)"
                    break

                # 2. REASON: Planner decides next action
                action = await self.planner.plan_next_action(
                    objective=objective,
                    trajectory=trajectory,
                    tools=tools,
                )

                called_tools = [
                    s.action.tool_name for s in trajectory if s.action.tool_name
                ]

                # 3. ACT: Handle chosen action
                if action.action_type == "finish":
                    trajectory.append(
                        TrajectoryStep(
                            iteration=iteration,
                            stage=PlanStage.FINISH,
                            thought=action.thought,
                            action=action,
                            result=None,
                            timestamp=time.time(),
                        )
                    )
                    success = True
                    completed = True
                    termination_reason = f"Planner completed: {action.message or 'Done'}"
                    break

                elif action.action_type == "abort":
                    trajectory.append(
                        TrajectoryStep(
                            iteration=iteration,
                            stage=PlanStage.ABORT,
                            thought=action.thought,
                            action=action,
                            result=None,
                            timestamp=time.time(),
                        )
                    )
                    success = False
                    completed = False
                    termination_reason = f"Planner aborted: {action.message or 'Aborted'}"
                    break

                elif action.action_type == "call_tool":
                    stage = self._infer_stage(action.tool_name, called_tools)

                    # Execute action via MCPClient
                    tool_res = await self.client.call_tool(
                        name=action.tool_name or "",
                        arguments=action.tool_args or {},
                    )

                    trajectory.append(
                        TrajectoryStep(
                            iteration=iteration,
                            stage=stage,
                            thought=action.thought,
                            action=action,
                            result=tool_res,
                            timestamp=time.time(),
                        )
                    )

                    # Update consecutive failure circuit breaker
                    if tool_res.success:
                        consecutive_failures = 0
                    else:
                        consecutive_failures += 1

                    if consecutive_failures >= self.max_consecutive_failures:
                        termination_reason = (
                            f"Circuit breaker tripped: {consecutive_failures} "
                            "consecutive tool failures encountered."
                        )
                        break

            # 4. Extract final candidate git diff
            final_patch = ""
            try:
                diff_res = await self.client.call_tool("get_git_diff", {})
                if diff_res.success and diff_res.data and isinstance(diff_res.data, dict):
                    final_patch = diff_res.data.get("diff", "")
                elif diff_res.success:
                    final_patch = diff_res.content
            except Exception:
                final_patch = ""

        finally:
            if should_disconnect:
                await self.client.disconnect()

        total_duration = time.time() - start_time

        return AgentRunResult(
            task_id=task_id,
            success=success,
            completed=completed,
            iterations=len(trajectory),
            final_patch=final_patch,
            tool_calls_count=self.client.total_calls,
            failed_calls_count=self.client.failed_calls,
            duration_seconds=total_duration,
            termination_reason=termination_reason,
            trajectory=trajectory,
        )
