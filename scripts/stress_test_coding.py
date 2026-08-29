#!/usr/bin/env python3
"""Stress test effGen coding agent with increasing difficulty.

Tests the Qwen 2.5 1.5B model on progressively harder Python tasks
to find where performance degrades.

Run from ace_enterprise root:
    python scripts/stress_test_coding.py
"""

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agents.podman_orchestrator import PodmanOrchestrator, SecurityBreachError  # noqa: E402
from src.agents.podman_runner import PodmanRunner  # noqa: E402

_RESULT_MARKER = "===STRESS_TEST_RESULT==="


@dataclass
class TestCase:
    """A coding test case with difficulty level."""
    level: int
    name: str
    prompt: str
    validation: str  # Python code to validate the result
    timeout: int = 90  # seconds


# Graduated difficulty test cases
TEST_CASES = [
    # Level 1: Basic operations
    TestCase(
        level=1,
        name="simple_arithmetic",
        prompt="Write a Python function called 'add' that takes two numbers and returns their sum.",
        validation="add(2, 3) == 5 and add(-1, 1) == 0",
    ),
    TestCase(
        level=1,
        name="string_reverse",
        prompt="Write a Python function called 'reverse_string' that reverses a string.",
        validation="reverse_string('hello') == 'olleh' and reverse_string('') == ''",
    ),

    # Level 2: Basic algorithms
    TestCase(
        level=2,
        name="find_max",
        prompt="Write a Python function called 'find_max' that finds the maximum value in a list of numbers.",
        validation="find_max([1, 5, 3, 9, 2]) == 9 and find_max([-1, -5]) == -1",
    ),
    TestCase(
        level=2,
        name="count_vowels",
        prompt="Write a Python function called 'count_vowels' that counts vowels (a,e,i,o,u) in a string, case insensitive.",
        validation="count_vowels('Hello World') == 3 and count_vowels('xyz') == 0",
    ),

    # Level 3: Intermediate algorithms
    TestCase(
        level=3,
        name="fibonacci",
        prompt="Write a Python function called 'fibonacci' that returns the nth Fibonacci number (0-indexed, so fibonacci(0)=0, fibonacci(1)=1).",
        validation="fibonacci(0) == 0 and fibonacci(1) == 1 and fibonacci(10) == 55",
    ),
    TestCase(
        level=3,
        name="is_palindrome",
        prompt="Write a Python function called 'is_palindrome' that returns True if a string is a palindrome (ignoring spaces and case).",
        validation="is_palindrome('racecar') == True and is_palindrome('A man a plan a canal Panama'.replace(' ', '')) == True",
    ),

    # Level 4: Data structures
    TestCase(
        level=4,
        name="remove_duplicates",
        prompt="Write a Python function called 'remove_duplicates' that removes duplicates from a list while preserving order.",
        validation="remove_duplicates([1, 2, 2, 3, 1, 4]) == [1, 2, 3, 4]",
    ),
    TestCase(
        level=4,
        name="flatten_list",
        prompt="Write a Python function called 'flatten' that flattens a nested list. Example: flatten([[1, 2], [3, [4, 5]]]) returns [1, 2, 3, 4, 5].",
        validation="flatten([[1, 2], [3, [4, 5]]]) == [1, 2, 3, 4, 5]",
        timeout=120,
    ),

    # Level 5: Complex algorithms
    TestCase(
        level=5,
        name="binary_search",
        prompt="Write a Python function called 'binary_search' that returns the index of a target in a sorted list, or -1 if not found.",
        validation="binary_search([1, 3, 5, 7, 9], 5) == 2 and binary_search([1, 3, 5], 4) == -1",
        timeout=120,
    ),
    TestCase(
        level=5,
        name="merge_sorted",
        prompt="Write a Python function called 'merge_sorted' that merges two sorted lists into one sorted list.",
        validation="merge_sorted([1, 3, 5], [2, 4, 6]) == [1, 2, 3, 4, 5, 6]",
        timeout=120,
    ),

    # Level 6: Advanced
    TestCase(
        level=6,
        name="prime_factors",
        prompt="Write a Python function called 'prime_factors' that returns a list of prime factors of a number. Example: prime_factors(12) returns [2, 2, 3].",
        validation="prime_factors(12) == [2, 2, 3] and prime_factors(17) == [17]",
        timeout=150,
    ),
    TestCase(
        level=6,
        name="balanced_parens",
        prompt="Write a Python function called 'is_balanced' that checks if parentheses in a string are balanced. Handle (), [], and {}.",
        validation="is_balanced('([])') == True and is_balanced('([)]') == False and is_balanced('') == True",
        timeout=150,
    ),
]


