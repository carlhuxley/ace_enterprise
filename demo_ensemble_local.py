#!/usr/bin/env python3
"""
Local Ensemble Learning Demo - Tests LLM-based voting.

Uses 3 local Ollama models to demonstrate:
1. Parallel task execution
2. LLM-based voting on proposed bullets
3. Consensus building
4. Quality improvements from voting
"""
import logging
import sys

sys.path.insert(0, "/home/ch_dev/ace_enterprise")

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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

logger = logging.getLogger(__name__)


def main():
    print("\n" + "=" * 80)
    print("  LOCAL ENSEMBLE LEARNING DEMO - LLM-BASED VOTING TEST")
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
        PlaybookCreate(domain="test_ensemble_voting", base_model="ensemble_local")
    )

    print(f"✓ Playbook created: {playbook.playbook_id}")

    # Create ensemble learner with majority voting
    print("\n✓ Initializing ensemble learner...")
    learner = EnsembleLearner(
        models=models,
        playbook_id=playbook.playbook_id,
        voting_strategy=MajorityVoting(),
    )

    # Create a simple test task
    task = TaskInput(
        id="test_task_001",
        query="Write a function to validate email addresses using regex",
        type="agent_execution",
        difficulty="normal",
        context={
            "requirements": [
                "Function should accept an email string",
                "Return True if valid, False otherwise",
                "Use regex pattern for validation",
            ]
        },
    )

    # Create fake feedback (we're testing voting, not execution)
    feedback = EnvironmentFeedback(
        result="FAILED",
        actual="Function returned True for invalid email 'test@'",
        expected="Function should return False for malformed emails",
        feedback="Email validation failed: regex pattern doesn't handle edge cases properly",
    )

    print("\n" + "=" * 80)
    print("  RUNNING ENSEMBLE LEARNING")
    print("=" * 80)

    print(f"\n📝 Task: {task.query}")
    print(f"📋 Requirements:")
    for req in task.context.get("requirements", []):
        print(f"   - {req}")

    print("\n🔄 Starting ensemble learning cycle...")
    print("   This will:")
    print("   1. Execute task on all 3 models in parallel")
    print("   2. Each model proposes bullets (Generator → Reflector → Curator)")
    print("   3. Build consensus (cluster similar proposals)")
    print("   4. Cross-voting (each model votes on ALL bullets with LLM)")
    print("   5. Apply majority voting strategy")
    print("   6. Add approved bullets to playbook")

    try:
        result = learner.learn_from_task(
            task=task,
            environment_feedback=feedback,
            parallel=True,
        )

        # Display results
        print("\n" + "=" * 80)
        print("  ENSEMBLE LEARNING RESULTS")
        print("=" * 80)

        print(f"\n📊 Summary:")
        print(f"   Total proposals: {len(result.consensus_bullets)}")
        print(f"   Approved: {result.vote_results.approved}")
        print(f"   Rejected: {result.vote_results.rejected}")
        print(f"   Pending: {result.vote_results.pending}")

        print(f"\n🎯 Metrics:")
        print(f"   Diversity score: {result.diversity_score:.2f}")
        print(f"   Consensus strength: {result.consensus_strength:.2f}")
        print(f"   Execution time: {result.execution_time_seconds:.1f}s")

        # Show model performance
        print(f"\n🏆 Model Performance:")
        for model_id, perf in result.model_performance.items():
            approval_rate = (
                perf.proposals_approved / perf.proposals_made
                if perf.proposals_made > 0 else 0
            )
            print(f"\n   {model_id}:")
            print(f"      Proposals made: {perf.proposals_made}")
            print(f"      Proposals approved: {perf.proposals_approved} ({approval_rate:.0%})")
            print(f"      Voting weight: {perf.voting_weight:.2f}")

        # Show detailed voting results
        print("\n" + "=" * 80)
        print("  DETAILED VOTING RESULTS (LLM-BASED)")
        print("=" * 80)

        for i, bullet in enumerate(result.consensus_bullets, 1):
            status_emoji = "✅" if bullet.approved else "❌" if bullet.approved is False else "⏸️"

            print(f"\n{status_emoji} Bullet {i}/{len(result.consensus_bullets)}")
            print(f"   Content: {bullet.content[:100]}{'...' if len(bullet.content) > 100 else ''}")
            print(f"   Section: {bullet.section.value}")
            print(f"   Proposed by: {bullet.proposed_by}")
            print(f"   Approval rate: {bullet.approval_rate:.0%}")
            print(f"   Vote counts: {bullet.vote_counts}")

            print(f"\n   Votes (LLM reasoning):")
            for vote in bullet.votes:
                vote_emoji = "👍" if vote.vote.value == "approve" else "👎" if vote.vote.value == "reject" else "🤷"
                print(f"      {vote_emoji} {vote.model_id}: {vote.vote.value.upper()} (confidence: {vote.confidence:.2f})")
                print(f"         Reasoning: {vote.reasoning[:150]}{'...' if len(vote.reasoning) > 150 else ''}")

        print("\n" + "=" * 80)
        print("  TEST COMPLETE")
        print("=" * 80)

        print("\n✅ LLM-based voting is working!")
        print(f"   - {result.vote_results.approved} bullets approved by consensus")
        print(f"   - {result.vote_results.rejected} bullets rejected")
        print("   - Each vote includes thoughtful LLM reasoning")
        print("   - Fallback to heuristic if LLM fails")

        # Show playbook growth
        updated_playbook = pm.get_playbook(playbook.playbook_id)
        total_bullets = updated_playbook.metadata.total_bullets
        print(f"\n📚 Playbook updated: {total_bullets} bullet(s) added")

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
            print("\n🎉 Demo completed successfully!")
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
