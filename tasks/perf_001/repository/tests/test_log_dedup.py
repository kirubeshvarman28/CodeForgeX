"""Public tests for log deduplication and performance."""

import sys
import time
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest
from log_dedup import deduplicate_logs


def test_basic_deduplication():
    """Verify duplicates within window are removed and outside window are retained."""
    logs = [
        "A",  # kept (window: [A])
        "B",  # kept (window: [A, B])
        "A",  # duplicate of A within window=2 -> DROPPED
        "C",  # kept (window: [A, B, C]) -> oldest falls out if window=2
        "A",  # A is now outside window of size 2 -> KEPT
    ]
    # Window size 2
    res = deduplicate_logs(logs, window_size=2)
    assert res == ["A", "B", "C", "A"]


def test_empty_and_zero_window():
    """Verify edge cases with empty lists and zero window size."""
    assert deduplicate_logs([], window_size=10) == []
    assert deduplicate_logs(["A", "A", "B"], window_size=0) == ["A", "A", "B"]


def test_performance_scale():
    """Performance requirement: 20,000 items with window 1,000 must finish in under 0.25s."""
    # Generate 20,000 logs with periodic patterns
    entries = [f"msg_{i % 500}" for i in range(20000)]

    start = time.perf_counter()
    res = deduplicate_logs(entries, window_size=1000)
    elapsed = time.perf_counter() - start

    assert len(res) > 0
    # Must complete in under 0.25 seconds (optimized version finishes in ~0.02s)
    assert elapsed < 0.25, f"Execution too slow: {elapsed:.3f}s (must be < 0.25s)"
