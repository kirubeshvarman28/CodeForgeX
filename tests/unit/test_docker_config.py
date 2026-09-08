"""Unit tests for Dockerfile, .dockerignore, and Docker Compose configurations."""

import subprocess
import sys
from pathlib import Path

import pytest


def test_dockerfile_security_and_standards():
    """Verify Dockerfile enforces non-root execution, healthchecks, and dependency caching."""
    dockerfile = Path("Dockerfile")
    assert dockerfile.exists()

    content = dockerfile.read_text(encoding="utf-8")

    # Security: Non-root user
    assert "USER codeforge" in content
    assert "groupadd -g 1000 codeforge" in content
    assert "useradd -u 1000 -g codeforge" in content

    # Cleanliness: Base image and apt clean
    assert "FROM python:" in content
    assert "apt-get update" in content
    assert "rm -rf /var/lib/apt/lists/*" in content

    # Determinism: Environment flags
    assert "PYTHONUNBUFFERED=1" in content
    assert "PYTHONDONTWRITEBYTECODE=1" in content
    assert "PYTHONPATH=" in content and "/app/src" in content

    # Healthcheck
    assert "HEALTHCHECK" in content
    assert "import mcp_server" in content

    # Entrypoint
    assert 'ENTRYPOINT ["python", "scripts/docker_entrypoint.py"]' in content


def test_dockerignore_exclusions():
    """Verify .dockerignore excludes virtual environments, git repositories, and caches."""
    dockerignore = Path(".dockerignore")
    assert dockerignore.exists()

    content = dockerignore.read_text(encoding="utf-8")
    ignored_patterns = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]

    expected_exclusions = {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        "scratch/",
        ".env",
    }
    for expected in expected_exclusions:
        assert any(expected in pat for pat in ignored_patterns), f"Missing exclusion for {expected}"


def test_docker_compose_configuration():
    """Verify docker-compose.yml defines services with strict security and resource caps."""
    compose_file = Path("docker-compose.yml")
    assert compose_file.exists()

    content = compose_file.read_text(encoding="utf-8")

    # Required services
    assert "codeforge-eval:" in content
    assert "codeforge-test:" in content
    assert "mcp-server:" in content

    # Security hardening directives
    assert "no-new-privileges:true" in content
    assert "cap_drop:" in content
    assert "- ALL" in content

    # Ephemeral in-memory scratch storage
    assert "tmpfs:" in content
    assert "/app/scratch" in content

    # Resource caps
    assert "memory: 2048M" in content
    assert 'cpus: "2.0"' in content


def test_docker_entrypoint_cli_help():
    """Verify docker_entrypoint.py displays available execution modes cleanly."""
    entrypoint_script = Path("scripts/docker_entrypoint.py")
    assert entrypoint_script.exists()

    proc = subprocess.run(
        [sys.executable, str(entrypoint_script), "--help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "--test" in proc.stdout
    assert "--evaluate" in proc.stdout
    assert "--evaluate-all" in proc.stdout
    assert "--server" in proc.stdout
