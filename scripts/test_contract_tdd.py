#!/usr/bin/env python3
"""Contract-driven TDD with full audit integration.

Bead: ace_enterprise-9m8

Flow:
1. Contract defines interface + test cases
2. Generate pytest tests from contract (RED setup)
3. effGen Agent implements until tests pass (GREEN)
4. Audit records all events for human visibility
5. Dashboard shows agent performance

Run from ace_enterprise root:
    python scripts/test_contract_tdd.py
"""

import base64
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.contracts.contract_driven import (
    InterfaceContract,
    TestCase,
)
from src.audit.local_client import LocalAuditClient
from src.audit.schemas import AuditEventType
from src.audit.dashboard import AuditDashboard, AgentIdentity


# Agent identity for audit
EFFGEN_AGENT_ID = "effgen-qwen-1.5b-tdd"
EFFGEN_AGENT_IDENTITY = AgentIdentity(
    display_name="Qwen 2.5 1.5B (TDD)",
    model_id="Qwen/Qwen2.5-1.5B-Instruct",
    provider="effGen (local, 4-bit)"
)


@dataclass
class TDDCycleResult:
    """Result of a TDD cycle for a contract."""
    contract_id: str
    red_passed: bool  # Tests exist and fail without implementation
    green_passed: bool  # Tests pass with implementation
    implementation: str
    test_output: str
    elapsed: float
    attempts: int = 1
    test_count: int = 0


def generate_pytest_from_contract(contract: InterfaceContract) -> str:
    """Generate pytest test file from contract test cases."""

    # Determine imports based on fixtures
    imports = f"from implementation import {contract.function_name}"
    if contract.fixtures and contract.fixtures.setup:
        # Extract function names from setup for imports
        setup_funcs = [f.split("(")[0] for f in contract.fixtures.setup.split(";") if f.strip()]
        for func in setup_funcs:
            func = func.strip()
            if func and func != contract.function_name:
                imports += f", {func}"

    test_code = f'''"""Auto-generated tests for {contract.function_name}."""
import pytest
{imports}


class Test{contract.function_name.title().replace("_", "")}:
    """Tests for {contract.function_name}."""

'''
    # Add setup method if fixtures defined
    if contract.fixtures and contract.fixtures.setup:
        test_code += f'''    def setup_method(self):
        """Setup before each test."""
        {contract.fixtures.setup}

'''
    # Add teardown method if fixtures defined
    if contract.fixtures and contract.fixtures.teardown:
        test_code += f'''    def teardown_method(self):
        """Cleanup after each test."""
        {contract.fixtures.teardown}

'''
    for tc in contract.test_cases:
        test_code += f'''    def test_{tc.name}(self):
        """{tc.description or tc.name}"""
        result = {contract.function_name}{tc.input_expr}
        expected = {tc.expected_expr}
        assert result == expected

'''
    return test_code


