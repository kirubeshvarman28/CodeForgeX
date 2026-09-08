# Docker Reproducibility & Container Sandbox Environment

CodeForgeX uses Docker and OCI container isolation to guarantee **100% deterministic, hermetic, and safe** evaluation of untrusted AI-agent generated code.

---

## 1. Why Container Isolation is Essential

Evaluating software engineering agents requires executing arbitrary code, tests, and subprocess commands. Running untrusted code on a host machine exposes systems to:
- **Process Escapes & Host Mutation**: Agent code writing outside its designated folder.
- **Resource Exhaustion**: Memory leaks, infinite recursion, or fork bombs hanging host machines.
- **Environment Drift**: Inconsistent line endings (`CRLF` vs `LF`), missing system dependencies, or unpinned library versions producing flaky evaluation results.

CodeForgeX resolves this by executing benchmarks within a hardened, ephemeral container environment.

---

## 2. Container Security Architecture

```
                       Host Operating System
  ┌─────────────────────────────────────────────────────────────┐
  │  Docker / Containerd Daemon (Namespaces & cgroups v2)      │
  │                                                             │
  │  ┌───────────────────────────────────────────────────────┐  │
  │  │  CodeForgeX Container (UID: 1000 / codeforge)         │  │
  │  │  - cap_drop: [ALL]                                    │  │
  │  │  - security_opt: [no-new-privileges:true]             │  │
  │  │  - Memory Limit: 2048 MB (no swap)                   │  │
  │  │  - CPU Limit: 2.0 Cores                               │  │
  │  │                                                       │  │
  │  │  ┌────────────────────┐   ┌────────────────────────┐  │  │
  │  │  │  /app (Read-Only)  │   │  /tmp & /app/scratch   │  │  │
  │  │  │  Immutable Code    │   │  (Ephemeral tmpfs)     │  │  │
  │  │  └────────────────────┘   └────────────────────────┘  │  │
  │  └───────────────────────────────────────────────────────┘  │
  └─────────────────────────────────────────────────────────────┘
```

### Key Hardening Guarantees:
1. **Unprivileged Non-Root User**:
   - Runs as user `codeforge` (`uid=1000`, `gid=1000`). Root access is permanently dropped during image build.
2. **Capability Dropping**:
   - `cap_drop: [ALL]` removes all Linux kernel capabilities (e.g. `CAP_NET_ADMIN`, `CAP_SYS_ADMIN`, `CAP_CHOWN`), preventing privilege escalation even if a kernel vulnerability is attempted.
3. **No New Privileges**:
   - `no-new-privileges:true` prevents setuid binaries from gaining additional permissions at runtime.
4. **Ephemeral In-Memory Workspaces (`tmpfs`)**:
   - Sandboxes operate on RAM-backed `tmpfs` mounts (`/app/scratch` and `/tmp`). When the container exits or task concludes, all modified data is immediately purged by the OS kernel without leaving residual artifacts on host disks.
5. **Strict Cgroups Limits**:
   - Capped at 2.0 CPU cores and 2048 MB RAM to enforce fair benchmark timings and prevent resource starvation.

---

## 3. Quickstart Commands

### Building the Image
```bash
docker build -t codeforge-x:latest .
```

### Running the Full Regression Test Suite (82 Tests)
```bash
docker run --rm codeforge-x:latest --test
```

### Running Benchmark Evaluation Across All Tasks
```bash
docker run --rm codeforge-x:latest --evaluate-all
```

### Evaluating a Specific Benchmark Task
```bash
# Evaluate the token bucket rate limiter
docker run --rm codeforge-x:latest --evaluate feature_001

# Evaluate the topological sort dependency resolver
docker run --rm codeforge-x:latest --evaluate algo_001
```

### Starting the MCP Server Inside Docker
```bash
docker run -i --rm codeforge-x:latest --server
```

---

## 4. Docker Compose Orchestration

Use `docker compose` to run pre-configured, resource-constrained evaluation profiles:

```bash
# Run benchmark evaluation across all 6 tasks with 2GB memory cap
docker compose up codeforge-eval

# Run full unit & integration test suite in container
docker compose up codeforge-test
```
