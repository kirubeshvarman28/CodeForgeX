# CodeForgeX: System Architecture & Design Specification

CodeForgeX is a deterministic AI-agent software engineering evaluation environment and tool-calling execution harness built on the official **Model Context Protocol (MCP)** Python SDK v2.

---

## 1. High-Level Architectural Topology

```mermaid
flowchart TD
    subgraph ControlPlane["CLI & Orchestration Layer (Phase 11)"]
        CLI["scripts/run_evaluation.py"] --> Runner["EvaluationRunner"]
        CLI --> Loop["AgentExecutionLoop"]
    end

    subgraph AgentLayer["Agent & Planning Layer (Phase 7 & 8)"]
        Loop --> Planner["SystematicSWEPlanner / LLMPlanner"]
        Planner -->|AgentAction| Loop
        Loop -->|call_tool| MCPClient["MCPClient (Async stdio)"]
    end

    subgraph ProtocolBoundary["Model Context Protocol (MCP SDK v2)"]
        MCPClient <==>|Anonymous OS Pipes (stdio JSON-RPC)| MCPServer["MCPServer (Subprocess)"]
    end

    subgraph ToolSurface["Sandboxed Tool Surface (Phase 1 - 4)"]
        MCPServer --> T1["list_files"]
        MCPServer --> T2["read_file"]
        MCPServer --> T3["search_code"]
        MCPServer --> T4["apply_patch"]
        MCPServer --> T5["get_git_diff"]
        MCPServer --> T6["run_tests"]
        MCPServer --> T7["get_test_output"]
        MCPServer --> T8["get_repository_status"]
    end

    subgraph SecuritySandbox["Security & Anti-Cheat Boundary (Phase 4)"]
        T1 & T2 & T3 & T4 & T5 & T6 & T7 & T8 --> Policy["SecurityPolicy Engine"]
        Policy --> Containment["Path Traversal Containment (resolve_safe_path)"]
        Policy --> AntiCheat["Anti-Cheat Protection (is_protected_resource)"]
        Policy --> CmdWhitelisting["Command Whitelisting & Injection Defense"]
        Policy --> Limits["Resource Quotas (File size & Patch limits)"]
    end

    subgraph TaskEnvironment["Task Sandboxes & Benchmarks (Phase 5 & 9)"]
        Containment --> TargetRepo["Ephemeral Task Workspace (.git)"]
        TasksDir["tasks/ (6 Benchmarks)"] --> WorkspaceManager["WorkspaceManager"]
        WorkspaceManager -->|Clone & Init| TargetRepo
    end

    subgraph VerificationEngine["Deterministic Evaluator (Phase 6)"]
        TargetRepo --> Verifier["TaskVerifier"]
        TasksDir -->|Hidden Tests| Verifier
        Verifier --> ShaCheck["SHA-256 Digest Tamper Check"]
        Verifier --> PublicRun["Public Test Execution"]
        Verifier --> HiddenRun["Privileged Hidden Test Execution"]
        Verifier --> DiffAnalysis["Git Diff & Line Metrics"]
        ShaCheck & PublicRun & HiddenRun & DiffAnalysis --> ScoringEngine["ScoringEngine (100 Pt Model)"]
        ScoringEngine --> Metrics["Structured EvaluationMetrics"]
        Metrics --> Reports["JSON & Markdown Artifacts (results/)"]
    end
```

---

## 2. Subsystem Deep-Dives

### 2.1 Model Context Protocol Server (`src/mcp_server/`)
- **Transport**: Communicates strictly over standard input/output (`stdio`) using JSON-RPC 2.0 framed messages. `stdio` eliminates TCP port exhaustion, race conditions in concurrent execution, and external network attack surfaces.
- **SDK**: Built on the official `mcp.server.mcpserver.MCPServer` (Python MCP SDK v2).
- **Tool Suite**:
  - `list_files`: Recursive and non-recursive directory exploration with depth bounding.
  - `read_file`: Line-windowed file inspection with automatic binary file detection and CRLF $\rightarrow$ LF normalization.
  - `search_code`: Scoped literal substring and regular expression search across worktree files.
  - `run_tests`: Subprocess argument vector execution (`pytest`) with hard timeout watchdogs and structured metrics parsing.
  - `get_test_output`: In-memory retrieval of historical test execution logs.
  - `apply_patch`: Two-phase atomic patch application (`git apply --check` dry-run validation before disk writes).
  - `get_git_diff`: Deterministic inspection of staged/unstaged unified diffs.
  - `get_repository_status`: Machine-readable worktree status parsing via `git status --porcelain=v1`.

