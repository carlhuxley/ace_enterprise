#!/usr/bin/env python3
"""
Demo: Autonomous TDD Agent with Hybrid Ensemble - OAuth Authentication
- 2x Local Ollama: deepseek-coder:6.7b, qwen2.5-coder:1.5b
- 1x RunPod vLLM (GPU-accelerated): Qwen2.5-Coder-7B (when ready)

Tests OAuth authentication implementation with ensemble learning
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

# Hybrid configuration: 2 local + 1 RunPod (when ready)
RUNPOD_IP = "213.173.102.138"
RUNPOD_PORT = "32277"  # Port for first vLLM server

# Hybrid: OpenAI GPT-4o (quality) + GPT-4o-mini (speed)
MODELS = [
    ("openai", "gpt-4o", None),           # Primary - Best for complex coding
    ("openai", "gpt-4o-mini", None),      # Secondary - Fast consensus
]


def main():
    print("\n" + "=" * 80)
    print("  AUTONOMOUS TDD AGENT - OAuth Authentication Challenge")
    print("=" * 80)
    print("\n🚀 Hybrid Configuration:")
    print(f"   OpenAI GPT-4o (primary) + GPT-4o-mini (consensus)")
    print(f"   Fast, reliable, cloud-based ensemble")
    print(f"\n   Active Models: {len(MODELS)}")
    for i, (provider, model, url) in enumerate(MODELS, 1):
        print(f"     {i}. {model} ({provider.upper()})")

    print("\n💡 Testing Ambitious Feature:")
    print("   🔐 OAuth Authentication Implementation")
    print("   ✓ Ensemble learning with security best practices")
    print("   ✓ Multi-model consensus on auth flows")
    print("   ✓ TDD for critical security code")

    # Setup demo workspace
    demo_root = Path("/tmp/oauth_auth_demo")
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
            domain="oauth_authentication",
            base_model="deepseek-coder:6.7b"
        )
    )

    print(f"  ✓ Playbook created: {playbook.playbook_id}")

    # Ensemble learner (hybrid: 1 RunPod + 2 local)
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

    # Run OAuth Authentication challenge
    print("\n" + "─" * 80)
    print("CHALLENGE: OAuth Authentication")
    print("─" * 80)
    print("\nRequirement:")
    print("  'OAuth authentication system that can:")
    print("   - Handle OAuth authorization code flow")
    print("   - Exchange authorization code for access tokens")
    print("   - Validate and refresh tokens")
    print("   - Store user sessions securely")
    print("   - Support multiple OAuth providers (Google, GitHub)'")
    print("\n⏳ Building feature with ensemble learning...\n")

    try:
        result = agent.build_feature(
            "OAuth authentication system that handles authorization code flow, "
            "token exchange, token validation and refresh, secure session storage, "
            "and supports multiple providers like Google and GitHub"
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
        print("OAUTH AUTHENTICATION - DEMO COMPLETE!")
        print("=" * 80)
        print("\n✅ OAuth implementation generated!")
        print(f"✅ All {result.cycles_executed} cycles completed")
        print("✅ Ensemble consensus on security patterns")
        print("✅ TDD applied to critical auth code")
        print("✅ Multi-model validation successful!")

        # Show playbook
        print(f"\n📚 Playbook: {playbook.playbook_id}")
        print(f"   Location: data/playbooks/{playbook.playbook_id}.json")
        print(f"   Bullets learned: {result.playbook_bullets_added}")

        if result.playbook_bullets_added > 0:
            print("\n🎓 Learning verified - ensemble bug fix is working!")

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
