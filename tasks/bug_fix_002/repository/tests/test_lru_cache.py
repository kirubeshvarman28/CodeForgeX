"""Public tests for LRUCache."""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest
from lru_cache import LRUCache


def test_lru_cache_basic_put_get():
    """Verify basic key insertion and retrieval."""
    cache = LRUCache(capacity=3)
    cache.put("k1", "v1")
    cache.put("k2", "v2")

    assert cache.get("k1") == "v1"
    assert cache.get("k2") == "v2"
    assert cache.get("missing") is None


def test_lru_eviction_order():
    """Verify least recently used entry is evicted when capacity is reached."""
    cache = LRUCache(capacity=2)
    cache.put("a", 1)
    cache.put("b", 2)

    # Access 'a' so 'b' becomes the LRU item
    assert cache.get("a") == 1

    # Insert 'c', which should evict 'b' (not 'a')
    cache.put("c", 3)

    assert cache.get("a") == 1
    assert cache.get("c") == 3
    assert cache.get("b") is None  # Should have been evicted!


def test_ttl_expiration_and_cleanup():
    """Verify expired items return None and decrease size."""
    now = 100.0

    def mock_time():
        return now

    cache = LRUCache(capacity=2, time_func=mock_time)
    cache.put("temp", "value", ttl=10.0)

    assert cache.get("temp") == "value"
    assert cache.size() == 1

    # Advance time past TTL
    now = 115.0

    assert cache.get("temp") is None
    # Expired entry should be cleaned up immediately on access
    assert cache.size() == 0
