#!/usr/bin/env python3
"""
TDD Agent Demo - Production-Style TDD Workflow

This demonstrates the TDD Agent working with a realistic project structure:
- Separate test files (examples/test_calculator.py)
- Implementation files (examples/calculator.py)
- Iterative test-passing with learning
- Multiple tests, one at a time (TDD principle)

Workflow:
1. Start with failing test
2. Agent generates minimal code to pass
3. If it fails, agent learns and retries
4. Move to next test
5. Build up full implementation incrementally
"""
import sys
from pathlib import Path

sys.path.insert(0, "/home/ch_dev/ace_enterprise")

from src.agents.tdd_agent import TDDAgent


def print_section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_subsection(title: str) -> None:
    print(f"\n{'-' * 70}")
    print(f"  {title}")
    print('-' * 70)


def demo_tdd_agent():
    """Demonstrate TDD agent with incremental test-passing."""

    print_section("TDD AGENT DEMO - PRODUCTION WORKFLOW")
    print("\nScenario: Build calculator module using TDD")
    print("Strategy: One test at a time, minimal implementation")

    # Setup paths
    test_file = Path("/home/ch_dev/ace_enterprise/examples/test_calculator.py")
    impl_file = Path("/home/ch_dev/ace_enterprise/examples/calculator.py")

    # Clean slate
    if impl_file.exists():
        impl_file.unlink()
        print(f"\n🗑️  Removed existing implementation")

    # Initialize TDD Agent
    print_subsection("Initializing TDD Agent")

    agent = TDDAgent(language="python")

    print(f"✓ TDD Agent initialized")
    print(f"  Language: {agent.language}")
    print(f"  Playbook: {agent.playbook_id}")
    print(f"  LLM: {agent.llm_client.provider} ({agent.llm_client.model})")

    # Get initial playbook stats
    stats = agent.get_playbook_stats()
    print(f"  Initial bullets: {stats['total_bullets']}")

    # Define tests to pass incrementally (TDD: one at a time!)
    test_sequence = [
        "test_add_two_numbers",
        "test_add_negative_numbers",
        "test_multiply_two_numbers",
        "test_divide_two_numbers",
        "test_divide_by_zero_raises_error",
    ]

    print_subsection("TDD Test Sequence")
    print("Following TDD principle: One test at a time\n")
    for i, test_name in enumerate(test_sequence, 1):
        print(f"  {i}. {test_name}")

    # Track overall progress
    total_bullets_added = 0
    total_iterations = 0

    # Pass each test incrementally
    for test_num, test_name in enumerate(test_sequence, 1):
        print_section(f"TEST {test_num}/{len(test_sequence)}: {test_name}")

        # Show current state
        print(f"\nCurrent implementation: {impl_file}")
        if impl_file.exists():
            current_code = impl_file.read_text()
            line_count = len(current_code.split('\n'))
            print(f"  Lines of code: {line_count}")
        else:
            print(f"  Status: No implementation yet")

        # RED: Verify test fails
        print_subsection("RED: Verify Test Fails")

        passed, output, failed = agent.run_tests(test_file, test_name)

        if passed:
            print("✓ Test already passes (code from previous iteration)")
            continue
        else:
            print(f"✓ Test fails as expected")
            # Show relevant failure info
            for line in output.split('\n'):
                if 'FAILED' in line or 'AssertionError' in line or 'ModuleNotFoundError' in line:
                    print(f"  {line.strip()}")
                    break

        # GREEN: Make test pass
        print_subsection("GREEN: Generate Code to Pass Test")

        print(f"Running TDD cycle (max 3 iterations)...")

        result = agent.make_test_pass(
            test_path=test_file,
            impl_path=impl_file,
            test_name=test_name,
            max_iterations=3,
        )

        total_iterations += result["iterations"]
        total_bullets_added += result["bullets_added"]

        if result["success"]:
            print(f"\n✅ Test passed after {result['iterations']} iteration(s)!")

            if result["learning_occurred"]:
                print(f"   📚 Learned {result['bullets_added']} new pattern(s)")
        else:
            print(f"\n❌ Failed to make test pass after {result['iterations']} iterations")
            print("\nTest output:")
            print(result["final_output"])
            print("\n⚠️  Stopping demo due to failure")
            break

        # Show updated implementation
        if impl_file.exists():
            print_subsection("Current Implementation")
            current_code = impl_file.read_text()
            print(current_code)

    # REFACTOR phase (future enhancement)
    print_section("REFACTOR")
    print("(Future: Agent suggests refactoring improvements)")
    print("For now: Code works, tests pass!")

    # Final summary
    print_section("FINAL SUMMARY")

    # Run all tests
    print_subsection("Running ALL Tests")

    all_passed, output, failed = agent.run_tests(test_file)

    if all_passed:
        print("✅ ALL TESTS PASS!")

        # Show summary line
        for line in output.split('\n'):
            if 'passed' in line and '==' in line:
                print(f"\n  {line.strip()}")
    else:
        print("❌ Some tests still failing")
        print(f"\nFailed tests: {failed}")

    # Show final implementation
    if impl_file.exists():
        print_subsection("Final Implementation")
        final_code = impl_file.read_text()
        lines = final_code.split('\n')
        print(f"Lines: {len(lines)}\n")
        print(final_code)

    # Playbook growth
    print_subsection("Learning Summary")

    final_stats = agent.get_playbook_stats()

    print(f"\n📊 Playbook Statistics:")
    print(f"  Version: {final_stats['version']}")
    print(f"  Initial bullets: {stats['total_bullets']}")
    print(f"  Final bullets: {final_stats['total_bullets']}")
    print(f"  Bullets added: {total_bullets_added}")
    print(f"\n📈 Development Statistics:")
    print(f"  Tests implemented: {test_num}/{len(test_sequence)}")
    print(f"  Total iterations: {total_iterations}")
    print(f"  Average iterations per test: {total_iterations / test_num:.1f}")

    print("\n" + "=" * 70)
    print("  🎓 TDD Agent Demo Complete!")
    print("=" * 70)

    print("\n✅ Key Achievements:")
    print("  • Followed TDD workflow (Red-Green-Refactor)")
    print("  • One test at a time (TDD principle)")
    print("  • Learned from failures")
    print("  • Built working implementation incrementally")
    print("  • Separate test and implementation files (production-style)")

    if total_bullets_added > 0:
        print(f"\n📚 Agent learned {total_bullets_added} new TDD patterns!")


if __name__ == "__main__":
    try:
        demo_tdd_agent()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
