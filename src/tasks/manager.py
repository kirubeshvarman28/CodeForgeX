"""Workspace manager for instantiating isolated task execution environments.

Copies task repositories into pristine workspace sandboxes, initializes Git
histories, and guarantees baseline reproducibility.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from tasks.loader import load_task_definition
from tasks.schema import TaskDefinition


class WorkspaceManager:
    """Manages creation, initialization, and teardown of task execution sandboxes."""

    def __init__(self, workspace_root: Path | str):
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def setup_task_workspace(
        self,
        task_id: str,
        tasks_root: Path | str,
        clean: bool = True,
    ) -> Path:
        """Create a pristine sandbox environment for a specific task.

        Args:
            task_id: The identifier of the task to instantiate.
            tasks_root: Root directory containing task definitions.
            clean: If True, deletes existing workspace for this task before setup.

        Returns:
            Path to the initialized sandbox repository ready for MCP server bounded execution.

        Raises:
            FileNotFoundError: If the task or repository directory does not exist.
        """
        task_dir = Path(tasks_root).resolve() / task_id
        if not task_dir.exists():
            raise FileNotFoundError(f"Task directory '{task_dir}' does not exist.")

        repo_template = task_dir / "repository"
        if not repo_template.exists():
            raise FileNotFoundError(f"Missing repository template in '{repo_template}'.")

        target_workspace = (self.workspace_root / task_id).resolve()
        if target_workspace.exists() and clean:
            shutil.rmtree(target_workspace, ignore_errors=True)

        # Copy template repository into target workspace
        shutil.copytree(repo_template, target_workspace, dirs_exist_ok=True)

        # Initialize fresh Git repository
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=str(target_workspace),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Task Initializer"],
            cwd=str(target_workspace),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "evaluator@codeforgex.internal"],
            cwd=str(target_workspace),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "core.autocrlf", "false"],
            cwd=str(target_workspace),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=str(target_workspace),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"chore: initial baseline state for task {task_id}"],
            cwd=str(target_workspace),
            check=True,
            capture_output=True,
        )

        return target_workspace

    def cleanup_task_workspace(self, task_id: str) -> None:
        """Remove a task sandbox workspace completely, handling read-only git files."""
        target_workspace = self.workspace_root / task_id
        if not target_workspace.exists():
            return

        def _on_rm_error(func, path, exc_info):
            import os
            import stat
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception:
                pass

        try:
            shutil.rmtree(target_workspace, onexc=_on_rm_error)
        except TypeError:
            shutil.rmtree(target_workspace, onerror=_on_rm_error)
