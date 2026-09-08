"""Filesystem exploration tools for the MCP Software Engineering Agent.

Provides deterministic, security-bounded file listing and reading operations.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_server.security.sandbox import (
    DEFAULT_SECURITY_POLICY,
    ResourceLimitExceededError,
    SecurityPolicy,
    is_ignored_path,
    is_protected_resource,
    resolve_safe_path,
)

MAX_READ_LINES = 1000


def list_files_impl(
    repo_root: Path | str,
    directory: str = "",
    recursive: bool = True,
    max_depth: int = 10,
    policy: Optional[SecurityPolicy] = None,
) -> Dict[str, Any]:
    """List files in the repository within safe boundaries.

    Args:
        repo_root: Absolute canonical path to the repository root.
        directory: Relative subfolder inside the repository (empty string for root).
        recursive: Whether to list recursively.
        max_depth: Maximum recursion depth.
        policy: Optional active SecurityPolicy.

    Returns:
        Structured dict with directory, total_entries, and entries list.
    """
    root = Path(repo_root).resolve()
    effective_policy = policy if policy is not None else DEFAULT_SECURITY_POLICY
    target_dir = resolve_safe_path(root, directory, must_exist=True, policy=effective_policy)

    if not target_dir.is_dir():
        raise NotADirectoryError(f"Target path is not a directory: {directory}")

    entries: List[Dict[str, Any]] = []

    def _traverse(current_dir: Path, current_depth: int):
        if current_depth > max_depth:
            return

        try:
            children = sorted(current_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return

        for child in children:
            if is_ignored_path(child.name, effective_policy.ignored_dirs):
                continue

            rel_path = child.relative_to(root).as_posix()
            if effective_policy.enforce_anti_cheat and is_protected_resource(rel_path, effective_policy):
                continue

            is_directory = child.is_dir()
            size = 0
            if not is_directory:
                try:
                    size = child.stat().st_size
                except OSError:
                    size = 0

            entries.append({
                "path": rel_path,
                "is_dir": is_directory,
                "size_bytes": size,
            })

            if is_directory and recursive:
                _traverse(child, current_depth + 1)

    _traverse(target_dir, current_depth=1)

    return {
        "directory": directory,
        "total_entries": len(entries),
        "entries": entries,
    }


def read_file_impl(
    repo_root: Path | str,
    path: str,
    start_line: int = 1,
    end_line: Optional[int] = None,
    max_lines: int = MAX_READ_LINES,
    policy: Optional[SecurityPolicy] = None,
) -> Dict[str, Any]:
    """Read file content with line windowing and security containment.

    Args:
        repo_root: Absolute canonical path to the repository root.
        path: Relative path to the file inside the repository.
        start_line: 1-indexed start line number (inclusive).
        end_line: 1-indexed end line number (inclusive). If None, reads up to max_lines.
        max_lines: Safety ceiling on maximum lines returned in a single call.
        policy: Optional active SecurityPolicy.

    Returns:
        Structured dict with path, line metadata, and file content.
    """
    root = Path(repo_root).resolve()
    effective_policy = policy if policy is not None else DEFAULT_SECURITY_POLICY
    file_path = resolve_safe_path(root, path, must_exist=True, policy=effective_policy)

    if not file_path.is_file():
        raise IsADirectoryError(f"Target path is a directory, not a file: {path}")

    # Check file size before reading entire file
    stat = file_path.stat()
    if stat.st_size > effective_policy.max_file_read_bytes:
        raise ResourceLimitExceededError(
            f"File '{path}' exceeds max allowed size of {effective_policy.max_file_read_bytes} bytes "
            f"(actual: {stat.st_size} bytes)."
        )

    # Read bytes and check for binary characters
    raw_data = file_path.read_bytes()
    if b"\x00" in raw_data:
        return {
            "path": Path(path).as_posix(),
            "is_binary": True,
            "size_bytes": len(raw_data),
            "content": "[Binary file cannot be displayed as text]",
            "total_lines": 0,
            "start_line": 0,
            "end_line": 0,
            "is_truncated": False,
        }

    text = raw_data.decode("utf-8", errors="replace").replace("\r\n", "\n")
    all_lines = text.splitlines(keepends=True)
    total_lines = len(all_lines)

    if start_line < 1:
        start_line = 1

    if end_line is None or end_line > total_lines:
        end_line = total_lines

    # Ensure start_line <= end_line
    if start_line > total_lines:
        return {
            "path": Path(path).as_posix(),
            "is_binary": False,
            "size_bytes": len(raw_data),
            "total_lines": total_lines,
            "start_line": start_line,
            "end_line": total_lines,
            "content": "",
            "is_truncated": False,
        }

    # Slice lines (1-indexed conversion)
    selected_lines = all_lines[start_line - 1 : end_line]
    is_truncated = False
    if len(selected_lines) > max_lines:
        selected_lines = selected_lines[:max_lines]
        is_truncated = True
        end_line = start_line + max_lines - 1

    content = "".join(selected_lines)

    return {
        "path": Path(path).as_posix(),
        "is_binary": False,
        "size_bytes": len(raw_data),
        "total_lines": total_lines,
        "start_line": start_line,
        "end_line": end_line,
        "content": content,
        "is_truncated": is_truncated,
    }
