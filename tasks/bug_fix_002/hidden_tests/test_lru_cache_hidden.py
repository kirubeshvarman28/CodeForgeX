"""Hidden verification tests for LRUCache."""

import concurrent.futures
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest
from lru_cache import LRUCache


def test_update_existing_key_refreshes_recency():
    """Verify updating existing key updates value and recency without evicting other keys."""
    cache = LRUCache(capacity=2)
    cache.put("x", 10)
    cache.put("y", 20)

    # Update 'x', making 'y' the LRU item
    cache.put("x", 100)

    # Insert 'z', should evict 'y'
    cache.put("z", 30)

    assert cache.get("x") == 100
    assert cache.get("z") == 30
    assert cache.get("y") is None


def test_mixed_ttl_and_lru_eviction():
    """Verify expired items do not prevent subsequent valid entries from being stored."""
    now = 0.0

    def mock_time():
        return now

    cache = LRUCache(capacity=2, time_func=mock_time)
    cache.put("item1", "A", ttl=5.0)
    cache.put("item2", "B", ttl=50.0)

    # Advance to 10s: item1 has expired
    now = 10.0
    assert cache.get("item1") is None
    assert cache.size() == 1

    # Insert two new items, which should fit
    cache.put("item3", "C")
    assert cache.size() == 2
    assert cache.get("item2") == "B"
    assert cache.get("item3") == "C"


def test_concurrent_access_thread_safety():
    """Verify concurrent reads and writes maintain cache invariants without deadlock."""
    cache = LRUCache(capacity=50)
    num_threads = 8
    ops_per_thread = 50

    def worker(tid: int):
        for i in range(ops_per_thread):
            key = f"key_{i % 10}"
            cache.put(key, f"val_{tid}_{i}", ttl=100.0)
            cache.get(key)
            cache.size()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, tid) for tid in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert cache.size() <= 50
