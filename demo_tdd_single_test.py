#!/usr/bin/env python3
"""
ACE TDD Demo - Single Test Focus

Demonstrates ACE making a SINGLE test pass in a realistic workflow:
1. Test file exists (examples/test_calculator.py)
2. ACE reads the test
3. ACE generates implementation (examples/calculator.py)
4. Test passes!

This is closer to production usage where tests exist separately.
"""
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, "/home/ch_dev/ace_enterprise")

from src.core.generator.module import Generator
from src.playbook.manager import PlaybookManager
from src.storage.schemas import PlaybookCreate, TaskInput
from src.utils.llm_client import LLMClient


def print_section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_subsection(title: str) -> None:
    print(f"\n{'-' * 70}")
    print(f"  {title}")
    print('-' * 70)


def run_single_test(test_path: Path, test_name: str) -> tuple[bool, str]:
    """
    Run a single test function.

    Args:
        test_path: Path to test file
        test_name: Name of test function to run

    Returns:
        (passed, output)
    """
    result = subprocess.run(
        [
            "python", "-m", "pytest",
            str(test_path),
            f"-k", test_name,
            "-v",
            "--tb=short",
            "-p", "no:cov",  # Disable coverage plugin
            "--override-ini=addopts="  # Clear pytest addopts from config
        ],
        capture_output=True,
        text=True,
        cwd=test_path.parent
    )

    passed = result.returncode == 0
    output = result.stdout + result.stderr
    return passed, output


def extract_code_from_solution(solution: str) -> str:
    """Extract clean Python code from LLM solution."""
    import re

    # Try to find code in markdown blocks
    patterns = [
        r'```python\n(.*?)\n```',
        r'```\n(.*?)\n```',
        r'```python(.*?)```',
        r'```(.*?)```',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, solution, re.DOTALL)
        if matches:
            return matches[0].strip()

    # Return as-is if no markdown blocks
    return solution.strip()


def demo_single_test():
    """Demonstrate ACE making a single test pass."""

    print_section("ACE TDD DEMO - SINGLE TEST")
    print("\nScenario: Make ONE test pass")
    print("Test file: examples/test_calculator.py")
    print("Target test: test_add_two_numbers")

    # Setup
    test_file = Path("/home/ch_dev/ace_enterprise/examples/test_calculator.py")
    impl_file = Path("/home/ch_dev/ace_enterprise/examples/calculator.py")
    test_name = "test_add_two_numbers"

    # Ensure test file exists
    if not test_file.exists():
        print(f"\n❌ Test file not found: {test_file}")
        return

    # Remove implementation if it exists (start fresh)
    if impl_file.exists():
        impl_file.unlink()
        print(f"\n🗑️  Removed existing implementation: {impl_file}")

    # Show that test fails initially
    print_subsection("Step 1: Verify Test Fails (No Implementation)")

    passed, output = run_single_test(test_file, test_name)

    if passed:
        print("⚠️  Test already passes! This shouldn't happen.")
        return
    else:
        print("✓ Test fails as expected (no implementation exists)")
        # Show relevant error
        for line in output.split('\n'):
            if 'ModuleNotFoundError' in line or 'ImportError' in line:
                print(f"  {line.strip()}")

    # Initialize ACE
    print_subsection("Step 2: Initialize ACE")

    playbook_manager = PlaybookManager()
    llm_client = LLMClient()

    if not llm_client.check_availability():
        print("\n⚠️  LLM not available - using fallback simulation")
        use_llm = False
    else:
        print(f"✓ LLM Client: {llm_client.provider} ({llm_client.model})")
        use_llm = True

    # Create empty playbook (we're just testing code generation, not learning yet)
    playbook = playbook_manager.create_playbook(
        PlaybookCreate(
            domain="python_tdd",
            base_model=llm_client.model if use_llm else "simulated",
        )
    )

    generator = Generator(playbook_manager, llm_client)
    print(f"✓ Generator ready")
    print(f"✓ Playbook: {playbook.playbook_id}")

    # Read the test file
    print_subsection("Step 3: Read Test Requirements")

    test_content = test_file.read_text()

    # Extract just the relevant test
    test_lines = []
    in_target_test = False
    for line in test_content.split('\n'):
        if f"def {test_name}" in line:
            in_target_test = True
        if in_target_test:
            test_lines.append(line)
            # Stop at next function or end
            if line.startswith('def ') and f"def {test_name}" not in line:
                break

    target_test = '\n'.join(test_lines)
    print(f"Target test:\n")
    print(target_test)

    # Generate implementation
    print_subsection("Step 4: Generate Implementation")

    task = TaskInput(
        id="tdd_single_001",
        query=f"""Generate a Python module called 'calculator.py' that makes this test pass:

{target_test}

Requirements:
- Create an 'add' function that takes two numbers and returns their sum
- Return ONLY the Python code for calculator.py
- No markdown blocks, no explanations
- Just the function definition(s)""",
        type="code_generation",
        difficulty="easy",
    )

    if use_llm:
        gen_output = generator.execute(
            task=task,
            playbook_id=playbook.playbook_id,
        )

        print(f"\n✓ Code generated in {gen_output.latency_ms}ms")
        implementation = extract_code_from_solution(gen_output.solution)
    else:
        # Fallback implementation
        implementation = """def add(a, b):
    \"\"\"Add two numbers and return the result.\"\"\"
    return a + b"""
        print("\n✓ Using fallback implementation (LLM unavailable)")

    print(f"\nGenerated code:\n{implementation}")

    # Write implementation
    print_subsection("Step 5: Write Implementation File")

    impl_file.write_text(implementation)
    print(f"✓ Written to: {impl_file}")

    # Run test again
    print_subsection("Step 6: Run Test Again")

    passed, output = run_single_test(test_file, test_name)

    if passed:
        print("✅ TEST PASSED!")
        print("\n🎉 Success! ACE generated code that makes the test pass.")

        # Show test output
        for line in output.split('\n'):
            if 'PASSED' in line or 'passed' in line:
                print(f"  {line.strip()}")
    else:
        print("❌ Test still failing")
        print("\nTest output:")
        print(output)

    # Summary
    print_section("SUMMARY")

    print("\n✓ Workflow demonstrated:")
    print("  1. Test file exists separately (like real projects)")
    print("  2. ACE reads the test requirements")
    print("  3. ACE generates implementation code")
    print("  4. Test passes!")
    print("\n💡 Next step: Add learning loop for test failures")
    print("💡 Next step: Build full TDD agent for multi-test workflows")


if __name__ == "__main__":
    try:
        demo_single_test()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
