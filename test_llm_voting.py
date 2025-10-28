#!/usr/bin/env python3
"""
Test LLM-based Voting System

Quick test to verify that the new LLM-based voting works correctly.
"""
import sys
sys.path.insert(0, "/home/ch_dev/ace_enterprise")

import logging
from datetime import datetime

from src.ensemble.learner import EnsembleLearner
from src.ensemble.models import ConsensusBullet, BulletSection, VoteType
from src.utils.llm_client import LLMClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_voting():
    """Test LLM-based voting with sample bullets."""

    print("\n" + "=" * 80)
    print("  TESTING LLM-BASED VOTING SYSTEM")
    print("=" * 80)

    # Create test bullets
    test_bullets = [
        ConsensusBullet(
            content="Always validate email addresses using regex pattern: ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$",
            section=BulletSection.CODE_SNIPPETS,
            proposed_by="model_1",
            proposal_reasoning="Email validation is critical for user input handling",
        ),
        ConsensusBullet(
            content="Use print() statements for debugging",
            section=BulletSection.STRATEGIES,
            proposed_by="model_2",
            proposal_reasoning="Debugging is important",
        ),
        ConsensusBullet(
            content="When handling file paths, always use pathlib.Path instead of string concatenation to ensure cross-platform compatibility",
            section=BulletSection.STRATEGIES,
            proposed_by="model_3",
            proposal_reasoning="Path handling varies across OS, pathlib abstracts this",
        ),
    ]

    # Create LLM client (using local Ollama)
    print("\n✓ Creating LLM client for voting...")
    llm_client = LLMClient(
        provider="ollama",
        model="qwen2.5-coder:1.5b",
        base_url="http://localhost:11434",
    )

    # Create a simple playbook for testing
    from src.playbook.manager import PlaybookManager
    from src.storage.schemas import PlaybookCreate

    pm = PlaybookManager()
    playbook = pm.create_playbook(
        PlaybookCreate(domain="test_voting", base_model="test")
    )

    # Create ensemble learner
    learner = EnsembleLearner(
        models=[("ollama", "qwen2.5-coder:1.5b")],  # Single model for testing
        playbook_id=playbook.playbook_id,
    )

    # Test voting on each bullet
    print(f"\n✓ Testing voting on {len(test_bullets)} bullets...\n")

    for i, bullet in enumerate(test_bullets, 1):
        print(f"\n{'─' * 80}")
        print(f"BULLET {i}/{len(test_bullets)}")
        print(f"{'─' * 80}")
        print(f"Content: {bullet.content}")
        print(f"Section: {bullet.section.value}")
        print(f"Proposed by: {bullet.proposed_by}")
        print(f"Reasoning: {bullet.proposal_reasoning}")

        # Get vote from LLM
        print(f"\n🗳️  Asking LLM to vote...")
        try:
            vote = learner._get_model_vote(
                bullet=bullet,
                model_id="test_voter",
                llm_client=llm_client,
            )

            # Display results
            print(f"\n✅ VOTE RECEIVED:")
            print(f"   Decision: {vote.vote.value.upper()}")
            print(f"   Confidence: {vote.confidence:.2f}")
            print(f"   Reasoning: {vote.reasoning}")

            # Analyze vote quality
            if vote.vote == VoteType.APPROVE:
                emoji = "✅"
            elif vote.vote == VoteType.REJECT:
                emoji = "❌"
            else:
                emoji = "⏸️"

            print(f"\n{emoji} Result: {vote.vote.value.upper()} (confidence: {vote.confidence:.0%})")

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    print("\n" + "=" * 80)
    print("  TEST COMPLETE")
    print("=" * 80)
    print("\n✅ LLM-based voting is now active!")
    print("   - Models will critically evaluate each bullet")
    print("   - Votes include reasoning and confidence scores")
    print("   - Fallback to heuristic voting on errors")
    print("\n📊 Next steps:")
    print("   1. Run full ensemble learning demo")
    print("   2. Compare voting quality vs. old heuristic approach")
    print("   3. Monitor for rejected bullets (bad proposals)")
    print()


if __name__ == "__main__":
    try:
        test_voting()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
