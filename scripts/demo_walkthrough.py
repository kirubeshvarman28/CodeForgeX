#!/usr/bin/env python3
"""CodeForgeX Live Interactive Demonstration and Architecture Walkthrough.

Demonstrates the core pillars of the system in real time:
1. Model Context Protocol (MCP) tool discovery and multi-provider schema reflection.
2. Security sandbox containment (path traversal defense and anti-cheat protection).
3. Autonomous ReAct agent execution loop over stdio.
4. Deterministic multi-dimensional evaluation and tamper detection.
5. Live benchmark evaluation across task archetypes.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

# Add project root and src to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent.client import MCPClient
from agent.loop import AgentExecutionLoop
from agent.planner import SystematicSWEPlanner
from evaluator.metrics import EvaluationMetrics
from evaluator.runner import EvaluationRunner
from evaluator.scoring import ScoringEngine
from mcp_server.security.sandbox import (
    DEFAULT_SECURITY_POLICY,
    PathTraversalError,
    ProtectedResourceError,
    resolve_safe_path,
)
from tasks.loader import discover_tasks, load_task_definition, load_task_solution
from tasks.manager import WorkspaceManager


def print_banner(title: str):
    """Render a visual section banner."""
    print("\n" + "=" * 80)
    print(f"  {title.upper()}")
    print("=" * 80 + "\n")


async def demo_mcp_client_and_reflection():
    """Demonstrate MCP stdio connection, tool discovery, and multi-provider reflection."""
    print_banner("1. Model Context Protocol (MCP) Stdio Handshake & Tool Reflection")
    print("[+] Connecting to MCPServer subprocess over anonymous stdio pipes...")

    async with MCPClient(repo_root=PROJECT_ROOT) as client:
        print(f"[+] Connected successfully! Server: '{client.server_info.name}' (v{client.server_info.version})")

        tools = await client.list_tools()
        print(f"[+] Discovered {len(tools)} registered MCP tools:")
        for t in tools:
            print(f"    - {t.name:<24} : {t.description[:55]}...")

        # Demonstrate multi-provider schema reflection
        sample_tool = tools[0]
        print(f"\n[+] Multi-Provider Schema Reflection for '{sample_tool.name}':")
        print("    [OpenAI Tool Format]:")
        print("      " + json.dumps(sample_tool.to_openai_tool(), indent=6)[:120] + "\n      ...")
        print("    [Anthropic Claude Format]:")
        print("      " + json.dumps(sample_tool.to_anthropic_tool(), indent=6)[:120] + "\n      ...")


def demo_security_sandbox():
    """Demonstrate sandbox defense against directory traversal and anti-cheat protected resources."""
    print_banner("2. Security Sandbox Containment & Threat Defense")

    # 1. Path Traversal Defense
    print("[+] Attack Vector 1: Attempting directory traversal outside repository root ('../../Windows/System32')...")
    try:
        resolve_safe_path(PROJECT_ROOT, "../../Windows/System32", must_exist=False)
        print("    [-] ERROR: Traversal was not blocked!")
    except PathTraversalError as err:
        print(f"    [+] BLOCKED BY SANDBOX: {type(err).__name__}: {err}")

    # 2. Anti-Cheat Protection
    print("\n[+] Attack Vector 2: Attempting to read protected hidden test suite ('hidden_tests/test_pricing_hidden.py')...")
    from mcp_server.security.sandbox import is_protected_resource
    policy = DEFAULT_SECURITY_POLICY
    test_path = Path("tasks/bug_fix_001/hidden_tests/test_pricing_hidden.py")
    if is_protected_resource(test_path, policy):
        print(f"    [+] BLOCKED BY ANTI-CHEAT: Resource '{test_path.name}' is flagged protected and concealed from agent.")
    else:
        print("    [-] ERROR: Protected resource was not recognized!")


async def demo_autonomous_agent_trial():
    """Demonstrate autonomous agent execution loop solving bug_fix_001."""
    print_banner("3. Autonomous Agent Execution Loop (ReAct over MCP stdio)")

    tasks_dir = PROJECT_ROOT / "tasks"
    task_def = load_task_definition(tasks_dir / "bug_fix_001")
    golden_patch = load_task_solution(tasks_dir / "bug_fix_001")

    scratch_dir = PROJECT_ROOT / "scratch" / "demo_ws"
    ws_manager = WorkspaceManager(workspace_root=scratch_dir)
    ws_path = ws_manager.setup_task_workspace("bug_fix_001", tasks_root=tasks_dir)

    print(f"[+] Instantiated ephemeral task sandbox at: {ws_path.name}/")
    print(f"[+] Task Objective: {task_def.title}")

    try:
        client = MCPClient(repo_root=ws_path)
        planner = SystematicSWEPlanner(
            candidate_patch=golden_patch,
            target_file="src/pricing.py",
            test_target="tests",
        )
        loop = AgentExecutionLoop(
            client=client,
            planner=planner,
            max_iterations=10,
            max_consecutive_failures=3,
        )

        print("[+] Starting ReAct agent loop...")
        start_time = time.time()
        agent_result = await loop.run(objective=task_def.description, task_id="bug_fix_001")
        elapsed = time.time() - start_time

        print(f"[+] Agent Loop Completed in {elapsed:.2f}s across {agent_result.iterations} iterations!")
        print(f"[+] Outcome: Completed={agent_result.completed}, Success={agent_result.success}")
        print(f"[+] Tool Calls Executed: {agent_result.tool_calls_count} (Failed: {agent_result.failed_calls_count})")
        print("\n[+] Agent Execution Trajectory:")
        for step in agent_result.trajectory:
            action_desc = f"tool '{step.action.tool_name}'" if step.action.tool_name else step.action.action_type
            print(f"    Iter {step.iteration} [{step.stage.value.upper():<9}] -> {action_desc:<28} | Thought: {step.thought[:45]}...")

        print(f"\n[+] Extracted Working Tree Unified Diff directly from Git:\n")
        for line in agent_result.final_patch.splitlines()[:12]:
            print(f"    {line}")
        print("    ...")

    finally:
        ws_manager.cleanup_task_workspace("bug_fix_001")


def demo_deterministic_evaluator():
    """Demonstrate multi-dimensional scoring and tamper detection."""
    print_banner("4. Deterministic Multi-Factor Scoring & Anti-Tampering Engine")

    engine = ScoringEngine()

    # Case A: Perfect Run
    metrics_perfect = EvaluationMetrics(
        task_id="bug_fix_001",
        public_tests_passed=4,
        public_tests_total=4,
        hidden_tests_passed=6,
        hidden_tests_total=6,
        regressions_detected=0,
        tool_call_count=5,
        failed_tool_calls=0,
        patch_valid=True,
        patch_lines_added=4,
        patch_lines_deleted=3,
    )
    score_perfect, breakdown = engine.calculate_score(metrics_perfect)
    print(f"[+] Scenario A (Valid Verified Solution): Total Score = {score_perfect:.1f} / 100.0")
    for factor, pts in breakdown.items():
        print(f"    - {factor.replace('_', ' ').title():<22} : {pts:4.1f} pts")

    # Case B: Tampering Detected (Agent edited tests)
    print("\n[+] Scenario B (Agent tampered with public test files to fake a pass):")
    metrics_tampered = EvaluationMetrics(
        task_id="bug_fix_001",
        public_tests_passed=4,
        public_tests_total=4,
        hidden_tests_passed=6,
        hidden_tests_total=6,
        test_tampering_detected=True,  # Tamper detected!
    )
    score_tampered, _ = engine.calculate_score(metrics_tampered)
    print(f"    [!] SHA-256 Digest Mismatch -> test_tampering_detected=True")
    print(f"    [!] DISQUALIFIED SCORE: {score_tampered:.1f} / 100.0 (Zero tolerance on reward hacking)")


async def demo_full_benchmark_catalog():
    """Demonstrate full benchmark suite execution across all 6 archetypes."""
    print_banner("5. Full Benchmark Suite Evaluation Across 6 SE Archetypes")

    from scripts.run_evaluation import run_benchmark_suite
    return_code = await run_benchmark_suite(mode="golden")
    print(f"[+] Benchmark Suite Run Exited with code: {return_code} (0 = Success)")


async def main():
    """Run all live demonstrations sequentially."""
    print("\n" + "#" * 80)
    print("      CODEFORGEX: LIVE INTERACTIVE DEMONSTRATION & SYSTEM WALKTHROUGH")
    print("#" * 80)

    await demo_mcp_client_and_reflection()
    demo_security_sandbox()
    await demo_autonomous_agent_trial()
    demo_deterministic_evaluator()
    await demo_full_benchmark_catalog()

    print("\n" + "#" * 80)
    print("                ALL LIVE DEMONSTRATION SCENARIOS COMPLETED")
    print("#" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
