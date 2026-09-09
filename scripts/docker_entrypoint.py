"""Container Entrypoint script for CodeForgeX Docker runtime.

Dispatches execution to test runner, benchmark evaluator, or standalone MCP server
based on command-line arguments.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from evaluator.runner import EvaluationRunner
from tasks.loader import discover_tasks, load_task_solution


def run_tests(args: list[str]) -> int:
    """Execute pytest within container environment."""
    cmd = [sys.executable, "-m", "pytest"] + (args if args else ["-v"])
    print(f"[CodeForgeX Container] Executing tests: {' '.join(cmd)}")
    proc = subprocess.run(cmd)
    return proc.returncode



def evaluate_single_task(task_id: str) -> int:
    """Evaluate a single benchmark task using its golden reference solution."""
    tasks_root = Path("/app/tasks").resolve()
    if not tasks_root.exists():
        tasks_root = Path("tasks").resolve()

    scratch_ws = Path("/app/scratch/eval_ws").resolve()
    if not scratch_ws.parent.exists():
        scratch_ws = Path("scratch/eval_ws").resolve()

    runner = EvaluationRunner(tasks_root=tasks_root, workspace_root=scratch_ws)
    solution = load_task_solution(tasks_root / task_id)

    print(f"\n[CodeForgeX Container] Evaluating task: {task_id} ...")
    metrics = runner.evaluate_task(task_id=task_id, patch_to_apply=solution, cleanup=True)

    print(metrics.summary_report)
    return 0 if metrics.success else 1


def evaluate_all_tasks() -> int:
    """Discover and evaluate all benchmark tasks, printing a summary table."""
    tasks_root = Path("/app/tasks").resolve()
    if not tasks_root.exists():
        tasks_root = Path("tasks").resolve()

    scratch_ws = Path("/app/scratch/eval_ws").resolve()
    if not scratch_ws.parent.exists():
        scratch_ws = Path("scratch/eval_ws").resolve()

    tasks = discover_tasks(tasks_root)
    runner = EvaluationRunner(tasks_root=tasks_root, workspace_root=scratch_ws)

    print(f"\n{'='*70}")
    print(f" CodeForgeX Benchmark Suite Evaluation: {len(tasks)} Tasks Discovered")
    print(f"{'='*70}\n")

    results = []
    overall_passed = True

    for task_id in sorted(tasks.keys()):
        solution = load_task_solution(tasks_root / task_id)
        metrics = runner.evaluate_task(task_id=task_id, patch_to_apply=solution, cleanup=True)
        results.append(metrics)
        status_str = "PASS" if metrics.success else "FAIL"
        print(f"  [{status_str}] {task_id:15} | Score: {metrics.score:5.1f} / 100.0 | Public: {metrics.public_tests_passed}/{metrics.public_tests_total} | Hidden: {metrics.hidden_tests_passed}/{metrics.hidden_tests_total}")
        if not metrics.success:
            overall_passed = False

    total_score = sum(m.score for m in results) / len(results) if results else 0.0
    print(f"\n{'-'*70}")
    print(f" Benchmark Average Score: {total_score:.1f} / 100.0")
    print(f" Benchmark Outcome: {'ALL TASKS RESOLVED' if overall_passed else 'SOME TASKS FAILED'}")
    print(f"{'='*70}\n")

    return 0 if overall_passed else 1


def run_mcp_server(extra_args: list[str] | None = None) -> int:
    """Launch the MCP server process over stdio or HTTP/SSE."""
    cmd = [sys.executable, "-m", "mcp_server"] + (extra_args or [])
    print(f"[CodeForgeX Container] Launching MCP Server: {' '.join(cmd)}")
    proc = subprocess.run(cmd)
    return proc.returncode


def main() -> int:
    """Main CLI entrypoint."""
    # Ensure git safe.directory is configured for unprivileged container operations
    subprocess.run(["git", "config", "--global", "--add", "safe.directory", "*"], capture_output=True)

    parser = argparse.ArgumentParser(description="CodeForgeX Container Execution Harness")

    parser.add_argument("--test", action="store_true", help="Run pytest test suite")
    parser.add_argument("--evaluate", type=str, metavar="TASK_ID", help="Evaluate a specific benchmark task")
    parser.add_argument("--evaluate-all", action="store_true", help="Evaluate all discovered benchmark tasks")
    parser.add_argument("--server", action="store_true", help="Launch MCP Server over stdio or HTTP")

    # If no recognized flag is passed, pass raw arguments to pytest or subshell
    if len(sys.argv) > 1 and sys.argv[1] not in ("--test", "--evaluate", "--evaluate-all", "--server", "-h", "--help"):
        proc = subprocess.run(sys.argv[1:])
        return proc.returncode

    parsed, extra = parser.parse_known_args()

    if parsed.test:
        return run_tests(extra)
    elif parsed.evaluate:
        return evaluate_single_task(parsed.evaluate)
    elif parsed.evaluate_all:
        return evaluate_all_tasks()
    elif parsed.server:
        return run_mcp_server(extra)
    else:
        # If PORT or MCP_TRANSPORT is set in environment, default to running MCP server
        if os.environ.get("PORT") or os.environ.get("MCP_TRANSPORT"):
            return run_mcp_server(extra)
        # Default to running tests
        return run_tests(extra)



if __name__ == "__main__":
    sys.exit(main())