def _build_stress_test_script(code: str, validation: str) -> str:
    """Pytest driver that execs/evals model-generated code *inside the sandbox*
    and reports the result via a marked stdout line, mirroring the pattern in
    src/contracts/contract_driven.py's _build_validation_script."""
    return f'''
import json

_MARKER = {_RESULT_MARKER!r}
_CODE = {code!r}
_VALIDATION = {validation!r}


def test_stress_case():
    result = {{"valid": False, "error": None}}
    exec_globals = {{}}
    try:
        exec(_CODE, exec_globals)
        result["valid"] = bool(eval(_VALIDATION, exec_globals))
    except Exception as e:
        result["error"] = f"Validation failed: {{str(e)[:100]}}"
    raise AssertionError(_MARKER + json.dumps(result))
'''


def _parse_stress_marker(output: str | None) -> dict | None:
    for line in (output or "").splitlines():
        idx = line.find(_RESULT_MARKER)
        if idx == -1:
            continue
        try:
            return json.loads(line[idx + len(_RESULT_MARKER):])
        except json.JSONDecodeError:
            continue
    return None


def run_coding_task(prompt: str, validation: str, timeout: int, orchestrator: PodmanOrchestrator) -> dict:
    """Execute a coding task and validate the result."""

    # Direct model generation without agent - cleaner code extraction
    test_script = f'''
import sys
sys.path.insert(0, "{Path.home() / 'effgen_test'}")
import logging
logging.basicConfig(level=logging.WARNING)

from effgen import load_model

model = load_model("Qwen/Qwen2.5-1.5B-Instruct", quantization="4bit")

# Direct generation without agent framework
prompt = """{prompt}

Respond with ONLY the Python function code. No explanations, no markdown, just the function."""

response = model.generate(prompt, max_tokens=256)
print("OUTPUT_START")
print(response)
print("OUTPUT_END")
'''

    try:
        effgen_python = Path.home() / "effgen_test" / ".venv" / "bin" / "python"
        start_time = time.time()

        result = subprocess.run(
            [str(effgen_python), "-c", test_script],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path.home() / "effgen_test"),
        )

        elapsed = time.time() - start_time
        output = result.stdout

        # Extract code from output
        if "OUTPUT_START" in output and "OUTPUT_END" in output:
            code = output.split("OUTPUT_START")[1].split("OUTPUT_END")[0].strip()
        else:
            code = output

        # Clean up code
        # Handle escaped newlines from model output
        code = code.replace("\\n", "\n").replace("\\t", "\t")

        # Remove markdown if present
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].split("```")[0].strip()

        # Strip leading/trailing whitespace
        code = code.strip()

        # Validate the generated code inside the Podman sandbox -- never
        # exec/eval model output in-process on the host.
        try:
            sandbox_script = _build_stress_test_script(code, validation)
            pulse_result = orchestrator.pulse(sandbox_script)
        except SecurityBreachError as exc:
            return {
                "success": True,
                "valid": False,
                "code": code[:500],
                "elapsed": elapsed,
                "error": f"SecurityBreach: {exc}"
            }

        payload = _parse_stress_marker(pulse_result.output)
        if payload is None:
            return {
                "success": True,
                "valid": False,
                "code": code[:500],
                "elapsed": elapsed,
                "error": f"No result from sandbox: {(pulse_result.error or '')[:200]}"
            }

        return {
            "success": True,
            "valid": payload.get("valid", False),
            "code": code[:500],
            "elapsed": elapsed,
            "error": payload.get("error")
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "valid": False,
            "code": "",
            "elapsed": timeout,
            "error": f"Timeout ({timeout}s)"
        }
    except Exception as e:
        return {
            "success": False,
            "valid": False,
            "code": "",
            "elapsed": 0,
            "error": str(e)[:100]
        }


