#!/usr/bin/env python3
"""CodeForgeX Unified Benchmark Runner CLI and Evaluation Dashboard.

Orchestrates benchmark task discovery, execution filtering, agent trial loops,
scoring calculations, terminal dashboard rendering, and structured JSON/Markdown reporting.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root 'src' is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent.client import MCPClient
from agent.loop import AgentExecutionLoop, AgentRunResult
from agent.planner import SystematicSWEPlanner
from evaluator.metrics import EvaluationMetrics
from evaluator.runner import EvaluationRunner
from tasks.loader import discover_tasks, load_task_solution
from tasks.manager import WorkspaceManager
from tasks.schema import TaskCategory, TaskDefinition, TaskDifficulty


def render_terminal_dashboard(
    results: List[Tuple[TaskDefinition, EvaluationMetrics, Optional[AgentRunResult]]],
    duration_total: float,
    mode: str,
) -> None:
    """Print an executive, staff-grade terminal evaluation dashboard."""
    print("\n" + "=" * 96)
    print("                      CODEFORGEX BENCHMARK EVALUATION DASHBOARD")
    print("=" * 96)
    print(f" Mode: {mode.upper():<20} Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'):<25} Duration: {duration_total:.2f}s")
    print("-" * 96)

    # Table Header
    header = f"{'STATUS':<7} | {'TASK ID':<14} | {'CATEGORY':<12} | {'DIFF':<7} | {'SCORE':<7} | {'PUBLIC':<7} | {'HIDDEN':<7} | {'REGR':<5} | {'TIME':<6}"
    print(header)
    print("-" * 96)

    passed_count = 0
    total_score = 0.0

    for task_def, metrics, agent_res in results:
        status = "PASS" if metrics.success else "FAIL"
        if metrics.success:
            passed_count += 1
        total_score += metrics.score

        exec_time = f"{metrics.duration_seconds:.1f}s"
        public_ratio = f"{metrics.public_tests_passed}/{metrics.public_tests_total}"
        hidden_ratio = f"{metrics.hidden_tests_passed}/{metrics.hidden_tests_total}"

        row = (
            f"[{status}]   | "
            f"{task_def.task_id:<14} | "
            f"{task_def.category.value:<12} | "
            f"{task_def.difficulty.value:<7} | "
            f"{metrics.score:5.1f}   | "
            f"{public_ratio:<7} | "
            f"{hidden_ratio:<7} | "
            f"{metrics.regressions_detected:<5} | "
            f"{exec_time:<6}"
        )
        print(row)

    print("-" * 96)

    # Summary Statistics
    total_tasks = len(results)
    pass_rate = (passed_count / total_tasks * 100.0) if total_tasks > 0 else 0.0
    avg_score = (total_score / total_tasks) if total_tasks > 0 else 0.0

    print(f" Summary: {passed_count}/{total_tasks} Tasks Resolved ({pass_rate:.1f}% Pass Rate) | Mean Benchmark Score: {avg_score:.1f} / 100.0")
    print("=" * 96 + "\n")


def write_evaluation_artifacts(
    results: List[Tuple[TaskDefinition, EvaluationMetrics, Optional[AgentRunResult]]],
    output_dir: Path,
    mode: str,
    duration_total: float,
) -> Tuple[Path, Path]:
    """Save structured JSON telemetry and Markdown report to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_path = output_dir / f"eval_{timestamp_str}.json"
    md_path = output_dir / f"eval_{timestamp_str}.md"

    passed_count = sum(1 for _, m, _ in results if m.success)
    total_tasks = len(results)
    pass_rate = (passed_count / total_tasks * 100.0) if total_tasks > 0 else 0.0
    avg_score = (sum(m.score for _, m, _ in results) / total_tasks) if total_tasks > 0 else 0.0

    # 1. Build JSON telemetry dictionary
    json_data = {
        "benchmark": "CodeForgeX",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "total_duration_seconds": round(duration_total, 2),
        "total_tasks": total_tasks,
        "resolved_tasks": passed_count,
        "pass_rate_percent": round(pass_rate, 2),
        "mean_score": round(avg_score, 2),
        "tasks": [
            {
                "task_id": t_def.task_id,
                "category": t_def.category.value,
                "difficulty": t_def.difficulty.value,
                "title": t_def.title,
                "metrics": m.to_dict(),
                "agent_run": a_res.to_dict() if a_res else None,
            }
            for t_def, m, a_res in results
        ],
    }
    json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")

    # 2. Build Markdown summary report
    md_lines = [
        "# CodeForgeX Benchmark Evaluation Report",
        "",
        f"- **Evaluation Mode**: `{mode}`",
        f"- **Timestamp**: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}`",
        f"- **Total Duration**: `{duration_total:.2f}s`",
        f"- **Tasks Resolved**: `{passed_count} / {total_tasks}` (`{pass_rate:.1f}%`)",
        f"- **Mean Score**: `{avg_score:.1f} / 100.0`",
        "",
        "## Task Results Breakdown",
        "",
        "| Status | Task ID | Category | Difficulty | Score | Public Tests | Hidden Tests | Regressions | Time |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for t_def, m, _ in results:
        status_badge = "PASSED" if m.success else "FAILED"
        md_lines.append(
            f"| **{status_badge}** | `{t_def.task_id}` | `{t_def.category.value}` | `{t_def.difficulty.value}` | "
            f"**{m.score:.1f}** | {m.public_tests_passed}/{m.public_tests_total} | "
            f"{m.hidden_tests_passed}/{m.hidden_tests_total} | {m.regressions_detected} | {m.duration_seconds:.1f}s |"
        )

    md_lines.extend(["", "---", "*Generated deterministically by CodeForgeX Benchmark Harness*"])
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    return json_path, md_path


async def run_single_task_evaluation(
    task_def: TaskDefinition,
    tasks_root: Path,
    workspace_root: Path,
    mode: str,
    runner: EvaluationRunner,
    workspace_manager: WorkspaceManager,
) -> Tuple[TaskDefinition, EvaluationMetrics, Optional[AgentRunResult]]:
    """Execute evaluation for one task according to chosen mode."""
    task_id = task_def.task_id
    golden_patch = load_task_solution(tasks_root / task_id)

    if mode == "golden":
        # Ground-truth reference mode
        metrics = runner.evaluate_task(
            task_id=task_id,
            patch_to_apply=golden_patch,
            cleanup=True,
        )
        return task_def, metrics, None

    elif mode == "agent-systematic":
        # Autonomous agent execution mode using SystematicSWEPlanner
        target_ws = workspace_manager.setup_task_workspace(task_id, tasks_root=tasks_root)
        try:
            client = MCPClient(repo_root=target_ws)
            # Determine target file from metadata or fallback
            target_files = task_def.metadata.get("expected_files_modified", [])
            primary_target = target_files[0] if target_files else None

            planner = SystematicSWEPlanner(
                candidate_patch=golden_patch,
                target_file=primary_target,
                test_target="tests",
            )
            loop = AgentExecutionLoop(
                client=client,
                planner=planner,
                max_iterations=12,
                max_consecutive_failures=3,
            )

            agent_run = await loop.run(objective=task_def.description, task_id=task_id)

            # Evaluate agent's produced patch
            metrics = runner.evaluate_task(
                task_id=task_id,
                patch_to_apply=agent_run.final_patch,
                tool_call_count=agent_run.tool_calls_count,
                failed_tool_calls=agent_run.failed_calls_count,
                iterations=agent_run.iterations,
                cleanup=True,
            )
            return task_def, metrics, agent_run
        finally:
            workspace_manager.cleanup_task_workspace(task_id)

    else:
        raise ValueError(f"Unsupported evaluation mode: '{mode}'")


async def run_benchmark_suite(
    task_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    difficulty_filter: Optional[str] = None,
    mode: str = "golden",
    tasks_dir: Path | str = "tasks",
    output_dir: Path | str = "results",
) -> int:
    """Discover, filter, and run benchmark evaluations across matching tasks."""
    tasks_root = Path(tasks_dir).resolve()
    out_root = Path(output_dir).resolve()
    scratch_root = PROJECT_ROOT / "scratch" / "cli_eval_ws"

    all_tasks = discover_tasks(tasks_root)
    if not all_tasks:
        print(f"[Error] No benchmark tasks found in '{tasks_root}'.")
        return 1

    # Filter tasks
    selected_tasks: Dict[str, TaskDefinition] = {}
    for task_id, t_def in sorted(all_tasks.items()):
        if task_filter and t_def.task_id != task_filter:
            continue
        if category_filter and t_def.category.value != category_filter:
            continue
        if difficulty_filter and t_def.difficulty.value != difficulty_filter:
            continue
        selected_tasks[task_id] = t_def

    if not selected_tasks:
        print("[Error] No benchmark tasks matched the specified filters:")
        if task_filter:
            print(f"  - task: {task_filter}")
        if category_filter:
            print(f"  - category: {category_filter}")
        if difficulty_filter:
            print(f"  - difficulty: {difficulty_filter}")
        return 1

    runner = EvaluationRunner(tasks_root=tasks_root, workspace_root=scratch_root)
    ws_manager = WorkspaceManager(workspace_root=scratch_root)

    print(f"\n[CodeForgeX] Discovered {len(selected_tasks)} matching benchmark tasks. Starting evaluation...")
    start_time = time.time()
    results = []

    for task_id, task_def in selected_tasks.items():
        print(f"  > Evaluating '{task_id}' ({task_def.category.value}, {task_def.difficulty.value}) ...", end="", flush=True)
        t0 = time.time()
        res_tuple = await run_single_task_evaluation(
            task_def=task_def,
            tasks_root=tasks_root,
            workspace_root=scratch_root,
            mode=mode,
            runner=runner,
            workspace_manager=ws_manager,
        )
        results.append(res_tuple)
        t_el = time.time() - t0
        status_text = "PASS" if res_tuple[1].success else "FAIL"
        print(f" [{status_text}] ({res_tuple[1].score:.1f} pts in {t_el:.1f}s)")

    total_duration = time.time() - start_time

    # Render terminal dashboard
    render_terminal_dashboard(results, total_duration, mode)

    # Save artifacts
    json_file, md_file = write_evaluation_artifacts(results, out_root, mode, total_duration)
    print(f"[CodeForgeX] Artifacts saved:")
    print(f"  - JSON Report:     {json_file}")
    print(f"  - Markdown Report: {md_file}\n")

    # Exit with 0 if all tasks passed, 1 if any task failed
    all_passed = all(m.success for _, m, _ in results)
    return 0 if all_passed else 1


def main() -> int:
    """CLI argument parsing and entrypoint."""
    parser = argparse.ArgumentParser(
        description="CodeForgeX: Deterministic AI-Agent Evaluation Harness & Benchmark Runner"
    )
    parser.add_argument("--task", "-t", type=str, help="Target a specific task ID (e.g. bug_fix_001)")
    parser.add_argument("--all", "-a", action="store_true", help="Run all discovered benchmark tasks")
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        choices=["bug_fix", "feature", "refactor", "performance", "algorithm"],
        help="Filter tasks by category",
    )
    parser.add_argument(
        "--difficulty",
        "-d",
        type=str,
        choices=["easy", "medium", "hard"],
        help="Filter tasks by difficulty",
    )
    parser.add_argument(
        "--mode",
        "-m",
        type=str,
        choices=["golden", "agent-systematic"],
        default="golden",
        help="Evaluation execution mode (default: 'golden')",
    )
    parser.add_argument("--tasks-dir", type=str, default="tasks", help="Tasks repository path (default: 'tasks')")
    parser.add_argument("--output-dir", type=str, default="results", help="Directory to save evaluation reports (default: 'results')")

    args = parser.parse_args()

    # Default to --all if no task or category or difficulty filter specified
    if not args.task and not args.category and not args.difficulty and not args.all:
        args.all = True

    return asyncio.run(
        run_benchmark_suite(
            task_filter=args.task,
            category_filter=args.category,
            difficulty_filter=args.difficulty,
            mode=args.mode,
            tasks_dir=args.tasks_dir,
            output_dir=args.output_dir,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
