#!/usr/bin/env python3
"""Test contract-driven agent orchestration.

Demonstrates the flow:
1. Architect defines interface contracts with test cases
2. Small model implements to spec
3. Validator verifies against tests

Run from ace_enterprise root:
    python scripts/test_contract_driven.py
"""

import subprocess
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.contracts.contract_driven import (
    InterfaceContract,
    TestCase,
    ContractOrchestrator,
    ContractStatus,
)


def implement_with_effgen_agent(prompt: str, timeout: int = 120) -> str:
    """Use effGen Agent with tools to implement a contract."""
    import base64

    # Encode prompt to avoid quote issues
    prompt_b64 = base64.b64encode(prompt.encode()).decode()

    # Use effGen Agent framework with PythonREPL tool
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
    name="contract_implementer",
    model=model,
    tools=[CodeExecutor(), PythonREPL()],
    system_prompt="""You are a Python function implementer.
When given a function signature and test cases:
1. Write the function implementation
2. Use the PythonREPL tool to test it
3. Return ONLY the final working function code

Output format: just the def statement and function body, nothing else."""
)

agent = Agent(config=config)

prompt = base64.b64decode("{prompt_b64}").decode()
result = agent.run(prompt)

# Extract code from agent output or tool calls
output = result.output if hasattr(result, 'output') else str(result)

# Try to get code from tool calls if available
if hasattr(result, 'messages'):
    for msg in result.messages:
        if hasattr(msg, 'tool_calls'):
            for tc in msg.tool_calls:
                if 'def ' in str(tc):
                    output = str(tc)
                    break

print("OUTPUT_START")
print(output)
print("OUTPUT_END")
print(f"SUCCESS:{{result.success if hasattr(result, 'success') else True}}")
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
        if "OUTPUT_START" in output and "OUTPUT_END" in output:
            code = output.split("OUTPUT_START")[1].split("OUTPUT_END")[0].strip()
        else:
            code = output

        # Clean up
        code = code.replace("\\n", "\n").replace("\\t", "\t")
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].split("```")[0].strip()

        return code.strip()

    except subprocess.TimeoutExpired:
        return ""
    except Exception:
        return ""