def main():
    print("=" * 70)
    print("CODING STRESS TEST - Qwen 2.5 1.5B")
    print("=" * 70)
    print("Testing increasingly difficult Python coding tasks")
    print("Machine-friendly: sequential execution, reasonable timeouts\n")

    results_by_level = {}
    all_results = []

    current_level = 0
    consecutive_failures = 0

    max_timeout = max(test.timeout for test in TEST_CASES)
    orchestrator = PodmanOrchestrator(PodmanRunner(test_timeout=max_timeout))
    try:
        for test in TEST_CASES:
            if test.level != current_level:
                current_level = test.level
                print(f"\n{'─' * 70}")
                print(f"LEVEL {current_level}")
                print("─" * 70)

            print(f"\n[{test.name}] {test.prompt[:60]}...")

            result = run_coding_task(test.prompt, test.validation, test.timeout, orchestrator)

            # Track results
            if test.level not in results_by_level:
                results_by_level[test.level] = {"passed": 0, "failed": 0, "times": []}

            if result["valid"]:
                results_by_level[test.level]["passed"] += 1
                consecutive_failures = 0
                status = "PASS"
            else:
                results_by_level[test.level]["failed"] += 1
                consecutive_failures += 1
                status = "FAIL"

            results_by_level[test.level]["times"].append(result["elapsed"])

            all_results.append({
                "level": test.level,
                "name": test.name,
                "valid": result["valid"],
                "elapsed": result["elapsed"],
                "error": result["error"]
            })

            print(f"  Status: {status}")
            print(f"  Time: {result['elapsed']:.1f}s")
            if result["error"]:
                print(f"  Error: {result['error']}")
            if result["code"] and not result["valid"]:
                print(f"  Generated: {result['code'][:100]}...")

            # Early termination if too many failures
            if consecutive_failures >= 3:
                print(f"\n*** 3 consecutive failures - stopping at level {test.level} ***")
                break
    finally:
        orchestrator.stop()

    # Summary
    print(f"\n{'=' * 70}")
    print("RESULTS SUMMARY")
    print("=" * 70)

    print("\nPerformance by Level:")
    print("─" * 50)
    print(f"{'Level':<8} {'Passed':<10} {'Failed':<10} {'Rate':<10} {'Avg Time':<10}")
    print("─" * 50)

    for level in sorted(results_by_level.keys()):
        data = results_by_level[level]
        total = data["passed"] + data["failed"]
        rate = data["passed"] / total * 100 if total > 0 else 0
        avg_time = sum(data["times"]) / len(data["times"]) if data["times"] else 0

        print(f"{level:<8} {data['passed']:<10} {data['failed']:<10} {rate:>5.0f}%     {avg_time:>6.1f}s")

    print("─" * 50)

    # Find breaking point
    print("\nBreaking Point Analysis:")
    for level in sorted(results_by_level.keys()):
        data = results_by_level[level]
        total = data["passed"] + data["failed"]
        rate = data["passed"] / total * 100 if total > 0 else 0
        if rate < 50:
            print(f"  Performance degrades significantly at Level {level} ({rate:.0f}% pass rate)")
            break
    else:
        max_level = max(results_by_level.keys())
        print(f"  Model handled all levels up to {max_level}")

    # Total stats
    total_passed = sum(d["passed"] for d in results_by_level.values())
    total_failed = sum(d["failed"] for d in results_by_level.values())
    total = total_passed + total_failed

    print(f"\nOverall: {total_passed}/{total} tasks passed ({100*total_passed/total:.0f}%)")


if __name__ == "__main__":
    main()
