"""Hidden verification tests for TokenBucketRateLimiter."""

import concurrent.futures
import sys
import time
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest
from rate_limiter import TokenBucketRateLimiter


def test_capacity_saturation_guard():
    """Verify tokens never exceed max capacity regardless of elapsed idle time."""
    current_time = 0.0

    def mock_time():
        return current_time

    limiter = TokenBucketRateLimiter(rate=100.0, capacity=20.0, time_func=mock_time)
    current_time = 10000.0  # 10,000 seconds later
    assert limiter.available_tokens() == 20.0


def test_fractional_token_consumption():
    """Verify fractional token quantities are accurately tracked."""
    current_time = 0.0

    def mock_time():
        return current_time

    limiter = TokenBucketRateLimiter(rate=1.0, capacity=1.0, time_func=mock_time)
    assert limiter.acquire(0.25) is True
    assert pytest.approx(limiter.available_tokens(), 0.001) == 0.75
    assert limiter.acquire(0.5) is True
    assert pytest.approx(limiter.available_tokens(), 0.001) == 0.25
    assert limiter.acquire(0.3) is False  # not enough


def test_concurrent_multithreaded_acquisition():
    """Verify thread-safety when multiple worker threads hammer the limiter simultaneously."""
    rate = 1000.0
    capacity = 50.0
    limiter = TokenBucketRateLimiter(rate=rate, capacity=capacity)

    num_threads = 10
    requests_per_thread = 20
    successful_acquisitions = 0

    def worker():
        nonlocal successful_acquisitions
        acquired_count = 0
        for _ in range(requests_per_thread):
            if limiter.acquire(1.0):
                acquired_count += 1
        return acquired_count

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker) for _ in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            successful_acquisitions += f.result()

    # The total number acquired immediately should be at least capacity (50) but never exceed total requested
    assert 50 <= successful_acquisitions <= (num_threads * requests_per_thread)


def test_try_acquire_with_successful_wait():
    """Verify try_acquire actually waits and acquires when replenishment occurs within max_wait_seconds."""
    limiter = TokenBucketRateLimiter(rate=20.0, capacity=1.0)
    assert limiter.acquire(1.0) is True  # Bucket now empty

    start = time.monotonic()
    # At rate=20 tokens/sec, 1 token takes 0.05 seconds. Max wait is 0.2 seconds -> should succeed
    success = limiter.try_acquire(tokens=1.0, max_wait_seconds=0.2)
    elapsed = time.monotonic() - start

    assert success is True
    assert elapsed >= 0.03  # Must have actually waited
