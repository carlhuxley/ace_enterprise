#!/usr/bin/env python3
"""
Demo: TDD with Test Review

Shows complete workflow:
1. Human writes test
2. Test Review Agent validates quality
3. Human improves test based on feedback
4. TDD Agent makes test pass
5. Patterns saved to playbook
"""
import sys
sys.path.insert(0, "/home/ch_dev/ace_enterprise")

from pathlib import Path
from src.agents.test_review_agent import TestReviewAgent
from src.agents.tdd_agent import TDDAgent


def main():
    print("\n" + "=" * 80)
    print("  TDD WITH TEST REVIEW - COMPLETE WORKFLOW")
    print("=" * 80)

    # Step 1: Human writes test
    print("\n📝 Step 1: Human Writes Test")
    print("-" * 80)

    # Let's write a test for a calculator function
    test_code = '''"""Test calculator module."""
import pytest


def test_add_positive_numbers():
    """Test addition of two positive numbers."""
    # Arrange
    a = 5
    b = 3

    # Act
    result = add(a, b)

    # Assert
    assert result == 8, f"Expected 5 + 3 = 8, got {result}"


def test_add_negative_numbers():
    """Test addition of negative numbers."""
    # Arrange
    a = -5
    b = -3

    # Act
    result = add(a, b)

    # Assert
    assert result == -8, f"Expected -5 + -3 = -8, got {result}"


def test_add_zero():
    """Test addition with zero."""
    # Arrange
    a = 5
    b = 0

    # Act
    result = add(a, b)

    # Assert
    assert result == 5, f"Expected 5 + 0 = 5, got {result}"


def test_add_handles_none():
    """Test that add handles None gracefully."""
    # Arrange
    a = 5
    b = None

    # Act & Assert
    with pytest.raises(TypeError):
        add(a, b)
'''

    test_path = Path("/tmp/test_calculator.py")
    test_path.write_text(test_code)

    print(f"✅ Test written: {test_path}")
    print(f"   - 4 test cases")
    print(f"   - Tests positive, negative, zero, and None")

    # Step 2: Review test quality
    print("\n🔍 Step 2: Test Review Agent Validates Quality")
    print("-" * 80)

    reviewer = TestReviewAgent(use_llm_analysis=False)  # Disable LLM for speed
    review_result = reviewer.review_test_file(test_path)

    print(f"\n📊 Quality Score: {review_result.overall_score:.1%}")

    if review_result.strengths:
        print("\n✅ Strengths:")
        for strength in review_result.strengths:
            print(f"   - {strength}")

    if review_result.issues:
        print(f"\n⚠️  Issues ({len(review_result.issues)}):")
        for issue in review_result.issues:
            emoji = {"critical": "🔴", "warning": "🟡", "suggestion": "🔵"}[issue.severity]
            print(f"   {emoji} {issue.message}")
            if issue.suggestion:
                print(f"      💡 {issue.suggestion}")

    if review_result.edge_cases_covered:
        print(f"\n✅ Edge Cases Covered: {', '.join(review_result.edge_cases_covered)}")

    if review_result.edge_cases_missing:
        print(f"\n❌ Edge Cases Missing: {', '.join(review_result.edge_cases_missing)}")

    # Step 3: Decision point
    print("\n🎯 Step 3: Quality Gate")
    print("-" * 80)

    if review_result.is_good_quality(threshold=0.7):
        print("✅ Test quality PASSED (>70%) - Safe to proceed with TDD!")
    else:
        print("❌ Test quality FAILED (<70%) - Should improve test first")
        print("\n💡 In real workflow, human would revise test based on feedback")
        print("   Then re-review until quality threshold met")

    # Step 4: TDD Agent makes test pass
    print("\n🤖 Step 4: TDD Agent Makes Test Pass")
    print("-" * 80)

    if review_result.is_good_quality():
        print("\n✓ Creating TDD Agent...")

        tdd_agent = TDDAgent(language="python")

        print(f"✓ Playbook: {tdd_agent.playbook_id}")

        # Create implementation file path
        impl_path = Path("/tmp/calculator.py")

        print(f"✓ Implementation will be written to: {impl_path}")
        print("\n⏳ Running TDD cycle (this may take a minute)...")

        try:
            result = tdd_agent.make_test_pass(
                test_path=test_path,
                impl_path=impl_path,
                max_iterations=3,
            )

            print("\n📊 TDD Results:")
            print(f"   Success: {result['success']}")
            print(f"   Iterations: {result['iterations']}")
            print(f"   Bullets added: {result['bullets_added']}")
            print(f"   Learning occurred: {result['learning_occurred']}")

            if result['success']:
                print("\n✅ All tests PASSED!")
                print(f"\n📄 Generated implementation:")
                print("-" * 80)
                print(impl_path.read_text())
                print("-" * 80)
            else:
                print("\n❌ Tests still failing after max iterations")
                print("\n🔍 Final test output:")
                print(result['final_output'][-500:])  # Last 500 chars

        except Exception as e:
            print(f"\n❌ TDD cycle failed: {e}")
            import traceback
            traceback.print_exc()

        # Step 5: Check playbook learning
        print("\n📚 Step 5: Playbook Learning")
        print("-" * 80)

        stats = tdd_agent.get_playbook_stats()
        print(f"   Total bullets: {stats.get('total_bullets', 0)}")
        print(f"   By section:")
        for section, count in stats.get('bullets_by_section', {}).items():
            print(f"      - {section}: {count}")

        print("\n💡 Patterns learned from this TDD cycle are now in playbook!")
        print("   Future TDD cycles will leverage this knowledge")

    # Summary
    print("\n\n" + "=" * 80)
    print("  WORKFLOW SUMMARY")
    print("=" * 80)
    print("""
This workflow ensures:
1. ✅ Human writes tests (you control what's tested)
2. ✅ Automated review catches issues (before wasting time)
3. ✅ Quality gate prevents bad tests from teaching ACE
4. ✅ TDD agent learns from HIGH-QUALITY tests only
5. ✅ Playbook grows stronger with reliable patterns

The Test Review Agent answers your question:
   "How do I make sure I'm writing good tests?"

Answer: Let ACE validate your test quality BEFORE using it for learning!

This gives you:
   - Immediate feedback on test quality
   - Specific suggestions for improvement
   - Confidence that ACE learns from good examples
   - Protection against learning from bad patterns
""")
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted")
    except Exception as e:
        print(f"\n\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
