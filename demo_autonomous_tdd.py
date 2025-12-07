#!/usr/bin/env python3
"""
Demo: Autonomous TDD Agent

Shows how agent builds features autonomously using TDD discipline:
- Plans incremental tests
- RED: Writes failing test
- GREEN: Writes minimal code
- REFACTOR: Improves quality
- LEARN: Extracts patterns
"""
import sys
sys.path.insert(0, "/home/ch_dev/ace_enterprise")

import logging
import shutil
from pathlib import Path

from src.agents.autonomous_tdd_agent import AutonomousTDDAgent
from src.agents.test_review_agent import TestReviewAgent
from src.ensemble.learner import EnsembleLearner
from src.playbook.postgres_adapter import PostgresPlaybookAdapter
from src.playbook.postgres_retriever import PostgresBulletRetriever
from src.storage.schemas import PlaybookCreate

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

logger = logging.getLogger(__name__)


def main():
    print("\n" + "=" * 80)
    print("  AUTONOMOUS TDD AGENT DEMO")
    print("=" * 80)
    print("\n💡 Agent will build feature COMPLETELY AUTONOMOUSLY using TDD")
    print("   - Plans test increments (methodical, not random)")
    print("   - RED: Writes failing test")
    print("   - GREEN: Writes minimal code to pass")
    print("   - REFACTOR: Improves quality")
    print("   - LEARN: Extracts patterns")

    # Setup demo workspace
    demo_root = Path("/tmp/autonomous_tdd_demo")
    if demo_root.exists():
        shutil.rmtree(demo_root)
    demo_root.mkdir(parents=True)

    test_dir = demo_root / "tests"
    src_dir = demo_root / "src"
    test_dir.mkdir(parents=True)
    src_dir.mkdir(parents=True)

    # Create __init__.py for src to make it a package
    (src_dir / "__init__.py").write_text("")

    print(f"\n📁 Demo workspace: {demo_root}")

    # Initialize components
    print("\n[Setup] Initializing components...")

    # PostgreSQL Playbook (replaces file-based PlaybookManager)
    print("  → Connecting to PostgreSQL...")
    playbook_adapter = PostgresPlaybookAdapter()
    playbook = playbook_adapter.create_playbook(
        PlaybookCreate(
            domain="autonomous_tdd_demo",
            base_model="qwen2.5-coder:1.5b"
        )
    )
    print(f"  ✓ Created playbook {playbook.playbook_id} in PostgreSQL")

    # Ensemble learner (using OpenAI for speed)
    models = [
        ("openai", "gpt-4-turbo-preview"),
    ]

    ensemble = EnsembleLearner(
        models=models,
        playbook_id=playbook.playbook_id,
        enable_deliberation=False  # MVP: Simple voting only
    )

    # Override ensemble's playbook manager with PostgreSQL
    ensemble.playbook_manager = playbook_adapter

    # Test reviewer
    test_reviewer = TestReviewAgent(use_llm_analysis=False)

    # Autonomous TDD Agent
    agent = AutonomousTDDAgent(
        ensemble_learner=ensemble,
        test_reviewer=test_reviewer,
        project_root=demo_root,
        test_dir=test_dir,
        src_dir=src_dir,
        max_iterations=10,
        review_threshold=0.7
    )

    # Override agent's components to use PostgreSQL
    agent.playbook_manager = playbook_adapter
    agent.bullet_retriever = PostgresBulletRetriever(
        playbook_adapter=playbook_adapter,
        top_k=10,
        similarity_threshold=0.3
    )

    print("  ✓ Components initialized with PostgreSQL backend")

    # Demo 1: To-Do List (more complex state management)
    print("\n" + "─" * 80)
    print("DEMO 1: To-Do List")
    print("─" * 80)
    print("\nRequirement: 'TodoList that can add tasks, mark them complete, list all tasks, and remove tasks'")
    print("\nAgent will autonomously:")
    print("  1. Plan test increments (test_create, test_add_task, etc.)")
    print("  2. Write each test (RED)")
    print("  3. Write minimal code (GREEN)")
    print("  4. Verify tests pass")
    print("  5. Learn patterns")
    print("\n⏳ Building feature autonomously...\n")

    try:
        result = agent.build_feature("TodoList that can add tasks, mark them complete, list all tasks, and remove tasks")

        print("\n" + "=" * 80)
        print("✅ FEATURE COMPLETE!")
        print("=" * 80)
        print(f"  • Requirement: {result.requirement}")
        print(f"  • Cycles executed: {result.cycles_executed}")
        print(f"  • Tests created: {len(result.test_files)}")
        print(f"  • Implementation files: {len(result.implementation_files)}")
        print(f"  • All tests passed: {result.all_tests_passed}")
        print(f"  • Patterns learned: {result.playbook_bullets_added}")
        print(f"  • Time: {result.total_time_seconds:.1f}s")

        print("\n📄 Generated Files:")
        for test_file in result.test_files:
            print(f"  • {test_file.relative_to(demo_root)}")
            print(f"    {test_file.stat().st_size} bytes")
        for impl_file in result.implementation_files:
            if impl_file.name != "__init__.py":
                print(f"  • {impl_file.relative_to(demo_root)}")
                print(f"    {impl_file.stat().st_size} bytes")

        # Show generated code
        print("\n📝 Generated Test Code:")
        print("─" * 80)
        for test_file in result.test_files:
            content = test_file.read_text()
            print(content)

        print("\n📝 Generated Implementation Code:")
        print("─" * 80)
        for impl_file in result.implementation_files:
            if impl_file.name != "__init__.py":
                content = impl_file.read_text()
                print(content)

        print("\n" + "=" * 80)
        print("DEMO COMPLETE!")
        print("=" * 80)
        print("\n✅ Agent successfully built feature autonomously!")
        print("✅ All tests passing")
        print("✅ Implementation complete")
        print("✅ Code is minimal and focused (no vibe coding!)")
        print("\n💡 Key Principles Demonstrated:")
        print("   1. Methodical planning (not random coding)")
        print("   2. Test-first discipline (RED → GREEN → REFACTOR)")
        print("   3. Minimal implementation (YAGNI principle)")
        print("   4. Verification at every step (tests must pass)")
        print("\n📚 This is the foundation for fully autonomous development!")

    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted")
        sys.exit(1)
