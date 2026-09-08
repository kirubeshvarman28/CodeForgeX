"""Security sandbox, policy enforcement, and anti-cheat protection module.

Enforces:
1. Canonical repository boundary containment (path traversal & symlink escape guards).
2. Anti-cheat file protection (preventing access to hidden tests, solutions, evaluator scripts).
3. Command execution whitelisting and shell injection mitigation.
4. Resource consumption caps (file size limits, command execution timeouts).
"""

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

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

DEFAULT_PROTECTED_PATTERNS: List[str] = [
    r"(?:^|[\\/])\.hidden.*",
    r"(?:^|[\\/]).*_hidden\.py$",
    r"(?:^|[\\/])solution[\\/].*",
    r"(?:^|[\\/])solution\..*",
    r"(?:^|[\\/])expected\..*",
    r"(?:^|[\\/])task\.json$",
    r"(?:^|[\\/])metadata\.json$",
    r"(?:^|[\\/])evaluator.*",
]

DEFAULT_ALLOWED_COMMANDS: Set[str] = {
    "git",
    "pytest",
    "python",
    "python3",
}

DEFAULT_BLOCKED_COMMANDS: Set[str] = {
    "rm",
    "del",
    "erase",
    "rmdir",
    "format",
    "powershell",
    "cmd",
    "bash",
    "sh",
    "zsh",
    "curl",
    "wget",
    "nc",
    "netcat",
    "ssh",
    "scp",
    "ftp",
    "telnet",
    "sudo",
    "su",
    "chmod",
    "chown",
    "kill",
    "pkill",
    "killall",
    "taskkill",
    "shutdown",
    "reboot",
}

SHELL_INJECTION_CHARS: Set[str] = {";", "&&", "||", "|", "`", "$", "(", ")", ">", "<"}


class SecuritySandboxError(Exception):
    """Base exception for all security sandbox violations."""
    pass


class PathTraversalError(SecuritySandboxError):
    """Raised when an operation attempts to escape the designated repository root."""
    pass


class ProtectedResourceError(SecuritySandboxError):
    """Raised when an agent attempts to access hidden tests, solutions, or evaluator internals."""
    pass


class CommandSecurityError(SecuritySandboxError):
    """Raised when an unauthorized, dangerous, or un-sanitized command is attempted."""
    pass


class ResourceLimitExceededError(SecuritySandboxError):
    """Raised when an operation exceeds memory, file size, or line length limits."""
    pass


@dataclass
class SecurityPolicy:
    """Configurable security boundaries and privilege restrictions for task execution."""
    max_file_read_bytes: int = 2 * 1024 * 1024  # 2MB
    max_file_write_bytes: int = 500 * 1024       # 500KB
    max_command_timeout: int = 120              # 120 seconds
    enforce_anti_cheat: bool = True
    ignored_dirs: Set[str] = field(default_factory=lambda: set(DEFAULT_IGNORED_DIRS))
    protected_patterns: List[str] = field(default_factory=lambda: list(DEFAULT_PROTECTED_PATTERNS))
    allowed_commands: Set[str] = field(default_factory=lambda: set(DEFAULT_ALLOWED_COMMANDS))
    blocked_commands: Set[str] = field(default_factory=lambda: set(DEFAULT_BLOCKED_COMMANDS))


DEFAULT_SECURITY_POLICY = SecurityPolicy()


def resolve_safe_path(
    repo_root: Path | str,
    target_path: Path | str,
    must_exist: bool = False,
    policy: Optional[SecurityPolicy] = None,
) -> Path:
    """Resolve and validate that target_path strictly resides within repo_root.

    Also verifies that the target path does not violate anti-cheat protection
    rules when policy.enforce_anti_cheat is enabled.

    Args:
        repo_root: The root directory that bounds all operations.
        target_path: Relative (or supposedly internal) path to resolve.
        must_exist: If True, raises FileNotFoundError if target_path does not exist.
        policy: SecurityPolicy containing anti-cheat and containment rules.

    Returns:
        The fully resolved, canonicalized Path inside repo_root.

    Raises:
        PathTraversalError: If target_path resolves outside repo_root.
        ProtectedResourceError: If target_path accesses protected evaluator files.
        FileNotFoundError: If must_exist is True and the path does not exist.
    """
    effective_policy = policy if policy is not None else DEFAULT_SECURITY_POLICY
    root = Path(repo_root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Repository root directory does not exist: {root}")

    # Handle path strings safely
    raw_path = Path(target_path)
    if raw_path.is_absolute():
        candidate = raw_path.resolve()
    else:
        candidate = (root / raw_path).resolve()

    # Check repository containment
    try:
        rel = candidate.relative_to(root)
    except ValueError:
        raise PathTraversalError(
            f"Security violation: path '{target_path}' resolves to '{candidate}', "
            f"which escapes repository root '{root}'."
        )

    # Enforce anti-cheat resource isolation
    if effective_policy.enforce_anti_cheat and is_protected_resource(rel.as_posix(), effective_policy):
        raise ProtectedResourceError(
            f"Access denied: '{target_path}' is a protected evaluator or solution resource."
        )

    if must_exist and not candidate.exists():
        raise FileNotFoundError(f"File or directory does not exist: {target_path}")

    return candidate


def is_ignored_path(path: Path | str, ignored_dirs: Optional[Set[str]] = None) -> bool:
    """Check if any segment of the path matches standard ignored directory names."""
    dirs = ignored_dirs if ignored_dirs is not None else DEFAULT_IGNORED_DIRS
    parts = Path(path).parts
    return any(part in dirs for part in parts)


def is_protected_resource(relative_path: str, policy: Optional[SecurityPolicy] = None) -> bool:
    """Check whether a path targets protected evaluator internals, solutions, or hidden tests."""
    effective_policy = policy if policy is not None else DEFAULT_SECURITY_POLICY
    normalized = relative_path.replace("\\", "/")
    for pattern in effective_policy.protected_patterns:
        if re.search(pattern, normalized, re.IGNORECASE):
            return True
    return False


def validate_safe_command(
    cmd_args: List[str],
    policy: Optional[SecurityPolicy] = None,
) -> List[str]:
    """Validate command arguments against allowed whitelists and block shell injection.

    Args:
        cmd_args: Command argument vector (e.g. ['git', 'diff']).
        policy: Active security policy.

    Returns:
        The validated command argument list.

    Raises:
        CommandSecurityError: If binary is disallowed or contains shell metacharacters.
    """
    if not cmd_args:
        raise CommandSecurityError("Cannot execute empty command.")

    effective_policy = policy if policy is not None else DEFAULT_SECURITY_POLICY

    raw_binary = cmd_args[0]
    binary_name = Path(raw_binary).stem.lower()

    # 1. Check blacklist
    if binary_name in effective_policy.blocked_commands:
        raise CommandSecurityError(
            f"Security violation: execution of command '{binary_name}' is strictly prohibited."
        )

    # 2. Check whitelist
    if binary_name not in effective_policy.allowed_commands:
        raise CommandSecurityError(
            f"Security violation: command '{binary_name}' is not in the authorized whitelist "
            f"({sorted(list(effective_policy.allowed_commands))})."
        )

    # 3. Check for shell injection characters in arguments
    for arg in cmd_args:
        for char in SHELL_INJECTION_CHARS:
            if char in arg:
                raise CommandSecurityError(
                    f"Security violation: argument '{arg}' contains disallowed shell operator '{char}'."
                )

    return cmd_args
