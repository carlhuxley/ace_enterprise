#!/usr/bin/env python3
"""
ACE TDD Loop Demo - Test-Driven Development with Learning

Shows how ACE can:
1. Take a failing unit test
2. Generate code to pass it
3. Learn from failures
4. Improve over iterations
"""
import sys
import subprocess
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/ch_dev/ace_enterprise")

from src.core.curator.module import Curator
from src.core.generator.module import Generator
from src.core.reflector.module import Reflector
from src.playbook.manager import PlaybookManager
from src.storage.schemas import (
    EnvironmentFeedback,
    PlaybookCreate,
    TaskInput,
)
from src.utils.llm_client import LLMClient


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_subsection(title: str) -> None:
    """Print a formatted subsection header."""
    print(f"\n{'-' * 70}")
    print(f"  {title}")
    print('-' * 70)


def extract_code_from_markdown(text: str) -> str:
    """
    Extract Python code from markdown code blocks.

    Handles:
    - ```python ... ```
    - ```\n ... ```
    - Plain code
    """
    import re

    # Try to find code in markdown blocks
    patterns = [
        r'```python\n(.*?)\n```',
        r'```\n(.*?)\n```',
        r'```python(.*?)```',
        r'```(.*?)```',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            return matches[0].strip()

    # If no markdown blocks, return as-is (might be plain code)
    return text.strip()


def run_test(code: str, test_code: str) -> tuple[bool, str, str]:
    """
    Run a unit test against generated code.

    Returns:
        (passed, stdout, stderr)
    """
    # Extract actual code from markdown if present
    clean_code = extract_code_from_markdown(code)

    # Create temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Write implementation
        impl_file = tmppath / "implementation.py"
        impl_file.write_text(clean_code)

        # Write test
        test_file = tmppath / "test_implementation.py"
        test_file.write_text(test_code)

        # Run pytest
        result = subprocess.run(
            ["python", "-m", "pytest", str(test_file), "-v", "--tb=short"],
            capture_output=True,
            text=True,
            cwd=tmpdir
        )

        passed = result.returncode == 0
        return passed, result.stdout, result.stderr


def demo_tdd_loop():
    """Demonstrate TDD loop with ACE learning"""

    print_section("ACE TDD LOOP DEMO")
    print("\nScenario: Implement a function to calculate Fibonacci numbers")
    print("Test-Driven Development with ACE learning")

    # Initialize ACE components
    print_subsection("Initializing ACE Components")

    playbook_manager = PlaybookManager()
    llm_client = LLMClient()

    if not llm_client.check_availability():
        print("\n⚠️  Warning: LLM not available!")
        print("    This demo requires an LLM to be running.")
        return

    print(f"✓ LLM Client: {llm_client.provider} ({llm_client.model})")

    generator = Generator(playbook_manager, llm_client)
    reflector = Reflector(llm_client)
    curator = Curator(playbook_manager, llm_client)

    print("✓ Generator Module")
    print("✓ Reflector Module")
    print("✓ Curator Module")

    # Create playbook
    print_subsection("Creating TDD Playbook")

    playbook = playbook_manager.create_playbook(
        PlaybookCreate(
            domain="python_tdd",
            base_model=llm_client.model,
        )
    )

    print(f"✓ Playbook Created: {playbook.playbook_id}")

    # Define the unit test
    unit_test = """
import pytest
from implementation import fibonacci

def test_fibonacci_base_cases():
    \"\"\"Test Fibonacci base cases\"\"\"
    assert fibonacci(0) == 0
    assert fibonacci(1) == 1

def test_fibonacci_sequence():
    \"\"\"Test Fibonacci sequence\"\"\"
    assert fibonacci(2) == 1
    assert fibonacci(3) == 2
    assert fibonacci(4) == 3
    assert fibonacci(5) == 5
    assert fibonacci(10) == 55

def test_fibonacci_negative():
    \"\"\"Test negative input handling\"\"\"
    with pytest.raises(ValueError):
        fibonacci(-1)
"""

    print_subsection("Unit Test Definition")
    print("Test requirements:")
    print("  - fibonacci(0) = 0")
    print("  - fibonacci(1) = 1")
    print("  - fibonacci(n) = fib(n-1) + fib(n-2)")
    print("  - Raise ValueError for negative input")

    # Iteration 1: First attempt
    print_section("ITERATION 1: First Attempt")

    task1 = TaskInput(
        id="tdd_001",
        query=f"""Write a Python function called 'fibonacci' that passes these tests:

{unit_test}

IMPORTANT: Return ONLY the raw Python code for the implementation.
Do NOT include markdown code blocks, explanations, or any text besides the code.
Just the Python function definition and any necessary imports.""",
        type="code_generation",
        difficulty="normal",
    )

    print(f"\nTask: Generate fibonacci function")
    print(f"Playbook bullets: {playbook.metadata.total_bullets}")

    # Generate code
    print_subsection("Generator: Writing Code")

    gen_output1 = generator.execute(
        task=task1,
        playbook_id=playbook.playbook_id,
    )

    print(f"\n✓ Code generated in {gen_output1.latency_ms}ms")
    print(f"  Tokens used: {gen_output1.tokens_used}")
    print(f"\nGenerated code (raw):\n")
    print(gen_output1.solution)

    # Extract clean code
    clean_code = extract_code_from_markdown(gen_output1.solution)
    if clean_code != gen_output1.solution:
        print(f"\nExtracted code (cleaned):\n")
        print(clean_code)

    # Run the test
    print_subsection("Environment: Running Tests")

    passed, stdout, stderr = run_test(gen_output1.solution, unit_test)

    if passed:
        print("✅ All tests passed!")
        env_feedback1 = EnvironmentFeedback(
            result="SUCCESS",
            feedback="All unit tests passed",
            test_report={"stdout": stdout}
        )
    else:
        print("❌ Tests failed!")
        print(f"\nTest output:\n{stdout}")
        if stderr:
            print(f"\nErrors:\n{stderr}")

        env_feedback1 = EnvironmentFeedback(
            result="FAILED",
            feedback=f"Unit tests failed: {stdout}",
            test_report={"stdout": stdout, "stderr": stderr}
        )

    # If failed, reflect and learn
    if not passed:
        print_subsection("Reflector: Analyzing Failure")

        refl_output1 = reflector.reflect(
            task=task1,
            generator_output=gen_output1,
            environment_feedback=env_feedback1,
        )

        print(f"\n✓ Analysis complete (quality: {refl_output1.quality_score:.2f})")
        if refl_output1.error_identification:
            print(f"\nError: {refl_output1.error_identification[:200]}...")
        if refl_output1.correct_approach:
            print(f"\nCorrect approach: {refl_output1.correct_approach[:200]}...")

        # Curate new knowledge
        print_subsection("Curator: Learning from Failure")

        cur_output1 = curator.curate(
            reflector_output=refl_output1,
            playbook_id=playbook.playbook_id,
        )

        print(f"\n✓ Created {len(cur_output1.delta_bullets)} new bullet(s)")
        for i, bullet in enumerate(cur_output1.delta_bullets, 1):
            print(f"\n  Bullet {i} [{bullet.section}]:")
            print(f"    {bullet.content[:150]}...")

        # Apply updates
        added_ids = curator.apply_updates(
            playbook_id=playbook.playbook_id,
            curator_output=cur_output1,
        )

        print(f"\n✓ Added {len(added_ids)} bullet(s) to playbook")

        # Iteration 2: Retry with learned knowledge
        print_section("ITERATION 2: Retry with Learned Knowledge")

        task2 = TaskInput(
            id="tdd_002",
            query=task1.query,  # Same task
            type="code_generation",
            difficulty="normal",
        )

        print(f"\nTask: Generate fibonacci function (retry)")
        print(f"Playbook bullets: {playbook.metadata.total_bullets} (learned from failure!)")

        # Generate code with learned context
        print_subsection("Generator: Writing Code (with playbook)")

        gen_output2 = generator.execute(
            task=task2,
            playbook_id=playbook.playbook_id,
        )

        print(f"\n✓ Code generated in {gen_output2.latency_ms}ms")
        print(f"  Bullets used: {len(gen_output2.bullets_used)}")
        print(f"\nGenerated code (raw):\n")
        print(gen_output2.solution)

        # Extract clean code
        clean_code2 = extract_code_from_markdown(gen_output2.solution)
        if clean_code2 != gen_output2.solution:
            print(f"\nExtracted code (cleaned):\n")
            print(clean_code2)

        # Run the test again
        print_subsection("Environment: Running Tests (Retry)")

        passed2, stdout2, stderr2 = run_test(gen_output2.solution, unit_test)

        if passed2:
            print("✅ All tests passed!")
            print("\n🎓 ACE learned from the failure and succeeded!")
        else:
            print("❌ Tests still failing")
            print(f"\nTest output:\n{stdout2}")

    # Show final playbook stats
    print_section("FINAL RESULTS")

    stats = playbook_manager.get_statistics(playbook.playbook_id)

    print("\n📊 Playbook Statistics:")
    print(f"  Version: {stats['version']}")
    print(f"  Total Bullets: {stats['total_bullets']}")

    for section, section_stats in stats['sections'].items():
        if section_stats['bullet_count'] > 0:
            print(f"\n  Section: {section}")
            print(f"    Bullets: {section_stats['bullet_count']}")

    print("\n" + "=" * 70)
    print("  🎓 TDD Loop Complete!")
    print("=" * 70)
    print("\nKey Takeaway:")
    print("  ACE can learn from test failures and improve code generation")
    print("  over iterations, building domain expertise in TDD patterns.")


if __name__ == "__main__":
    try:
        demo_tdd_loop()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