### 2.2 Security Containment Sandbox (`src/mcp_server/security/`)
The sandbox enforces multi-layer defense-in-depth:
1. **Path Traversal Defense**: All relative paths are resolved against the bounded repository root via `resolve_safe_path()`. Symbolic link loops and `..` directory traversal attempts outside the root raise `PathTraversalError`.
2. **Anti-Cheat Resource Guard**: Protects hidden verification files (`*_hidden.py`, `solution/`, `.git`) from being inspected, listed, or patched by the agent via `is_protected_resource()`.
3. **Command Whitelisting**: Subprocess executions are restricted to whitelisted binary vectors (`python`, `pytest`, `git`) without `shell=True`, neutralizing shell metacharacter injections (`;`, `&&`, `|`, `` ` ``).
4. **Quota Guards**: Hard caps on maximum read buffer size (1 MB) and maximum patch payload size (500 KB).

### 2.3 Task Management & Workspace Sandboxing (`src/tasks/`)
- **Task Schema (`src/tasks/schema.py`)**: Strict Pydantic v2 schemas validating task IDs, difficulty levels (`easy`, `medium`, `hard`), categories (`bug_fix`, `feature`, `refactor`, `performance`, `algorithm`), and test targets.
- **Lifecycle Isolation (`src/tasks/manager.py`)**: `WorkspaceManager` copies the immutable `repository/` template into an ephemeral folder, executes a clean `git init -b main`, and ensures that no `.git` history or hidden verification tests are present inside the agent's worktree.

### 2.4 Deterministic Evaluation & Multi-Dimensional Scoring (`src/evaluator/`)
Unlike subjective "LLM-as-a-judge" grading, CodeForgeX scores solutions deterministically based on objective execution metrics:

$$\text{Total Score} = S_{\text{completion}} + S_{\text{hidden}} + S_{\text{public}} + S_{\text{regression}} + S_{\text{efficiency}} + S_{\text{patch}}$$

- **Task Completion (40 pts)**: Binary gate awarded when all public and hidden test suites pass.
- **Hidden Test Ratio (25 pts)**: Proportional score based on unseen verification tests.
- **Public Test Ratio (15 pts)**: Proportional score based on baseline public test cases.
- **Regression Safety (10 pts)**: Penalized by 5 points for every previously passing test that breaks.
- **Tool Efficiency (5 pts)**: Penalized by 1 point per failed tool invocation (rewards efficient planning).
- **Patch Quality (5 pts)**: Rewards concise, minimal unified diffs over bloated multi-file edits.
- **Anti-Tampering Disqualification**: `TaskVerifier` computes cryptographic SHA-256 hashes of all public test files before evaluation. If an agent modifies, comments out, or deletes public tests, `test_tampering_detected=True` is triggered and the total score is immediately forced to **`0.0`**.

### 2.5 MCP Client & Autonomous Agent Loop (`src/agent/`)
- **Async MCP Client (`src/agent/client.py`)**: Manages the subprocess lifecycle of `mcp_server` using `AsyncExitStack`. Implements multi-provider schema reflection:
  - `.to_openai_tool()`
  - `.to_anthropic_tool()`
  - `.to_gemini_declaration()`
- **Software Engineering Planning (`src/agent/planner.py`)**:
  - Implements the 6-stage SWE workflow: `EXPLORE` $\rightarrow$ `REPRODUCE` $\rightarrow$ `ANALYZE` $\rightarrow$ `PATCH` $\rightarrow$ `VERIFY` $\rightarrow$ `FINISH`.
  - `SystematicSWEPlanner`: Rule-based deterministic planning engine for reproducible baseline evaluation.
  - `LLMPlanner`: Asynchronous LLM planner supporting OpenAI, Claude, Gemini, or local models.
- **ReAct Execution Loop (`src/agent/loop.py`)**:
  - Manages iteration budgets (`max_iterations`).
  - Implements a consecutive failure **circuit breaker** (`max_consecutive_failures`) to prevent runaway token expenditure when tools fail repeatedly.
  - Automatically extracts final working tree diffs via `get_git_diff` directly from Git.

### 2.6 Docker Containerization (`Dockerfile`, `docker-compose.yml`)
- **Non-Root Execution**: Runs under unprivileged user `codeforge` (`uid=1000`, `gid=1000`).
- **Capability Dropping**: `cap_drop: [ALL]` strips all Linux kernel capabilities.
- **Privilege Lockdown**: `security_opt: [no-new-privileges:true]` blocks privilege escalation.
- **In-Memory Sandboxes**: Binds `/app/scratch` to RAM-backed `tmpfs`, ensuring sub-millisecond clone times and automatic kernel cleanup upon task completion.
- **Resource Constraints**: Capped at 2.0 CPU cores and 2048 MB RAM.

---

## 3. Benchmark Task Catalog

| Task ID | Category | Difficulty | Domain | Baseline Defect |
| :--- | :--- | :--- | :--- | :--- |
| **`bug_fix_001`** | `bug_fix` | Easy | Pricing Engine | Flat rate subtraction instead of % calculation; missing range check. |
| **`bug_fix_002`** | `bug_fix` | Medium | Concurrent LRU Cache | Expired TTL nodes not deleted on access; evicts MRU instead of LRU. |
| **`feature_001`** | `feature` | Medium | Rate Limiter | Missing thread-safe Token Bucket implementation with burst capacity. |
| **`refactor_001`** | `refactor` | Medium | Request Dispatcher | Monolithic `if/elif/else` router refactored to Strategy/Registry pattern. |
| **`perf_001`** | `performance`| Medium | Log Deduplicator | $O(N \times W)$ quadratic nested search optimized to $O(N)$ sliding window. |
| **`algo_001`** | `algorithm` | Medium | Build Dependency Sorter | Topological sorter using Kahn's min-heap with DFS cycle path detection. |
