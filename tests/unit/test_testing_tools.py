"""Unit tests for the testing tools (run_tests_impl and get_test_output_impl)."""

import pytest
from pathlib import Path
from mcp_server.security.sandbox import PathTraversalError
from mcp_server.tools.testing import (
    TestRunStore,
    get_test_output_impl,
    parse_pytest_metrics,
    run_tests_impl,
)


@pytest.fixture
def repo_with_tests(tmp_path: Path) -> Path:
    """Create a temporary repository with passing, failing, and slow tests."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Source code
    (repo / "src").mkdir()
    (repo / "src" / "math_lib.py").write_text(
        "def add(a, b): return a + b\n"
        "def broken_sub(a, b): return a + b\n",  # Intentional bug
        encoding="utf-8",
    )

    # Tests
    (repo / "tests").mkdir()
    (repo / "tests" / "test_pass.py").write_text(
        "from math_lib import add\n"
        "def test_add_positive(): assert add(2, 3) == 5\n"
        "def test_add_zero(): assert add(0, 5) == 5\n",
        encoding="utf-8",
    )

    (repo / "tests" / "test_fail.py").write_text(
        "from math_lib import broken_sub\n"
        "def test_broken_sub(): assert broken_sub(5, 3) == 2\n",
        encoding="utf-8",
    )

    (repo / "tests" / "test_hang.py").write_text(
        "import time\n"
        "def test_hanging_infinite(): time.sleep(10)\n",
        encoding="utf-8",
    )

    return repo


def test_parse_pytest_metrics():
    """Verify parsing summary statistics from various pytest outputs."""
    sample_stdout = "================ 3 passed, 2 failed, 1 error in 0.45s ================"
    metrics = parse_pytest_metrics(sample_stdout, "", exit_code=1)

    assert metrics["passed"] == 3
    assert metrics["failed"] == 2
    assert metrics["errors"] == 1
    assert metrics["skipped"] == 0
    assert "3 passed, 2 failed, 1 error(s)" in metrics["summary"]


def test_run_tests_passing_target(repo_with_tests: Path):
    """Test running only passing tests."""
    store = TestRunStore()
    result = run_tests_impl(
        repo_root=repo_with_tests,
        test_target="tests/test_pass.py",
        timeout_seconds=15,
        store=store,
    )

    assert result["exit_code"] == 0
    assert result["is_timeout"] is False
    assert result["passed"] == 2
    assert result["failed"] == 0
    assert "2 passed" in result["summary"]
    assert result["run_id"].startswith("run_")


def test_run_tests_failing_target(repo_with_tests: Path):
    """Test executing tests that contain failures."""
    store = TestRunStore()
    result = run_tests_impl(
        repo_root=repo_with_tests,
        test_target="tests/test_fail.py",
        timeout_seconds=15,
        store=store,
    )

    assert result["exit_code"] != 0
    assert result["is_timeout"] is False
    assert result["failed"] == 1
    assert "1 failed" in result["summary"]


def test_run_tests_nodeid_scoping(repo_with_tests: Path):
    """Test scoping execution down to a specific test function nodeid."""
    store = TestRunStore()
    result = run_tests_impl(
        repo_root=repo_with_tests,
        test_target="tests/test_pass.py::test_add_positive",
        timeout_seconds=15,
        store=store,
    )

    assert result["exit_code"] == 0
    assert result["passed"] == 1
    assert result["failed"] == 0


def test_run_tests_timeout_enforcement(repo_with_tests: Path):
    """Test that execution times out and is terminated when exceeding deadline."""
    store = TestRunStore()
    result = run_tests_impl(
        repo_root=repo_with_tests,
        test_target="tests/test_hang.py",
        timeout_seconds=1,
        store=store,
    )

    assert result["is_timeout"] is True
    assert result["exit_code"] == -9
    assert "TIMEOUT" in result["summary"]


def test_run_tests_path_traversal_blocked(repo_with_tests: Path):
    """Test that targeting tests outside repo raises PathTraversalError."""
    store = TestRunStore()
    with pytest.raises(PathTraversalError):
        run_tests_impl(
            repo_root=repo_with_tests,
            test_target="../../outside_tests.py",
            store=store,
        )


def test_get_test_output_retrieval(repo_with_tests: Path):
    """Test retrieving latest test output and specific run by ID."""
    store = TestRunStore()

    # Before any runs
    empty = get_test_output_impl(store=store)
    assert empty["has_runs"] is False

    # Execute a run
    res = run_tests_impl(
        repo_root=repo_with_tests,
        test_target="tests/test_pass.py",
        store=store,
    )
    run_id = res["run_id"]

    # Query latest
    latest = get_test_output_impl(store=store)
    assert latest["has_runs"] is True
    assert latest["run_id"] == run_id
    assert latest["passed"] == 2

    # Query specific by id
    by_id = get_test_output_impl(store=store, run_id=run_id)
    assert by_id["run_id"] == run_id

    # Query non-existent ID
    with pytest.raises(KeyError):
        get_test_output_impl(store=store, run_id="non_existent_run_id")
