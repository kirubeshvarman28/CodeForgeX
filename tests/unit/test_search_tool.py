"""Unit tests for the code search tool (search_code_impl)."""

import pytest
from pathlib import Path
from mcp_server.security.sandbox import PathTraversalError
from mcp_server.tools.search import search_code_impl


@pytest.fixture
def dummy_repo(tmp_path: Path) -> Path:
    """Create a structured dummy repository for search tool verification."""
    repo = tmp_path / "search_repo"
    repo.mkdir()

    (repo / "src").mkdir()
    (repo / "src" / "pricing.py").write_text(
        "def calculate_discount(price, rate):\n"
        "    # Apply discount rate\n"
        "    return price * (1 - rate)\n"
        "\n"
        "def get_final_price(price, discount):\n"
        "    return calculate_discount(price, discount)\n",
        encoding="utf-8",
    )

    (repo / "src" / "orders.py").write_text(
        "class OrderManager:\n"
        "    def create_order(self, order_id):\n"
        "        print(f'Creating order: {order_id}')\n",
        encoding="utf-8",
    )

    # Ignored directory
    (repo / ".git").mkdir()
    (repo / ".git" / "COMMIT_EDITMSG").write_text("calculate_discount in commit", encoding="utf-8")

    return repo


def test_search_code_literal_substring(dummy_repo: Path):
    """Test searching for a literal substring across codebase."""
    result = search_code_impl(dummy_repo, query="calculate_discount")

    assert result["total_matches"] == 2
    assert result["is_truncated"] is False

    match_lines = [m["line_number"] for m in result["matches"]]
    assert 1 in match_lines
    assert 6 in match_lines
    assert all(m["path"] == "src/pricing.py" for m in result["matches"])


def test_search_code_case_sensitivity(dummy_repo: Path):
    """Test case-insensitive (default) vs case-sensitive search."""
    # Case-insensitive matches "order" in OrderManager and create_order
    res_insensitive = search_code_impl(dummy_repo, query="order", case_sensitive=False)
    assert res_insensitive["total_matches"] >= 3

    # Case-sensitive matches only lowercase "order"
    res_sensitive = search_code_impl(dummy_repo, query="OrderManager", case_sensitive=True)
    assert res_sensitive["total_matches"] == 1
    assert res_sensitive["matches"][0]["line_number"] == 1


def test_search_code_regex(dummy_repo: Path):
    """Test regex pattern matching."""
    result = search_code_impl(dummy_repo, query=r"def\s+\w+\(", is_regex=True)

    # Functions: calculate_discount, get_final_price, create_order
    assert result["total_matches"] == 3
    paths = [m["path"] for m in result["matches"]]
    assert "src/pricing.py" in paths
    assert "src/orders.py" in paths


def test_search_code_scoped_path(dummy_repo: Path):
    """Test scoping search to a specific file or folder."""
    result = search_code_impl(dummy_repo, query="order", path="src/pricing.py")
    assert result["total_matches"] == 0

    result2 = search_code_impl(dummy_repo, query="order", path="src/orders.py")
    assert result2["total_matches"] > 0


def test_search_code_max_results(dummy_repo: Path):
    """Test truncation when max_results is reached."""
    result = search_code_impl(dummy_repo, query="def", max_results=1)

    assert result["total_matches"] == 1
    assert result["is_truncated"] is True


def test_search_code_invalid_regex(dummy_repo: Path):
    """Test invalid regex syntax error handling."""
    with pytest.raises(ValueError, match="Invalid regular expression"):
        search_code_impl(dummy_repo, query="[unclosed-bracket", is_regex=True)


def test_search_code_empty_query(dummy_repo: Path):
    """Test empty query raises ValueError."""
    with pytest.raises(ValueError, match="cannot be empty"):
        search_code_impl(dummy_repo, query="")


def test_search_code_path_traversal_blocked(dummy_repo: Path):
    """Test path traversal in search path argument is blocked."""
    with pytest.raises(PathTraversalError):
        search_code_impl(dummy_repo, query="test", path="../../outside")
