"""Log deduplication module."""

from typing import List


def deduplicate_logs(entries: List[str], window_size: int = 100) -> List[str]:
    """Filter out duplicate log messages occurring within window_size entries.

    Args:
        entries: Ordered list of incoming log message strings.
        window_size: Number of preceding retained entries to check against.

    Returns:
        List of log entries with window duplicates eliminated.
    """
    if window_size <= 0:
        return list(entries)

    result: List[str] = []

    # NAIVE O(N * W) quadratic implementation
    for entry in entries:
        start_idx = max(0, len(result) - window_size)
        recent_window = result[start_idx:]

        # O(W) linear scan
        if entry not in recent_window:
            result.append(entry)

    return result
