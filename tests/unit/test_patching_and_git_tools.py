"""Unit tests for patching and Git inspection tools."""

import subprocess
import pytest
from pathlib import Path
from mcp_server.security.sandbox import PathTraversalError
from mcp_server.tools.git import get_git_diff_impl, get_repository_status_impl
from mcp_server.tools.patching import apply_patch_impl, extract_patch_target_paths


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary initialized Git repository with commit history."""
    repo = tmp_path / "git_test_repo"
    repo.mkdir()

    # Initialize git and set local identity
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Agent Tester"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "agent@test.com"], cwd=str(repo), check=True, capture_output=True)

    # Add initial files
    (repo / "src").mkdir()
    (repo / "src" / "pricing.py").write_text(
        "def calculate_discount(price, discount_percent):\n"
        "    # Buggy implementation\n"
        "    return price - discount_percent\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text("# Pricing Engine\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo), check=True, capture_output=True)

    return repo


def test_extract_patch_target_paths():
    """Verify regex extraction of file targets from unified diff headers."""
    patch = (
        "diff --git a/src/pricing.py b/src/pricing.py\n"
        "--- a/src/pricing.py\n"
        "+++ b/src/pricing.py\n"
        "@@ -1,3 +1,3 @@\n"
        "-old\n"
        "+new\n"
        "diff --git a/new_file.py b/new_file.py\n"
        "--- /dev/null\n"
        "+++ b/new_file.py\n"
    )
    targets = extract_patch_target_paths(patch)
    assert "src/pricing.py" in targets
    assert "new_file.py" in targets
    assert "/dev/null" not in targets


def test_apply_patch_clean(git_repo: Path):
    """Test applying a valid unified diff patch cleanly."""
    valid_patch = (
        "--- a/src/pricing.py\n"
        "+++ b/src/pricing.py\n"
        "@@ -1,3 +1,3 @@\n"
        " def calculate_discount(price, discount_percent):\n"
        "-    # Buggy implementation\n"
        "-    return price - discount_percent\n"
        "+    # Fixed implementation\n"
        "+    return price * (1.0 - (discount_percent / 100.0))\n"
    )

    result = apply_patch_impl(git_repo, valid_patch)
    assert result["success"] is True
    assert "src/pricing.py" in result["changed_files"]

    # Verify content was updated
    new_content = (git_repo / "src" / "pricing.py").read_text(encoding="utf-8")
    assert "Fixed implementation" in new_content
    assert "price * (1.0 - (discount_percent / 100.0))" in new_content


def test_apply_patch_dry_run_failure_preserves_file(git_repo: Path):
    """Test that an unaligned/corrupt patch fails validation and preserves file."""
    bad_patch = (
        "--- a/src/pricing.py\n"
        "+++ b/src/pricing.py\n"
        "@@ -1,3 +1,3 @@\n"
        " def non_existent_function():\n"
        "-    old\n"
        "+    new\n"
    )

    original_content = (git_repo / "src" / "pricing.py").read_text(encoding="utf-8")
    result = apply_patch_impl(git_repo, bad_patch)

    assert result["success"] is False
    assert "Patch dry-run validation failed" in result["error"]
    # File must be completely untouched
    assert (git_repo / "src" / "pricing.py").read_text(encoding="utf-8") == original_content


def test_apply_patch_blocks_path_traversal(git_repo: Path):
    """Test that a patch targeting files outside repo raises PathTraversalError."""
    traversal_patch = (
        "--- a/../../secret.txt\n"
        "+++ b/../../secret.txt\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
    )

    with pytest.raises(PathTraversalError):
        apply_patch_impl(git_repo, traversal_patch)


def test_get_git_diff_and_status(git_repo: Path):
    """Test inspecting git diff and repository status before and after modification."""
    # 1. Clean status
    status_clean = get_repository_status_impl(git_repo)
    assert status_clean["clean"] is True
    assert status_clean["branch"] == "main"
    assert len(status_clean["modified"]) == 0

    diff_clean = get_git_diff_impl(git_repo)
    assert diff_clean["has_changes"] is False
    assert diff_clean["diff"] == ""

    # 2. Modify a file
    (git_repo / "src" / "pricing.py").write_text("def modified(): pass\n", encoding="utf-8")

    # 3. Create an untracked file
    (git_repo / "notes.txt").write_text("untracked notes\n", encoding="utf-8")

    status_dirty = get_repository_status_impl(git_repo)
    assert status_dirty["clean"] is False
    assert "src/pricing.py" in status_dirty["modified"]
    assert "notes.txt" in status_dirty["untracked"]

    diff_dirty = get_git_diff_impl(git_repo)
    assert diff_dirty["has_changes"] is True
    assert "src/pricing.py" in diff_dirty["changed_files"]
    assert "-def calculate_discount" in diff_dirty["diff"]
    assert "+def modified(): pass" in diff_dirty["diff"]

    # Test scoped diff
    scoped = get_git_diff_impl(git_repo, path="README.md")
    assert scoped["has_changes"] is False
