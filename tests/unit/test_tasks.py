"""Unit and integration tests for task definitions, loader, and workspace manager."""

import shutil
import pytest
from pathlib import Path
from pydantic import ValidationError

from mcp_server.security.sandbox import SecurityPolicy
from mcp_server.tools.patching import apply_patch_impl
from mcp_server.tools.testing import TestRunStore, run_tests_impl
from tasks.loader import (
    discover_tasks,
    load_task_definition,
    load_task_metadata,
    load_task_solution,
)
from tasks.manager import WorkspaceManager
from tasks.schema import TaskCategory, TaskDefinition, TaskDifficulty


def test_task_schema_valid():
    """Verify standard TaskDefinition validation."""
    task = TaskDefinition(
        task_id="sample_task_001",
        category=TaskCategory.BUG_FIX,
        title="Sample Bug Fix",
        description="A detailed description of the bug fix task requirements.",
        difficulty=TaskDifficulty.EASY,
        public_test_targets=["tests/test_sample.py"],
    )
    assert task.task_id == "sample_task_001"
    assert task.category == TaskCategory.BUG_FIX
    assert task.timeout_seconds == 300


def test_task_schema_invalid():
    """Verify validation fails on malformed task specifications."""
    # Invalid characters in task_id
    with pytest.raises(ValidationError):
        TaskDefinition(
            task_id="invalid task id!",
            category=TaskCategory.BUG_FIX,
            title="Sample",
            description="Sample description.",
        )

    # Description too short
    with pytest.raises(ValidationError):
        TaskDefinition(
            task_id="valid_id",
            category=TaskCategory.BUG_FIX,
            title="Valid Title",
            description="Short",
        )


def test_task_loader_discovers_bug_fix_001():
    """Verify discovering and loading the real bug_fix_001 task."""
    tasks_root = Path("tasks")
    tasks = discover_tasks(tasks_root)

    assert "bug_fix_001" in tasks
    task = tasks["bug_fix_001"]
    assert task.category == TaskCategory.BUG_FIX
    assert "pricing" in task.title.lower()
    assert len(task.public_test_targets) > 0

    # Test metadata
    meta = load_task_metadata(tasks_root / "bug_fix_001")
    assert meta is not None
    assert "pricing" in meta.tags

    # Test golden solution
    solution = load_task_solution(tasks_root / "bug_fix_001")
    assert solution is not None
    assert "--- a/src/pricing.py" in solution


def test_workspace_lifecycle_and_baseline_bug(tmp_path: Path):
    """Test setting up task workspace, verifying baseline failure, and fixing via golden patch."""
    tasks_root = Path("tasks").resolve()
    workspace_root = tmp_path / "workspace"
    manager = WorkspaceManager(workspace_root)

    # 1. Setup task workspace
    ws = manager.setup_task_workspace(
        task_id="bug_fix_001",
        tasks_root=tasks_root,
    )
    assert ws.exists()
    assert (ws / "src" / "pricing.py").exists()
    assert (ws / "tests" / "test_pricing.py").exists()
    assert (ws / ".git").exists()

    # 2. Run tests against baseline buggy repository
    store = TestRunStore()
    baseline_run = run_tests_impl(
        repo_root=ws,
        test_target="tests/test_pricing.py",
        store=store,
    )
    # Baseline tests MUST fail because of the intentional bug!
    assert baseline_run["exit_code"] != 0
    assert baseline_run["failed"] >= 1
    assert baseline_run["passed"] >= 1

    # 3. Apply golden reference solution patch
    solution_patch = load_task_solution(tasks_root / "bug_fix_001")
    assert solution_patch is not None
    patch_result = apply_patch_impl(repo_root=ws, patch=solution_patch)
    assert patch_result["success"] is True

    # 4. Re-run public tests: MUST NOW PASS!
    post_patch_run = run_tests_impl(
        repo_root=ws,
        test_target="tests/test_pricing.py",
        store=store,
    )
    assert post_patch_run["exit_code"] == 0
    assert post_patch_run["failed"] == 0
    assert post_patch_run["passed"] >= 4

    # 5. Inject and run hidden verification tests using evaluator policy
    evaluator_policy = SecurityPolicy(enforce_anti_cheat=False)
    hidden_tests_src = tasks_root / "bug_fix_001" / "hidden_tests" / "test_pricing_hidden.py"
    hidden_tests_dst = ws / "tests" / "test_pricing_hidden.py"
    shutil.copyfile(hidden_tests_src, hidden_tests_dst)

    hidden_run = run_tests_impl(
        repo_root=ws,
        test_target="tests/test_pricing_hidden.py",
        store=store,
        policy=evaluator_policy,
    )
    assert hidden_run["exit_code"] == 0
    assert hidden_run["failed"] == 0
    assert hidden_run["passed"] >= 6

    # 6. Teardown
    manager.cleanup_task_workspace("bug_fix_001")
    assert not ws.exists()


def test_discover_complete_benchmark_suite():
    """Verify discovery of all 6 benchmark tasks across diverse SE categories."""
    tasks_root = Path("tasks")
    tasks = discover_tasks(tasks_root)

    expected_tasks = {
        "bug_fix_001",
        "bug_fix_002",
        "feature_001",
        "refactor_001",
        "perf_001",
        "algo_001",
    }
    assert expected_tasks.issubset(set(tasks.keys()))

    categories = {t.category for t in tasks.values()}
    assert TaskCategory.BUG_FIX in categories
    assert TaskCategory.FEATURE in categories
    assert TaskCategory.REFACTOR in categories
    assert TaskCategory.PERFORMANCE in categories
    assert TaskCategory.ALGORITHM in categories

    for task_id in expected_tasks:
        task = tasks[task_id]
        assert task.difficulty in (TaskDifficulty.EASY, TaskDifficulty.MEDIUM, TaskDifficulty.HARD)
        assert len(task.public_test_targets) > 0
        assert len(task.hidden_test_targets) > 0
        assert load_task_solution(tasks_root / task_id) is not None


@pytest.mark.parametrize("task_id", [
    "bug_fix_001",
    "bug_fix_002",
    "feature_001",
    "refactor_001",
    "perf_001",
    "algo_001",
])
def test_all_tasks_golden_patch_evaluation(tmp_path: Path, task_id: str):
    """Verify each benchmark task evaluates to passing score (>= 95.0) with golden patch."""
    from evaluator.runner import EvaluationRunner

    tasks_root = Path("tasks").resolve()
    runner = EvaluationRunner(tasks_root=tasks_root, workspace_root=tmp_path / "eval_ws")
    golden_patch = load_task_solution(tasks_root / task_id)
    assert golden_patch is not None

    metrics = runner.evaluate_task(
        task_id=task_id,
        patch_to_apply=golden_patch,
        cleanup=True,
    )

    assert metrics.success is True
    assert metrics.score >= 95.0
    assert metrics.regressions_detected == 0
    assert metrics.test_tampering_detected is False
    assert metrics.public_tests_passed == metrics.public_tests_total
    assert metrics.hidden_tests_passed == metrics.hidden_tests_total

