"""Unit and integration tests for the deterministic evaluation and scoring engine."""

import pytest
from pathlib import Path

from evaluator.metrics import EvaluationMetrics
from evaluator.runner import EvaluationRunner
from evaluator.scoring import ScoringEngine, ScoringWeights
from tasks.loader import load_task_solution


def test_scoring_engine_perfect_run():
    """Verify that a flawless run with all tests passing scores 100.0."""
    metrics = EvaluationMetrics(
        task_id="test_task",
        public_tests_passed=4,
        public_tests_total=4,
        hidden_tests_passed=6,
        hidden_tests_total=6,
        patch_valid=True,
        patch_lines_added=5,
        patch_lines_deleted=3,
        failed_tool_calls=0,
        regressions_detected=0,
    )

    engine = ScoringEngine()
    score, breakdown = engine.calculate_score(metrics)

    assert score == 100.0
    assert breakdown["task_completion"] == 40.0
    assert breakdown["hidden_tests"] == 25.0
    assert breakdown["public_tests"] == 15.0
    assert breakdown["regression_safety"] == 10.0
    assert breakdown["tool_efficiency"] == 5.0
    assert breakdown["patch_quality"] == 5.0


def test_scoring_engine_partial_failure():
    """Verify scoring reflects partial test completion and failed tool calls."""
    metrics = EvaluationMetrics(
        task_id="test_task",
        public_tests_passed=2,
        public_tests_total=4,  # 50% public pass
        hidden_tests_passed=3,
        hidden_tests_total=6,  # 50% hidden pass
        patch_valid=True,
        failed_tool_calls=2,   # -2 on tool efficiency
        regressions_detected=1,# -5 on regression safety
    )

    engine = ScoringEngine()
    score, breakdown = engine.calculate_score(metrics)

    assert breakdown["task_completion"] == 0.0  # Not complete
    assert breakdown["public_tests"] == 7.5     # 50% of 15
    assert breakdown["hidden_tests"] == 12.5    # 50% of 25
    assert breakdown["regression_safety"] == 5.0 # 10 - 5
    assert breakdown["tool_efficiency"] == 3.0  # 5 - 2
    assert score == 33.0


def test_scoring_engine_tampering_zeroes_score():
    """Verify that test tampering immediately triggers a 0.0 score penalty."""
    metrics = EvaluationMetrics(
        task_id="test_task",
        public_tests_passed=10,
        public_tests_total=10,
        hidden_tests_passed=10,
        hidden_tests_total=10,
        test_tampering_detected=True,  # Tampered!
    )

    engine = ScoringEngine()
    score, breakdown = engine.calculate_score(metrics)

    assert score == 0.0
    assert breakdown["anti_tampering_penalty"] == 0.0


def test_evaluator_runner_on_baseline_failure(tmp_path: Path):
    """Test running evaluation on buggy baseline repository without fix."""
    tasks_root = Path("tasks").resolve()
    workspace_root = tmp_path / "eval_ws_fail"

    runner = EvaluationRunner(tasks_root=tasks_root, workspace_root=workspace_root)
    metrics = runner.evaluate_task("bug_fix_001", patch_to_apply=None, cleanup=True)

    assert metrics.success is False
    assert metrics.score < 40.0
    assert metrics.public_tests_passed < metrics.public_tests_total
    assert len(metrics.failure_messages) > 0
    assert "[FAILED]" in metrics.summary_report


def test_evaluator_runner_on_golden_solution(tmp_path: Path):
    """Test running evaluation with reference golden solution achieves 100.0 score."""
    tasks_root = Path("tasks").resolve()
    workspace_root = tmp_path / "eval_ws_pass"
    golden_patch = load_task_solution(tasks_root / "bug_fix_001")
    assert golden_patch is not None

    runner = EvaluationRunner(tasks_root=tasks_root, workspace_root=workspace_root)
    metrics = runner.evaluate_task(
        task_id="bug_fix_001",
        patch_to_apply=golden_patch,
        tool_call_count=5,
        failed_tool_calls=0,
        iterations=1,
        cleanup=True,
    )

    assert metrics.success is True
    assert metrics.score == 100.0
    assert metrics.public_tests_passed == metrics.public_tests_total
    assert metrics.hidden_tests_passed == metrics.hidden_tests_total
    assert metrics.test_tampering_detected is False
    assert "[PASSED]" in metrics.summary_report
    assert "Score Breakdown" in metrics.summary_report


def test_verifier_catches_tampering(tmp_path: Path):
    """Test that modifying public test files is caught as tampering."""
    tasks_root = Path("tasks").resolve()
    workspace_root = tmp_path / "eval_ws_tamper"
    runner = EvaluationRunner(tasks_root=tasks_root, workspace_root=workspace_root)

    # Setup workspace
    ws = runner.workspace_manager.setup_task_workspace("bug_fix_001", tasks_root)
    
    # Tamper with public tests: delete assertions to fake pass
    (ws / "tests" / "test_pricing.py").write_text("def test_fake(): assert True\n", encoding="utf-8")

    task_def = runner.verifier.tasks_root / "bug_fix_001"
    from tasks.loader import load_task_definition
    task = load_task_definition(task_def)

    metrics = runner.verifier.verify_workspace(task=task, workspace=ws)
    assert metrics.test_tampering_detected is True
    assert metrics.success is False

    runner.workspace_manager.cleanup_task_workspace("bug_fix_001")
