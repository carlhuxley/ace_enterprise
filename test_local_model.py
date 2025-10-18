#!/usr/bin/env python3
"""
Test TDD Agent with Local Qwen2.5-Coder Model

Compare local model performance against OpenAI.
"""
import sys
from pathlib import Path

sys.path.insert(0, "/home/ch_dev/ace_enterprise")

from src.agents.tdd_agent import TDDAgent
from src.utils.llm_client import LLMClient


def print_section(title: str) -> None:
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print('=' * 80)


def test_local_model():
    """Test TDD Agent with local Ollama model."""

    print_section("LOCAL MODEL TEST - Qwen2.5-Coder 32B")

    # Create simple test file
    test_dir = Path("examples/local_test")
    test_dir.mkdir(exist_ok=True)

    test_file = test_dir / "test_string_utils.py"
    impl_file = test_dir / "string_utils.py"

    # Write a simple test
    test_file.write_text("""
import pytest

def test_reverse_string():
    from string_utils import reverse_string
    assert reverse_string("hello") == "olleh"
    assert reverse_string("") == ""
    assert reverse_string("a") == "a"

def test_is_palindrome():
    from string_utils import is_palindrome
    assert is_palindrome("racecar") is True
    assert is_palindrome("hello") is False
    assert is_palindrome("") is True
    assert is_palindrome("A") is True

def test_count_vowels():
    from string_utils import count_vowels
    assert count_vowels("hello") == 2
    assert count_vowels("AEIOU") == 5
    assert count_vowels("xyz") == 0
    assert count_vowels("") == 0
""")

    # Clean implementation
    if impl_file.exists():
        impl_file.unlink()

    print("\n📝 Test Suite Created:")
    print("  - test_reverse_string")
    print("  - test_is_palindrome")
    print("  - test_count_vowels")

    # Initialize with LOCAL model
    print_section("INITIALIZING LOCAL MODEL")

    print("Connecting to Ollama...")
    # Using smallest model to demonstrate learning loop better
    # Smaller model = more mistakes = more learning opportunities!
    llm = LLMClient(provider="ollama", model="qwen3:1.7b")

    if not llm.check_availability():
        print("❌ Ollama not available!")
        print("   Make sure Ollama is running: ollama serve")
        return False

    print(f"✓ Connected to {llm.provider}")
    print(f"✓ Model: {llm.model}")

    agent = TDDAgent(llm_client=llm, language="python")
    print(f"✓ TDD Agent initialized")
    print(f"  Playbook: {agent.playbook_id}")

    # Test each function
    tests = [
        ("test_reverse_string", "Reverse a string"),
        ("test_is_palindrome", "Check if palindrome"),
        ("test_count_vowels", "Count vowels in string"),
    ]

    print_section("RUNNING TDD CYCLE WITH LOCAL MODEL")

    total_time = 0
    success_count = 0

    for i, (test_name, desc) in enumerate(tests, 1):
        print(f"\n[{i}/{len(tests)}] {desc}")
        print(f"      Test: {test_name}")

        import time
        start = time.time()

        result = agent.make_test_pass(
            test_path=test_file,
            impl_path=impl_file,
            test_name=test_name,
            max_iterations=3,
        )

        elapsed = time.time() - start
        total_time += elapsed

        if result["success"]:
            print(f"      ✅ Passed in {elapsed:.1f}s ({result['iterations']} iteration(s))")
            success_count += 1
        else:
            print(f"      ❌ Failed after {elapsed:.1f}s ({result['iterations']} iterations)")

    # Final verification
    print_section("VERIFICATION")

    all_passed, output, failed = agent.run_tests(test_file)

    if all_passed:
        print("\n✅ ALL TESTS PASS!")
    else:
        print(f"\n📊 {3 - len(failed)}/3 tests passing")

    # Show generated code
    if impl_file.exists():
        print_section("GENERATED CODE")
        code = impl_file.read_text()
        print(f"\n{code}")

    # Performance summary
    print_section("PERFORMANCE SUMMARY")

    print(f"\n🤖 Model: {llm.model}")
    print(f"📊 Success Rate: {success_count}/{len(tests)} ({success_count/len(tests)*100:.0f}%)")
    print(f"⏱️  Total Time: {total_time:.1f}s")
    print(f"⏱️  Avg Time/Test: {total_time/len(tests):.1f}s")
    print(f"🔄 Total Iterations: {sum([r[1]['iterations'] for r in enumerate(tests)])}")

    print("\n💡 Comparison Notes:")
    print("  - Local model runs on your hardware (no API costs)")
    print("  - Speed depends on your GPU")
    print("  - Privacy: all data stays local")
    print("  - Quality: Compare this output to OpenAI results")

    return all_passed


if __name__ == "__main__":
    try:
        success = test_local_model()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
