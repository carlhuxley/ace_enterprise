#!/usr/bin/env python3
"""
ACE TDD Loop Demo - Harder Challenge

A more complex test that will likely fail initially,
demonstrating the learning loop.
"""
import sys
import subprocess
import tempfile
from pathlib import Path
import re

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
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_subsection(title: str) -> None:
    print(f"\n{'-' * 70}")
    print(f"  {title}")
    print('-' * 70)


def extract_code_from_markdown(text: str) -> str:
    """Extract Python code from markdown code blocks."""
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

    return text.strip()


def run_test(code: str, test_code: str) -> tuple[bool, str, str]:
    """Run a unit test against generated code."""
    clean_code = extract_code_from_markdown(code)

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


def demo_tdd_harder():
    """Demonstrate TDD loop with a harder problem"""

    print_section("ACE TDD LOOP - HARDER CHALLENGE")
    print("\nScenario: Implement a Roman numeral converter")
    print("Challenge: Has many edge cases that require learning")

    # Initialize ACE
    print_subsection("Initializing ACE Components")

    playbook_manager = PlaybookManager()
    llm_client = LLMClient()

    if not llm_client.check_availability():
        print("\n⚠️  Warning: LLM not available!")
        return

    print(f"✓ LLM Client: {llm_client.provider} ({llm_client.model})")

    generator = Generator(playbook_manager, llm_client)
    reflector = Reflector(llm_client)
    curator = Curator(playbook_manager, llm_client)

    # Create playbook
    playbook = playbook_manager.create_playbook(
        PlaybookCreate(
            domain="python_tdd_roman_numerals",
            base_model=llm_client.model,
        )
    )

    print(f"✓ Playbook Created: {playbook.playbook_id}")

    # Define unit test with tricky cases
    unit_test = """
import pytest
from implementation import int_to_roman

def test_basic_numerals():
    \"\"\"Test basic Roman numerals\"\"\"
    assert int_to_roman(1) == "I"
    assert int_to_roman(5) == "V"
    assert int_to_roman(10) == "X"

def test_additive_combinations():
    \"\"\"Test additive combinations\"\"\"
    assert int_to_roman(3) == "III"
    assert int_to_roman(6) == "VI"
    assert int_to_roman(7) == "VII"
    assert int_to_roman(8) == "VIII"

def test_subtractive_notation():
    \"\"\"Test subtractive notation (tricky!)\"\"\"
    assert int_to_roman(4) == "IV"
    assert int_to_roman(9) == "IX"
    assert int_to_roman(40) == "XL"
    assert int_to_roman(90) == "XC"
    assert int_to_roman(400) == "CD"
    assert int_to_roman(900) == "CM"

def test_complex_numbers():
    \"\"\"Test complex combinations\"\"\"
    assert int_to_roman(49) == "XLIX"
    assert int_to_roman(94) == "XCIV"
    assert int_to_roman(1994) == "MCMXCIV"
    assert int_to_roman(3999) == "MMMCMXCIX"

def test_edge_cases():
    \"\"\"Test edge cases\"\"\"
    with pytest.raises(ValueError):
        int_to_roman(0)
    with pytest.raises(ValueError):
        int_to_roman(-1)
    with pytest.raises(ValueError):
        int_to_roman(4000)
"""

    print_subsection("Unit Test Definition")
    print("Test requirements:")
    print("  - Basic numerals (I, V, X, L, C, D, M)")
    print("  - Additive combinations (III = 3)")
    print("  - Subtractive notation (IV = 4, IX = 9, etc.)")
    print("  - Complex numbers (1994 = MCMXCIV)")
    print("  - Edge cases (0, negative, >3999 raise ValueError)")
    print("\n⚠️  This is tricky! Subtractive notation often trips up first attempts.")

    max_iterations = 3

    for iteration in range(1, max_iterations + 1):
        print_section(f"ITERATION {iteration}")

        task = TaskInput(
            id=f"tdd_roman_{iteration:03d}",
            query=f"""Write a Python function called 'int_to_roman' that converts integers to Roman numerals.

Test suite:
{unit_test}

Requirements:
- Handle numbers 1-3999
- Use proper subtractive notation (IV, IX, XL, XC, CD, CM)
- Raise ValueError for invalid inputs (0, negative, >3999)

IMPORTANT: Return ONLY the raw Python code.
No markdown blocks, no explanations.""",
            type="code_generation",
            difficulty="hard",
        )

        print(f"\nAttempt {iteration} of {max_iterations}")
        print(f"Playbook bullets: {playbook.metadata.total_bullets}")

        # Generate code
        print_subsection(f"Generator: Writing Code (Attempt {iteration})")

        gen_output = generator.execute(
            task=task,
            playbook_id=playbook.playbook_id,
        )

        print(f"\n✓ Code generated in {gen_output.latency_ms}ms")
        print(f"  Bullets used: {len(gen_output.bullets_used)}")

        clean_code = extract_code_from_markdown(gen_output.solution)
        print(f"\nGenerated code:\n{clean_code}\n")

        # Run tests
        print_subsection("Environment: Running Tests")

        passed, stdout, stderr = run_test(gen_output.solution, unit_test)

        if passed:
            print("✅ All tests passed!")
            print(f"\n🎓 Success on iteration {iteration}!")

            if iteration > 1:
                print(f"\nACE learned from {iteration - 1} failure(s) and succeeded!")

            break
        else:
            print("❌ Tests failed!")

            # Show which tests failed
            if "FAILED" in stdout:
                print("\nFailed tests:")
                for line in stdout.split('\n'):
                    if 'FAILED' in line or 'ERROR' in line or 'AssertionError' in line:
                        print(f"  {line}")

            env_feedback = EnvironmentFeedback(
                result="FAILED",
                feedback=f"Unit tests failed on iteration {iteration}",
                test_report={"stdout": stdout, "stderr": stderr, "iteration": iteration}
            )

            # Reflect and learn
            print_subsection("Reflector: Analyzing Failure")

            refl_output = reflector.reflect(
                task=task,
                generator_output=gen_output,
                environment_feedback=env_feedback,
            )

            print(f"\n✓ Analysis complete (quality: {refl_output.quality_score:.2f})")
            if refl_output.error_identification:
                print(f"\nError identified:\n  {refl_output.error_identification[:300]}...")
            if refl_output.correct_approach:
                print(f"\nCorrect approach:\n  {refl_output.correct_approach[:300]}...")

            # Curate knowledge
            print_subsection("Curator: Learning from Failure")

            cur_output = curator.curate(
                reflector_output=refl_output,
                playbook_id=playbook.playbook_id,
            )

            print(f"\n✓ Created {len(cur_output.delta_bullets)} new bullet(s)")
            for i, bullet in enumerate(cur_output.delta_bullets, 1):
                print(f"\n  Bullet {i} [{bullet.section}]:")
                print(f"    {bullet.content[:200]}...")

            # Apply updates
            added_ids = curator.apply_updates(
                playbook_id=playbook.playbook_id,
                curator_output=cur_output,
            )

            print(f"\n✓ Knowledge updated: {len(added_ids)} bullet(s) added")

            if iteration < max_iterations:
                print(f"\n⟳ Retrying with learned knowledge...")
            else:
                print(f"\n⚠️  Reached max iterations ({max_iterations})")

    # Show final stats
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
    print("  🎓 TDD Learning Loop Complete!")
    print("=" * 70)


if __name__ == "__main__":
    try:
        demo_tdd_harder()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
