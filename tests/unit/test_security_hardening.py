"""Security penetration and hardening test suite.

Simulates adversary and exploratory agent actions to verify:
1. Anti-cheat file protection (preventing access to hidden tests, solutions, and evaluator scripts).
2. Command execution whitelisting and shell injection mitigation.
3. Resource consumption ceilings (file size and patch byte caps).
4. Graceful error reporting through the MCP Server interface.
"""

import json
import pytest
from pathlib import Path
from mcp_server.security.sandbox import (
    CommandSecurityError,
    PathTraversalError,
    ProtectedResourceError,
    ResourceLimitExceededError,
    SecurityPolicy,
    is_protected_resource,
    resolve_safe_path,
    validate_safe_command,
)
from mcp_server.server import create_mcp_server
from mcp_server.tools.filesystem import list_files_impl, read_file_impl
from mcp_server.tools.patching import apply_patch_impl
from mcp_server.tools.search import search_code_impl


@pytest.fixture
def repo_with_hidden_files(tmp_path: Path) -> Path:
    """Create a repository containing both normal code and protected evaluation files."""
    repo = tmp_path / "sandbox_repo"
    repo.mkdir()

    # Public repository files
    (repo / "src").mkdir()
    (repo / "src" / "pricing.py").write_text("def calc(): return 42\n", encoding="utf-8")
    (repo / "README.md").write_text("# Project\n", encoding="utf-8")

    # Protected evaluator / hidden test files
    (repo / ".hidden_tests").mkdir()
    (repo / ".hidden_tests" / "test_secret.py").write_text("def test_secret(): assert True\n", encoding="utf-8")
    (repo / "task.json").write_text('{"task_id": "test_001", "solution": "secret"}', encoding="utf-8")
    (repo / "solution.patch").write_text("diff --git a/src/pricing.py ...\n", encoding="utf-8")

    return repo


def test_is_protected_resource():
    """Verify regex patterns identifying hidden tests, solutions, and task metadata."""
    assert is_protected_resource(".hidden_tests/test_secret.py")
    assert is_protected_resource("tests/test_hidden.py")
    assert is_protected_resource("solution.patch")
    assert is_protected_resource("solution/expected.patch")
    assert is_protected_resource("task.json")
    assert is_protected_resource("metadata.json")

    # Normal public files must not be flagged as protected
    assert not is_protected_resource("src/pricing.py")
    assert not is_protected_resource("tests/test_pricing.py")
    assert not is_protected_resource("README.md")


def test_anti_cheat_blocks_reading_protected_files(repo_with_hidden_files: Path):
    """Verify that read_file_impl rejects access to protected evaluator files."""
    with pytest.raises(ProtectedResourceError, match="Access denied"):
        read_file_impl(repo_with_hidden_files, ".hidden_tests/test_secret.py")

    with pytest.raises(ProtectedResourceError, match="Access denied"):
        read_file_impl(repo_with_hidden_files, "task.json")

    with pytest.raises(ProtectedResourceError, match="Access denied"):
        read_file_impl(repo_with_hidden_files, "solution.patch")


def test_anti_cheat_hides_protected_files_from_listing(repo_with_hidden_files: Path):
    """Verify list_files_impl filters out protected evaluator files from agent sight."""
    result = list_files_impl(repo_with_hidden_files, directory="", recursive=True)
    paths = [e["path"] for e in result["entries"]]

    # Public files visible
    assert "src/pricing.py" in paths
    assert "README.md" in paths

    # Protected files completely concealed
    assert not any(".hidden" in p for p in paths)
    assert "task.json" not in paths
    assert "solution.patch" not in paths


def test_anti_cheat_hides_protected_files_from_search(repo_with_hidden_files: Path):
    """Verify search_code_impl does not scan or leak contents from protected files."""
    result = search_code_impl(repo_with_hidden_files, query="secret")
    # "secret" only appears in task.json and .hidden_tests/test_secret.py
    assert result["total_matches"] == 0


