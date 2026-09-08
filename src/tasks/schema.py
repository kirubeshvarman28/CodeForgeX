"""Task schema definitions for the benchmark environment.

Uses Pydantic v2 to validate task configuration, difficulty levels,
categories, and verification test targets.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class TaskCategory(str, Enum):
    """Supported task problem categories."""
    BUG_FIX = "bug_fix"
    FEATURE = "feature"
    REFACTOR = "refactor"
    PERFORMANCE = "performance"
    REGRESSION = "regression"
    ALGORITHM = "algorithm"


class TaskDifficulty(str, Enum):
    """Task complexity rating."""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class TaskDefinition(BaseModel):
    """Complete specification of a benchmark programming task."""
    task_id: str = Field(..., min_length=3, pattern=r"^[a-zA-Z0-9_-]+$")
    category: TaskCategory
    title: str = Field(..., min_length=5)
    description: str = Field(..., min_length=10)
    difficulty: TaskDifficulty = TaskDifficulty.EASY
    timeout_seconds: int = Field(default=300, ge=10, le=1800)
    public_test_targets: List[str] = Field(default_factory=list)
    hidden_test_targets: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        return v.strip()


class TaskMetadata(BaseModel):
    """Extended metadata for tracking task provenance and requirements."""
    author: Optional[str] = None
    version: str = "1.0.0"
    tags: List[str] = Field(default_factory=list)
    estimated_minutes: int = Field(default=15, ge=1)
