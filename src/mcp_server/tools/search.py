"""Code search tool for the MCP Software Engineering Agent.

Provides deterministic line-by-line regex and literal search across repository files.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_server.security.sandbox import (
    DEFAULT_SECURITY_POLICY,
    SecurityPolicy,
    is_ignored_path,
    is_protected_resource,
    resolve_safe_path,
)

DEFAULT_MAX_MATCHES = 50


def search_code_impl(
    repo_root: Path | str,
    query: str,
    path: str = "",
    is_regex: bool = False,
    case_sensitive: bool = False,
    max_results: int = DEFAULT_MAX_MATCHES,
    policy: Optional[SecurityPolicy] = None,
) -> Dict[str, Any]:
    """Search for literal string or regex pattern across repository files.

    Args:
        repo_root: Absolute canonical path to the repository root.
        query: The substring or regular expression to search for.
        path: Optional relative directory or specific file path to scope the search.
        is_regex: Whether query should be interpreted as a regular expression.
        case_sensitive: Whether search should be case-sensitive.
        max_results: Maximum number of match items to return.
        policy: Optional active SecurityPolicy.

    Returns:
        Structured dict with query parameters, total_matches, is_truncated, and matches list.
    """
    if not query:
        raise ValueError("Search query cannot be empty.")

    root = Path(repo_root).resolve()
    effective_policy = policy if policy is not None else DEFAULT_SECURITY_POLICY
    target = resolve_safe_path(root, path, must_exist=True, policy=effective_policy)

    # Compile regex or prepare match predicate
    flags = 0 if case_sensitive else re.IGNORECASE
    if is_regex:
        try:
            pattern = re.compile(query, flags=flags)
        except re.error as err:
            raise ValueError(f"Invalid regular expression pattern '{query}': {err}")
    else:
        escaped = re.escape(query)
        pattern = re.compile(escaped, flags=flags)

    matches: List[Dict[str, Any]] = []
    is_truncated = False

    # Determine files to inspect
    if target.is_file():
        files_to_scan = [target]
    else:
        files_to_scan = []
        for file_path in sorted(target.rglob("*")):
            if file_path.is_file():
                rel_to_root = file_path.relative_to(root)
                # Skip ignored and protected files
                if is_ignored_path(rel_to_root, effective_policy.ignored_dirs):
                    continue
                if effective_policy.enforce_anti_cheat and is_protected_resource(rel_to_root.as_posix(), effective_policy):
                    continue
                files_to_scan.append(file_path)

    for file_path in files_to_scan:
        rel_posix = file_path.relative_to(root).as_posix()
        try:
            raw = file_path.read_bytes()
            if b"\x00" in raw:
                # Skip binary files
                continue
            text = raw.decode("utf-8", errors="replace")
        except OSError:
            continue

        for line_num, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                matches.append({
                    "path": rel_posix,
                    "line_number": line_num,
                    "line_content": line.rstrip("\r\n"),
                })
                if len(matches) >= max_results:
                    is_truncated = True
                    break
        if is_truncated:
            break

    return {
        "query": query,
        "path": path,
        "is_regex": is_regex,
        "case_sensitive": case_sensitive,
        "total_matches": len(matches),
        "is_truncated": is_truncated,
        "matches": matches,
    }
