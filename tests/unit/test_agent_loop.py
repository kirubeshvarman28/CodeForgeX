"""Unit tests for the Agent Execution Loop and Autonomous Planner."""

from pathlib import Path

import pytest
from agent.client import MCPClient, ToolDefinition
from agent.loop import AgentExecutionLoop, AgentRunResult
from agent.planner import (
    AgentAction,
    LLMPlanner,
    PlanStage,
    SystematicSWEPlanner,
    TrajectoryStep,
)
from evaluator.runner import EvaluationRunner
from tasks.loader import load_task_definition, load_task_solution
from tasks.manager import WorkspaceManager


@pytest.mark.anyio
async def test_systematic_planner_action_sequence():
    """Verify SystematicSWEPlanner progresses through all software engineering stages."""
    planner = SystematicSWEPlanner(
        candidate_patch="dummy patch",
        target_file="src/module.py",
        test_target="tests",
    )
    tools = [
        ToolDefinition("get_repository_status", "status"),
        ToolDefinition("run_tests", "tests"),
        ToolDefinition("read_file", "read"),
        ToolDefinition("apply_patch", "patch"),
        ToolDefinition("get_git_diff", "diff"),
    ]

    trajectory = []

    # 1. First step should be status
    action1 = await planner.plan_next_action("Fix bug", trajectory, tools)
    assert action1.action_type == "call_tool"
    assert action1.tool_name == "get_repository_status"
    trajectory.append(
        TrajectoryStep(1, PlanStage.EXPLORE, action1.thought, action1)
    )

    # 2. Next step should reproduce baseline failure
    action2 = await planner.plan_next_action("Fix bug", trajectory, tools)
    assert action2.tool_name == "run_tests"
    trajectory.append(
        TrajectoryStep(2, PlanStage.REPRODUCE, action2.thought, action2)
    )

    # 3. Next step should inspect code
    action3 = await planner.plan_next_action("Fix bug", trajectory, tools)
    assert action3.tool_name == "read_file"
    trajectory.append(
        TrajectoryStep(3, PlanStage.ANALYZE, action3.thought, action3)
    )

    # 4. Next step should apply patch
    action4 = await planner.plan_next_action("Fix bug", trajectory, tools)
    assert action4.tool_name == "apply_patch"
    trajectory.append(
        TrajectoryStep(4, PlanStage.PATCH, action4.thought, action4)
    )

    # 5. Next step should re-test (verify)
    action5 = await planner.plan_next_action("Fix bug", trajectory, tools)
    assert action5.tool_name == "run_tests"
    trajectory.append(
        TrajectoryStep(5, PlanStage.VERIFY, action5.thought, action5)
    )

    # 6. Next step should check diff
    action6 = await planner.plan_next_action("Fix bug", trajectory, tools)
    assert action6.tool_name == "get_git_diff"
    trajectory.append(
        TrajectoryStep(6, PlanStage.VERIFY, action6.thought, action6)
    )

    # 7. Final step should finish
    action7 = await planner.plan_next_action("Fix bug", trajectory, tools)
    assert action7.action_type == "finish"


@pytest.mark.anyio
async def test_llm_planner_parses_model_output():
    """Verify LLMPlanner transforms mock model outputs into AgentActions."""
    call_count = 0

    async def mock_llm(system_prompt, messages, tools):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "thought": "I need to inspect the tests folder.",
                "tool_calls": [
                    {
                        "function": {
                            "name": "list_files",
                            "arguments": '{"directory": "tests"}',
                        }
                    }
                ],
            }
        return {
            "thought": "Everything looks verified.",
            "finish": True,
            "finish_message": "All requirements satisfied.",
        }

    planner = LLMPlanner(llm_fn=mock_llm)
    tools = [ToolDefinition("list_files", "list")]

    # Turn 1
    action1 = await planner.plan_next_action("Goal", [], tools)
    assert action1.action_type == "call_tool"
    assert action1.tool_name == "list_files"
    assert action1.tool_args == {"directory": "tests"}

    # Turn 2
    step1 = TrajectoryStep(1, PlanStage.EXPLORE, action1.thought, action1)
    action2 = await planner.plan_next_action("Goal", [step1], tools)
    assert action2.action_type == "finish"
    assert "All requirements satisfied" in (action2.message or "")


