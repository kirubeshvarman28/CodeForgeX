"""Unit tests for the security sandbox and safe path resolution."""

import pytest
from pathlib import Path
from mcp_server.security.sandbox import (
    PathTraversalError,
    is_ignored_path,
    resolve_safe_path,
)


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary dummy repository structure for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Create dummy files and folders
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print('hello')", encoding="utf-8")
    (repo / "README.md").write_text("# Test Repo", encoding="utf-8")

    # Create dummy ignored folders
    (repo / ".git").mkdir()
    (repo / ".git" / "config").write_text("dummy git config", encoding="utf-8")
    (repo / "__pycache__").mkdir()
    (repo / "__pycache__" / "app.cpython-314.pyc").write_bytes(b"\x00\x01\x02")

    return repo


def test_resolve_safe_path_valid_paths(temp_repo: Path):
    """Ensure valid relative paths resolve correctly to canonical paths inside root."""
    # Root itself
    root_resolved = resolve_safe_path(temp_repo, "")
    assert root_resolved == temp_repo.resolve()

    # Subdirectory
    src_resolved = resolve_safe_path(temp_repo, "src", must_exist=True)
    assert src_resolved == (temp_repo / "src").resolve()

    # File inside subdirectory
    app_resolved = resolve_safe_path(temp_repo, "src/app.py", must_exist=True)
    assert app_resolved == (temp_repo / "src" / "app.py").resolve()


def test_resolve_safe_path_blocks_directory_traversal(temp_repo: Path):
    """Ensure path traversal attacks with '..' are caught and blocked."""
    with pytest.raises(PathTraversalError):
        resolve_safe_path(temp_repo, "../outside.txt")

    with pytest.raises(PathTraversalError):
        resolve_safe_path(temp_repo, "src/../../outside.txt")

    with pytest.raises(PathTraversalError):
        resolve_safe_path(temp_repo, "../../..")


def test_resolve_safe_path_blocks_external_absolute_paths(temp_repo: Path):
    """Ensure external absolute paths are rejected with PathTraversalError."""
    external_dir = temp_repo.parent / "secret_dir"
    external_dir.mkdir(exist_ok=True)
    secret_file = external_dir / "secret.txt"
    secret_file.write_text("secret content", encoding="utf-8")

    with pytest.raises(PathTraversalError):
        resolve_safe_path(temp_repo, str(secret_file))


def test_resolve_safe_path_must_exist_flag(temp_repo: Path):
    """Ensure must_exist raises FileNotFoundError for missing files."""
    # must_exist=False should resolve safely
    candidate = resolve_safe_path(temp_repo, "src/non_existent.py", must_exist=False)
    assert candidate == (temp_repo / "src" / "non_existent.py").resolve()

    # must_exist=True should raise FileNotFoundError
    with pytest.raises(FileNotFoundError):
        resolve_safe_path(temp_repo, "src/non_existent.py", must_exist=True)


def test_is_ignored_path():
    """Ensure standard ignored directory patterns are identified."""
    assert is_ignored_path(".git")
    assert is_ignored_path("src/__pycache__/app.py")
    assert is_ignored_path(".venv/lib/python")
    assert is_ignored_path("dist/bundle.whl")
    assert not is_ignored_path("src/module.py")
    assert not is_ignored_path("tests/test_app.py")
