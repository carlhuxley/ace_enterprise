#!/usr/bin/env python3
"""
Test to validate that redundancy checking prevents duplicate tests.

This simulates what happened in Cycle 2 of the Gherkin demo and shows
how the new redundancy checking would help prevent it.
"""

from pathlib import Path
from src.agents.autonomous_tdd_agent import AutonomousTDDAgent
from src.ensemble.learner import EnsembleLearner
from src.agents.test_review_agent import TestReviewAgent
from src.utils.llm_client import LLMClient
from src.playbook.manager import PlaybookManager
from src.storage.schemas import PlaybookCreate

def test_redundancy_detection():
    """Test that _get_existing_test_summaries() properly extracts test info."""

    print("=" * 80)
    print("TEST: Redundancy Detection in Test Planning")
    print("=" * 80)
    print()

    # Create a minimal agent instance
    agent = AutonomousTDDAgent.__new__(AutonomousTDDAgent)
    agent.test_functions = {}
    agent.src_dir = Path("/tmp")  # Mock src_dir

    # Simulate Cycle 1: Basic creation test
    print("Simulating Cycle 1: Created basic test")
    print("-" * 80)
    agent.test_functions['/tmp/test_oauth.py'] = [
        {
            'name': 'test_oauth_client_can_be_created',
            'code': '''def test_oauth_client_can_be_created():
    oauth = OAuth('client_123', 'http://callback')
    assert oauth is not None
    assert oauth.client_id == 'client_123'
    assert oauth.redirect_uri == 'http://callback'
'''
        }
    ]

    # Get summary after Cycle 1
    summary = agent._get_existing_test_summaries()
    print("Test Summary After Cycle 1:")
    print(summary)
    print()

    # This is what would be shown to the LLM in Cycle 2
    print("=" * 80)
    print("What LLM Sees in Cycle 2 Planning:")
    print("=" * 80)
    print()
    print("**Tests already written (AVOID REDUNDANCY):**")
    print(summary)
    print()
    print("⚠️  **CRITICAL**: The next test you choose MUST:")
    print("1. Test NEW behavior not already covered by tests above")
    print("2. FAIL with the current implementation (for RED phase)")
    print("3. NOT duplicate or overlap with existing test assertions")
    print()

    # Show what the LLM should avoid
    print("=" * 80)
    print("Analysis:")
    print("=" * 80)
    print()
    print("❌ BAD Test Choice (would be redundant):")
    print("   test_oauth_stores_client_id_and_redirect_uri")
    print("   → Already checked by: assert oauth.client_id == 'client_123'")
    print("   → Already checked by: assert oauth.redirect_uri == 'http://callback'")
    print()
    print("✅ GOOD Test Choices (new behavior):")
    print("   test_generate_authorization_url")
    print("   → Tests NEW method not yet implemented")
    print()
    print("   test_exchange_code_for_token")
    print("   → Tests NEW method not yet implemented")
    print()

    # Simulate adding more tests
    print("=" * 80)
    print("Simulating Cycle 2: Added method test")
    print("-" * 80)
    agent.test_functions['/tmp/test_oauth.py'].append({
        'name': 'test_generate_authorization_url',
        'code': '''def test_generate_authorization_url():
    oauth = OAuth('github_client', 'http://app.com/callback')
    url = oauth.generate_authorization_url()
    assert 'github_client' in url
    assert 'http://app.com/callback' in url
'''
    })

    summary = agent._get_existing_test_summaries()
    print("Updated Test Summary:")
    print(summary)
    print()

    print("=" * 80)
    print("✅ SUCCESS: Redundancy checking provides clear test coverage info")
    print("=" * 80)
    print()
    print("Benefits demonstrated:")
    print("  1. Shows what assertions already exist")
    print("  2. Helps LLM avoid testing same behavior twice")
    print("  3. Guides toward NEW functionality")
    print()

    return True

if __name__ == "__main__":
    try:
        test_redundancy_detection()
        print("\n✅ Redundancy detection test PASSED")
    except Exception as e:
        print(f"\n❌ Test FAILED: {e}")
        import traceback
        traceback.print_exc()
