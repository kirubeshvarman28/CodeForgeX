# ==============================================================================
# CodeForgeX: Deterministic AI-Agent Evaluation & Sandbox Container
# Multi-stage security-hardened container runtime for untrusted code evaluation
# ==============================================================================

FROM python:3.11-slim AS base

LABEL maintainer="CodeForgeX Architecture Team" \
      description="Deterministic AI-agent evaluation environment and MCP tools" \
      version="0.1.0"

# Set non-interactive environment and deterministic flags
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/src"

# Install essential OS packages (git is required for patching and repository operations)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Configure global git identity for deterministic sandbox commits
RUN git config --global user.name "CodeForgeX Agent" && \
    git config --global user.email "agent@codeforgex.internal" && \
    git config --global init.defaultBranch main && \
    git config --global core.autocrlf false

# Create unprivileged sandbox user and group (UID/GID 1000)
RUN groupadd -g 1000 codeforge && \
    useradd -u 1000 -g codeforge -m -s /bin/bash codeforge

# Create virtual environment owned by unprivileged user
RUN python -m venv /opt/venv && \
    chown -R codeforge:codeforge /opt/venv

# Set up application workspace
WORKDIR /app

# Copy dependency configuration first to optimize Docker layer caching
COPY --chown=codeforge:codeforge pyproject.toml README.md ./

# Install project dependencies into virtual environment
RUN /opt/venv/bin/pip install --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install -e .

# Copy application sources, task definitions, and tests
COPY --chown=codeforge:codeforge src/ /app/src/
COPY --chown=codeforge:codeforge tasks/ /app/tasks/
COPY --chown=codeforge:codeforge tests/ /app/tests/
COPY --chown=codeforge:codeforge scripts/ /app/scripts/

# Create scratch directory for ephemeral sandboxes with correct ownership
RUN mkdir -p /app/scratch && \
    chown -R codeforge:codeforge /app/scratch

# Drop root privileges and switch to unprivileged user
USER codeforge

# Define healthcheck to verify core environment imports
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import mcp_server; import evaluator; import tasks; import agent; print('CodeForgeX healthy')" || exit 1

# Set container entrypoint
ENTRYPOINT ["python", "scripts/docker_entrypoint.py"]

# Default command runs full test suite
CMD ["--test"]
