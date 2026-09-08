"""Task loader module for discovering and parsing benchmark tasks.

Parses task definitions, metadata, and optional golden reference patches.
"""

import json
from pathlib import Path
from typing import Dict, Optional

from tasks.schema import TaskDefinition, TaskMetadata


def load_task_definition(task_dir: Path | str) -> TaskDefinition:
    """Load and validate task.json from a task directory.

    Args:
        task_dir: Path to the task folder.

    Returns:
        Validated TaskDefinition instance.

    Raises:
        FileNotFoundError: If task.json is missing.
        ValueError: If task.json is malformed or invalid according to schema.
    """
    path = Path(task_dir)
    config_file = path / "task.json"
    if not config_file.exists():
        raise FileNotFoundError(f"Missing task.json in task directory: {path}")

    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise ValueError(f"Failed to parse JSON in {config_file}: {err}")

    return TaskDefinition.model_validate(data)


def load_task_metadata(task_dir: Path | str) -> Optional[TaskMetadata]:
    """Load optional metadata.json from a task directory.

    Args:
        task_dir: Path to the task folder.

    Returns:
        TaskMetadata instance if present, None otherwise.
    """
    path = Path(task_dir)
    meta_file = path / "metadata.json"
    if not meta_file.exists():
        return None

    try:
        data = json.loads(meta_file.read_text(encoding="utf-8"))
        return TaskMetadata.model_validate(data)
    except Exception:
        return None


def load_task_solution(task_dir: Path | str) -> Optional[str]:
    """Load the golden reference patch from solution/expected.patch if present.

    Args:
        task_dir: Path to the task folder.

    Returns:
        Patch string if present, None otherwise.
    """
    path = Path(task_dir)
    candidates = [
        path / "solution" / "expected.patch",
        path / "solution.patch",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return None


def discover_tasks(tasks_root: Path | str) -> Dict[str, TaskDefinition]:
    """Discover all benchmark tasks present under the tasks directory.

    Args:
        tasks_root: Root directory containing task subdirectories.

    Returns:
        Mapping of task_id to TaskDefinition.
    """
    root = Path(tasks_root)
    if not root.exists():
        return {}

    tasks: Dict[str, TaskDefinition] = {}
    for entry in sorted(root.iterdir()):
        if entry.is_dir() and (entry / "task.json").exists():
            try:
                definition = load_task_definition(entry)
                tasks[definition.task_id] = definition
            except Exception:
                continue

    return tasks
