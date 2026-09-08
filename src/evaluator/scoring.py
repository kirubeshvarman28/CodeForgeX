"""Deterministic scoring engine for evaluating agent performance.

Computes weighted multi-factor scores based on public tests, hidden tests,
regression safety, tool efficiency, patch quality, and anti-tampering guards.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from evaluator.metrics import EvaluationMetrics


@dataclass
class ScoringWeights:
    """Configurable weights for multi-factor evaluation scoring."""
    task_completion_weight: float = 40.0
    hidden_tests_weight: float = 25.0
    public_tests_weight: float = 15.0
    regression_safety_weight: float = 10.0
    tool_efficiency_weight: float = 5.0
    patch_quality_weight: float = 5.0

    def total_weight(self) -> float:
        return (
            self.task_completion_weight
            + self.hidden_tests_weight
            + self.public_tests_weight
            + self.regression_safety_weight
            + self.tool_efficiency_weight
            + self.patch_quality_weight
        )


DEFAULT_SCORING_WEIGHTS = ScoringWeights()


class ScoringEngine:
    """Computes deterministic scores and breakdowns from evaluation metrics."""

    def __init__(self, weights: Optional[ScoringWeights] = None):
        self.weights = weights if weights is not None else DEFAULT_SCORING_WEIGHTS

    def calculate_score(
        self,
        metrics: EvaluationMetrics,
    ) -> Tuple[float, Dict[str, float]]:
        """Calculate weighted score and detailed component breakdown.

        Args:
            metrics: Recorded evaluation metrics.

        Returns:
            Tuple of (total_score, breakdown_dict).
        """
        breakdown: Dict[str, float] = {}

        # Anti-tampering check: modifying test suites to fake pass results drops score to 0
        if metrics.test_tampering_detected:
            breakdown["anti_tampering_penalty"] = 0.0
            breakdown["task_completion"] = 0.0
            breakdown["public_tests"] = 0.0
            breakdown["hidden_tests"] = 0.0
            breakdown["regression_safety"] = 0.0
            breakdown["tool_efficiency"] = 0.0
            breakdown["patch_quality"] = 0.0
            return 0.0, breakdown

        # 1. Public tests
        if metrics.public_tests_total > 0:
            pub_ratio = metrics.public_tests_passed / metrics.public_tests_total
            breakdown["public_tests"] = round(pub_ratio * self.weights.public_tests_weight, 2)
        else:
            breakdown["public_tests"] = self.weights.public_tests_weight

        # 2. Hidden verification tests
        if metrics.hidden_tests_total > 0:
            hid_ratio = metrics.hidden_tests_passed / metrics.hidden_tests_total
            breakdown["hidden_tests"] = round(hid_ratio * self.weights.hidden_tests_weight, 2)
        else:
            breakdown["hidden_tests"] = self.weights.hidden_tests_weight

        # 3. Overall task completion (all public + hidden tests passing and patch valid)
        all_public_pass = (metrics.public_tests_passed == metrics.public_tests_total) and metrics.public_tests_total > 0
        all_hidden_pass = (metrics.hidden_tests_passed == metrics.hidden_tests_total) and metrics.hidden_tests_total > 0
        is_complete = all_public_pass and all_hidden_pass and metrics.patch_valid

        breakdown["task_completion"] = self.weights.task_completion_weight if is_complete else 0.0

        # 4. Regression safety
        if metrics.regressions_detected == 0:
            breakdown["regression_safety"] = self.weights.regression_safety_weight
        else:
            # Deduct points per regression
            reg_penalty = metrics.regressions_detected * 5.0
            breakdown["regression_safety"] = max(0.0, self.weights.regression_safety_weight - reg_penalty)

        # 5. Tool efficiency (penalize excessive failed tool calls)
        tool_score = self.weights.tool_efficiency_weight
        if metrics.failed_tool_calls > 0:
            tool_score = max(0.0, tool_score - (metrics.failed_tool_calls * 1.0))
        breakdown["tool_efficiency"] = round(tool_score, 2)

        # 6. Patch quality (conciseness and validity)
        if not metrics.patch_valid:
            breakdown["patch_quality"] = 0.0
        else:
            patch_score = self.weights.patch_quality_weight
            # Penalize absurdly bloated patches (e.g. > 150 lines modified for a small fix)
            total_lines_changed = metrics.patch_lines_added + metrics.patch_lines_deleted
            if total_lines_changed > 150:
                patch_score = max(1.0, patch_score - 2.0)
            breakdown["patch_quality"] = round(patch_score, 2)

        total_score = round(sum(breakdown.values()), 1)
        total_score = max(0.0, min(100.0, total_score))

        return total_score, breakdown
