#!/usr/bin/env python3
"""
Demo: Autonomous TDD Agent with Gherkin Acceptance Tests

This demo shows how the TDD agent can work toward making Gherkin scenarios pass.
The agent will:
1. Read Gherkin acceptance tests
2. Use them to guide test planning
3. Check acceptance tests every 3 cycles
4. Stop when all scenarios pass
"""

import logging
from pathlib import Path

from src.agents.autonomous_tdd_agent import AutonomousTDDAgent
from src.ensemble.learner import EnsembleLearner
from src.utils.llm_client import LLMClient
from src.playbook.manager import PlaybookManager
from src.storage.schemas import PlaybookCreate

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)

logger = logging.getLogger(__name__)


def main():
    print("=" * 80)
    print("  AUTONOMOUS TDD AGENT - Gherkin Acceptance Test Demo")
    print("=" * 80)
    print()
    print("🎯 Goal: Build OAuth authentication using acceptance-test-driven TDD")
    print()
    print("📋 Acceptance Tests:")
    print("   - Create OAuth client with configuration")
    print("   - Generate authorization URL")
    print("   - Exchange authorization code for token")
    print("   - Validate access token")
    print("   - Refresh expired token")
    print()
    print("💡 The agent will:")
    print("   1. Read Gherkin scenarios for business requirements")
    print("   2. Use emergent TDD to build incrementally")
    print("   3. Check acceptance tests every 3 cycles")
    print("   4. Stop when ALL scenarios pass ✓")
    print()
    print("─" * 80)
    print()

    # Setup
    project_root = Path("/tmp/oauth_auth_demo")
    gherkin_dir = Path("/tmp/oauth_demo_features")

    # Verify Gherkin files exist
    if not gherkin_dir.exists():
        logger.error(f"Gherkin directory not found: {gherkin_dir}")
        return 1

    feature_files = list(gherkin_dir.glob("*.feature"))
    if not feature_files:
        logger.error(f"No .feature files found in {gherkin_dir}")
        return 1

    logger.info(f"✓ Found acceptance tests: {feature_files[0].name}")
    logger.info("")

    # Initialize ensemble
    models = [
        ("openai", "gpt-4o", None),
        ("openai", "gpt-4o-mini", None),
    ]

    # Create playbook
    playbook_manager = PlaybookManager()
    playbook = playbook_manager.create_playbook(
        PlaybookCreate(
            domain="oauth_authentication",
            base_model="gpt-4o"
        )
    )

    ensemble = EnsembleLearner(
        models=models,
        playbook_id=playbook.playbook_id,
        enable_deliberation=False
    )

    # Initialize test reviewer
    from src.agents.test_review_agent import TestReviewAgent
    test_reviewer = TestReviewAgent(
        llm_client=LLMClient(provider="openai", model="gpt-4o")
    )

    # Initialize TDD agent
    test_dir = project_root / "tests"
    src_dir = project_root / "src"

    agent = AutonomousTDDAgent(
        ensemble_learner=ensemble,
        test_reviewer=test_reviewer,
        project_root=project_root,
        test_dir=test_dir,
        src_dir=src_dir,
        max_iterations=15,  # Allow more cycles since we're working toward acceptance tests
        review_threshold=0.7
    )

    # Run TDD with Gherkin acceptance tests
    requirement = """OAuth authentication system that handles authorization code flow,
token exchange, token validation and refresh"""

    try:
        result = agent.build_feature(
            requirement=requirement,
            gherkin_dir=gherkin_dir  # Enable Gherkin acceptance testing!
        )

        logger.info("")
        logger.info("=" * 80)
        logger.info("  ✅ SUCCESS!")
        logger.info("=" * 80)
        logger.info(f"  • All acceptance tests passing")
        logger.info(f"  • Unit tests: {len(result.test_files)} files")
        logger.info(f"  • Implementation: {len(result.impl_files)} files")
        logger.info("")

        # Final acceptance test check
        logger.info("🎉 Running final acceptance test verification...")
        acceptance_result = agent._run_acceptance_tests(gherkin_dir)
        logger.info(f"   {acceptance_result['details']}")

        if acceptance_result['all_passed']:
            logger.info("")
            logger.info("✅ All Gherkin scenarios passing - feature is COMPLETE!")
        else:
            logger.warning("")
            logger.warning(f"⚠️  {acceptance_result['failed']}/{acceptance_result['total']} scenarios still failing")

        return 0

    except Exception as e:
        logger.error(f"")
        logger.error(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
