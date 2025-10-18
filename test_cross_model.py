#!/usr/bin/env python3
"""
Test Cross-Model Retrieval

Demonstrates the difference between model-specific and cross-model hybrid retrieval.
"""
import sys
sys.path.insert(0, "/home/ch_dev/ace_enterprise")

from src.config.settings import settings
from src.core.generator.module import Generator
from src.playbook.manager import PlaybookManager
from src.storage.schemas import TaskInput
from src.utils.llm_client import LLMClient


def print_section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_subsection(title: str) -> None:
    print(f"\n{'-' * 70}")
    print(f"  {title}")
    print('-' * 70)


def test_cross_model_retrieval():
    """Test and compare retrieval modes."""

    print_section("CROSS-MODEL RETRIEVAL TEST")

    # Initialize
    pm = PlaybookManager()
    llm = LLMClient()

    print(f"\nCurrent Configuration:")
    print(f"  Retrieval Mode: {settings.retrieval_mode}")
    print(f"  Cross-Model Weight: {settings.cross_model_weight}")

    # Check available playbooks
    print_subsection("Available Playbooks")

    playbooks = pm._playbooks
    if not playbooks:
        print("❌ No playbooks found! Run a demo first to generate playbooks.")
        return

    for pb_id, pb in playbooks.items():
        print(f"\n  {pb_id}")
        print(f"    Domain: {pb.metadata.domain}")
        print(f"    Model: {pb.metadata.base_model}")
        print(f"    Bullets: {pb.metadata.total_bullets}")

    # Find playbooks in same domain
    domains = {}
    for pb_id, pb in playbooks.items():
        domain = pb.metadata.domain
        if domain not in domains:
            domains[domain] = []
        domains[domain].append((pb_id, pb))

    print_subsection("Domain Analysis")

    for domain, pbs in domains.items():
        print(f"\n  Domain: {domain}")
        print(f"  Playbooks: {len(pbs)}")
        for pb_id, pb in pbs:
            print(f"    - {pb_id} ({pb.metadata.base_model}, {pb.metadata.total_bullets} bullets)")

    # Test retrieval
    if len(playbooks) < 2:
        print("\n⚠️  Only one playbook available.")
        print("   Cross-model retrieval requires multiple playbooks in the same domain.")
        print("   Run more demos to create additional playbooks!")
        return

    # Choose first playbook as primary
    primary_id = list(playbooks.keys())[0]
    primary_pb = playbooks[primary_id]

    print_subsection(f"Testing with Primary Playbook: {primary_id}")
    print(f"  Domain: {primary_pb.metadata.domain}")
    print(f"  Model: {primary_pb.metadata.base_model}")

    # Create test task
    task = TaskInput(
        id="cross_model_test",
        query="How do I write a function to check if a string is a palindrome?",
        type="coding_question",
        difficulty="easy",
    )

    print(f"\nTest Query: {task.query}")

    # Create generator
    generator = Generator(pm, llm)

    # Test Mode 1: Model-Specific
    print_section("MODE 1: MODEL-SPECIFIC RETRIEVAL")
    print("Only using bullets from the primary playbook")

    # Temporarily set mode
    original_mode = settings.retrieval_mode
    settings.retrieval_mode = "model_specific"

    try:
        result1 = generator.execute(task, primary_id)
        print(f"\n✓ Retrieved {len(result1.bullets_used)} bullets")
        print(f"  Source: {primary_id} only")
        if result1.bullets_used:
            print(f"  Bullet IDs: {', '.join(result1.bullets_used[:5])}")
            if len(result1.bullets_used) > 5:
                print(f"              ... and {len(result1.bullets_used) - 5} more")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test Mode 2: Cross-Model Hybrid
    print_section("MODE 2: CROSS-MODEL HYBRID RETRIEVAL")
    print(f"Using bullets from primary + other playbooks in domain '{primary_pb.metadata.domain}'")
    print(f"Secondary bullets weighted at {settings.cross_model_weight}x")

    settings.retrieval_mode = "cross_model_hybrid"

    try:
        result2 = generator.execute(task, primary_id)
        print(f"\n✓ Retrieved {len(result2.bullets_used)} bullets")
        print(f"  May include bullets from multiple models in same domain")
        if result2.bullets_used:
            print(f"  Bullet IDs: {', '.join(result2.bullets_used[:5])}")
            if len(result2.bullets_used) > 5:
                print(f"              ... and {len(result2.bullets_used) - 5} more")

        # Compare
        print_subsection("Comparison")
        print(f"\n  Model-Specific:   {len(result1.bullets_used)} bullets")
        print(f"  Cross-Model:      {len(result2.bullets_used)} bullets")

        unique_to_cross = set(result2.bullets_used) - set(result1.bullets_used)
        if unique_to_cross:
            print(f"\n  {len(unique_to_cross)} additional bullet(s) from cross-model retrieval:")
            for bullet_id in list(unique_to_cross)[:3]:
                print(f"    - {bullet_id}")
        else:
            print(f"\n  No additional bullets from cross-model (query may not match other playbooks)")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        # Restore original mode
        settings.retrieval_mode = original_mode

    print_section("TEST COMPLETE")
    print("\nTo switch modes, update .env file:")
    print("  RETRIEVAL_MODE=model_specific      # Use only model-specific playbook")
    print("  RETRIEVAL_MODE=cross_model_hybrid  # Use model + domain knowledge")
    print("\nAdjust cross-model weight (0.0 - 1.0):")
    print("  CROSS_MODEL_WEIGHT=0.5  # 50% weight for other models' bullets")


if __name__ == "__main__":
    try:
        test_cross_model_retrieval()
    except KeyboardInterrupt:
        print("\n\nTest interrupted")
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
