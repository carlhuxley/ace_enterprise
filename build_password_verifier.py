#!/usr/bin/env python3
"""
Build Password Verifier using TDD Agent

This script demonstrates using the TDD Agent to build a real feature
incrementally, following TDD principles.

The password verifier will be built one test at a time, showing:
- True TDD workflow (Red-Green-Refactor)
- Code evolution as requirements are added
- Any learning that occurs from failures
"""
import sys
from pathlib import Path

sys.path.insert(0, "/home/ch_dev/ace_enterprise")

from src.agents.tdd_agent import TDDAgent


def print_section(title: str) -> None:
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print('=' * 80)


def print_subsection(title: str) -> None:
    print(f"\n{'-' * 80}")
    print(f"  {title}")
    print('-' * 80)


def build_password_verifier():
    """Build password verifier incrementally using TDD."""

    print_section("BUILDING PASSWORD VERIFIER WITH TDD AGENT")
    print("\n🎯 Goal: Build a production-ready password verifier")
    print("📋 Strategy: Implement one test at a time")
    print("🤖 Agent: ACE TDD Agent with learning")

    # Setup paths
    test_file = Path("/home/ch_dev/ace_enterprise/examples/test_password_verifier.py")
    impl_file = Path("/home/ch_dev/ace_enterprise/examples/password_verifier.py")

    # Clean slate
    if impl_file.exists():
        impl_file.unlink()
        print(f"\n🗑️  Removed existing implementation")

    # Initialize TDD Agent
    print_subsection("Initializing TDD Agent")

    agent = TDDAgent(language="python")

    stats = agent.get_playbook_stats()

    print(f"✓ TDD Agent ready")
    print(f"  Language: {agent.language}")
    print(f"  Playbook: {agent.playbook_id}")
    print(f"  Initial knowledge: {stats['total_bullets']} bullets")
    print(f"  LLM: {agent.llm_client.provider} ({agent.llm_client.model})")

    # Define test sequence (following TDD: simple to complex)
    test_sequence = [
        # Phase 1: Basic validation
        ("test_empty_password_is_invalid", "Reject empty passwords"),
        ("test_short_password_is_invalid", "Enforce minimum length"),
        ("test_minimum_length_password_is_valid", "Accept valid length"),

        # Phase 2: Character requirements
        ("test_password_requires_uppercase", "Require uppercase letter"),
        ("test_password_requires_lowercase", "Require lowercase letter"),
        ("test_password_requires_digit", "Require digit"),
        ("test_password_requires_special_character", "Require special character"),

        # Phase 3: Enhanced validation
        ("test_accepts_various_special_characters", "Accept various special chars"),
        ("test_whitespace_in_password_is_invalid", "Reject whitespace"),
        ("test_common_passwords_are_rejected", "Reject common passwords"),

        # Phase 4: Advanced features
        ("test_get_password_requirements", "Report requirement status"),
        ("test_get_password_requirements_all_met", "Report all requirements met"),
        ("test_password_strength_weak", "Calculate weak strength"),
        ("test_password_strength_medium", "Calculate medium strength"),
        ("test_password_strength_strong", "Calculate strong strength"),
        ("test_validate_with_custom_min_length", "Support custom min length"),
        ("test_very_long_password_is_valid", "Accept very long passwords"),
    ]

    print_subsection("Test Implementation Plan")
    print(f"\nTotal tests to implement: {len(test_sequence)}\n")

    for i, (test_name, description) in enumerate(test_sequence, 1):
        print(f"  {i:2d}. {description:40s} [{test_name}]")

    # Track progress
    total_iterations = 0
    total_bullets_added = 0
    failed_tests = []
    phase_markers = {
        0: "Phase 1: Basic Validation",
        3: "Phase 2: Character Requirements",
        7: "Phase 3: Enhanced Validation",
        10: "Phase 4: Advanced Features",
    }

    # Implement each test
    for test_num, (test_name, description) in enumerate(test_sequence):

        # Print phase markers
        if test_num in phase_markers:
            print_section(phase_markers[test_num])

        print(f"\n[{test_num + 1}/{len(test_sequence)}] {description}")
        print(f"Test: {test_name}")

        # Show current implementation size
        if impl_file.exists():
            code = impl_file.read_text()
            lines = len([l for l in code.split('\n') if l.strip() and not l.strip().startswith('#')])
            funcs = code.count('def ')
            print(f"Current implementation: {lines} lines, {funcs} function(s)")
        else:
            print("Current implementation: None")

        # RED: Check if test fails
        passed_before, _, _ = agent.run_tests(test_file, test_name)

        if passed_before:
            print("  ✓ Already passes (covered by previous implementation)")
            continue

        print("  ✓ Test fails (RED) - ready to implement")

        # GREEN: Make test pass
        result = agent.make_test_pass(
            test_path=test_file,
            impl_path=impl_file,
            test_name=test_name,
            max_iterations=3,
        )

        total_iterations += result["iterations"]
        total_bullets_added += result["bullets_added"]

        if result["success"]:
            print(f"  ✅ Test passes (GREEN) after {result['iterations']} iteration(s)")

            if result["bullets_added"] > 0:
                print(f"  📚 Learned {result['bullets_added']} new pattern(s)")
        else:
            print(f"  ❌ Failed after {result['iterations']} iterations")
            failed_tests.append(test_name)

            # Show error details
            print("\n  Error output:")
            for line in result["final_output"].split('\n')[-10:]:
                if line.strip():
                    print(f"    {line}")

            print("\n  ⚠️  Continuing with remaining tests...")

    # Final summary
    print_section("FINAL RESULTS")

    # Run all tests
    print_subsection("Running Complete Test Suite")

    all_passed, output, failed = agent.run_tests(test_file)

    if all_passed:
        print("✅ ALL TESTS PASS!")

        # Show summary
        for line in output.split('\n'):
            if 'passed' in line and '==' in line:
                print(f"\n  {line.strip()}")
    else:
        print(f"❌ {len(failed)} test(s) still failing:")
        for f in failed:
            print(f"  - {f}")

    # Show final implementation
    print_subsection("Final Implementation")

    if impl_file.exists():
        code = impl_file.read_text()
        lines = code.split('\n')
        non_empty = [l for l in lines if l.strip() and not l.strip().startswith('#')]
        funcs = code.count('def ')

        print(f"\n📄 File: {impl_file}")
        print(f"📊 Stats: {len(non_empty)} lines of code, {funcs} function(s)")
        print(f"\n{code}")
    else:
        print("\n❌ No implementation file created")

    # Learning summary
    print_subsection("Learning & Development Statistics")

    final_stats = agent.get_playbook_stats()

    print(f"\n📚 Playbook Growth:")
    print(f"  Initial bullets: {stats['total_bullets']}")
    print(f"  Final bullets: {final_stats['total_bullets']}")
    print(f"  New patterns learned: {total_bullets_added}")

    print(f"\n📈 Development Metrics:")
    print(f"  Tests planned: {len(test_sequence)}")
    print(f"  Tests passed: {len(test_sequence) - len(failed_tests)}")
    print(f"  Success rate: {((len(test_sequence) - len(failed_tests)) / len(test_sequence)) * 100:.1f}%")
    print(f"  Total iterations: {total_iterations}")
    print(f"  Average iterations per test: {total_iterations / len(test_sequence):.2f}")

    if failed_tests:
        print(f"\n⚠️  Failed tests: {len(failed_tests)}")
        for test in failed_tests:
            print(f"  - {test}")

    # Playbook details
    if final_stats['total_bullets'] > 0:
        print(f"\n📖 Playbook Contents:")
        for section, section_stats in final_stats['sections'].items():
            if section_stats['bullet_count'] > 0:
                print(f"\n  {section}:")
                print(f"    Bullets: {section_stats['bullet_count']}")
                if section_stats.get('helpful_count', 0) > 0:
                    print(f"    Helpful: {section_stats['helpful_count']}")

    print("\n" + "=" * 80)
    print("  🎓 Password Verifier Build Complete!")
    print("=" * 80)

    print("\n✨ Key Achievements:")
    print("  ✓ Built real-world feature using TDD")
    print("  ✓ Followed Red-Green-Refactor cycle")
    print("  ✓ Implemented tests incrementally (simple → complex)")
    print("  ✓ Production-ready code with separate test files")

    if total_bullets_added > 0:
        print(f"  ✓ Agent learned {total_bullets_added} new TDD patterns")

    return all_passed


if __name__ == "__main__":
    try:
        success = build_password_verifier()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Build interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Build failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
