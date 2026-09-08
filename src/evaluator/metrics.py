"""Evaluation metrics and telemetry models.

Defines typed dataclasses for capturing deterministic evaluation results,
tool telemetry, test pass ratios, and score breakdowns.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class EvaluationMetrics:
    """Comprehensive metrics generated during task verification."""
    task_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    success: bool = False
    score: float = 0.0
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    
    # Test execution metrics
    public_tests_passed: int = 0
    public_tests_total: int = 0
    hidden_tests_passed: int = 0
    hidden_tests_total: int = 0
    regressions_detected: int = 0
    
    # Tool telemetry & efficiency
    tool_call_count: int = 0
    failed_tool_calls: int = 0
    iterations: int = 1
    duration_seconds: float = 0.0
    
    # Code & patch metrics
    patch_valid: bool = True
    patch_lines_added: int = 0
    patch_lines_deleted: int = 0
    files_modified: List[str] = field(default_factory=list)
    test_tampering_detected: bool = False
    
    # Detailed log traces
    failure_messages: List[str] = field(default_factory=list)
    summary_report: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary representation."""
        return asdict(self)
