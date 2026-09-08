"""Hidden verification tests for DependencyResolver."""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest
from dep_resolver import CircularDependencyError, DependencyResolver


def test_diamond_dependency_dag():
    """Verify diamond dependency ordering."""
    resolver = DependencyResolver()
    graph = {
        "app": ["cache", "db"],
        "cache": ["core"],
        "db": ["core"],
        "core": [],
    }
    order = resolver.resolve_build_order(graph)
    # 'core' must be first, 'cache' before 'db' (alphabetical), 'app' last
    assert order == ["core", "cache", "db", "app"]


def test_self_dependency_cycle():
    """Verify self-referencing package triggers cycle error."""
    resolver = DependencyResolver()
    graph = {"self_pkg": ["self_pkg"]}

    with pytest.raises(CircularDependencyError) as exc_info:
        resolver.resolve_build_order(graph)

    err = exc_info.value
    assert "self_pkg" in err.cycle_path


def test_multinode_indirect_cycle():
    """Verify 3-node cycle detection with leading linear dependency."""
    resolver = DependencyResolver()
    graph = {
        "root": ["node_1"],
        "node_1": ["node_2"],
        "node_2": ["node_3"],
        "node_3": ["node_1"],  # cycle between 1 -> 2 -> 3 -> 1
    }
    with pytest.raises(CircularDependencyError) as exc_info:
        resolver.resolve_build_order(graph)

    err = exc_info.value
    assert any(n in err.cycle_path for n in ["node_1", "node_2", "node_3"])


def test_disconnected_subgraphs_alphabetical():
    """Verify separate independent subgraphs maintain alphabetical order."""
    resolver = DependencyResolver()
    graph = {
        "z_child": ["z_parent"],
        "z_parent": [],
        "a_child": ["a_parent"],
        "a_parent": [],
    }
    order = resolver.resolve_build_order(graph)
    assert order == ["a_parent", "a_child", "z_parent", "z_child"]
