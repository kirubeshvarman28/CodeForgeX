"""Testing tools for the MCP Software Engineering Agent.

Provides deterministic test execution, timeout enforcement, output capture,
and structured test metric parsing.
"""

import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_server.security.sandbox import resolve_safe_path

MAX_STDOUT_SUMMARY_CHARS = 10000
DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 180


@dataclass
class TestRunRecord:
    """Represents the complete execution log and metrics of a single test run."""
    __test__ = False  # Prevent pytest from attempting to collect as a test class
    run_id: str
    timestamp: str
    test_target: str
    exit_code: int
    passed: int
    failed: int
    errors: int
    skipped: int
    duration_seconds: float
    stdout: str
    stderr: str
    is_timeout: bool
    summary: str


class TestRunStore:
    """In-memory store retaining recent test execution records."""
    __test__ = False  # Prevent pytest from attempting to collect as a test class

    def __init__(self, max_history: int = 50):
        self.max_history = max_history
        self._history: List[TestRunRecord] = []
        self._by_id: Dict[str, TestRunRecord] = {}

    def record_run(self, record: TestRunRecord) -> None:
        self._history.append(record)
        self._by_id[record.run_id] = record
        if len(self._history) > self.max_history:
            oldest = self._history.pop(0)
            self._by_id.pop(oldest.run_id, None)

    def get_latest(self) -> Optional[TestRunRecord]:
        return self._history[-1] if self._history else None

    def get_by_id(self, run_id: str) -> Optional[TestRunRecord]:
        return self._by_id.get(run_id)

    def clear(self) -> None:
        self._history.clear()
        self._by_id.clear()


# Default singleton instance for test run history
GLOBAL_TEST_STORE = TestRunStore()


def parse_pytest_metrics(stdout: str, stderr: str, exit_code: int) -> Dict[str, Any]:
    """Parse structured test counts and execution summary from pytest output.

    Args:
        stdout: Standard output string from pytest.
        stderr: Standard error string from pytest.
        exit_code: Process exit code.

    Returns:
        Dict with counts for passed, failed, errors, skipped, and summary line.
    """
    passed = 0
    failed = 0
    errors = 0
    skipped = 0

    combined_text = f"{stdout}\n{stderr}"

    # Regex patterns matching standard pytest summary lines
    passed_match = re.search(r"(\d+)\s+passed", combined_text)
    if passed_match:
        passed = int(passed_match.group(1))

    failed_match = re.search(r"(\d+)\s+failed", combined_text)
    if failed_match:
        failed = int(failed_match.group(1))

    errors_match = re.search(r"(\d+)\s+error(?:s)?\b", combined_text)
    if errors_match:
        errors = int(errors_match.group(1))

    skipped_match = re.search(r"(\d+)\s+skipped", combined_text)
    if skipped_match:
        skipped = int(skipped_match.group(1))

    summary_parts = []
    if passed > 0:
        summary_parts.append(f"{passed} passed")
    if failed > 0:
        summary_parts.append(f"{failed} failed")
    if errors > 0:
        summary_parts.append(f"{errors} error(s)")
    if skipped > 0:
        summary_parts.append(f"{skipped} skipped")

    if not summary_parts:
        if exit_code == 0:
            summary = "All tests passed (no test collection reported)"
        elif exit_code == 5:
            summary = "No tests were collected"
        else:
            summary = f"Test execution exited with code {exit_code}"
    else:
        summary = ", ".join(summary_parts)

    return {
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "summary": summary,
    }


