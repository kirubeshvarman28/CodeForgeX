# CodeForgeX: Deterministic AI-Agent Evaluation Environment & MCP Software Engineering Harness

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP SDK v2](https://img.shields.io/badge/MCP%20SDK-v2.0-green.svg)](https://modelcontextprotocol.io/)
[![Tests Passing](https://img.shields.io/badge/tests-91%2F91%20passing-brightgreen.svg)](tests/)
[![Benchmark Score](https://img.shields.io/badge/benchmark%20score-99.0%2F100.0-gold.svg)](tasks/)
[![Docker Hardened](https://img.shields.io/badge/docker-non--root%20%7C%20cap__drop%20ALL-purple.svg)](Dockerfile)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**CodeForgeX** is an enterprise-grade, deterministic AI-agent software engineering evaluation environment and tool-calling execution harness. Built on the official **Model Context Protocol (MCP Python SDK v2)**, it provides an isolated, uncheatable sandbox where AI agents explore repositories, reproduce failures, formulate hypotheses, apply unified diff patches, and verify solutions against public and hidden test suites.

Unlike subjective "LLM-as-a-judge" grading, CodeForgeX employs **deterministic, multi-criteria verification** with cryptographic test tampering detection, regression guards, and wall-clock execution limits.

---

## Architecture Topology

```mermaid
flowchart TD
    subgraph ControlPlane["CLI & Orchestration (scripts/run_evaluation.py)"]
        CLI["CLI Runner"] --> Runner["EvaluationRunner"]
        CLI --> Loop["AgentExecutionLoop"]
    end

    subgraph AgentLayer["Autonomous Agent & Planning (src/agent/)"]
        Loop --> Planner["SystematicSWEPlanner / LLMPlanner"]
        Planner -->|AgentAction| Loop
        Loop -->|call_tool| Client["MCPClient (Async stdio)"]
    end

    subgraph ProtocolBoundary["Model Context Protocol Boundary"]
        Client <==>|Anonymous OS Pipes (stdio JSON-RPC)| Server["MCPServer (Subprocess)"]
    end

    subgraph ToolSurface["Sandboxed Tool Surface (src/mcp_server/)"]
        Server --> T1["list_files"]
        Server --> T2["read_file"]
        Server --> T3["search_code"]
        Server --> T4["apply_patch"]
        Server --> T5["get_git_diff"]
        Server --> T6["run_tests"]
        Server --> T7["get_test_output"]
        Server --> T8["get_repository_status"]
    end

    subgraph SecurityBoundary["Security & Anti-Cheat Sandbox (src/mcp_server/security/)"]
        T1 & T2 & T3 & T4 & T5 & T6 & T7 & T8 --> Sandbox["SecurityPolicy Engine"]
        Sandbox --> Guard1["Path Traversal Containment"]
        Sandbox --> Guard2["Anti-Cheat (Hidden Tests Isolated)"]
        Sandbox --> Guard3["Command Whitelisting & Injection Defense"]
    end

    subgraph TaskWorkspaces["Ephemeral Sandboxes (tasks/)"]
        Guard1 & Guard2 & Guard3 --> TargetRepo["Ephemeral Workspace (.git)"]
    end

    subgraph Evaluator["Deterministic Evaluator Engine (src/evaluator/)"]
        TargetRepo --> Verifier["TaskVerifier"]
        Verifier --> ShaCheck["SHA-256 Digest Tamper Check"]
        Verifier --> PublicRun["Public Test Execution"]
        Verifier --> HiddenRun["Privileged Hidden Test Suite"]
        Verifier --> DiffAnalysis["Git Diff & Line Metrics"]
        ShaCheck & PublicRun & HiddenRun & DiffAnalysis --> Scorer["ScoringEngine (100 Pt Model)"]
        Scorer --> Artifacts["Telemetry Artifacts (results/eval_*.json, .md)"]
    end
```

---

## Key System Capabilities

- **Official Model Context Protocol (SDK v2)**: Real-time tool discovery and execution over standard I/O (`stdio`), eliminating TCP port exhaustion and network race conditions.
- **Multi-Provider Schema Reflection**: Dynamic tool schema conversion supporting **OpenAI function calling**, **Anthropic Claude**, and **Google Gemini** function declarations.
- **Multi-Dimensional Scoring (0 - 100 Points)**:
  - Task Completion (40 pts)
  - Hidden Verification Tests (25 pts)
  - Public Baseline Tests (15 pts)
  - Regression Safety (10 pts)
  - Tool Efficiency & Token Conservation (5 pts)
  - Patch Conciseness & Quality (5 pts)
- **Anti-Cheat & Anti-Tampering Protection**: Dual-layer defense with cryptographic SHA-256 test file digest verification. Modifying or deleting test assertions forces an immediate **`0.0 / 100.0`** disqualification score.
- **Systematic SWE Reasoning Workflow**: Enforces Test-Driven Software Engineering: `EXPLORE` $\rightarrow$ `REPRODUCE` $\rightarrow$ `ANALYZE` $\rightarrow$ `PATCH` $\rightarrow$ `VERIFY` $\rightarrow$ `FINISH`.
- **Fault-Tolerant Circuit Breakers**: Active consecutive-failure guards prevent runaway token expenditure and model hallucination loops.
- **Hardened Docker Isolation**: Non-root user execution (`uid=1000`), `cap_drop: [ALL]`, `no-new-privileges:true`, and RAM-backed in-memory `tmpfs` mounts.
- **Unified Benchmark Dashboard**: Terminal dashboard with JSON and Markdown artifact generation.

---

## Benchmark Suite Catalog

CodeForgeX includes 6 diverse benchmark tasks spanning core software engineering modalities:

| Task ID | Category | Difficulty | Problem Domain | Baseline Defect | Golden Score |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`bug_fix_001`** | `bug_fix` | Easy | E-Commerce Pricing Engine | Flat rate subtraction instead of % calculation; no bound checks | **`100.0 / 100.0`** |
| **`bug_fix_002`** | `bug_fix` | Medium | Concurrent LRU Cache with TTL | Expired nodes not purged on access; evicts MRU instead of LRU | **`98.0 / 100.0`** |
| **`feature_001`** | `feature` | Medium | Thread-Safe Token Bucket Limiter | Class raises `NotImplementedError` across all methods | **`98.0 / 100.0`** |
| **`refactor_001`** | `refactor` | Medium | Request Dispatcher to Strategy | Monolithic `if/elif/else` router; lacks `BaseRequestHandler` registry | **`98.0 / 100.0`** |
| **`perf_001`** | `performance`| Medium | Log Stream Deduplication ($O(N^2) \rightarrow O(N)$) | $O(N \times W)$ quadratic nested search takes > 1.5s and times out | **`100.0 / 100.0`** |
| **`algo_001`** | `algorithm` | Medium | Topological Build Dependency Sorter | Lacks topological sort and Tarjan/DFS cycle path detection | **`100.0 / 100.0`** |

---

## Quickstart Guide

### 1. Installation & Environment Setup
```bash
# Clone the repository
git clone https://github.com/kirubesh/CodeForgeX.git
cd CodeForgeX

# Install virtual environment and dependencies using uv or pip
pip install -e .
```

### 2. Run the Full Test Suite (91 Tests)
```bash
pytest -v
```

### 3. Run Benchmark Evaluations via CLI
```bash
# Run the entire benchmark suite in golden reference mode
python scripts/run_evaluation.py --all

# Run a specific task in autonomous agent mode (MCP stdio tool-calling loop)
python scripts/run_evaluation.py --task bug_fix_001 --mode agent-systematic

# Filter benchmarks by category or difficulty
python scripts/run_evaluation.py --category algorithm
python scripts/run_evaluation.py --difficulty medium
```

### 4. Containerized Execution with Docker
```bash
# Build the security-hardened container
docker build -t codeforge-x:latest .

# Run full evaluation across all tasks inside Docker
docker run --rm codeforge-x:latest --evaluate-all

# Or run using Docker Compose with cgroups limits and tmpfs in-memory sandboxes
docker compose up codeforge-eval
```

---

## Technical Documentation & Interview Defenses

- **[System Architecture Specification](docs/architecture.md)**: Deep-dive into MCP server tools, security sandboxing, scoring math, and agent loop lifecycle.
- **[Security & Threat Modeling](docs/security.md)**: Comprehensive threat matrix covering path traversal, shell injection, privilege elevation, and anti-cheat guards.
- **[Docker Reproducibility Guide](docs/docker.md)**: Container security specs, capability dropping, and cgroup resource quotas.
- **[Staff-Level Technical Interview Defense Guide](docs/interview_defense.md)**: Complete question-and-answer handbook defending every architectural trade-off and systems engineering choice.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
