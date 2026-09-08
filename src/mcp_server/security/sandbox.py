"""Security sandbox and path validation module.

Prevents path traversal, directory escape, and symlink escape attacks by
enforcing strict repository boundary containment on all file operations.
"""

from pathlib import Path
from typing import Set

DEFAULT_IGNORED_DIRS: Set[str] = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "dist",
    "build",
    ".egg-info",
}


class SecuritySandboxError(Exception):
    """Base exception for security sandbox violations."""
    pass


class PathTraversalError(SecuritySandboxError):
    """Raised when an operation attempts to escape the designated repository root."""
    pass


def resolve_safe_path(
    repo_root: Path | str,
    target_path: Path | str,
    must_exist: bool = False,
) -> Path:
    """Resolve and validate that target_path strictly resides within repo_root.

    Args:
        repo_root: The root directory that bounds all operations.
        target_path: Relative (or supposedly internal) path to resolve.
        must_exist: If True, raises FileNotFoundError if target_path does not exist.

    Returns:
        The fully resolved, canonicalized Path inside repo_root.

    Raises:
        PathTraversalError: If target_path resolves outside repo_root or escapes via symlink.
        FileNotFoundError: If must_exist is True and the path does not exist.
    """
    root = Path(repo_root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Repository root directory does not exist: {root}")

    # Handle path strings safely
    raw_path = Path(target_path)
    if raw_path.is_absolute():
        # If absolute, verify if it's already rooted in root
        candidate = raw_path.resolve()
    else:
        candidate = (root / raw_path).resolve()

    # Check path containment
    try:
        candidate.relative_to(root)
    except ValueError:
        raise PathTraversalError(
            f"Security violation: path '{target_path}' resolves to '{candidate}', "
            f"which escapes repository root '{root}'."
        )

    if must_exist and not candidate.exists():
        raise FileNotFoundError(f"File or directory does not exist: {target_path}")

    return candidate


def is_ignored_path(path: Path | str, ignored_dirs: Set[str] = DEFAULT_IGNORED_DIRS) -> bool:
    """Check if any segment of the path matches standard ignored directory names."""
    parts = Path(path).parts
    return any(part in ignored_dirs for part in parts)