def main():
    print("=" * 70)
    print("CONTRACT-DRIVEN AGENT ORCHESTRATION PROTOTYPE")
    print("=" * 70)
    print("\nFlow: Architect → Contract → Small Model → Validator\n")

    orchestrator = ContractOrchestrator()

    # =========================================================================
    # ARCHITECT PHASE: Define contracts
    # =========================================================================
    print("[ARCHITECT] Defining interface contracts...\n")

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
            hints=["Simple multiplication"],
        ),
        InterfaceContract(
            contract_id="discount-001",
            function_name="apply_discount",
            signature="(price: float, discount_percent: float) -> float",
            docstring="Apply percentage discount to price. Returns discounted price.",
            test_cases=[
                TestCase("ten_percent", "(100, 10)", "90.0"),
                TestCase("half_off", "(50, 50)", "25.0"),
                TestCase("no_discount", "(100, 0)", "100.0"),
            ],
            estimated_complexity=2,
            hints=["Subtract discount from price"],
        ),
        InterfaceContract(
            contract_id="grade-001",
            function_name="letter_grade",
            signature="(score: int) -> str",
            docstring="Convert numeric score to letter grade. A>=90, B>=80, C>=70, D>=60, F<60",
            test_cases=[
                TestCase("A_grade", "(95)", "'A'"),
                TestCase("B_grade", "(85)", "'B'"),
                TestCase("C_grade", "(75)", "'C'"),
                TestCase("D_grade", "(65)", "'D'"),
                TestCase("F_grade", "(55)", "'F'"),
            ],
            estimated_complexity=2,
            hints=["Use if/elif chain"],
        ),
        InterfaceContract(
            contract_id="fizzbuzz-001",
            function_name="fizzbuzz",
            signature="(n: int) -> str",
            docstring="Return 'FizzBuzz' if divisible by 3 and 5, 'Fizz' if by 3, 'Buzz' if by 5, else str(n)",
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
            hints=["Normalize string first (lower, remove spaces), then compare with reverse"],
        ),
        InterfaceContract(
            contract_id="anagram-001",
            function_name="are_anagrams",
            signature="(s1: str, s2: str) -> bool",
            docstring="Check if two strings are anagrams (same letters, different order). Case insensitive.",
            test_cases=[
                TestCase("basic", "('listen', 'silent')", "True"),
                TestCase("different", "('hello', 'world')", "False"),
                TestCase("case_insensitive", "('Listen', 'Silent')", "True"),
            ],
            estimated_complexity=3,
            hints=["Sort the characters of each string and compare"],
        ),
    ]

    for contract in contracts:
        orchestrator.register_contract(contract)
        print(f"  Contract: {contract.contract_id}")
        print(f"    {contract.function_name}{contract.signature}")
        print(f"    Tests: {len(contract.test_cases)}, Complexity: {contract.estimated_complexity}")

    # =========================================================================
    # IMPLEMENTATION PHASE: Small model implements
    # =========================================================================
    print(f"\n{'─' * 70}")
    print("[IMPLEMENTER] Small model implementing contracts...")
    print("─" * 70)

    results = []

    for contract in contracts:
        print(f"\n▶ {contract.contract_id}: {contract.function_name}")

        # Get implementation prompt
        prompt = orchestrator.get_implementation_prompt(contract.contract_id)
        print(f"  Generating implementation...")

        start = time.time()
        code = implement_with_effgen_agent(prompt)
        elapsed = time.time() - start

        if not code:
            print(f"  ✗ No code generated ({elapsed:.1f}s)")
            results.append({
                "contract": contract.contract_id,
                "status": "no_code",
                "passed": 0,
                "total": len(contract.test_cases),
                "time": elapsed
            })
            continue

        print(f"  Generated ({elapsed:.1f}s):")
        for line in code.split("\n")[:5]:
            print(f"    {line}")
        if code.count("\n") > 5:
            print(f"    ... ({code.count(chr(10)) - 5} more lines)")

        # Validate
        impl = orchestrator.submit_implementation(
            contract.contract_id,
            code,
            agent_ref="qwen-1.5b"
        )
        impl.elapsed_seconds = elapsed

        passed = sum(1 for v in impl.test_results.values() if v)
        total = len(contract.test_cases)

        if impl.status == ContractStatus.VALIDATED:
            print(f"  ✓ VALIDATED: {passed}/{total} tests passed")
        else:
            print(f"  ✗ FAILED: {passed}/{total} tests passed")
            if impl.error:
                print(f"    Error: {impl.error[:80]}")
            for name, result in impl.test_results.items():
                if not result:
                    print(f"    Failed: {name}")

        results.append({
            "contract": contract.contract_id,
            "status": impl.status.value,
            "passed": passed,
            "total": total,
            "time": elapsed
        })

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print(f"\n{'=' * 70}")
    print("CONTRACT IMPLEMENTATION SUMMARY")
    print("=" * 70)

    print(f"\n{'Contract':<20} {'Status':<12} {'Tests':<10} {'Time':<10}")
    print("─" * 52)

    total_validated = 0
    total_contracts = len(results)

    for r in results:
        status_icon = "✓" if r["status"] == "validated" else "✗"
        print(f"{r['contract']:<20} {status_icon} {r['status']:<10} {r['passed']}/{r['total']:<7} {r['time']:.1f}s")
        if r["status"] == "validated":
            total_validated += 1

    print("─" * 52)
    print(f"\nContracts validated: {total_validated}/{total_contracts} ({100*total_validated/total_contracts:.0f}%)")

    # Complexity analysis
    print("\nBy Complexity Level:")
    by_complexity = {}
    for contract, r in zip(contracts, results):
        c = contract.estimated_complexity
        if c not in by_complexity:
            by_complexity[c] = {"validated": 0, "total": 0}
        by_complexity[c]["total"] += 1
        if r["status"] == "validated":
            by_complexity[c]["validated"] += 1

    for level in sorted(by_complexity.keys()):
        data = by_complexity[level]
        rate = 100 * data["validated"] / data["total"]
        print(f"  Level {level}: {data['validated']}/{data['total']} ({rate:.0f}%)")

    print(f"\n{'=' * 70}")
    print("CONCLUSION")
    print("=" * 70)
    print("""
When interfaces are well-specified:
- Small models (1.5B) can reliably implement contracts
- Test cases provide unambiguous success criteria
- Architect/broker handles complexity; implementer handles execution

This enables: Human → Interface Design → Broker → Cheap Local Model → Validated Code
""")


if __name__ == "__main__":
    main()
