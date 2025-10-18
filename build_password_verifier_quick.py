#!/usr/bin/env python3
"""
Quick Password Verifier Build - Demonstrating TDD Agent

This shows the TDD Agent building a password verifier with a smaller
set of tests for faster demonstration.
"""
import sys
from pathlib import Path

sys.path.insert(0, "/home/ch_dev/ace_enterprise")

from src.agents.tdd_agent import TDDAgent


def main():
    print("=" * 80)
    print("  TDD AGENT: Building Password Verifier")
    print("=" * 80)

    # Setup
    test_file = Path("examples/test_password_verifier.py")
    impl_file = Path("examples/password_verifier.py")

    # Clean start
    if impl_file.exists():
        impl_file.unlink()
        print("\n🗑️  Removed existing implementation\n")

    # Initialize agent
    agent = TDDAgent(language="python")

    print(f"✓ TDD Agent initialized")
    print(f"  Playbook: {agent.playbook_id}\n")

    # Key tests to implement (focused set)
    tests = [
        ("test_empty_password_is_invalid", "Reject empty passwords"),
        ("test_short_password_is_invalid", "Enforce 8+ characters"),
        ("test_password_requires_uppercase", "Require uppercase"),
        ("test_password_requires_lowercase", "Require lowercase"),
        ("test_password_requires_digit", "Require digit"),
        ("test_password_requires_special_character", "Require special char"),
        ("test_common_passwords_are_rejected", "Reject common passwords"),
        ("test_get_password_requirements", "Report requirements"),
    ]

    print(f"Implementing {len(tests)} tests:\n")

    for i, (test_name, desc) in enumerate(tests, 1):
        print(f"[{i}/{len(tests)}] {desc}")
        print(f"      Test: {test_name}")

        # Check if already passes
        passed_before, _, _ = agent.run_tests(test_file, test_name)

        if passed_before:
            print("      ✓ Already passes\n")
            continue

        # Make it pass
        result = agent.make_test_pass(
            test_path=test_file,
            impl_path=impl_file,
            test_name=test_name,
            max_iterations=3,
        )

        if result["success"]:
            print(f"      ✅ Passed after {result['iterations']} iteration(s)")
            if result["bullets_added"] > 0:
                print(f"      📚 Learned {result['bullets_added']} pattern(s)")
        else:
            print(f"      ❌ Failed after {result['iterations']} iterations")

        print()

    # Final results
    print("=" * 80)
    print("  RESULTS")
    print("=" * 80)

    # Run all tests
    all_passed, output, failed = agent.run_tests(test_file)

    if all_passed:
        print("\n✅ ALL 18 TESTS PASS!\n")
    else:
        passing = 18 - len(failed)
        print(f"\n📊 {passing}/18 tests passing")
        if failed:
            print(f"\n❌ Failed tests:")
            for f in failed[:5]:  # Show first 5
                print(f"  - {f}")

    # Show implementation
    if impl_file.exists():
        print("\n📄 Final Implementation:\n")
        code = impl_file.read_text()
        print(code)

        lines = [l for l in code.split('\n') if l.strip()]
        funcs = code.count('def ')
        print(f"\n📊 {len(lines)} lines, {funcs} function(s)")

    print("\n" + "=" * 80)
    print("  ✨ Demo Complete!")
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
