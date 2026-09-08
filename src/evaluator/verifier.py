"""Task verifier for executing deterministic multi-criteria checks.

Validates:
1. Public test suites
2. Hidden verification suites (isolated injection & execution)
3. Anti-tampering check on public test suites
4. Git diff size and changed file lists
"""

import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from evaluator.metrics import EvaluationMetrics
from mcp_server.security.sandbox import SecurityPolicy
from mcp_server.tools.testing import TestRunStore, run_tests_impl
from tasks.schema import TaskDefinition


class TaskVerifier:
    """Orchestrates test execution, test tampering detection, and diff analysis."""

    def __init__(self, tasks_root: Path | str):
        self.tasks_root = Path(tasks_root).resolve()
        self.evaluator_policy = SecurityPolicy(enforce_anti_cheat=False)

    def verify_workspace(
        self,
        task: TaskDefinition,
        workspace: Path | str,
        tool_call_count: int = 0,
        failed_tool_calls: int = 0,
        iterations: int = 1,
    ) -> EvaluationMetrics:
        """Run complete deterministic verification against a task workspace.

        Args:
            task: The benchmark TaskDefinition.
            workspace: Bounded workspace directory containing agent-modified code.
            tool_call_count: Total tool calls made by agent.
            failed_tool_calls: Count of failed tool calls made by agent.
            iterations: Iteration loops taken by agent.

        Returns:
            Populated EvaluationMetrics instance.
        """
        ws_root = Path(workspace).resolve()
        task_dir = self.tasks_root / task.task_id
        start_time = time.perf_counter()

        metrics = EvaluationMetrics(
            task_id=task.task_id,
            tool_call_count=tool_call_count,
            failed_tool_calls=failed_tool_calls,
            iterations=iterations,
        )

        # 1. Anti-tampering check: verify agent did not modify or delete public test files
        tampering = self._check_test_tampering(task, ws_root, task_dir)
        metrics.test_tampering_detected = tampering
        if tampering:
            metrics.failure_messages.append("Test tampering detected: public tests were altered or removed.")
            metrics.duration_seconds = round(time.perf_counter() - start_time, 2)
            return metrics

        # 2. Run public tests
        store = TestRunStore()
        for target in task.public_test_targets:
            res = run_tests_impl(
                repo_root=ws_root,
                test_target=target,
                store=store,
                timeout_seconds=task.timeout_seconds,
            )
            metrics.public_tests_passed += res["passed"]
            metrics.public_tests_total += (res["passed"] + res["failed"] + res["errors"])
            if res["failed"] > 0 or res["errors"] > 0:
                metrics.failure_messages.append(f"Public test failure in '{target}': {res['summary']}")

        # 3. Inject and run hidden verification tests
        hidden_dir = task_dir / "hidden_tests"
        injected_files: List[Path] = []
        if hidden_dir.exists():
            for hidden_file in hidden_dir.glob("*.py"):
                target_dest = ws_root / "tests" / hidden_file.name
                shutil.copyfile(hidden_file, target_dest)
                injected_files.append(target_dest)

        try:
            for target in task.hidden_test_targets:
                res = run_tests_impl(
                    repo_root=ws_root,
                    test_target=target,
                    store=store,
                    timeout_seconds=task.timeout_seconds,
                    policy=self.evaluator_policy,
                )
                metrics.hidden_tests_passed += res["passed"]
                metrics.hidden_tests_total += (res["passed"] + res["failed"] + res["errors"])
                if res["failed"] > 0 or res["errors"] > 0:
                    metrics.failure_messages.append(f"Hidden test failure in '{target}': {res['summary']}")
        finally:
            # Always clean up injected hidden test files
            for f in injected_files:
                if f.exists():
                    f.unlink()

        # 4. Analyze git diff
        diff_info = self._analyze_git_diff(ws_root)
        metrics.patch_lines_added = diff_info["added"]
        metrics.patch_lines_deleted = diff_info["deleted"]
        metrics.files_modified = diff_info["files"]

        # 5. Determine overall success
        all_public_pass = (metrics.public_tests_passed == metrics.public_tests_total) and metrics.public_tests_total > 0
        all_hidden_pass = (metrics.hidden_tests_passed == metrics.hidden_tests_total) and metrics.hidden_tests_total > 0
        metrics.success = all_public_pass and all_hidden_pass and not metrics.test_tampering_detected

        metrics.duration_seconds = round(time.perf_counter() - start_time, 2)
        return metrics

    def _check_test_tampering(
        self,
        task: TaskDefinition,
        ws_root: Path,
        task_dir: Path,
    ) -> bool:
        """Check if any public test files were modified or deleted by the agent."""
        original_tests = task_dir / "repository" / "tests"
        ws_tests = ws_root / "tests"

        if not original_tests.exists() or not ws_tests.exists():
            return False

        for orig_file in original_tests.glob("test_*.py"):
            ws_file = ws_tests / orig_file.name
            if not ws_file.exists():
                return True  # Agent deleted a test file

            # Compare contents (normalizing line endings)
            orig_text = orig_file.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
            ws_text = ws_file.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
            if orig_text != ws_text:
                return True  # Agent modified assertions or test contents

        return False

    def _analyze_git_diff(self, ws_root: Path) -> dict:
        """Analyze git diff metrics against the initial commit."""
        try:
            # Check diff against initial baseline commit
            proc = subprocess.run(
                ["git", "diff", "--stat", "HEAD"],
                cwd=str(ws_root),
                capture_output=True,
                text=True,
            )
            # Check diff --numstat
            num_proc = subprocess.run(
                ["git", "diff", "--numstat"],
                cwd=str(ws_root),
                capture_output=True,
                text=True,
            )
            added = 0
            deleted = 0
            files: List[str] = []
            for line in num_proc.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) >= 3:
                    try:
                        added += int(parts[0])
                        deleted += int(parts[1])
                    except ValueError:
                        pass
                    files.append(parts[2].strip())

            return {"added": added, "deleted": deleted, "files": files}
        except Exception:
            return {"added": 0, "deleted": 0, "files": []}
