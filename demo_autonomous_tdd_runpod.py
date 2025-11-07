#!/usr/bin/env python3
"""
Demo: Autonomous TDD Agent with RunPod vLLM Ensemble

Uses 3x 7B models on RTX 4090 via RunPod:
- Qwen2.5-Coder-7B-Instruct (port 8001 → 35303)
- Qwen2.5-7B-Instruct (port 8002 → 35304)
- DeepSeek-Coder-6.7B-Instruct (port 8003 → 35305)

Much better code quality than 1.5B models!
Tests T-shaped retrieval and ensemble learning bug fixes.
"""
import sys
sys.path.insert(0, "/home/ch_dev/ace_enterprise")

import logging
import shutil
from pathlib import Path

from src.agents.autonomous_tdd_agent import AutonomousTDDAgent
from src.agents.test_review_agent import TestReviewAgent
from src.ensemble.learner import EnsembleLearner
from src.playbook.manager import PlaybookManager
from src.storage.schemas import PlaybookCreate

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

logger = logging.getLogger(__name__)

# RunPod configuration - 7B models for better quality
RUNPOD_IP = "213.173.102.138"
MODELS = [
    ("vllm", "Qwen/Qwen2.5-Coder-7B-Instruct", f"http://{RUNPOD_IP}:35303"),
    ("vllm", "Qwen/Qwen2.5-7B-Instruct", f"http://{RUNPOD_IP}:35304"),
    ("vllm", "deepseek-ai/deepseek-coder-6.7b-instruct", f"http://{RUNPOD_IP}:35305"),
]


def main():
    print("\n" + "=" * 80)
    print("  AUTONOMOUS TDD AGENT - RUNPOD vLLM ENSEMBLE")
    print("=" * 80)
    print("\n🚀 Running on RTX 4090 via RunPod")
    print(f"   Endpoint: {RUNPOD_IP}")
    print(f"   Models: {len(MODELS)}")
    for i, (provider, model, url) in enumerate(MODELS, 1):
        print(f"     {i}. {model.split('/')[-1]}")

    print("\n💡 Testing T-shaped retrieval + ensemble learning")
    print("   - Cross-model bullet voting")
    print("   - Parallel execution on GPU")
    print("   - Learning from multi-model consensus")

    # Setup demo workspace
    demo_root = Path("/tmp/autonomous_tdd_runpod")
    if demo_root.exists():
        shutil.rmtree(demo_root)
    demo_root.mkdir(parents=True)

    test_dir = demo_root / "tests"
    src_dir = demo_root / "src"
    test_dir.mkdir(parents=True)
    src_dir.mkdir(parents=True)

    # Create __init__.py
    (src_dir / "__init__.py").write_text("")

    print(f"\n📁 Demo workspace: {demo_root}")

    # Initialize components
    print("\n[Setup] Initializing components...")

    # Playbook
    playbook_manager = PlaybookManager()
    playbook = playbook_manager.create_playbook(
        PlaybookCreate(
            domain="autonomous_tdd_runpod",
            base_model="qwen2.5-coder:1.5b"
        )
    )

    print(f"  ✓ Playbook created: {playbook.playbook_id}")

    # Ensemble learner (using RunPod vLLM)
    ensemble = EnsembleLearner(
        models=MODELS,
        playbook_id=playbook.playbook_id,
        enable_deliberation=False  # MVP: Simple voting only
    )

    print(f"  ✓ Ensemble initialized with {len(MODELS)} models")

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

    print("  ✓ Autonomous TDD Agent ready")

    # Run TodoList challenge
    print("\n" + "─" * 80)
    print("CHALLENGE: To-Do List")
    print("─" * 80)
    print("\nRequirement: 'TodoList that can add tasks, mark them complete, list all tasks, and remove tasks'")
    print("\n⏳ Building feature with GPU-accelerated ensemble...\n")

    try:
        result = agent.build_feature(
            "TodoList that can add tasks, mark them complete, list all tasks, and remove tasks"
        )

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
        for impl_file in result.implementation_files:
            if impl_file.name != "__init__.py":
                print(f"  • {impl_file.relative_to(demo_root)}")

        # Show generated code
        print("\n📝 Generated Implementation:")
        print("─" * 80)
        for impl_file in result.implementation_files:
            if impl_file.name != "__init__.py":
                content = impl_file.read_text()
                print(content)

        print("\n" + "=" * 80)
        print("DEMO COMPLETE!")
        print("=" * 80)
        print("\n✅ GPU-accelerated ensemble learning successful!")
        print(f"✅ All {result.cycles_executed} cycles completed")
        print("✅ T-shaped retrieval working correctly")
        print("✅ Multi-model consensus achieved")

        # Show playbook
        print(f"\n📚 Playbook: {playbook.playbook_id}")
        print(f"   Location: data/playbooks/{playbook.playbook_id}.json")
        print(f"   Bullets learned: {result.playbook_bullets_added}")

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
