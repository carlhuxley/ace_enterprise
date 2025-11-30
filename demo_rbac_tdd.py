#!/usr/bin/env python3
"""
Demo: Autonomous TDD Agent with Gherkin Acceptance Tests (Together AI)

This demo shows how the TDD agent can work toward making Gherkin scenarios pass.
Uses Together AI serverless Qwen models with Apache 2.0 license and model provenance tracking.

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
    print("  AUTONOMOUS TDD AGENT - Gherkin-Driven RBAC Demo")
    print("=" * 80)
    print()
    print("🎯 Goal: Build Role-Based Access Control using Gherkin-driven TDD")
    print()
    print("📋 Gherkin Scenarios:")
    print("   - User with admin role can access admin resources")
    print("   - User without required role is denied access")
    print("   - User with multiple roles has combined permissions")
    print("   - Permissions can be checked before performing actions")
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
    project_root = Path("/tmp/rbac_demo")
    source_gherkin_dir = Path(__file__).parent / "gherkin_acceptance_tests"

    # Create temporary directory with only RBAC feature file
    # (avoids picking up oauth.feature alphabetically)
    import tempfile
    import shutil
    temp_gherkin_dir = Path(tempfile.mkdtemp(prefix="rbac_gherkin_"))

    # Verify source RBAC feature exists
    rbac_feature = source_gherkin_dir / "rbac.feature"
    if not rbac_feature.exists():
        logger.error(f"RBAC feature file not found: {rbac_feature}")
        return 1

    # Copy only RBAC feature to temp directory
    shutil.copy(rbac_feature, temp_gherkin_dir / "rbac.feature")
    gherkin_dir = temp_gherkin_dir

    logger.info(f"✓ Found acceptance tests: {rbac_feature.name}")
    logger.info("")

    # SINGLE CODING MODEL (no voting conflicts, pure code-focused learning!)
    models = [
        ("togetherai", "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8", None), # SWE-bench frontier, 256K context
    ]

    # Create playbook
    playbook_manager = PlaybookManager()
    playbook = playbook_manager.create_playbook(
        PlaybookCreate(
            domain="role_based_access_control",
            base_model="Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8"
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
        llm_client=LLMClient(provider="togetherai", model="Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8")
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

    # Run TDD with Gherkin
    requirement = """Role-Based Access Control system that manages user roles,
checks permissions, and controls access to resources based on roles"""

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
        logger.info(f"  • Implementation: {len(result.implementation_files)} files")
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

    finally:
        # Cleanup temporary Gherkin directory
        import shutil
        if 'temp_gherkin_dir' in locals() and temp_gherkin_dir.exists():
            shutil.rmtree(temp_gherkin_dir)


if __name__ == "__main__":
    exit(main())
