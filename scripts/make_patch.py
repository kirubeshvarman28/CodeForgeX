"""Helper script to generate clean git patches for benchmark tasks."""

import subprocess
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path("src").resolve()))
from tasks.manager import WorkspaceManager

def create_patch_for_task(task_id: str, fixed_files: dict[str, str]):
    manager = WorkspaceManager(Path("scratch/make_patch_ws"))
    ws = manager.setup_task_workspace(task_id, tasks_root=Path("tasks"))
    
    for rel_path, content in fixed_files.items():
        target = ws / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and "\r\n" in target.read_text(encoding="utf-8"):
            content = content.replace("\r\n", "\n").replace("\n", "\r\n")
        else:
            content = content.replace("\r\n", "\n")
        target.write_text(content, encoding="utf-8")
        
    p = subprocess.run(["git", "diff"], cwd=str(ws), capture_output=True, text=True)
    diff = p.stdout.replace("\r\n", "\n")
    
    out_file = Path(f"tasks/{task_id}/solution/expected.patch")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(diff, encoding="utf-8")
    print(f"[{task_id}] Successfully generated patch: {len(diff.splitlines())} lines.")
    manager.cleanup_task_workspace(task_id)

if __name__ == "__main__":
    task_id = sys.argv[1]
    if task_id == "feature_001":
        manager = WorkspaceManager(Path("scratch/make_patch_ws"))
        ws = manager.setup_task_workspace(task_id, tasks_root=Path("tasks"))
        orig_text = (ws / "src" / "rate_limiter.py").read_text(encoding="utf-8").replace("\r\n", "\n")
        
        # Replace initialization
        t1 = "        self._lock = threading.Lock()\n        # TODO: Implement token bucket tracking and replenishment"
        r1 = """        self._lock = threading.Lock()
        self._tokens = float(capacity)
        self._last_replenish_time = self.time_func()

    def _replenish(self) -> None:
        now = self.time_func()
        elapsed = now - self._last_replenish_time
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._last_replenish_time = now"""
        
        # Replace acquire
        t2 = '        raise NotImplementedError("TokenBucketRateLimiter.acquire is not implemented yet.")'
        r2 = """        if tokens <= 0:
            raise ValueError("Tokens must be positive.")
        with self._lock:
            self._replenish()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False"""
            
        # Replace try_acquire
        t3 = '        raise NotImplementedError("TokenBucketRateLimiter.try_acquire is not implemented yet.")'
        r3 = """        if tokens <= 0:
            raise ValueError("Tokens must be positive.")
        deadline = self.time_func() + max(0.0, max_wait_seconds)
        while True:
            with self._lock:
                self._replenish()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                missing = tokens - self._tokens
                wait_needed = missing / self.rate
                if (deadline - self.time_func()) < wait_needed:
                    return False
            time.sleep(min(wait_needed, 0.05))"""
            
        # Replace available_tokens
        t4 = '        raise NotImplementedError("TokenBucketRateLimiter.available_tokens is not implemented yet.")'
        r4 = """        with self._lock:
            self._replenish()
            return self._tokens"""
            
        fixed_text = orig_text.replace(t1, r1).replace(t2, r2).replace(t3, r3).replace(t4, r4)
        create_patch_for_task("feature_001", {"src/rate_limiter.py": fixed_text})
            
    elif task_id == "bug_fix_002":
        manager = WorkspaceManager(Path("scratch/make_patch_ws"))
        ws = manager.setup_task_workspace(task_id, tasks_root=Path("tasks"))
        orig_text = (ws / "src" / "lru_cache.py").read_text(encoding="utf-8").replace("\r\n", "\n")
        
        # Fix 1: TTL purge on get
        t1 = """            # Check TTL expiration
            if node.expiry is not None and self.time_func() > node.expiry:
                # BUG 1: Does not purge the expired node from dictionary or linked list
                return None"""
        r1 = """            # Check TTL expiration
            if node.expiry is not None and self.time_func() > node.expiry:
                self._remove_node(node)
                if key in self.cache:
                    del self.cache[key]
                return None"""
                
        # Fix 2: LRU eviction from tail.prev
        t2 = """            # Check capacity eviction
            if len(self.cache) >= self.capacity:
                # BUG 2: Evicts self.head.next (MRU) instead of self.tail.prev (LRU)!
                lru_node = self.head.next
                if lru_node and lru_node != self.tail:
                    self._remove_node(lru_node)
                    if lru_node.key in self.cache:
                        del self.cache[lru_node.key]"""
        r2 = """            # Check capacity eviction
            if len(self.cache) >= self.capacity:
                lru_node = self.tail.prev
                if lru_node and lru_node != self.head:
                    self._remove_node(lru_node)
                    if lru_node.key in self.cache:
                        del self.cache[lru_node.key]"""
                        
        fixed_text = orig_text.replace(t1, r1).replace(t2, r2)
        create_patch_for_task("bug_fix_002", {"src/lru_cache.py": fixed_text})
        
    elif task_id == "refactor_001":
        fixed_code = '''"""Request Dispatcher module with Strategy Pattern."""

from abc import ABC, abstractmethod
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs


class UnsupportedContentTypeError(Exception):
    """Raised when a request specifies an unsupported Content-Type."""
    pass


@dataclass
class Request:
    """Incoming HTTP-like request model."""
    path: str
    content_type: str
    body: str = ""
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class Response:
    """Dispatched response model."""
    status_code: int
    content_type: str
    body: Any


class BaseRequestHandler(ABC):
    """Abstract strategy for handling specific request types."""

    @abstractmethod
    def can_handle(self, request: Request) -> bool:
        """Return True if this handler can process the given request."""
        raise NotImplementedError

    @abstractmethod
    def handle(self, request: Request) -> Response:
        """Process the request and return a structured Response."""
        raise NotImplementedError


class JsonRequestHandler(BaseRequestHandler):
    def can_handle(self, request: Request) -> bool:
        return (request.content_type or "").lower().strip() == "application/json"

    def handle(self, request: Request) -> Response:
        try:
            parsed = json.loads(request.body) if request.body else {}
            return Response(status_code=200, content_type="application/json", body=parsed)
        except Exception as e:
            return Response(status_code=400, content_type="application/json", body={"error": str(e)})


class XmlRequestHandler(BaseRequestHandler):
    def can_handle(self, request: Request) -> bool:
        ct = (request.content_type or "").lower().strip()
        return ct in ("application/xml", "text/xml")

    def handle(self, request: Request) -> Response:
        try:
            root = ET.fromstring(request.body) if request.body else ET.Element("empty")
            return Response(status_code=200, content_type="application/xml", body=root.tag)
        except Exception as e:
            return Response(status_code=400, content_type="application/xml", body=f"XML Error: {e}")


class FormRequestHandler(BaseRequestHandler):
    def can_handle(self, request: Request) -> bool:
        return (request.content_type or "").lower().strip() == "application/x-www-form-urlencoded"

    def handle(self, request: Request) -> Response:
        parsed = parse_qs(request.body)
        flattened = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
        return Response(status_code=200, content_type="application/json", body=flattened)


class RequestDispatcher:
    """Pluggable request dispatcher using the Strategy Pattern."""

    def __init__(self, handlers: Optional[List[BaseRequestHandler]] = None) -> None:
        if handlers is not None:
            self._handlers = list(handlers)
        else:
            self._handlers = [
                JsonRequestHandler(),
                XmlRequestHandler(),
                FormRequestHandler(),
            ]

    def register_handler(self, handler: BaseRequestHandler, prepend: bool = False) -> None:
        """Register a new strategy handler."""
        if prepend:
            self._handlers.insert(0, handler)
        else:
            self._handlers.append(handler)

    def dispatch(self, request: Request) -> Response:
        """Process incoming request through registered strategy handlers."""
        for handler in self._handlers:
            if handler.can_handle(request):
                return handler.handle(request)

        raise UnsupportedContentTypeError(f"Unsupported content type: '{request.content_type}'")
'''
        create_patch_for_task("refactor_001", {"src/dispatcher.py": fixed_code})
        
    elif task_id == "perf_001":
        fixed_code = '''"""Log deduplication module."""

from collections import deque
from typing import List


def deduplicate_logs(entries: List[str], window_size: int = 100) -> List[str]:
    """Filter out duplicate log messages occurring within window_size entries.

    Args:
        entries: Ordered list of incoming log message strings.
        window_size: Number of preceding retained entries to check against.

    Returns:
        List of log entries with window duplicates eliminated in O(N) time.
    """
    if window_size <= 0:
        return list(entries)

    result: List[str] = []
    active_window: deque[str] = deque()
    active_set = set()

    for entry in entries:
        if entry not in active_set:
            result.append(entry)
            active_window.append(entry)
            active_set.add(entry)

            if len(active_window) > window_size:
                oldest = active_window.popleft()
                active_set.remove(oldest)

    return result
'''
        create_patch_for_task("perf_001", {"src/log_dedup.py": fixed_code})
        
    elif task_id == "algo_001":
        fixed_code = '''"""Dependency resolution and topological sorting module."""

import heapq
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
        all_nodes = set(graph.keys())
        for deps in graph.values():
            all_nodes.update(deps)

        in_degree = {node: 0 for node in all_nodes}
        dependents: Dict[str, List[str]] = {node: [] for node in all_nodes}

        for pkg, deps in graph.items():
            unique_deps = set(deps)
            in_degree[pkg] = len(unique_deps)
            for dep in unique_deps:
                dependents[dep].append(pkg)

        ready_heap = [node for node, deg in in_degree.items() if deg == 0]
        heapq.heapify(ready_heap)

        build_order: List[str] = []

        while ready_heap:
            current = heapq.heappop(ready_heap)
            build_order.append(current)

            for dependent in dependents[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    heapq.heappush(ready_heap, dependent)

        if len(build_order) < len(all_nodes):
            remaining = {node for node, deg in in_degree.items() if deg > 0}
            cycle_path = self._find_cycle(graph, remaining)
            raise CircularDependencyError(
                f"Circular dependency detected: {' -> '.join(cycle_path)}",
                cycle_path=cycle_path,
            )

        return build_order

    def _find_cycle(self, graph: Dict[str, List[str]], remaining: set) -> List[str]:
        visited: Dict[str, int] = {}
        cycle_path: List[str] = []

        def dfs(u: str, path: List[str]) -> None:
            nonlocal cycle_path
            if cycle_path:
                return
            visited[u] = 1
            path.append(u)

            for v in graph.get(u, []):
                if v in remaining:
                    if visited.get(v, 0) == 1:
                        idx = path.index(v)
                        cycle_path = path[idx:] + [v]
                        return
                    elif visited.get(v, 0) == 0:
                        dfs(v, path)
                        if cycle_path:
                            return

            path.pop()
            visited[u] = 2

        for node in sorted(remaining):
            if visited.get(node, 0) == 0:
                dfs(node, [])
                if cycle_path:
                    break

        return cycle_path if cycle_path else list(remaining)
'''
        create_patch_for_task("algo_001", {"src/dep_resolver.py": fixed_code})
