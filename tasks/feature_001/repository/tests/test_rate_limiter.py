"""Public tests for TokenBucketRateLimiter."""

import sys
from pathlib import Path

# Ensure src is in sys.path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest
from rate_limiter import TokenBucketRateLimiter


def test_rate_limiter_initialization():
    """Verify rate limiter initializes with full capacity."""
    limiter = TokenBucketRateLimiter(rate=5.0, capacity=10.0)
    assert limiter.available_tokens() == 10.0

    with pytest.raises(ValueError):
        TokenBucketRateLimiter(rate=0, capacity=10.0)

    with pytest.raises(ValueError):
        TokenBucketRateLimiter(rate=5.0, capacity=-1.0)


def test_rate_limiter_acquire_immediate():
    """Verify immediate consumption up to bucket capacity."""
    current_time = 100.0

    def mock_time():
        return current_time

    limiter = TokenBucketRateLimiter(rate=2.0, capacity=5.0, time_func=mock_time)
    assert limiter.acquire(3.0) is True
    assert limiter.available_tokens() == 2.0

    assert limiter.acquire(2.0) is True
    assert limiter.available_tokens() == 0.0

    # Bucket is empty, immediate acquire should fail
    assert limiter.acquire(1.0) is False


def test_rate_limiter_replenishment():
    """Verify tokens replenish proportionally to elapsed time."""
    current_time = 0.0

    def mock_time():
        return current_time

    limiter = TokenBucketRateLimiter(rate=10.0, capacity=10.0, time_func=mock_time)
    assert limiter.acquire(10.0) is True
    assert limiter.available_tokens() == 0.0

    # Advance 0.5 seconds -> 5 tokens replenished
    current_time = 0.5
    assert limiter.available_tokens() == 5.0
    assert limiter.acquire(4.0) is True
    assert limiter.available_tokens() == 1.0


def test_rate_limiter_try_acquire_timeout():
    """Verify try_acquire returns False if requested tokens exceed wait window."""
    current_time = 0.0

    def mock_time():
        return current_time

    limiter = TokenBucketRateLimiter(rate=1.0, capacity=1.0, time_func=mock_time)
    assert limiter.acquire(1.0) is True

    # Needs 1 token, which takes 1 second at rate=1.0. Max wait is 0.2s -> should fail
    assert limiter.try_acquire(tokens=1.0, max_wait_seconds=0.2) is False