def run_tests_impl(
    repo_root: Path | str,
    test_target: str = "",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    store: Optional[TestRunStore] = None,
) -> Dict[str, Any]:
    """Execute pytest within the repository sandbox and capture deterministic results.

    Args:
        repo_root: Root directory of the repository.
        test_target: Optional test target path or nodeid (e.g. 'tests/test_app.py::test_func').
        timeout_seconds: Hard execution timeout in seconds.
        store: Optional TestRunStore instance (defaults to GLOBAL_TEST_STORE).

    Returns:
        Structured test result dictionary.
    """
    root = Path(repo_root).resolve()
    target_store = store if store is not None else GLOBAL_TEST_STORE

    # Bound timeout to prevent invalid / extreme values
    if timeout_seconds < 1:
        timeout_seconds = 1
    elif timeout_seconds > MAX_TIMEOUT_SECONDS:
        timeout_seconds = MAX_TIMEOUT_SECONDS

    # Validate target path if specified to prevent traversal
    resolved_target_arg: Optional[str] = None
    if test_target.strip():
        # Handle pytest nodeid format (file.py::test_case)
        parts = test_target.strip().split("::", 1)
        file_part = parts[0]
        safe_file = resolve_safe_path(root, file_part, must_exist=True)
        rel_file = safe_file.relative_to(root).as_posix()
        resolved_target_arg = f"{rel_file}::{parts[1]}" if len(parts) > 1 else rel_file

    # Build deterministic subprocess command
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-v",
        "--tb=short",
    ]
    if resolved_target_arg:
        cmd.append(resolved_target_arg)

    # Prepare execution environment (preserve necessary paths, set PYTHONPATH to include repo)
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    src_dir = (root / "src").as_posix()
    root_dir = root.as_posix()
    env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{root_dir}{os.pathsep}{existing_pythonpath}"

    start_time = time.perf_counter()
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    is_timeout = False
    stdout = ""
    stderr = ""
    exit_code = -1

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        duration = time.perf_counter() - start_time
        exit_code = proc.returncode
        stdout = proc.stdout.replace("\r\n", "\n")
        stderr = proc.stderr.replace("\r\n", "\n")
    except subprocess.TimeoutExpired as exc:
        duration = float(timeout_seconds)
        is_timeout = True
        exit_code = -9
        stdout = (exc.stdout or "").replace("\r\n", "\n") if isinstance(exc.stdout, str) else ""
        stderr = f"Execution timed out after {timeout_seconds} seconds."
    except Exception as exc:
        duration = time.perf_counter() - start_time
        exit_code = -1
        stderr = f"Failed to invoke test runner: {exc}"

    metrics = parse_pytest_metrics(stdout, stderr, exit_code)
    if is_timeout:
        metrics["summary"] = f"TIMEOUT: Test execution exceeded {timeout_seconds}s limit"

    # Store full record in run history
    record = TestRunRecord(
        run_id=run_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        test_target=test_target,
        exit_code=exit_code,
        passed=metrics["passed"],
        failed=metrics["failed"],
        errors=metrics["errors"],
        skipped=metrics["skipped"],
        duration_seconds=round(duration, 3),
        stdout=stdout,
        stderr=stderr,
        is_timeout=is_timeout,
        summary=metrics["summary"],
    )
    target_store.record_run(record)

    # Prepare response (truncate stdout if overly verbose)
    is_truncated = False
    response_stdout = stdout
    if len(stdout) > MAX_STDOUT_SUMMARY_CHARS:
        response_stdout = stdout[:MAX_STDOUT_SUMMARY_CHARS] + f"\n... [Truncated {len(stdout) - MAX_STDOUT_SUMMARY_CHARS} chars. Use get_test_output(full=True) for full logs]"
        is_truncated = True

    return {
        "run_id": run_id,
        "exit_code": exit_code,
        "is_timeout": is_timeout,
        "passed": metrics["passed"],
        "failed": metrics["failed"],
        "errors": metrics["errors"],
        "skipped": metrics["skipped"],
        "duration_seconds": round(duration, 3),
        "summary": metrics["summary"],
        "stdout": response_stdout,
        "stderr": stderr,
        "is_truncated": is_truncated,
    }


def get_test_output_impl(
    store: Optional[TestRunStore] = None,
    run_id: Optional[str] = None,
    full: bool = False,
) -> Dict[str, Any]:
    """Retrieve detailed output from a recent test execution.

    Args:
        store: Optional TestRunStore instance.
        run_id: Specific run identifier to query (defaults to latest run).
        full: If True, returns full untruncated stdout.

    Returns:
        Structured test run output dictionary.
    """
    target_store = store if store is not None else GLOBAL_TEST_STORE

    if run_id:
        record = target_store.get_by_id(run_id)
        if record is None:
            raise KeyError(f"Test run ID '{run_id}' not found in history.")
    else:
        record = target_store.get_latest()
        if record is None:
            return {
                "message": "No test runs recorded yet.",
                "has_runs": False,
            }

    data = asdict(record)
    if not full and len(data["stdout"]) > MAX_STDOUT_SUMMARY_CHARS:
        data["stdout"] = data["stdout"][:MAX_STDOUT_SUMMARY_CHARS] + "\n... [Truncated for brevity. Pass full=True to view all]"
        data["is_truncated"] = True
    else:
        data["is_truncated"] = False

    data["has_runs"] = True
    return data
