"""Unit tests for the unified Benchmark Runner CLI (scripts/run_evaluation.py)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

CLI_SCRIPT = Path("scripts/run_evaluation.py").resolve()


def test_cli_help():
    """Verify CLI help displays all options, filters, and modes."""
    proc = subprocess.run(
        [sys.executable, str(CLI_SCRIPT), "--help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "--task" in proc.stdout
    assert "--category" in proc.stdout
    assert "--difficulty" in proc.stdout
    assert "--mode" in proc.stdout
    assert "golden" in proc.stdout
    assert "agent-systematic" in proc.stdout


def test_cli_single_task_golden_mode(tmp_path: Path):
    """Verify executing CLI on single task in golden mode produces artifacts and passes."""
    proc = subprocess.run(
        [
            sys.executable,
            str(CLI_SCRIPT),
            "--task",
            "bug_fix_001",
            "--mode",
            "golden",
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "Evaluating 'bug_fix_001'" in proc.stdout
    assert "Summary: 1/1 Tasks Resolved" in proc.stdout

    # Verify JSON artifact
    json_files = list(tmp_path.glob("*.json"))
    assert len(json_files) == 1
    data = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert data["benchmark"] == "CodeForgeX"
    assert data["mode"] == "golden"
    assert data["resolved_tasks"] == 1
    assert data["mean_score"] == 100.0

    # Verify Markdown artifact
    md_files = list(tmp_path.glob("*.md"))
    assert len(md_files) == 1
    md_content = md_files[0].read_text(encoding="utf-8")
    assert "PASSED" in md_content
    assert "bug_fix_001" in md_content


def test_cli_category_filter(tmp_path: Path):
    """Verify category filtering isolates only matching tasks."""
    proc = subprocess.run(
        [
            sys.executable,
            str(CLI_SCRIPT),
            "--category",
            "algorithm",
            "--mode",
            "golden",
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "Evaluating 'algo_001'" in proc.stdout

    json_files = list(tmp_path.glob("*.json"))
    assert len(json_files) == 1
    data = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert data["total_tasks"] == 1
    assert data["tasks"][0]["task_id"] == "algo_001"
    assert data["tasks"][0]["category"] == "algorithm"


def test_cli_invalid_task_filter():
    """Verify unmatched task filter returns non-zero exit code with informative message."""
    proc = subprocess.run(
        [
            sys.executable,
            str(CLI_SCRIPT),
            "--task",
            "non_existent_task_12345",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "No benchmark tasks matched" in proc.stdout


def test_cli_agent_systematic_mode(tmp_path: Path):
    """Verify CLI executes autonomous agent loop over MCP stdio and records trajectory."""
    proc = subprocess.run(
        [
            sys.executable,
            str(CLI_SCRIPT),
            "--task",
            "bug_fix_001",
            "--mode",
            "agent-systematic",
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "Mode: AGENT-SYSTEMATIC" in proc.stdout
    assert "100.0 pts" in proc.stdout

    json_files = list(tmp_path.glob("*.json"))
    assert len(json_files) == 1
    data = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert data["mode"] == "agent-systematic"

    task_data = data["tasks"][0]
    assert task_data["agent_run"] is not None
    assert task_data["agent_run"]["completed"] is True
    assert len(task_data["agent_run"]["trajectory"]) >= 5