@pytest.mark.anyio
async def test_agent_execution_loop_circuit_breaker(tmp_path):
    """Verify circuit breaker terminates loop when consecutive tool failures occur."""
    async def failing_llm(system_prompt, messages, tools):
        return {
            "thought": "Calling non-existent file",
            "tool_calls": [
                {
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "non_existent.py"}',
                    }
                }
            ],
        }

    client = MCPClient(repo_root=Path(".").resolve())
    planner = LLMPlanner(llm_fn=failing_llm)
    loop = AgentExecutionLoop(
        client=client,
        planner=planner,
        max_iterations=10,
        max_consecutive_failures=2,
    )

    result = await loop.run(objective="Fail safely")
    assert not result.success
    assert not result.completed
    assert "Circuit breaker tripped" in result.termination_reason
    assert result.failed_calls_count >= 2


@pytest.mark.anyio
async def test_agent_execution_loop_max_iterations():
    """Verify loop halts cleanly when max_iterations is reached."""
    async def looping_llm(system_prompt, messages, tools):
        return {
            "thought": "Keep listing",
            "tool_calls": [
                {"function": {"name": "list_files", "arguments": '{"recursive": false}'}}
            ],
        }

    client = MCPClient(repo_root=Path(".").resolve())
    planner = LLMPlanner(llm_fn=looping_llm)
    loop = AgentExecutionLoop(
        client=client,
        planner=planner,
        max_iterations=3,
        max_consecutive_failures=5,
    )

    result = await loop.run(objective="Loop forever")
    assert not result.completed
    assert result.iterations == 3
    assert "Max iterations reached" in result.termination_reason


@pytest.mark.anyio
async def test_end_to_end_agent_solves_bug_fix_001(tmp_path):
    """End-to-end integration: Agent explores workspace, reproduces failure,

    applies fix, verifies resolution, and deterministic evaluator scores 100.0/100.0.
    """
    from tasks.loader import load_task_definition, load_task_solution

    tasks_dir = Path("tasks").resolve()
    task_dir = tasks_dir / "bug_fix_001"
    task = load_task_definition(task_dir)
    golden_patch = load_task_solution(task_dir)
    assert golden_patch is not None

    manager = WorkspaceManager(workspace_root=tmp_path / "workspaces")
    workspace_path = manager.setup_task_workspace("bug_fix_001", tasks_root=tasks_dir)

    try:
        # Build client bounded to the temporary workspace
        client = MCPClient(repo_root=workspace_path)

        planner = SystematicSWEPlanner(
            candidate_patch=golden_patch,
            target_file="src/pricing.py",
            test_target="tests",
        )

        loop = AgentExecutionLoop(
            client=client,
            planner=planner,
            max_iterations=10,
            max_consecutive_failures=3,
        )

        # Run the agent
        agent_result = await loop.run(
            objective=task.description,
            task_id=task.task_id,
        )

        assert agent_result.success
        assert agent_result.completed
        assert agent_result.final_patch != ""
        assert "def calculate_discount" in agent_result.final_patch
        assert agent_result.iterations >= 5

        # Evaluate the agent's produced patch using EvaluationRunner
        runner = EvaluationRunner(tasks_root=tasks_dir, workspace_root=tmp_path / "eval_ws")
        eval_metrics = runner.evaluate_task(
            task_id="bug_fix_001",
            patch_to_apply=agent_result.final_patch,
            tool_call_count=agent_result.tool_calls_count,
            failed_tool_calls=agent_result.failed_calls_count,
            iterations=agent_result.iterations,
        )

        assert eval_metrics.score == 100.0
        assert eval_metrics.success is True
        assert eval_metrics.public_tests_passed == 4
        assert eval_metrics.public_tests_total == 4
        assert eval_metrics.hidden_tests_passed == 6
        assert eval_metrics.hidden_tests_total == 6
        assert eval_metrics.regressions_detected == 0
        assert eval_metrics.test_tampering_detected is False

    finally:
        manager.cleanup_task_workspace("bug_fix_001")
