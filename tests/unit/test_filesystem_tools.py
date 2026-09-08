"""Unit tests for filesystem tools (list_files_impl and read_file_impl)."""

import pytest
from pathlib import Path
from mcp_server.security.sandbox import PathTraversalError
from mcp_server.tools.filesystem import list_files_impl, read_file_impl


@pytest.fixture
def dummy_repo(tmp_path: Path) -> Path:
    """Create a structured dummy repository for filesystem tool verification."""
    repo = tmp_path / "code_repo"
    repo.mkdir()

    # Create directory tree
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("line 1\nline 2\nline 3\nline 4\nline 5\n", encoding="utf-8")
    (repo / "src" / "utils.py").write_text("def helper(): pass\n", encoding="utf-8")

    (repo / "tests").mkdir()
    (repo / "tests" / "test_main.py").write_text("def test_one(): assert True\n", encoding="utf-8")

    # Ignored directory
    (repo / ".git").mkdir()
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    # Binary file
    (repo / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

    return repo


def test_list_files_recursive(dummy_repo: Path):
    """Test listing files recursively across repository."""
    result = list_files_impl(dummy_repo, directory="", recursive=True)

    assert result["total_entries"] > 0
    paths = [entry["path"] for entry in result["entries"]]

    # Verify normal files and directories are present
    assert "src" in paths
    assert "src/main.py" in paths
    assert "src/utils.py" in paths
    assert "tests" in paths
    assert "tests/test_main.py" in paths
    assert "image.png" in paths

    # Verify ignored directories are excluded
    assert not any(".git" in p for p in paths)


def test_list_files_non_recursive(dummy_repo: Path):
    """Test listing only top-level directory entries when recursive is False."""
    result = list_files_impl(dummy_repo, directory="", recursive=False)
    paths = [entry["path"] for entry in result["entries"]]

    assert "src" in paths
    assert "tests" in paths
    assert "image.png" in paths
    # Subdirectory contents should not be listed
    assert "src/main.py" not in paths


def test_list_files_invalid_dir(dummy_repo: Path):
    """Test error handling when listing non-existent directory or file."""
    with pytest.raises(FileNotFoundError):
        list_files_impl(dummy_repo, directory="non_existent")

    with pytest.raises(NotADirectoryError):
        list_files_impl(dummy_repo, directory="src/main.py")


def test_read_file_full_content(dummy_repo: Path):
    """Test reading entire file without line bounds."""
    result = read_file_impl(dummy_repo, "src/main.py")

    assert result["path"] == "src/main.py"
    assert result["total_lines"] == 5
    assert result["start_line"] == 1
    assert result["end_line"] == 5
    assert result["is_truncated"] is False
    assert result["content"] == "line 1\nline 2\nline 3\nline 4\nline 5\n"


def test_read_file_windowed(dummy_repo: Path):
    """Test reading specific line range from a file."""
    result = read_file_impl(dummy_repo, "src/main.py", start_line=2, end_line=4)

    assert result["start_line"] == 2
    assert result["end_line"] == 4
    assert result["content"] == "line 2\nline 3\nline 4\n"


def test_read_file_binary_detection(dummy_repo: Path):
    """Test graceful handling of binary files."""
    result = read_file_impl(dummy_repo, "image.png")

    assert result["is_binary"] is True
    assert "Binary file cannot be displayed" in result["content"]


def test_read_file_path_traversal_blocked(dummy_repo: Path):
    """Test that attempting to read files outside repo raises PathTraversalError."""
    with pytest.raises(PathTraversalError):
        read_file_impl(dummy_repo, "../secret.txt")
