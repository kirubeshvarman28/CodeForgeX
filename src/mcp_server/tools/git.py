"""Git inspection tools for the MCP Software Engineering Agent.

Provides deterministic git diff extraction and repository status inspection.
"""

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_server.security.sandbox import resolve_safe_path


def get_git_diff_impl(
    repo_root: Path | str,
    path: str = "",
    cached: bool = False,
) -> Dict[str, Any]:
    """Inspect deterministic Git diff of staged or unstaged changes.

    Args:
        repo_root: Root directory of the repository.
        path: Optional relative path to scope the diff to a specific file/folder.
        cached: If True, inspects staged changes (git diff --cached).

    Returns:
        Structured dict containing diff text, changed files list, and change flag.
    """
    root = Path(repo_root).resolve()

    cmd = ["git", "diff"]
    if cached:
        cmd.append("--cached")

    if path.strip():
        safe_path = resolve_safe_path(root, path, must_exist=False)
        rel_path = safe_path.relative_to(root).as_posix()
        cmd.extend(["--", rel_path])

    proc = subprocess.run(
        cmd,
        cwd=str(root),
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        raise RuntimeError(f"Git diff failed: {proc.stderr.strip()}")

    diff_text = proc.stdout.replace("\r\n", "\n")

    # Get changed files list
    name_cmd = ["git", "diff", "--name-only"]
    if cached:
        name_cmd.append("--cached")
    if path.strip():
        name_cmd.extend(["--", rel_path])

    name_proc = subprocess.run(
        name_cmd,
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    changed_files = [f.strip() for f in name_proc.stdout.splitlines() if f.strip()]

    return {
        "diff": diff_text,
        "has_changes": bool(diff_text.strip()),
        "changed_files": changed_files,
        "cached": cached,
    }


def get_repository_status_impl(repo_root: Path | str) -> Dict[str, Any]:
    """Inspect working tree and staging area status.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        Structured status dict with branch, modified, untracked, staged, and clean flags.
    """
    root = Path(repo_root).resolve()

    proc = subprocess.run(
        ["git", "status", "--porcelain=v1", "-b"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        raise RuntimeError(f"Git status failed: {proc.stderr.strip()}")

    lines = proc.stdout.splitlines()
    branch = "unknown"
    staged: List[str] = []
    modified: List[str] = []
    untracked: List[str] = []
    deleted: List[str] = []

    for line in lines:
        if line.startswith("##"):
            # Branch header, e.g. "## main...origin/main" or "## main"
            branch_match = re.match(r"^##\s+([^.\s]+)", line)
            if branch_match:
                branch = branch_match.group(1)
            continue

        if len(line) < 3:
            continue

        index_code = line[0]
        worktree_code = line[1]
        file_path = line[3:].strip()

        # Handle renamed files "old -> new"
        if " -> " in file_path:
            file_path = file_path.split(" -> ")[1].strip()

        # Check untracked
        if index_code == "?" and worktree_code == "?":
            untracked.append(file_path)
            continue

        # Check staged
        if index_code in ("M", "A", "D", "R", "C"):
            staged.append(file_path)

        # Check unstaged modified
        if worktree_code == "M":
            modified.append(file_path)
        elif worktree_code == "D":
            deleted.append(file_path)

    total_changes = len(staged) + len(modified) + len(untracked) + len(deleted)
    is_clean = total_changes == 0

    return {
        "branch": branch,
        "clean": is_clean,
        "total_changes": total_changes,
        "modified": sorted(list(set(modified))),
        "staged": sorted(list(set(staged))),
        "untracked": sorted(list(set(untracked))),
        "deleted": sorted(list(set(deleted))),
    }
