"""Evaluation runner orchestrating end-to-end benchmark verification.

Coordinates workspace provisioning, patch application, verification testing,
scoring calculation, and markdown evaluation report generation.
"""

from pathlib import Path
from typing import Optional

from evaluator.metrics import EvaluationMetrics
from evaluator.scoring import ScoringEngine, ScoringWeights
from evaluator.verifier import TaskVerifier
from mcp_server.tools.patching import apply_patch_impl
from tasks.loader import load_task_definition
from tasks.manager import WorkspaceManager


class EvaluationRunner:
    """End-to-end orchestrator for benchmark task evaluation."""

    def __init__(
        self,
        tasks_root: Path | str,
        workspace_root: Path | str,
        scoring_weights: Optional[ScoringWeights] = None,
    ):
        self.tasks_root = Path(tasks_root).resolve()
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_manager = WorkspaceManager(self.workspace_root)
        self.verifier = TaskVerifier(self.tasks_root)
        self.scoring_engine = ScoringEngine(scoring_weights)

    def evaluate_task(
        self,
        task_id: str,
        patch_to_apply: Optional[str] = None,
        tool_call_count: int = 0,
        failed_tool_calls: int = 0,
        iterations: int = 1,
        cleanup: bool = False,
    ) -> EvaluationMetrics:
        """Run complete benchmark evaluation on a task.

        Args:
            task_id: Target task identifier.
            patch_to_apply: Optional unified diff patch to apply before verification.
            tool_call_count: Number of tool calls recorded.
            failed_tool_calls: Number of failed tool calls recorded.
            iterations: Iteration loop count.
            cleanup: Whether to delete the workspace after evaluation.

        Returns:
            Fully populated EvaluationMetrics including score breakdown and summary report.
        """
        task_dir = self.tasks_root / task_id
        task_def = load_task_definition(task_dir)

        # 1. Instantiate clean sandbox workspace
        ws = self.workspace_manager.setup_task_workspace(
            task_id=task_id,
            tasks_root=self.tasks_root,
            clean=True,
        )

        patch_valid = True
        # 2. Apply patch if provided
        if patch_to_apply:
            patch_res = apply_patch_impl(repo_root=ws, patch=patch_to_apply)
            patch_valid = patch_res.get("success", False)

        try:
            # 3. Run verification tests and git diff analysis
            metrics = self.verifier.verify_workspace(
                task=task_def,
                workspace=ws,
                tool_call_count=tool_call_count,
                failed_tool_calls=failed_tool_calls,
                iterations=iterations,
            )
            metrics.patch_valid = patch_valid

            # 4. Compute weighted score
            score, breakdown = self.scoring_engine.calculate_score(metrics)
            metrics.score = score
            metrics.score_breakdown = breakdown

            # 5. Generate formatted markdown summary
            metrics.summary_report = self.generate_markdown_report(metrics)
            return metrics

        finally:
            if cleanup:
                self.workspace_manager.cleanup_task_workspace(task_id)

    def generate_markdown_report(self, metrics: EvaluationMetrics) -> str:
        """Format an evaluation report in clean GitHub markdown."""
        status_badge = "PASSED" if metrics.success else "FAILED"
        lines = [
            f"# Evaluation Report: `{metrics.task_id}` [{status_badge}]",
            f"**Final Score**: `{metrics.score} / 100.0`",
            f"**Evaluation Timestamp**: `{metrics.timestamp}`",
            "",
            "## Score Breakdown",
            "| Factor | Points Awarded | Max Possible |",
            "| :--- | :--- | :--- |",
            f"| **Task Completion** | {metrics.score_breakdown.get('task_completion', 0.0)} | 40.0 |",
            f"| **Hidden Tests** | {metrics.score_breakdown.get('hidden_tests', 0.0)} | 25.0 |",
            f"| **Public Tests** | {metrics.score_breakdown.get('public_tests', 0.0)} | 15.0 |",
            f"| **Regression Safety** | {metrics.score_breakdown.get('regression_safety', 0.0)} | 10.0 |",
            f"| **Tool Efficiency** | {metrics.score_breakdown.get('tool_efficiency', 0.0)} | 5.0 |",
            f"| **Patch Quality** | {metrics.score_breakdown.get('patch_quality', 0.0)} | 5.0 |",
            f"| **TOTAL SCORE** | **{metrics.score}** | **100.0** |",
            "",
            "## Test Results",
            f"- **Public Tests**: {metrics.public_tests_passed} / {metrics.public_tests_total} passed",
            f"- **Hidden Tests**: {metrics.hidden_tests_passed} / {metrics.hidden_tests_total} passed",
            f"- **Regressions**: {metrics.regressions_detected}",
            f"- **Anti-Tampering Violation**: {metrics.test_tampering_detected}",
            "",
            "## Code Changes & Telemetry",
            f"- **Files Modified**: {', '.join(metrics.files_modified) if metrics.files_modified else 'None'}",
            f"- **Lines Added**: `+{metrics.patch_lines_added}` | **Lines Deleted**: `-{metrics.patch_lines_deleted}`",
            f"- **Tool Calls**: {metrics.tool_call_count} (Failed: {metrics.failed_tool_calls})",
            f"- **Duration**: `{metrics.duration_seconds}s` across `{metrics.iterations}` iteration(s)",
        ]

        if metrics.failure_messages:
            lines.append("")
            lines.append("## Failure Messages")
            for msg in metrics.failure_messages:
                lines.append(f"- {msg}")

        return "\n".join(lines)