def run_effgen_tdd_cycle(
    contract: InterfaceContract,
    test_code: str,
    work_dir: Path,
    audit_client: LocalAuditClient,
    max_attempts: int = 3
) -> TDDCycleResult:
    """Run TDD cycle: RED (verify tests fail) → GREEN (implement until pass)."""

    start_time = time.time()
    session_id = f"tdd-{contract.contract_id}-{int(time.time())}"

    # Write test file
    test_file = work_dir / "test_contract.py"
    test_file.write_text(test_code)

    # Create empty implementation (for RED phase)
    impl_file = work_dir / "implementation.py"
    impl_file.write_text(f'''"""Implementation module."""

def {contract.function_name}{contract.signature}:
    """{contract.docstring}"""
    raise NotImplementedError("To be implemented")
''')

    # RED: Verify tests fail
    red_result = run_pytest(work_dir)
    red_passed = not red_result["passed"]  # Tests should FAIL in RED

    # Audit: TEST_GENERATED
    audit_client.emit_simple(
        event_type=AuditEventType.TEST_GENERATED,
        actor_id=EFFGEN_AGENT_ID,
        payload={
            "contract_id": contract.contract_id,
            "function_name": contract.function_name,
            "test_count": len(contract.test_cases),
            "red_passed": red_passed,
            "phase": "RED",
        },
        session_id=session_id,
    )

    if not red_passed:
        # Tests passed without implementation - something wrong
        return TDDCycleResult(
            contract_id=contract.contract_id,
            red_passed=False,
            green_passed=False,
            implementation="",
            test_output="RED phase failed: tests passed without implementation",
            elapsed=time.time() - start_time,
            test_count=len(contract.test_cases),
        )

    # GREEN: Use effGen to implement until tests pass
    implementation = ""
    green_passed = False
    test_output = ""
    attempt = 0

    for attempt in range(max_attempts):
        # Generate implementation with effGen agent
        prompt = contract.to_prompt()
        if attempt > 0:
            prompt += f"\n\nPrevious attempt failed with:\n{test_output[:500]}\n\nFix the implementation."

        implementation = call_effgen_agent(prompt)

        if not implementation or "def " not in implementation:
            continue

        # Write implementation
        impl_file.write_text(f'''"""Implementation module."""

{implementation}
''')

        # Run tests
        result = run_pytest(work_dir)
        test_output = result["output"]

        # Audit: IMPLEMENTATION_GENERATED
        audit_client.emit_simple(
            event_type=AuditEventType.IMPLEMENTATION_GENERATED,
            actor_id=EFFGEN_AGENT_ID,
            payload={
                "contract_id": contract.contract_id,
                "function_name": contract.function_name,
                "attempt": attempt + 1,
                "tests_passed": result["passed"],
                "phase": "GREEN",
            },
            session_id=session_id,
        )

        if result["passed"]:
            green_passed = True
            break

    elapsed = time.time() - start_time

    # Audit: CYCLE_COMPLETED
    audit_client.emit_simple(
        event_type=AuditEventType.CYCLE_COMPLETED,
        actor_id=EFFGEN_AGENT_ID,
        payload={
            "contract_id": contract.contract_id,
            "function_name": contract.function_name,
            "complexity": contract.estimated_complexity,  # For broker learning
            "red_passed": red_passed,
            "green_passed": green_passed,
            "attempts": attempt + 1 if 'attempt' in dir() else 0,
            "test_count": len(contract.test_cases),
            "elapsed_seconds": elapsed,
            "success": red_passed and green_passed,
        },
        session_id=session_id,
    )

    return TDDCycleResult(
        contract_id=contract.contract_id,
        red_passed=red_passed,
        green_passed=green_passed,
        implementation=implementation,
        test_output=test_output,
        elapsed=elapsed,
        attempts=attempt + 1 if 'attempt' in dir() else 0,
        test_count=len(contract.test_cases),
    )


def run_pytest(work_dir: Path) -> dict:
    """Run pytest in work directory."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-v", str(work_dir)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(work_dir),
            env={**os.environ, "PYTHONPATH": str(work_dir)}
        )
        return {
            "passed": result.returncode == 0,
            "output": result.stdout + result.stderr
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "output": "Timeout"}
    except Exception as e:
        return {"passed": False, "output": str(e)}


def call_effgen_agent(prompt: str, timeout: int = 120) -> str:
    """Call effGen agent to implement code."""

    prompt_b64 = base64.b64encode(prompt.encode()).decode()

    test_script = f'''
import sys
import base64
sys.path.insert(0, "{Path.home() / 'effgen_test'}")
import logging
logging.basicConfig(level=logging.WARNING)

from effgen import Agent, load_model
from effgen.core.agent import AgentConfig
from effgen.tools.builtin import PythonREPL, CodeExecutor

model = load_model("Qwen/Qwen2.5-1.5B-Instruct", quantization="4bit")

config = AgentConfig(
    name="tdd_implementer",
    model=model,
    tools=[CodeExecutor(), PythonREPL()],
    system_prompt="""You implement Python functions to pass tests.
Given a function signature and test cases:
1. Analyze what the function needs to do
2. Write the implementation
3. Test it with PythonREPL if needed
4. Output ONLY the final function code

