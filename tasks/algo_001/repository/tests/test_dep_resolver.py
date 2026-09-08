"""Public tests for DependencyResolver."""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest
from dep_resolver import CircularDependencyError, DependencyResolver


def test_linear_dependency_resolution():
    """Verify linear dependency chain builds from bottom up."""
    resolver = DependencyResolver()
    graph = {
        "app": ["service"],
        "service": ["database"],
        "database": [],
    }
    order = resolver.resolve_build_order(graph)
    assert order == ["database", "service", "app"]


def test_alphabetical_tie_breaking():
    """Verify nodes with zero remaining in-degree are processed alphabetically."""
    resolver = DependencyResolver()
    graph = {
        "zeta": [],
        "alpha": [],
        "beta": [],
    }
    order = resolver.resolve_build_order(graph)
    assert order == ["alpha", "beta", "zeta"]


def test_circular_dependency_error_raised():
    """Verify circular dependency raises CircularDependencyError with cycle path."""
    resolver = DependencyResolver()
    graph = {
        "pkg_a": ["pkg_b"],
        "pkg_b": ["pkg_a"],
    }
    with pytest.raises(CircularDependencyError) as exc_info:
        resolver.resolve_build_order(graph)

    err = exc_info.value
    assert len(err.cycle_path) >= 2
    assert "pkg_a" in err.cycle_path and "pkg_b" in err.cycle_path
