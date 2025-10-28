#!/usr/bin/env python3
"""
Demo: Test Review Agent

Shows how to validate test quality before running TDD cycle.
"""
import sys
sys.path.insert(0, "/home/ch_dev/ace_enterprise")

from pathlib import Path
from src.agents.test_review_agent import TestReviewAgent


def main():
    print("\n" + "=" * 80)
    print("  TEST REVIEW AGENT DEMO")
    print("=" * 80)
    print("\n💡 NOTE: Agent focuses on SUBSTANCE (assertions, coverage, isolation)")
    print("        NOT style (AAA comments, assertion messages, formatting)")

    # Example 1: Clean code style (no AAA comments)
    print("\n📝 Example 1: Clean Code Style (No AAA Comments)")
    print("-" * 80)

    clean_test = '''
def test_email_validation_accepts_valid_formats():
    """Test that valid email formats are accepted."""
    valid_emails = [
        "test@example.com",
        "user.name@domain.co.uk",
        "first+last@company.org",
    ]

    for email in valid_emails:
        result = validate_email(email)
        assert result is True


def test_email_validation_rejects_missing_at_symbol():
    """Test that emails without @ are rejected."""
    result = validate_email("notanemail.com")
    assert result is False


def test_email_validation_rejects_empty_input():
    """Test that empty string is rejected."""
    assert validate_email("") is False


def test_email_validation_handles_none():
    """Test that None input is handled gracefully."""
    assert validate_email(None) is False
'''

    # Write to temp file
    clean_path = Path("/tmp/test_clean_email.py")
    clean_path.write_text(clean_test)

    # Review it
    agent = TestReviewAgent(use_llm_analysis=False)  # Disable LLM for faster demo
    result = agent.review_test_file(clean_path)

    print(result.format_report())
    print("\n✅ PASSES: Has assertions, covers edge cases, tests one concept each")
    print("✅ NO COMPLAINTS: About missing AAA comments or assertion messages")

    # Example 1b: AAA style (also acceptable)
    print("\n\n📝 Example 1b: AAA Comment Style (Also Acceptable)")
    print("-" * 80)

    aaa_test = '''
def test_email_validation_accepts_valid_format():
    """Test that valid email formats are accepted."""
    # Arrange
    valid_email = "test@example.com"

    # Act
    result = validate_email(valid_email)

    # Assert
    assert result is True, f"Expected {valid_email} to be valid"


def test_email_validation_rejects_empty_input():
    """Test that empty string is rejected."""
    # Arrange
    empty = ""

    # Act
    result = validate_email(empty)

    # Assert
    assert result is False, "Expected empty string to be rejected"
'''

    aaa_path = Path("/tmp/test_aaa_email.py")
    aaa_path.write_text(aaa_test)

    result_aaa = agent.review_test_file(aaa_path)
    print(result_aaa.format_report())
    print("\n✅ SAME SCORE: AAA comments don't affect quality rating")
    print("✅ Your choice: Use AAA comments if your team prefers them")

    # Example 2: Substantive issues
    print("\n\n📝 Example 2: Substantive Issues (Missing Edge Cases)")
    print("-" * 80)

    bad_test = '''
def test_email():
    assert validate("test@example.com")
    assert not validate("bad")
    assert validate("another@test.com")
    assert validate("user@domain.co.uk")
    assert not validate("nope")
'''

    bad_path = Path("/tmp/test_incomplete_email.py")
    bad_path.write_text(bad_test)

    result2 = agent.review_test_file(bad_path)
    print(result2.format_report())
    print("\n⚠️  FLAGGED: Missing edge cases (empty, None) - substantive issue")
    print("✅ NOT FLAGGED: Lack of AAA comments - style preference")

    # Example 3: Critical issue (no assertions)
    print("\n\n📝 Example 3: Critical Issue (No Assertions)")
    print("-" * 80)

    critical_test = '''
def test_parse_age():
    """Test that age string is converted to integer."""
    age_str = "25"
    result = parse_age(age_str)
    # Forgot to assert!
'''

    critical_path = Path("/tmp/test_critical_age.py")
    critical_path.write_text(critical_test)

    result3 = agent.review_test_file(critical_path)
    print(result3.format_report())
    print("\n🔴 CRITICAL: No assertions - test doesn't verify anything!")
    print("❌ BLOCKS TDD: Score too low, must fix before proceeding")

    # Summary
    print("\n\n" + "=" * 80)
    print("  SUMMARY: SUBSTANCE OVER STYLE")
    print("=" * 80)
    print("\n✅ What Agent Checks (SUBSTANCE):")
    print("   1. ✅ Does test have assertions? (verifies behavior)")
    print("   2. ✅ Does test cover edge cases? (empty, null, invalid, boundary)")
    print("   3. ✅ Does test isolate one concept? (not testing 5 things)")
    print("   4. ✅ Is test name clear? (describes what's being tested)")
    print("\n❌ What Agent Ignores (STYLE):")
    print("   1. ❌ AAA comments (your choice - with or without)")
    print("   2. ❌ Assertion messages (nice but not required)")
    print("   3. ❌ Formatting preferences (indentation, spacing)")
    print("\n💡 Philosophy:")
    print("   - Write tests YOUR way (clean code OR AAA style)")
    print("   - Agent validates EFFECTIVENESS not STYLE")
    print("   - ACE learns from test QUALITY not formatting")
    print("\n📚 Result: HIGH-QUALITY learning without style wars!")
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
