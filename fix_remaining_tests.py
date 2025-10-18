#!/usr/bin/env python3
"""
Fix Remaining Password Verifier Tests

Use the TDD Agent to implement the missing features:
1. get_password_strength() - Calculate password strength
2. min_length parameter support - Custom minimum length
3. Whitespace rejection - No spaces/tabs/newlines allowed
"""
import sys
from pathlib import Path

sys.path.insert(0, "/home/ch_dev/ace_enterprise")

from src.agents.tdd_agent import TDDAgent


def main():
    print("=" * 80)
    print("  FIXING REMAINING PASSWORD VERIFIER TESTS")
    print("=" * 80)

    # Setup
    test_file = Path("examples/test_password_verifier.py")
    impl_file = Path("examples/password_verifier.py")

    # Initialize agent (will use existing implementation)
    agent = TDDAgent(language="python")

    print(f"\n✓ TDD Agent initialized")
    print(f"  Playbook: {agent.playbook_id}")

    # Show current status
    print("\n📊 Current Status:")
    all_passed, output, failed = agent.run_tests(test_file)

    passing = 17 - len(failed)
    print(f"  Tests passing: {passing}/17")

    if failed:
        print(f"\n❌ Failed tests ({len(failed)}):")
        for f in failed:
            test_name = f.split("::")[-1]
            print(f"  - {test_name}")

    # Tests to fix
    remaining_tests = [
        ("test_whitespace_in_password_is_invalid", "Reject whitespace in passwords"),
        ("test_validate_with_custom_min_length", "Support custom min_length parameter"),
        ("test_password_strength_weak", "Calculate weak strength"),
        ("test_password_strength_medium", "Calculate medium strength"),
        ("test_password_strength_strong", "Calculate strong strength"),
    ]

    print(f"\n🔧 Fixing {len(remaining_tests)} tests:\n")

    for i, (test_name, desc) in enumerate(remaining_tests, 1):
        print(f"[{i}/{len(remaining_tests)}] {desc}")
        print(f"      Test: {test_name}")

        # Check current status
        passed_before, _, _ = agent.run_tests(test_file, test_name)

        if passed_before:
            print("      ✓ Already passes\n")
            continue

        print("      ⚠️  Currently failing - fixing...")

        # Make it pass
        result = agent.make_test_pass(
            test_path=test_file,
            impl_path=impl_file,
            test_name=test_name,
            max_iterations=3,
        )

        if result["success"]:
            print(f"      ✅ Fixed after {result['iterations']} iteration(s)")
            if result["bullets_added"] > 0:
                print(f"      📚 Learned {result['bullets_added']} pattern(s)")
        else:
            print(f"      ❌ Still failing after {result['iterations']} iterations")
            print(f"      Error: {result['final_output'][-200:]}")

        print()

    # Final verification
    print("=" * 80)
    print("  FINAL VERIFICATION")
    print("=" * 80)

    all_passed, output, failed = agent.run_tests(test_file)

    if all_passed:
        print("\n✅ ALL 17 TESTS PASSING!")
    else:
        passing = 17 - len(failed)
        print(f"\n📊 {passing}/17 tests passing")

        if failed:
            print(f"\n❌ Still failing ({len(failed)}):")
            for f in failed:
                print(f"  - {f.split('::')[-1]}")

    # Show final implementation
    print("\n" + "=" * 80)
    print("  FINAL IMPLEMENTATION")
    print("=" * 80)

    code = impl_file.read_text()
    lines = [l for l in code.split('\n') if l.strip()]
    funcs = code.count('def ')

    print(f"\n📄 File: {impl_file}")
    print(f"📊 Stats: {len(lines)} lines, {funcs} function(s)")
    print(f"\n{code}")

    print("\n" + "=" * 80)
    print("  ✨ Complete!")
    print("=" * 80)

    return all_passed


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