Important: Output just the def statement and body. No markdown, no explanations."""
)

agent = Agent(config=config)

prompt = base64.b64decode("{prompt_b64}").decode()
result = agent.run(prompt)

output = result.output if hasattr(result, 'output') else str(result)
print("CODE_START")
print(output)
print("CODE_END")
'''

    try:
        effgen_python = Path.home() / "effgen_test" / ".venv" / "bin" / "python"
        result = subprocess.run(
            [str(effgen_python), "-c", test_script],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path.home() / "effgen_test"),
        )

        output = result.stdout
        if "CODE_START" in output and "CODE_END" in output:
            code = output.split("CODE_START")[1].split("CODE_END")[0].strip()
        else:
            code = output

        # Clean up
        code = code.replace("\\n", "\n").replace("\\t", "\t")
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].split("```")[0].strip()

        # Extract just the function definition
        lines = code.split("\n")
        func_lines = []
        in_func = False
        for line in lines:
            if line.strip().startswith("def "):
                in_func = True
            if in_func:
                func_lines.append(line)

        return "\n".join(func_lines).strip() if func_lines else code.strip()

    except subprocess.TimeoutExpired:
        return ""
    except Exception:
        return ""


def main():
    print("=" * 70)
    print("CONTRACT-DRIVEN TDD WITH AUDIT INTEGRATION")
    print("=" * 70)
    print("\nFlow: Contract → Tests (RED) → Implement (GREEN) → Audit → Dashboard\n")

    # Initialize audit client
    audit_client = LocalAuditClient()
    audit_events = []  # Track for dashboard

    # Define contracts
    contracts = [
        InterfaceContract(
            contract_id="tax-001",
            function_name="calculate_tax",
            signature="(income: float, rate: float) -> float",
            docstring="Calculate tax amount. Returns income * rate.",
            test_cases=[
                TestCase("basic", "(1000, 0.2)", "200.0"),
                TestCase("zero_income", "(0, 0.2)", "0.0"),
                TestCase("zero_rate", "(1000, 0)", "0.0"),
            ],
            estimated_complexity=1,
        ),
        InterfaceContract(
            contract_id="fizzbuzz-001",
            function_name="fizzbuzz",
            signature="(n: int) -> str",
            docstring="FizzBuzz: 'FizzBuzz' if div by 15, 'Fizz' if by 3, 'Buzz' if by 5, else str(n)",
            test_cases=[
                TestCase("fizzbuzz", "(15)", "'FizzBuzz'"),
                TestCase("fizz", "(9)", "'Fizz'"),
                TestCase("buzz", "(10)", "'Buzz'"),
                TestCase("number", "(7)", "'7'"),
            ],
            estimated_complexity=2,
        ),
        InterfaceContract(
            contract_id="palindrome-001",
            function_name="is_palindrome",
            signature="(s: str) -> bool",
            docstring="Check if string is palindrome (case insensitive, ignoring spaces)",
            test_cases=[
                TestCase("simple", "('racecar')", "True"),
                TestCase("with_spaces", "('race car')", "True"),
                TestCase("mixed_case", "('RaceCar')", "True"),
                TestCase("not_palindrome", "('hello')", "False"),
            ],
            estimated_complexity=3,
            hints=["Normalize: lowercase, remove spaces, then compare with reverse"],
        ),
    ]

    results = []

    for contract in contracts:
        print(f"\n{'─' * 70}")
        print(f"CONTRACT: {contract.contract_id}")
        print(f"Function: {contract.function_name}{contract.signature}")
        print("─" * 70)

        # Generate pytest tests from contract
        test_code = generate_pytest_from_contract(contract)
        print("\n[RED] Generated tests:")
        for line in test_code.split("\n")[5:12]:
            print(f"  {line}")
        print("  ...")

        # Run TDD cycle in temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)

            print("\n[TDD CYCLE] Running RED → GREEN...")
            result = run_effgen_tdd_cycle(contract, test_code, work_dir, audit_client)

            print(f"\n  RED phase (tests fail without impl): {'✓' if result.red_passed else '✗'}")
            print(f"  GREEN phase (tests pass with impl):  {'✓' if result.green_passed else '✗'}")
            print(f"  Time: {result.elapsed:.1f}s")

            if result.green_passed:
                print("\n[IMPLEMENTATION]")
                for line in result.implementation.split("\n")[:8]:
                    print(f"  {line}")
                if result.implementation.count("\n") > 8:
                    print(f"  ... ({result.implementation.count(chr(10)) - 8} more lines)")
            else:
                print(f"\n[FAILED] {result.test_output[:200]}...")

            results.append(result)

            # Track for dashboard
            audit_events.append({
                "actor_id": EFFGEN_AGENT_ID,
                "event_type": "CYCLE_COMPLETED",
                "payload": {
                    "success": result.green_passed,
                    "task_type": f"complexity-{contract.estimated_complexity}",
                    "contract_id": contract.contract_id,
                }
            })

    # Summary
    print(f"\n{'=' * 70}")
    print("TDD RESULTS SUMMARY")
    print("=" * 70)

    print(f"\n{'Contract':<20} {'RED':<8} {'GREEN':<8} {'Time':<10}")
    print("─" * 46)

    passed = 0
    for r in results:
        red = "✓" if r.red_passed else "✗"
        green = "✓" if r.green_passed else "✗"
        status = "PASS" if r.red_passed and r.green_passed else "FAIL"
        print(f"{r.contract_id:<20} {red:<8} {green:<8} {r.elapsed:.1f}s")
        if r.green_passed:
            passed += 1

    print("─" * 46)
    print(f"\nContracts implemented: {passed}/{len(results)} ({100*passed/len(results):.0f}%)")

    # =========================================================================
    # AUDIT DASHBOARD
    # =========================================================================
    print("\n" + "=" * 70)
    print("AUDIT DASHBOARD (Human Visibility)")
    print("=" * 70)

    # Get audit stats
    audit_stats = audit_client.get_stats()
    print(f"\nAudit events recorded: {audit_stats.get('total_events', 0)}")

    # Create dashboard from events
    dashboard = AuditDashboard(audit_events)
    dashboard.register_identity(EFFGEN_AGENT_ID, EFFGEN_AGENT_IDENTITY)

    # Calculate costs (example: $0.0001 per attempt for local model)
    total_attempts = sum(r.attempts for r in results)
    dashboard.inject_cost_data({
        EFFGEN_AGENT_ID: {
            "total_cost": total_attempts * 0.0001,
            "tasks": len(results),
        }
    })

    # Show performance report
    print("\n┌─────────────────────────────────────────────────────────────────┐")
    print("│                    AGENT PERFORMANCE                            │")
    print("├─────────────────────────────────────────────────────────────────┤")

    report = dashboard.get_full_report()
    for agent_ref, data in report.items():
        identity = data.get("identity", {})
        display_name = identity.get("display_name", agent_ref)
        model_id = identity.get("model_id", "unknown")
        provider = identity.get("provider", "unknown")

        perf = data.get("performance", {})
        success_rate = perf.get("success_rate", 0)
        total_tasks = perf.get("total_tasks", 0)

        costs = data.get("costs", {})
        cost_per_task = costs.get("cost_per_task", 0)

        print(f"│  Agent: {display_name:<40}       │")
        print(f"│  Model: {model_id:<40}       │")
        print(f"│  Provider: {provider:<37}       │")
        print(f"│  Tasks: {total_tasks}, Success: {success_rate:.0%}, Cost/task: ${cost_per_task:.6f}  │")

    print("├─────────────────────────────────────────────────────────────────┤")

    # Task type strengths
    strengths = dashboard.get_task_type_strengths()
    if strengths:
        print("│  PERFORMANCE BY COMPLEXITY:                                     │")
        for task_type, info in sorted(strengths.items()):
            rate = info.get("success_rate", 0)
            print(f"│    {task_type}: {rate:.0%} success                                     │")

    print("└─────────────────────────────────────────────────────────────────┘")

    # Summary
    print("\n" + "=" * 70)
    print("AUDIT INTEGRATION COMPLETE")
    print("=" * 70)
    print("""
Full audit trail recorded:
- TEST_GENERATED: When tests created from contract
- IMPLEMENTATION_GENERATED: Each implementation attempt
- CYCLE_COMPLETED: Final result per contract

Human can query audit DB for:
- Agent performance over time
- Success rates by complexity
- Cost analysis
- Pattern learning (when integrated with playbook)
""")


if __name__ == "__main__":
    main()
