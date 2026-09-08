# Security Model & Threat Mitigation Guide

The **MCP Software Engineering Agent & Deterministic Evaluation Environment** implements a defense-in-depth security architecture designed to contain untrusted or autonomous agent actions within a designated repository sandbox.

---

## 1. Threat Model

When executing autonomous AI agents against software repositories, five primary threat categories arise:

| Threat Category | Attack Vector | Potential Impact | Mitigation Layer |
| :--- | :--- | :--- | :--- |
| **Path Traversal** | `../../secret.txt`, symlink escapes, external absolute paths | Exfiltration of host machine credentials, environment variables, SSH keys. | Canonical path containment (`resolve_safe_path`). |
| **Command Injection** | Chained shell operators (`&&`, `;`, `\|`, backticks, redirection) | Execution of arbitrary host system binaries (`curl`, `rm`, `powershell`). | Explicit argument vectors (`shell=False`) & `validate_safe_command` whitelist. |
| **Benchmark Contamination (Cheating)** | Reading `solution.patch`, reading hidden tests, modifying `task.json` | Artificial inflation of evaluation benchmark scores without solving problems. | Anti-cheat pattern matching & resource isolation (`is_protected_resource`). |
| **Resource Exhaustion (DoS)** | Infinite loops in tests, megabyte-sized diff floods, memory exhaustion | Denial of service, runaway token consumption, stalled evaluation runners. | Hard process deadlines (`timeout_seconds`), file size ceilings, line caps. |
| **Dirty State / Partial Commits** | Applying multi-hunk patches where a middle hunk fails | Broken repository state, irreproducible evaluation baselines. | Atomic dry-run validation (`git apply --check`). |

---

## 2. Defense-in-Depth Mechanisms

### 2.1 Canonical Path Containment (`sandbox.py`)
Rather than relying on naive string checks (`if ".." in path`), which can be bypassed via URL encoding, alternative separators, or intermediate symlinks:
1. All path inputs are resolved to their canonical, absolute representation via `Path.resolve()`.
2. The candidate path is asserted to be a child of the canonical repository root via `candidate.relative_to(root)`.
3. If the candidate resolves outside `repo_root`, a `PathTraversalError` is immediately raised before any filesystem I/O occurs.

```python
# Canonical containment check
try:
    candidate.relative_to(root)
except ValueError:
    raise PathTraversalError(f"Path '{target_path}' escapes repository root '{root}'.")
```

### 2.2 Anti-Cheat Protection
To ensure benchmarks measure true software-engineering problem-solving ability:
1. `SecurityPolicy.protected_patterns` shields:
   - `solution.patch`, `expected.patch`
   - `.hidden_tests/`, `*_hidden.py`
   - `task.json`, `metadata.json`
   - `evaluator.*`
2. `list_files` actively filters these resources so the agent cannot observe their existence.
3. `search_code` skips them during code searches.
4. `read_file` and `apply_patch` raise `ProtectedResourceError` if an agent attempts direct access.

### 2.3 Command Whitelisting & Shell Injection Mitigation
1. **No Shell Invocations**: Subprocesses are spawned using explicit argument lists (e.g. `[sys.executable, "-m", "pytest", ...]` with `shell=False`).
2. **Binary Whitelist**: Only authorized binaries (`git`, `pytest`, `python`, `python3`) can be invoked. High-risk binaries (`rm`, `del`, `curl`, `wget`, `powershell`, `cmd`, `bash`) are explicitly blocked.
3. **Shell Metacharacter Sanitization**: Any argument containing shell operators (`;`, `&&`, `||`, `|`, `>`, `<`, backticks) triggers a `CommandSecurityError`.

### 2.4 Execution Timeouts & Resource Limits
1. **Hard Deadlines**: All subprocess executions (`pytest`) run under a strict timeout watchdog (`timeout_seconds`). When breached, the process is terminated, returning `is_timeout=True` and exit code `-9`.
2. **File Size Caps**: Files larger than 2MB cannot be read into memory in a single tool call (`max_file_read_bytes`), and patches larger than 500KB are rejected (`max_file_write_bytes`).
3. **Line Truncation**: Standard file reads are capped at 1,000 lines per call to prevent prompt context exhaustion.

---

## 3. Graceful Error Handling over MCP
To prevent an unhandled security exception from crashing the persistent MCP JSON-RPC server process:
- All tools catch `(PathTraversalError, ProtectedResourceError, ResourceLimitExceededError, SecuritySandboxError)`.
- Tools serialize the error into a structured JSON response:
  ```json
  {
    "error": "Access denied: 'task.json' is a protected evaluator or solution resource.",
    "success": false
  }
  ```
- This allows the agent to perceive the error within its reasoning loop, learn that the operation is impermissible, and pursue an alternative strategy.
