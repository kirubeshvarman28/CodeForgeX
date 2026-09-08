"""Hidden verification tests for log deduplication."""

import sys
import time
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest
from log_dedup import deduplicate_logs


def test_large_scale_stress():
    """Verify 50,000 entries process in under 0.40s."""
    entries = [f"event_{i % 2000}" for i in range(50000)]

    start = time.perf_counter()
    result = deduplicate_logs(entries, window_size=2500)
    duration = time.perf_counter() - start

    assert len(result) > 0
    assert duration < 0.40, f"Stress test exceeded 0.40s: {duration:.3f}s"


def test_window_size_one():
    """Verify window size 1 deduplicates only consecutive identical items."""
    logs = ["A", "A", "B", "B", "A", "C", "C", "C"]
    assert deduplicate_logs(logs, window_size=1) == ["A", "B", "A", "C"]


def test_all_identical_stream():
    """Verify stream of all identical items reduces to one item."""
    logs = ["ERROR"] * 1000
    assert deduplicate_logs(logs, window_size=100) == ["ERROR"]


def test_window_exceeding_stream_length():
    """Verify behavior when window size is larger than entire dataset."""
    logs = ["A", "B", "C", "A", "B", "D"]
    # Window size 100 means no duplicates of any previously seen item are admitted
    assert deduplicate_logs(logs, window_size=100) == ["A", "B", "C", "D"]
