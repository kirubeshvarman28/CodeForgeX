"""Patch application tool for the MCP Software Engineering Agent.

Provides deterministic unified diff patch validation, security containment,
and atomic application via git apply.
"""

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from mcp_server.security.sandbox import (
    DEFAULT_SECURITY_POLICY,
    PathTraversalError,
    ProtectedResourceError,
    ResourceLimitExceededError,
    SecurityPolicy,
    resolve_safe_path,
)


def extract_patch_target_paths(patch_content: str) -> Set[str]:
    """Extract all target file paths referenced in a unified diff patch.

    Handles headers like:
        --- a/path/to/file.py
        +++ b/path/to/file.py
        diff --git a/file.py b/file.py
    """
    paths: Set[str] = set()
    for line in patch_content.splitlines():
        # Match +++ or --- headers
        m_diff = re.match(r"^(?:\+\+\+|---)\s+(?:[ab]/)?([^\t\r\n]+)", line)
        if m_diff:
            target = m_diff.group(1).strip()
            if target != "/dev/null" and target != "dev/null":
                # Remove quotes if git formatted with quotes
                target = target.strip('"\'')
                paths.add(target)
        # Match diff --git a/path b/path
        m_git = re.match(r"^diff --git\s+(?:a/)?(\S+)\s+(?:b/)?(\S+)", line)
        if m_git:
            p1 = m_git.group(1).strip('"\'')
            p2 = m_git.group(2).strip('"\'')
            if p1 != "/dev/null":
                paths.add(p1)
            if p2 != "/dev/null":
                paths.add(p2)
    return paths


def apply_patch_impl(
    repo_root: Path | str,
    patch: str,
    file_path: Optional[str] = None,
    policy: Optional[SecurityPolicy] = None,
) -> Dict[str, Any]:
    """Validate and atomically apply a unified diff patch within repository boundaries.

    Args:
        repo_root: Root directory of the repository.
        patch: Unified diff patch string.
        file_path: Optional relative target path if patch is scoped to a single file.
        policy: Optional active SecurityPolicy.

    Returns:
        Structured result dict with success status, changed files, and validation message.

    Raises:
        ValueError: If patch is empty.
        ResourceLimitExceededError: If patch size exceeds policy limits.
        PathTraversalError: If any target file escapes repo_root.
        ProtectedResourceError: If attempting to patch protected evaluator files.
    """
    if not patch.strip():
        raise ValueError("Patch content cannot be empty.")

    root = Path(repo_root).resolve()
    effective_policy = policy if policy is not None else DEFAULT_SECURITY_POLICY

    patch_bytes = patch.encode("utf-8")
    if len(patch_bytes) > effective_policy.max_file_write_bytes:
        raise ResourceLimitExceededError(
            f"Patch size of {len(patch_bytes)} bytes exceeds allowed limit of "
            f"{effective_policy.max_file_write_bytes} bytes."
        )

    # If file_path is explicitly provided, validate it first
    if file_path:
        resolve_safe_path(root, file_path, must_exist=False, policy=effective_policy)

    # Extract all paths mentioned in the diff headers and enforce containment
    extracted_paths = extract_patch_target_paths(patch)
    for target in extracted_paths:
        resolve_safe_path(root, target, must_exist=False, policy=effective_policy)

    # Normalize patch content to ensure standard Unix line endings
    normalized_patch = patch.replace("\r\n", "\n")
    if not normalized_patch.endswith("\n"):
        normalized_patch += "\n"

    # Step 1: Dry-run check with git apply --check
    check_args = ["git", "apply", "--check", "--verbose"]
    check_proc = subprocess.run(
        check_args,
        input=normalized_patch,
        text=True,
        cwd=str(root),
        capture_output=True,
    )

    if check_proc.returncode != 0:
        # If -p1 check failed, try -p0 (for patches without a/ b/ prefixes)
        check_p0 = subprocess.run(
            ["git", "apply", "-p0", "--check", "--verbose"],
            input=normalized_patch,
            text=True,
            cwd=str(root),
            capture_output=True,
        )
        if check_p0.returncode == 0:
            apply_args = ["git", "apply", "-p0", "--whitespace=fix"]
        else:
            err_msg = check_proc.stderr.strip() or check_proc.stdout.strip() or "Patch does not apply cleanly."
            return {
                "success": False,
                "changed_files": [],
                "error": f"Patch dry-run validation failed: {err_msg}",
            }
    else:
        apply_args = ["git", "apply", "--whitespace=fix"]

    # Step 2: Actually apply the patch
    apply_proc = subprocess.run(
        apply_args,
        input=normalized_patch,
        text=True,
        cwd=str(root),
        capture_output=True,
    )

    if apply_proc.returncode != 0:
        err_msg = apply_proc.stderr.strip() or "Failed to apply patch."
        return {
            "success": False,
            "changed_files": [],
            "error": err_msg,
        }

    changed_list = sorted(list(extracted_paths))
    if not changed_list and file_path:
        changed_list = [Path(file_path).as_posix()]

    return {
        "success": True,
        "changed_files": changed_list,
        "message": f"Successfully applied patch to {len(changed_list)} file(s).",
    }
