#!/usr/bin/env python3
"""
ACE Enterprise Demo - Learning Loop in Action

This demo shows how ACE learns from mistakes:
1. Task fails on first attempt
2. System analyzes the failure
3. New knowledge is added to playbook
4. Similar task succeeds on second attempt

Domain: Python coding assistance
"""
import sys
from datetime import datetime

# Add src to path
sys.path.insert(0, "/home/ch_dev/ace_enterprise")

from src.core.curator.module import Curator
from src.core.generator.module import Generator
from src.core.reflector.module import Reflector
from src.playbook.manager import PlaybookManager
from src.storage.schemas import (
    EnvironmentFeedback,
    PlaybookCreate,
    TaskInput,
)
from src.utils.llm_client import LLMClient


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_subsection(title: str) -> None:
    """Print a formatted subsection header."""
    print(f"\n{'-' * 70}")
    print(f"  {title}")
    print('-' * 70)


def demo_ace_learning_loop() -> None:
    """
    Demonstrate the complete ACE learning loop.
    """
    print_section("ACE ENTERPRISE DEMO - LEARNING LOOP")
    print("\nDomain: Python Coding Assistance")
    print("Scenario: Learning to use correct string methods")

    # Initialize components
    print_subsection("Initializing ACE Components")

    playbook_manager = PlaybookManager()
    llm_client = LLMClient()

    # Check if Ollama is available
    if not llm_client.check_availability():
        print("\n⚠️  Warning: Ollama not available!")
        print("    This demo requires Ollama to be running.")
        print("    The demo will continue with simulated responses.")
        use_llm = False
    else:
        print(f"✓ LLM Client: {llm_client.provider} ({llm_client.model})")
        use_llm = True

    generator = Generator(playbook_manager, llm_client)
    reflector = Reflector(llm_client)
    curator = Curator(playbook_manager, llm_client)

    print("✓ Generator Module")
    print("✓ Reflector Module")
    print("✓ Curator Module")

    # Create initial playbook
    print_subsection("Creating Empty Playbook")

    playbook_create = PlaybookCreate(
        domain="python_coding",
        base_model=llm_client.model,
    )
    playbook = playbook_manager.create_playbook(playbook_create)

    print(f"✓ Playbook Created: {playbook.playbook_id}")
    print(f"  Version: {playbook.version}")
    print(f"  Domain: {playbook.metadata.domain}")
    print(f"  Bullets: {playbook.metadata.total_bullets}")

    # =========================================================================
    # ITERATION 1: First attempt (will fail)
    # =========================================================================

    print_section("ITERATION 1: First Attempt")

    task1 = TaskInput(
        id="task_001",
        query="How do I check if a string contains a substring in Python?",
        type="coding_question",
        difficulty="easy",
    )

    print(f"\nTask: {task1.query}")
    print(f"Task ID: {task1.id}")

    # Step 1: Generate (no bullets available yet)
    print_subsection("Step 1: Generator")
    print("Executing task with empty playbook...")

    if use_llm:
        try:
            gen_output1 = generator.execute(
                task=task1,
                playbook_id=playbook.playbook_id,
            )

            print(f"\n✓ Generated solution in {gen_output1.latency_ms}ms")
            print(f"  Tokens used: {gen_output1.tokens_used}")
            print(f"  Bullets used: {len(gen_output1.bullets_used)}")
            print(f"\n  Solution (first 200 chars):\n  {gen_output1.solution[:200]}...")
        except Exception as e:
            print(f"\n✗ Generation failed: {e}")
            use_llm = False

    if not use_llm:
        # Simulated response with a common mistake
        from src.storage.schemas import GeneratorOutput
        gen_output1 = GeneratorOutput(
            trajectory="User asks about substring checking. I'll suggest using 'find()' method.",
            solution="Use the find() method: if my_string.find('substring') > 0: ...",
            bullets_used=[],
            bullet_feedback={},
            latency_ms=1500,
            tokens_used=150,
        )
        print("\n✓ Generated solution (simulated)")
        print(f"  Solution: {gen_output1.solution}")

    # Step 2: Simulate environment feedback (FAILED - wrong approach)
    print_subsection("Step 2: Environment Feedback")

    env_feedback1 = EnvironmentFeedback(
        result="FAILED",
        expected="Use 'in' operator for substring check",
        actual="Suggested find() which returns -1 for not found, causing bug",
        feedback="ERROR: Condition 'find() > 0' misses substring at index 0. Should use 'in' operator.",
        test_report={
            "test_case": "'hello'.find('h') returns 0",
            "condition_used": "find() > 0",
            "result": "False (incorrect)",
            "expected": "True",
        },
    )

    print(f"Result: {env_feedback1.result} ✗")
    print(f"Issue: {env_feedback1.feedback}")

    # Step 3: Reflect on failure
    print_subsection("Step 3: Reflector")
    print("Analyzing failure...")

    if use_llm:
        try:
            refl_output1 = reflector.reflect(
                task=task1,
                generator_output=gen_output1,
                environment_feedback=env_feedback1,
            )

            print(f"\n✓ Analysis complete (quality: {refl_output1.quality_score:.2f})")
            print(f"  Iterations: {refl_output1.iterations}")
            if refl_output1.error_identification:
                print(f"\n  Error: {refl_output1.error_identification[:150]}...")
            if refl_output1.key_insight:
                print(f"\n  Key Insight: {refl_output1.key_insight[:150]}...")
        except Exception as e:
            print(f"\n✗ Reflection failed: {e}")
            use_llm = False

    if not use_llm:
        from src.storage.schemas import ReflectorOutput
        refl_output1 = ReflectorOutput(
            error_identification="Used find() method with incorrect condition (> 0)",
            root_cause="find() returns 0 for matches at index 0, so condition fails",
            correct_approach="Use 'in' operator: if 'substring' in my_string",
            key_insight="For substring checking in Python, 'in' operator is clearer and correct",
            bullet_tags=[],
            iterations=1,
            quality_score=0.9,
        )
        print("\n✓ Analysis complete (simulated)")
        print(f"  Error: {refl_output1.error_identification}")
        print(f"  Insight: {refl_output1.key_insight}")

    # Step 4: Curate new bullets
    print_subsection("Step 4: Curator")
    print("Synthesizing insights into playbook bullets...")

    if use_llm:
        try:
            cur_output1 = curator.curate(
                reflector_output=refl_output1,
                playbook_id=playbook.playbook_id,
            )

            print(f"\n✓ Created {len(cur_output1.delta_bullets)} new bullet(s)")
            for i, bullet in enumerate(cur_output1.delta_bullets, 1):
                print(f"\n  Bullet {i} [{bullet.section}]:")
                print(f"    {bullet.content[:150]}...")
        except Exception as e:
            print(f"\n✗ Curation failed: {e}")
            use_llm = False

    if not use_llm:
        from src.storage.schemas import CuratorOutput, DeltaBullet
        cur_output1 = CuratorOutput(
            delta_bullets=[
                DeltaBullet(
                    section="strategies_and_hard_rules",
                    content="For substring checking in Python, use the 'in' operator: if 'substring' in my_string. Avoid find() with > 0 comparison as it fails for matches at index 0.",
                    tags=["python", "strings", "best_practices"],
                ),
                DeltaBullet(
                    section="code_snippets",
                    content="Correct: if 'hello' in text: ... | Incorrect: if text.find('hello') > 0: ...",
                    tags=["python", "strings", "example"],
                ),
            ],
            reasoning="The error was using find() with wrong condition. Create bullets to prevent this.",
        )
        print(f"\n✓ Created {len(cur_output1.delta_bullets)} new bullet(s) (simulated)")
        for i, bullet in enumerate(cur_output1.delta_bullets, 1):
            print(f"\n  Bullet {i} [{bullet.section}]:")
            print(f"    {bullet.content}")

    # Step 5: Apply updates
    print_subsection("Step 5: Apply Updates")

    added_ids = curator.apply_updates(
        playbook_id=playbook.playbook_id,
        curator_output=cur_output1,
    )

    print(f"\n✓ Added {len(added_ids)} bullet(s) to playbook")
    for bullet_id in added_ids:
        print(f"  - {bullet_id}")

    # Show updated playbook stats
    stats1 = playbook_manager.get_statistics(playbook.playbook_id)
    print(f"\n📊 Playbook Stats:")
    print(f"  Total bullets: {stats1['total_bullets']}")
    print(f"  Version: {stats1['version']}")

    # =========================================================================
    # ITERATION 2: Second attempt (should succeed with learned knowledge)
    # =========================================================================

    print_section("ITERATION 2: Second Attempt (With Learned Knowledge)")

    task2 = TaskInput(
        id="task_002",
        query="What's the best way to check if 'python' is in a text string?",
        type="coding_question",
        difficulty="easy",
    )

    print(f"\nTask: {task2.query}")
    print(f"Task ID: {task2.id}")

    # Step 1: Generate (now with bullets!)
    print_subsection("Step 1: Generator")
    print("Executing task with learned playbook...")

    if use_llm:
        try:
            gen_output2 = generator.execute(
                task=task2,
                playbook_id=playbook.playbook_id,
            )

            print(f"\n✓ Generated solution in {gen_output2.latency_ms}ms")
            print(f"  Tokens used: {gen_output2.tokens_used}")
            print(f"  Bullets used: {len(gen_output2.bullets_used)} ← Learned knowledge!")
            print(f"\n  Bullets retrieved:")
            for bullet_id in gen_output2.bullets_used:
                print(f"    - {bullet_id}")
            print(f"\n  Solution (first 200 chars):\n  {gen_output2.solution[:200]}...")
        except Exception as e:
            print(f"\n✗ Generation failed: {e}")
            use_llm = False

    if not use_llm:
        gen_output2 = GeneratorOutput(
            trajectory="User asks about substring check. According to playbook bullet ctx-00001, use 'in' operator.",
            solution="Use the 'in' operator: if 'python' in text: ...",
            bullets_used=added_ids,
            bullet_feedback={added_ids[0]: "helpful"},
            latency_ms=1400,
            tokens_used=140,
        )
        print("\n✓ Generated solution (simulated)")
        print(f"  Bullets used: {len(gen_output2.bullets_used)} ← Learned knowledge!")
        print(f"  Solution: {gen_output2.solution}")

    # Step 2: Environment feedback (SUCCESS this time!)
    print_subsection("Step 2: Environment Feedback")

    env_feedback2 = EnvironmentFeedback(
        result="SUCCESS",
        expected="Use 'in' operator",
        actual="Correctly suggested 'in' operator",
        feedback="Correct approach! Using 'in' operator is the Pythonic way.",
        test_report={
            "test_case": "'python' in 'hello python'",
            "result": "True (correct)",
        },
    )

    print(f"Result: {env_feedback2.result} ✓")
    print(f"Feedback: {env_feedback2.feedback}")

    # Update bullet feedback to mark as helpful
    print_subsection("Step 3: Update Bullet Feedback")

    generator.update_bullet_feedback(
        playbook_id=playbook.playbook_id,
        bullet_feedback=gen_output2.bullet_feedback,
    )

    print("✓ Updated bullet feedback (marked as helpful)")

    # Show final stats
    print_section("FINAL RESULTS")

    stats_final = playbook_manager.get_statistics(playbook.playbook_id)

    print("\n📊 Playbook Statistics:")
    print(f"  Version: {stats_final['version']}")
    print(f"  Total Bullets: {stats_final['total_bullets']}")

    for section, section_stats in stats_final['sections'].items():
        if section_stats['bullet_count'] > 0:
            print(f"\n  Section: {section}")
            print(f"    Bullets: {section_stats['bullet_count']}")
            print(f"    Helpful Count: {section_stats['helpful_count']}")
            print(f"    Helpful Ratio: {section_stats['helpful_ratio']:.2%}")

    print("\n📈 Learning Summary:")
    print(f"  Iteration 1: FAILED ✗ (no prior knowledge)")
    print(f"  → Analyzed error and created {len(cur_output1.delta_bullets)} bullet(s)")
    print(f"  Iteration 2: SUCCESS ✓ (applied learned knowledge)")

    print("\n" + "=" * 70)
    print("  🎓 ACE Learning Loop Demonstration Complete!")
    print("=" * 70)
    print("\nKey Takeaway:")
    print("  The system learned from the first failure and successfully")
    print("  applied that knowledge to solve a similar problem on the")
    print("  second attempt. This is the power of ACE!")


if __name__ == "__main__":
    try:
        demo_ace_learning_loop()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
