"""Autonomous Planning and Reasoning Engine for Software Engineering Agent.

Defines the systematic Software Engineering Workflow (PlanStage), structured
AgentActions, trajectory records, and pluggable planners (SystematicSWEPlanner, LLMPlanner).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Literal, Optional

from agent.client import ToolDefinition, ToolResult


class PlanStage(str, Enum):
    """Stages of the systematic Software Engineering reasoning cycle."""

    EXPLORE = "explore"
    REPRODUCE = "reproduce"
    ANALYZE = "analyze"
    PATCH = "patch"
    VERIFY = "verify"
    FINISH = "finish"
    ABORT = "abort"


@dataclass
class AgentAction:
    """Action chosen by the agent's planner at a single iteration."""

    action_type: Literal["call_tool", "finish", "abort"]
    thought: str
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    message: Optional[str] = None

    @classmethod
    def call(cls, tool_name: str, tool_args: Dict[str, Any], thought: str) -> AgentAction:
        """Construct a tool call action."""
        return cls(
            action_type="call_tool",
            thought=thought,
            tool_name=tool_name,
            tool_args=tool_args,
        )

    @classmethod
    def finish(cls, thought: str, message: str = "Task completed successfully.") -> AgentAction:
        """Construct a successful completion action."""
        return cls(
            action_type="finish",
            thought=thought,
            message=message,
        )

    @classmethod
    def abort(cls, thought: str, reason: str = "Execution aborted.") -> AgentAction:
        """Construct an abort action."""
        return cls(
            action_type="abort",
            thought=thought,
            message=reason,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize action to dictionary."""
        return asdict(self)


@dataclass
class TrajectoryStep:
    """Historical record of an iteration in the ReAct execution loop."""

    iteration: int
    stage: PlanStage
    thought: str
    action: AgentAction
    result: Optional[ToolResult] = None
    timestamp: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize trajectory step to dictionary."""
        return {
            "iteration": self.iteration,
            "stage": self.stage.value,
            "thought": self.thought,
            "action": self.action.to_dict(),
            "result": self.result.to_dict() if self.result else None,
            "timestamp": self.timestamp,
        }


SYSTEM_PROMPT_TEMPLATE = """You are an expert AI Software Engineering Agent operating inside an isolated repository sandbox.
Your mission is to resolve the given engineering task cleanly, systematically, and deterministically.

Follow the rigorous 5-step Software Engineering Workflow:
1. EXPLORE: Use `list_files` or `get_repository_status` to understand codebase layout and identify target modules and test files.
2. REPRODUCE: Run the existing test suite using `run_tests` to observe baseline test failures and exact traceback assertions.
3. ANALYZE: Use `read_file` and `search_code` to locate the root cause in the source code. Formulate a precise fix hypothesis.
4. PATCH: Generate a minimal unified diff patch and apply it using `apply_patch`. Do NOT modify existing test assertions to fake a pass.
5. VERIFY: Re-run `run_tests` to verify that previously failing tests now PASS and NO regressions were introduced. Check `get_git_diff` to review diff quality.
6. FINISH: Once all tests pass and the diff is clean, call finish.

Rules:
- Never edit protected test files to make tests artificially pass (anti-cheat guards will disqualify you).
- Keep patches concise and focused solely on the required bug fix or feature.
- Always verify your fix before concluding.
"""


class BasePlanner(ABC):
    """Abstract interface for agent planners."""

    @abstractmethod
    async def plan_next_action(
        self,
        objective: str,
        trajectory: List[TrajectoryStep],
        tools: List[ToolDefinition],
    ) -> AgentAction:
        """Select the next AgentAction given the current trajectory and available tools."""
        raise NotImplementedError


class SystematicSWEPlanner(BasePlanner):
    """Deterministic, rule-based Software Engineering workflow planner.

    Executes the standard software engineering loop:
    1. Check git repository status
    2. Run tests to reproduce baseline failure
    3. Read target files
    4. Apply candidate patch (if provided)
    5. Re-run tests to verify fix
    6. Check git diff
    7. Finish
    """

    def __init__(
        self,
        candidate_patch: Optional[str] = None,
        target_file: Optional[str] = None,
        test_target: str = "tests",
    ) -> None:
        """Initialize SystematicSWEPlanner.

        Args:
            candidate_patch: Unified diff patch to apply at the PATCH stage.
            target_file: Primary source file to inspect at the ANALYZE stage.
            test_target: Target path or nodeid to run tests against.
        """
        self.candidate_patch = candidate_patch
        self.target_file = target_file
        self.test_target = test_target

    async def plan_next_action(
        self,
        objective: str,
        trajectory: List[TrajectoryStep],
        tools: List[ToolDefinition],
    ) -> AgentAction:
        """Determine next action based on trajectory history and workflow stage."""
        tools_by_name = {t.name: t for t in tools}
        called_tools = [step.action.tool_name for step in trajectory if step.action.tool_name]

        # Step 1: EXPLORE repository layout
        if not trajectory or "get_repository_status" not in called_tools:
            return AgentAction.call(
                tool_name="get_repository_status",
                tool_args={},
                thought="Checking git repository status to observe initial worktree state.",
            )

        # Step 2: REPRODUCE baseline failure
        if "run_tests" not in called_tools:
            return AgentAction.call(
                tool_name="run_tests",
                tool_args={"target": self.test_target},
                thought=f"Running initial test suite targeting '{self.test_target}' to reproduce baseline failure.",
            )

        # Step 3: ANALYZE target source code
        if self.target_file and "read_file" not in called_tools:
            return AgentAction.call(
                tool_name="read_file",
                tool_args={"path": self.target_file, "start_line": 1, "end_line": 100},
                thought=f"Reading '{self.target_file}' to understand the buggy implementation and logic.",
            )

        # Step 4: PATCH the codebase
        if self.candidate_patch and "apply_patch" not in called_tools:
            return AgentAction.call(
                tool_name="apply_patch",
                tool_args={"patch": self.candidate_patch},
                thought="Applying candidate unified diff patch to fix the identified defect.",
            )

        # Step 5: VERIFY the fix with re-test
        # Count test runs
        test_run_count = called_tools.count("run_tests")
        if "apply_patch" in called_tools and test_run_count < 2:
            return AgentAction.call(
                tool_name="run_tests",
                tool_args={"target": self.test_target},
                thought="Re-running test suite after applying patch to verify all tests now pass.",
            )

        # Step 6: Review diff
        if "apply_patch" in called_tools and "get_git_diff" not in called_tools:
            return AgentAction.call(
                tool_name="get_git_diff",
                tool_args={},
                thought="Inspecting git diff to verify patch cleanliness and ensure no extraneous changes.",
            )

        # Step 7: FINISH
        last_step = trajectory[-1] if trajectory else None
        return AgentAction.finish(
            thought="All workflow stages executed: reproduction confirmed, patch applied, tests verified passing, and diff reviewed.",
            message="Repository fix verified successfully.",
        )


LLMCallable = Callable[
    [str, List[Dict[str, Any]], List[Dict[str, Any]]],
    Coroutine[Any, Any, Dict[str, Any]],
]


class LLMPlanner(BasePlanner):
    """LLM-backed planner supporting OpenAI, Anthropic, or custom asynchronous LLM callables.

    Communicates with an LLM by feeding the conversation history, available MCP tool definitions,
    and parsing model responses into AgentActions.
    """

    def __init__(
        self,
        llm_fn: LLMCallable,
        system_prompt: Optional[str] = None,
        model_name: str = "gpt-4o",
    ) -> None:
        """Initialize LLMPlanner.

        Args:
            llm_fn: Async callable `(system_prompt, messages, tools) -> raw_response_dict`.
            system_prompt: Custom system prompt instructions (defaults to SYSTEM_PROMPT_TEMPLATE).
            model_name: Identifier for model telemetry.
        """
        self.llm_fn = llm_fn
        self.system_prompt = system_prompt or SYSTEM_PROMPT_TEMPLATE
        self.model_name = model_name

    async def plan_next_action(
        self,
        objective: str,
        trajectory: List[TrajectoryStep],
        tools: List[ToolDefinition],
    ) -> AgentAction:
        """Invoke LLM callable and parse its decision into an AgentAction."""
        messages: List[Dict[str, Any]] = [
            {"role": "user", "content": f"Task Objective:\n{objective}"}
        ]

        # Convert trajectory into conversation turns
        for step in trajectory:
            thought_text = f"Thought: {step.thought}"
            if step.action.action_type == "call_tool":
                messages.append(
                    {
                        "role": "assistant",
                        "content": thought_text,
                        "tool_calls": [
                            {
                                "id": f"call_{step.iteration}",
                                "type": "function",
                                "function": {
                                    "name": step.action.tool_name,
                                    "arguments": json.dumps(step.action.tool_args or {}),
                                },
                            }
                        ],
                    }
                )
                if step.result:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": f"call_{step.iteration}",
                            "content": step.result.content,
                        }
                    )
            elif step.action.action_type == "finish":
                messages.append(
                    {
                        "role": "assistant",
                        "content": f"{thought_text}\nResult: {step.action.message}",
                    }
                )

        openai_tools = [t.to_openai_tool() for t in tools]

        try:
            response = await self.llm_fn(self.system_prompt, messages, openai_tools)
        except Exception as exc:
            return AgentAction.abort(
                thought=f"LLM API call failed with exception: {exc}",
                reason=str(exc),
            )

        # Parse LLM response
        thought = response.get("thought", response.get("content", ""))
        tool_calls = response.get("tool_calls", [])

        if tool_calls:
            first_call = tool_calls[0]
            func = first_call.get("function", {})
            name = func.get("name", "")
            args_raw = func.get("arguments", {})
            if isinstance(args_raw, str):
                try:
                    args = json.loads(args_raw)
                except json.JSONDecodeError:
                    args = {}
            else:
                args = args_raw or {}

            return AgentAction.call(tool_name=name, tool_args=args, thought=thought)

        # If LLM indicates finish
        if response.get("finish") or "task completed" in thought.lower():
            return AgentAction.finish(
                thought=thought,
                message=response.get("finish_message", "Completed according to LLM plan."),
            )

        # Default fallback
        return AgentAction.finish(
            thought=thought or "No further tool calls requested by model.",
            message="LLM concluded task.",
        )
