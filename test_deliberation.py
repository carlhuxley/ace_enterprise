#!/usr/bin/env python3
"""
Test Deliberative Discussion System

Quick test to verify that deliberation works for contested bullets.
"""
import sys
sys.path.insert(0, "/home/ch_dev/ace_enterprise")

import logging

from src.ensemble.learner import EnsembleLearner
from src.ensemble.voting import MajorityVoting
from src.playbook.manager import PlaybookManager
from src.storage.schemas import (
    EnvironmentFeedback,
    PlaybookCreate,
    TaskInput,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    print("\n" + "=" * 80)
    print("  TESTING DELIBERATIVE DISCUSSION SYSTEM")
    print("=" * 80)

    print("\n📊 Using 3 local Ollama models:")
    models = [
        ("ollama", "qwen2.5-coder:1.5b"),
        ("ollama", "qwen2.5-coder:0.5b"),
        ("ollama", "deepseek-coder:1.3b"),
    ]

    for i, (provider, model) in enumerate(models, 1):
        print(f"  {i}. {model}")

    # Create playbook
    print("\n✓ Creating shared playbook...")
    pm = PlaybookManager()
    playbook = pm.create_playbook(
        PlaybookCreate(domain="test_deliberation", base_model="ensemble_local")
    )

    print(f"✓ Playbook created: {playbook.playbook_id}")

    # Create ensemble learner with deliberation ENABLED
    print("\n✓ Initializing ensemble learner with deliberation...")
    learner = EnsembleLearner(
        models=models,
        playbook_id=playbook.playbook_id,
        voting_strategy=MajorityVoting(),
        enable_deliberation=True,  # Enable deliberation
        deliberation_threshold_low=0.3,  # Lower threshold to catch more bullets
        deliberation_threshold_high=0.7,  # Higher threshold to catch more bullets
        max_deliberation_rounds=2,
    )

    print("✓ Deliberation settings:")
    print(f"   Enabled: {learner.enable_deliberation}")
    print(f"   Threshold: {learner.deliberation_threshold_low:.0%}-{learner.deliberation_threshold_high:.0%}")
    print(f"   Max rounds: {learner.max_deliberation_rounds}")

    # Create a test task that might produce contested bullets
    task = TaskInput(
        id="test_task_deliberation",
        query="Write a function to validate user input. Should we use regex or a library?",
        type="agent_execution",
        difficulty="normal",
        context={
            "requirements": [
                "Function should validate email, phone, and URL inputs",
                "Consider performance and maintainability",
                "Decide between regex patterns vs validation libraries",
            ]
        },
    )

    # Create feedback
    feedback = EnvironmentFeedback(
        result="FAILED",
        actual="Validation accepted invalid email 'test@'",
        expected="Should reject malformed emails",
        feedback="Regex pattern doesn't handle edge cases properly. Consider using a validation library instead.",
    )

    print("\n" + "=" * 80)
    print("  RUNNING ENSEMBLE LEARNING WITH DELIBERATION")
    print("=" * 80)

    print(f"\n📝 Task: {task.query}")
    print(f"📋 Deliberation will trigger for bullets with {learner.deliberation_threshold_low:.0%}-{learner.deliberation_threshold_high:.0%} approval")

    try:
        result = learner.learn_from_task(
            task=task,
            environment_feedback=feedback,
            parallel=True,
        )

        # Display results
        print("\n" + "=" * 80)
        print("  DELIBERATION RESULTS")
        print("=" * 80)

        # Check which bullets had deliberation
        deliberated_bullets = [b for b in result.consensus_bullets if b.deliberation_rounds > 0]

        print(f"\n📊 Summary:")
        print(f"   Total bullets: {len(result.consensus_bullets)}")
        print(f"   Bullets deliberated: {len(deliberated_bullets)}")
        print(f"   Approved: {result.vote_results.approved}")
        print(f"   Rejected: {result.vote_results.rejected}")
        print(f"   Avg deliberation rounds: {result.vote_results.avg_deliberation_rounds:.1f}")

        if deliberated_bullets:
            print(f"\n💬 Deliberated Bullets:")
            for i, bullet in enumerate(deliberated_bullets, 1):
                print(f"\n{i}. Bullet (deliberation rounds: {bullet.deliberation_rounds})")
                print(f"   Content: {bullet.content[:100]}{'...' if len(bullet.content) > 100 else ''}")
                print(f"   Final approval: {bullet.approval_rate:.0%}")
                print(f"   Status: {'✅ Approved' if bullet.approved else '❌ Rejected' if bullet.approved is False else '⏸️ Pending'}")

                print(f"\n   Votes:")
                for vote in bullet.votes:
                    vote_emoji = {"approve": "✅", "reject": "❌", "abstain": "⏸️"}.get(vote.vote.value, "?")
                    print(f"      {vote_emoji} {vote.model_id}: {vote.vote.value.upper()} (conf: {vote.confidence:.2f})")
                    print(f"         {vote.reasoning[:120]}{'...' if len(vote.reasoning) > 120 else ''}")
        else:
            print(f"\n⚠️  No bullets required deliberation (all had clear consensus)")

        print("\n" + "=" * 80)
        print("  TEST COMPLETE")
        print("=" * 80)

        if deliberated_bullets:
            print("\n✅ Deliberation system is working!")
            print(f"   - {len(deliberated_bullets)} bullets underwent discussion")
            print(f"   - Average {result.vote_results.avg_deliberation_rounds:.1f} rounds per bullet")
            print("   - Models had opportunity to reconsider based on peers' reasoning")
        else:
            print("\n⚠️  No deliberation occurred")
            print("   This could mean:")
            print("   - All bullets had clear consensus (no contested votes)")
            print("   - Try adjusting deliberation thresholds")
            print("   - Or test with a more controversial task")

        return result

    except Exception as e:
        print(f"\n❌ Ensemble learning failed: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    try:
        result = main()
        if result:
            print("\n🎉 Test completed successfully!")
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
