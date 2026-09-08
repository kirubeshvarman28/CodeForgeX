"""Dependency resolution and topological sorting module."""

from typing import Dict, List, Optional


class CircularDependencyError(Exception):
    """Raised when a circular dependency is detected in the graph."""

    def __init__(self, message: str, cycle_path: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.cycle_path = cycle_path or []


class DependencyResolver:
    """Resolves linear build execution order from a package dependency graph."""

    def resolve_build_order(self, graph: Dict[str, List[str]]) -> List[str]:
        """Compute deterministic linear build order for the given dependency graph.

        Args:
            graph: Mapping of package name to list of required direct dependencies.
                   Example: {"web": ["auth", "db"], "auth": ["db"], "db": []}

        Returns:
            List of packages in valid build order (dependencies precede dependents).
            Ties are broken alphabetically.

        Raises:
            CircularDependencyError: If a dependency cycle is detected.
        """
        raise NotImplementedError("DependencyResolver.resolve_build_order is not implemented yet.")