def test_anti_cheat_blocks_patching_protected_files(repo_with_hidden_files: Path):
    """Verify apply_patch_impl prevents modifying task.json or hidden tests."""
    malicious_patch = (
        "--- a/task.json\n"
        "+++ b/task.json\n"
        "@@ -1,1 +1,1 @@\n"
        "-secret\n"
        "+modified\n"
    )
    with pytest.raises(ProtectedResourceError):
        apply_patch_impl(repo_with_hidden_files, malicious_patch)


def test_validate_safe_command_whitelisting():
    """Verify only whitelisted command binaries are permitted."""
    # Authorized commands pass
    assert validate_safe_command(["git", "status"]) == ["git", "status"]
    assert validate_safe_command(["pytest", "-v"]) == ["pytest", "-v"]
    assert validate_safe_command(["python", "-m", "pytest"]) == ["python", "-m", "pytest"]

    # Blocked dangerous commands raise CommandSecurityError
    with pytest.raises(CommandSecurityError, match="strictly prohibited"):
        validate_safe_command(["rm", "-rf", "/"])

    with pytest.raises(CommandSecurityError, match="strictly prohibited"):
        validate_safe_command(["curl", "http://attacker.com"])

    with pytest.raises(CommandSecurityError, match="strictly prohibited"):
        validate_safe_command(["powershell", "-c", "dir"])

    # Non-whitelisted commands raise CommandSecurityError
    with pytest.raises(CommandSecurityError, match="not in the authorized whitelist"):
        validate_safe_command(["gcc", "main.c"])


def test_validate_safe_command_blocks_shell_injection():
    """Verify shell operators in arguments are rejected."""
    with pytest.raises(CommandSecurityError, match="disallowed shell operator"):
        validate_safe_command(["git", "status; rm -rf /"])

    with pytest.raises(CommandSecurityError, match="disallowed shell operator"):
        validate_safe_command(["pytest", "tests && cat /etc/passwd"])

    with pytest.raises(CommandSecurityError, match="disallowed shell operator"):
        validate_safe_command(["git", "log | grep secret"])


def test_resource_limits_enforced(repo_with_hidden_files: Path):
    """Verify file size and patch byte limits are enforced."""
    # Test small policy limit
    strict_policy = SecurityPolicy(max_file_read_bytes=10, max_file_write_bytes=20)

    # Reading file larger than 10 bytes raises ResourceLimitExceededError
    with pytest.raises(ResourceLimitExceededError, match="exceeds max allowed size"):
        read_file_impl(repo_with_hidden_files, "src/pricing.py", policy=strict_policy)

    # Patch larger than 20 bytes raises ResourceLimitExceededError
    large_patch = "--- a/src/pricing.py\n+++ b/src/pricing.py\n@@ -1,1 +1,1 @@\n-long line that exceeds twenty bytes\n+new\n"
    with pytest.raises(ResourceLimitExceededError, match="exceeds allowed limit"):
        apply_patch_impl(repo_with_hidden_files, large_patch, policy=strict_policy)


@pytest.mark.anyio
async def test_server_handles_security_violations_gracefully(repo_with_hidden_files: Path):
    """Verify server returns structured error JSON without crashing when security violations occur."""
    server = create_mcp_server(repo_with_hidden_files)

    # 1. Attempting to read protected task.json
    res = await server.call_tool("read_file", {"path": "task.json"})
    assert not res.is_error
    payload = json.loads(res.content[0].text)
    assert payload["success"] is False
    assert "Access denied" in payload["error"]

    # 2. Attempting directory traversal
    res_trav = await server.call_tool("read_file", {"path": "../../etc/shadow"})
    assert not res_trav.is_error
    trav_payload = json.loads(res_trav.content[0].text)
    assert trav_payload["success"] is False
    assert "Security violation" in trav_payload["error"]
