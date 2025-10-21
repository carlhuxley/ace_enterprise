#!/usr/bin/env python3
"""
Demonstration of Ensemble Learning System.

Shows how multiple local LLMs learn collaboratively:
1. Each model executes task independently
2. Models propose bullets from their analysis
3. Cross-voting on all proposals
4. Consensus-based selection
5. Approved bullets added to shared playbook

Expected Benefits:
- 3-5x learning speed (multiple models = more diverse insights)
- Error cancellation (bad proposals get voted down)
- Higher quality (only consensus bullets survive)
- Still FREE (all local models via Ollama)
"""
import logging
import sys

sys.path.insert(0, "/home/ch_dev/ace_enterprise")

from datetime import datetime

from src.ensemble.learner import EnsembleLearner
from src.ensemble.voting import MajorityVoting, SupermajorityVoting
from src.playbook.manager import PlaybookManager
from src.storage.schemas import (
    EnvironmentFeedback,
    PlaybookCreate,
    TaskInput,
)

# Configure logging for verbose output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)


def print_section(title: str):
    """Print section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_subsection(title: str):
    """Print subsection header."""
    print("\n" + "-" * 80)
    print(f"  {title}")
    print("-" * 80)


def main():
    print_section("ENSEMBLE LEARNING SYSTEM DEMO")

    print("\nConcept: Multiple LLMs learn together through consensus")
    print("Benefits:")
    print("  - Faster learning (parallel execution on GPU)")
    print("  - Better quality (voting filters bad ideas)")
    print("  - Error cancellation (diversity catches mistakes)")
    print("  - Cloud GPU acceleration (RunPod vLLM)")

    # Configuration
    print_subsection("Configuration")

    # RunPod vLLM Configuration
    # RunPod uses port mapping: internal ports are mapped to external ports
    RUNPOD_IP = "103.196.86.55"

    # Port mapping (internal:external):
    # 8001 -> 33186
    # 8002 -> 33187
    # 8003 -> 33188

    # Use 3 different vLLM models via RunPod for diversity
    # Format: (provider, model_name, base_url)
    models = [
        ("vllm", "Qwen/Qwen2.5-Coder-1.5B-Instruct", f"http://{RUNPOD_IP}:33186"),
        ("vllm", "Qwen/Qwen2.5-1.5B-Instruct", f"http://{RUNPOD_IP}:33187"),
        ("vllm", "Qwen/Qwen2.5-Coder-0.5B-Instruct", f"http://{RUNPOD_IP}:33188"),
    ]

    print(f"Models in ensemble (RunPod vLLM):")
    for i, (provider, model, url) in enumerate(models, 1):
        print(f"  {i}. {provider}/{model}")
        print(f"      Endpoint: {url}")

    # Create or get playbook
    pm = PlaybookManager()

    # Create new playbook for ensemble demo
    playbook_create = PlaybookCreate(
        domain="python_development",
        base_model="ensemble",
    )
    playbook = pm.create_playbook(playbook_create)
    playbook_id = playbook.playbook_id

    print(f"\nPlaybook: {playbook_id}")

    # Initialize ensemble
    print_subsection("Initializing Ensemble Learner")

    ensemble = EnsembleLearner(
        models=models,
        playbook_id=playbook_id,
        voting_strategy=SupermajorityVoting(threshold=0.67),  # 2/3 approval
        similarity_threshold=0.85,
    )

    print(f"Voting strategy: Supermajority (≥66.7% approval required)")
    print(f"Similarity threshold: 0.85 (for clustering similar bullets)")

    # Example Task: Learn from a simple coding problem
    print_section("TASK 1: Learn from String Validation Problem")

    task1 = TaskInput(
        id="task_ensemble_001",
        query="Write a Python function to validate if a string is a valid email address",
        type="coding",
        context={"instructions": "Use regex pattern matching. Handle basic validation only."},
        difficulty="normal",
    )

    feedback1 = EnvironmentFeedback(
        result="SUCCESS",
        expected="Valid email validation function",
        actual="Function correctly validates emails using regex",
        feedback="Tests passed: valid emails accepted, invalid emails rejected",
    )

    print(f"\nTask: {task1.query}")
    print(f"Result: {feedback1.result}")
    print("\nExecuting ensemble learning cycle...")
    print("(This runs Generator → Reflector → Curator for each model)")
    print("Note: vLLM on RunPod allows parallel execution with good performance")

    result1 = ensemble.learn_from_task(
        task=task1,
        environment_feedback=feedback1,
        parallel=True,  # Parallel execution with vLLM on GPU
    )

    # Display results
    print_section("ENSEMBLE LEARNING RESULTS")

    print(f"\n{result1.summary()}")

    # Show approved bullets
    if result1.approved_bullets:
        print_subsection("Approved Bullets (Consensus Reached)")
        for i, bullet in enumerate(result1.approved_bullets, 1):
            print(f"\n{i}. [{bullet.section.value}]")
            print(f"   Content: {bullet.content}")
            print(f"   Proposed by: {bullet.proposed_by}")
            print(f"   Votes: {bullet.vote_counts}")
            print(f"   Approval rate: {bullet.approval_rate:.1%}")
            print(f"   Strategy: {bullet.approval_strategy}")

    # Show rejected bullets
    if result1.rejected_bullets:
        print_subsection("Rejected Bullets (Failed to Reach Consensus)")
        for i, bullet in enumerate(result1.rejected_bullets[:5], 1):  # Show first 5
            print(f"\n{i}. {bullet.content[:80]}...")
            print(f"   Approval rate: {bullet.approval_rate:.1%}")
            print(f"   Reason: Did not meet {result1.voting_strategy} threshold")

    # Show model performance
    print_subsection("Model Performance")
    for model_id, perf in result1.model_performance.items():
        print(f"\n{model_id}:")
        print(f"  Proposals made: {perf.proposals_made}")
        print(f"  Proposals approved: {perf.proposals_approved}")
        print(f"  Success rate: {perf.proposal_success_rate:.1f}%")
        print(f"  Agreement rate: {perf.agreement_rate:.1f}%")
        print(f"  Voting weight: {perf.voting_weight:.2f}")

    # Add approved bullets to playbook
    print_subsection("Adding Approved Bullets to Playbook")

    added = ensemble.add_approved_bullets_to_playbook(result1)
    print(f"\n✓ Added {added} bullets to playbook {playbook_id}")

    # Show final playbook state
    playbook = pm.get_playbook(playbook_id)
    print(f"\nFinal playbook stats:")
    print(f"  Total bullets: {playbook.metadata.total_bullets}")

    # Count bullets by section
    section_counts = {
        "strategies_and_hard_rules": len(playbook.sections.get("strategies_and_hard_rules", [])),
        "code_snippets": len(playbook.sections.get("code_snippets", [])),
        "troubleshooting_tips": len(playbook.sections.get("troubleshooting", [])),
        "domain_knowledge": len(playbook.sections.get("domain_knowledge", [])),
    }

    for section, count in section_counts.items():
        if count > 0:
            print(f"  {section}: {count}")

    print_section("TASK 2: Learn from Another Problem (Same Playbook)")

    task2 = TaskInput(
        id="task_ensemble_002",
        query="Write a Python function to check if a password is strong",
        type="coding",
        context={"instructions": "Check length ≥8, has uppercase, lowercase, digit, special char"},
        difficulty="easy",
    )

    feedback2 = EnvironmentFeedback(
        result="SUCCESS",
        expected="Strong password validator",
        actual="Function correctly validates password strength",
    )

    print(f"\nTask: {task2.query}")
    print(f"Result: {feedback2.result}")
    print("\nExecuting ensemble learning cycle...")

    result2 = ensemble.learn_from_task(
        task=task2,
        environment_feedback=feedback2,
        parallel=True,  # Parallel execution with vLLM
    )

    print(f"\n{result2.summary()}")

    # Add to playbook
    added2 = ensemble.add_approved_bullets_to_playbook(result2)
    print(f"\n✓ Added {added2} more bullets to playbook")

    # Final stats
    playbook = pm.get_playbook(playbook_id)
    print_section("FINAL PLAYBOOK STATS")
    print(f"\nPlaybook: {playbook_id}")
    print(f"Total bullets: {playbook.metadata.total_bullets}")
    print(f"Total tasks: 2")
    print(f"Models used: {len(models)}")

    # Count bullets by section
    final_section_counts = {
        "Strategies": len(playbook.sections.get("strategies_and_hard_rules", [])),
        "Code snippets": len(playbook.sections.get("code_snippets", [])),
        "Troubleshooting": len(playbook.sections.get("troubleshooting", [])),
        "Domain knowledge": len(playbook.sections.get("domain_knowledge", [])),
    }

    print(f"\nKnowledge breakdown:")
    for section, count in final_section_counts.items():
        print(f"  {section}: {count}")

    print_section("KEY INSIGHTS")

    print("\n1. EXECUTION: Models run in parallel on GPU")
    print(f"   Task 1 duration: {result1.duration_seconds:.1f}s")
    print(f"   Task 2 duration: {result2.duration_seconds:.1f}s")
    print(f"   Note: vLLM on RunPod GPU provides excellent parallel performance")

    print("\n2. QUALITY: Consensus filters bad proposals")
    total_proposed = result1.vote_results.total_bullets + result2.vote_results.total_bullets
    total_approved = result1.vote_results.approved + result2.vote_results.approved
    print(f"   Total proposed: {total_proposed}")
    print(f"   Total approved: {total_approved}")
    print(f"   Quality filter: {(1 - total_approved/total_proposed)*100:.1f}% rejected")

    print("\n3. DIVERSITY: Different models propose different insights")
    print(f"   Task 1 diversity: {result1.diversity_score:.2f}")
    print(f"   Task 2 diversity: {result2.diversity_score:.2f}")
    print(f"   (1.0 = maximum diversity, 0.0 = all identical)")

    print("\n4. CONSENSUS: Strong agreement on approved bullets")
    print(f"   Task 1 consensus strength: {result1.consensus_strength:.2f}")
    print(f"   Task 2 consensus strength: {result2.consensus_strength:.2f}")
    print(f"   (1.0 = perfect agreement, 0.0 = no agreement)")

    print("\n5. COST: RunPod GPU (~$0.29/hour for RTX 4090)")

    print_section("NEXT STEPS")

    print("\n✓ Phase 1 (MVP) Complete:")
    print("  - Parallel model execution")
    print("  - Basic cross-voting")
    print("  - Consensus building")
    print("  - Supermajority voting")

    print("\n→ Phase 2 (Coming Soon):")
    print("  - LLM-based voting with reasoning")
    print("  - Deliberative discussion on contested bullets")
    print("  - Time-boxed decision making")
    print("  - Advanced voting strategies")

    print("\n→ Phase 3 (Advanced):")
    print("  - Adaptive voting weights")
    print("  - Model specialization")
    print("  - Disagreement mining")
    print("  - Quality prediction")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()
