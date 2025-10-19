#!/usr/bin/env python3
"""
Build Email Validator using ACE TDD Agent

Demonstrates how ACE benefits from existing playbook knowledge when
building similar validation tasks.
"""
import sys
sys.path.insert(0, "/home/ch_dev/ace_enterprise")

import os
from pathlib import Path

from src.agents.tdd_agent import TDDAgent

# Test specification for email validator
TEST_SPEC = """
import pytest
from email_validator import is_valid_email, get_email_parts, validate_email_domain

class TestBasicEmailValidation:
    def test_empty_email_is_invalid(self):
        assert is_valid_email("") == False

    def test_valid_simple_email(self):
        assert is_valid_email("user@example.com") == True

    def test_email_requires_at_symbol(self):
        assert is_valid_email("userexample.com") == False

    def test_email_requires_domain(self):
        assert is_valid_email("user@") == False

    def test_email_requires_username(self):
        assert is_valid_email("@example.com") == False

class TestEmailFormat:
    def test_email_allows_dots_in_username(self):
        assert is_valid_email("user.name@example.com") == True

    def test_email_allows_plus_in_username(self):
        assert is_valid_email("user+tag@example.com") == True

    def test_email_allows_hyphens_in_domain(self):
        assert is_valid_email("user@my-domain.com") == True

    def test_email_allows_subdomains(self):
        assert is_valid_email("user@mail.example.com") == True

    def test_email_rejects_spaces(self):
        assert is_valid_email("user name@example.com") == False

class TestAdvancedValidation:
    def test_email_requires_valid_tld(self):
        assert is_valid_email("user@example") == False

    def test_email_allows_long_tlds(self):
        assert is_valid_email("user@example.international") == True

    def test_email_rejects_consecutive_dots(self):
        assert is_valid_email("user..name@example.com") == False

    def test_email_rejects_starting_dot(self):
        assert is_valid_email(".user@example.com") == False

    def test_email_rejects_ending_dot(self):
        assert is_valid_email("user.@example.com") == False

class TestEmailParsing:
    def test_get_email_parts_extracts_username(self):
        username, domain = get_email_parts("user@example.com")
        assert username == "user"

    def test_get_email_parts_extracts_domain(self):
        username, domain = get_email_parts("user@example.com")
        assert domain == "example.com"

    def test_get_email_parts_handles_complex_email(self):
        username, domain = get_email_parts("user.name+tag@mail.example.com")
        assert username == "user.name+tag"
        assert domain == "mail.example.com"

class TestDomainValidation:
    def test_validate_domain_checks_format(self):
        assert validate_email_domain("example.com") == True

    def test_validate_domain_rejects_invalid(self):
        assert validate_email_domain("invalid") == False
"""


def main():
    print("\n" + "=" * 80)
    print("  BUILDING EMAIL VALIDATOR WITH ACE TDD AGENT")
    print("=" * 80)

    print("\n🎯 Goal: Build email validator benefiting from password validator knowledge")
    print("📋 Strategy: Use same TDD approach, leverage existing patterns")
    print("🤖 Expected: Faster completion due to 176 bullets of learned patterns")

    # Setup paths
    output_dir = Path("examples")
    output_dir.mkdir(exist_ok=True)

    impl_file = output_dir / "email_validator.py"
    test_file = output_dir / "test_email_validator.py"

    # Clean up existing files
    if impl_file.exists():
        impl_file.unlink()
        print(f"\n🗑️  Removed existing implementation")

    # Write test file
    test_file.write_text(TEST_SPEC)
    print(f"✓ Created test file: {test_file}")

    # Initialize TDD agent
    print("\n" + "-" * 80)
    print("  Initializing TDD Agent")
    print("-" * 80)

    # Use the existing password validator playbook to benefit from learned patterns
    agent = TDDAgent(
        language="python",
        playbook_id="pb_20251018_267",  # Password validator playbook
    )

    # Get playbook info
    from src.playbook.manager import PlaybookManager as PM
    pm_check = PM()
    playbook = pm_check.get_playbook(agent.playbook_id)

    print(f"✓ TDD Agent ready")
    print(f"  Language: {agent.language}")
    print(f"  Playbook: {agent.playbook_id}")
    print(f"  Initial knowledge: {playbook.metadata.total_bullets} bullets")
    print(f"  LLM: {agent.generator.llm_client.provider} ({agent.generator.llm_client.model})")

    # Show cross-model knowledge available
    print(f"\n📚 Knowledge available from other playbooks:")
    from src.config.settings import settings
    from src.playbook.manager import PlaybookManager

    pm = PlaybookManager()
    all_playbooks = list(pm._playbooks.values())

    print(f"  Total playbooks: {len(all_playbooks)}")
    for pb in all_playbooks[:5]:  # Show first 5
        print(f"    - {pb.playbook_id}: {pb.metadata.total_bullets} bullets ({pb.metadata.domain})")

    print(f"\n  Retrieval mode: {settings.retrieval_mode}")
    print(f"  Cross-model weight: {settings.cross_model_weight}")

    # Build with TDD
    print("\n" + "=" * 80)
    print("  BUILDING EMAIL VALIDATOR")
    print("=" * 80)

    result = agent.build_with_tdd(
        test_file=str(test_file),
        output_file=str(impl_file),
    )

    # Show results
    print("\n" + "=" * 80)
    print("  FINAL RESULTS")
    print("=" * 80)

    print(f"\n📊 Development Metrics:")
    print(f"  Tests planned: {result['total_tests']}")
    print(f"  Tests passed: {result['passed_tests']}")
    print(f"  Success rate: {result['success_rate']:.1f}%")
    print(f"  Total iterations: {result['total_iterations']}")
    print(f"  Avg iterations per test: {result['avg_iterations']:.2f}")

    print(f"\n📚 Knowledge Growth:")
    print(f"  Starting bullets: {result['initial_bullets']}")
    print(f"  Final bullets: {result['final_bullets']}")
    print(f"  New patterns learned: {result['new_bullets']}")

    if result['final_bullets'] > 0:
        print(f"\n📖 Playbook sections:")
        for section, count in result['section_counts'].items():
            if count > 0:
                print(f"    {section}: {count} bullets")

    print("\n" + "=" * 80)
    print("  🎓 Email Validator Build Complete!")
    print("=" * 80)

    # Compare with password validator
    print(f"\n📊 Comparison with Password Validator:")
    print(f"  Password validator: ~1.29 avg iterations per test")
    print(f"  Email validator:    {result['avg_iterations']:.2f} avg iterations per test")

    if result['avg_iterations'] < 1.29:
        improvement = ((1.29 - result['avg_iterations']) / 1.29) * 100
        print(f"  ✅ {improvement:.1f}% faster due to learned knowledge!")

    print(f"\n✨ Total knowledge base now: {sum(pb.metadata.total_bullets for pb in pm._playbooks.values())} bullets across {len(pm._playbooks)} playbooks")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nBuild interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Build failed: {e}")
        import traceback
        traceback.print_exc()
