#!/usr/bin/env python3
"""
Run TDD workflow to build analytics feature.

This demonstrates the complete ACE system working end-to-end:
1. TDD agent builds feature incrementally
2. Each cycle is logged to experiment_logs
3. Playbook is updated with learned patterns
4. Everything stored in PostgreSQL
"""
import logging
from pathlib import Path

from src.agents.autonomous_tdd_agent import AutonomousTDDAgent
from src.agents.test_review_agent import TestReviewAgent
from src.ensemble.learner import EnsembleLearner
from src.playbook.postgres_adapter import PostgresPlaybookAdapter
from src.storage.schemas import PlaybookCreate

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

logger = logging.getLogger(__name__)

# Project paths
PROJECT_ROOT = Path(__file__).parent
TEST_DIR = PROJECT_ROOT / "analytics_tests"
SRC_DIR = PROJECT_ROOT / "src" / "analytics"

# Create directories
TEST_DIR.mkdir(exist_ok=True)
SRC_DIR.mkdir(exist_ok=True, parents=True)

print("\n" + "="*80)
print("TDD WORKFLOW: Building Analytics Feature")
print("="*80)

# Read requirement
requirement = (PROJECT_ROOT / "analytics_requirement.txt").read_text()
print(f"\n📋 Requirement:\n{requirement}\n")

# Initialize components
print("🔧 Initializing TDD agent...")

# Create playbook for this session
# Note: Using in-memory playbook manager for now (ensemble creates its own manager)
from src.playbook.manager import PlaybookManager

playbook_manager = PlaybookManager()

# Create analytics playbook
analytics_playbook = playbook_manager.create_playbook(
    create_data=PlaybookCreate(
        domain="analytics",
        base_model="qwen2.5-coder:7b"
    )
)
analytics_playbook_id = analytics_playbook.playbook_id
print(f"   ✓ Created playbook: {analytics_playbook_id}")

# Initialize ensemble learner with TogetherAI
ensemble = EnsembleLearner(
    models=[("togetherai", "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8", "https://api.together.ai/v1")],
    playbook_id=analytics_playbook_id
)

# Initialize test reviewer with TogetherAI
from src.utils.llm_client import LLMClient

llm_client = LLMClient(
    provider="togetherai",
    model="Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8",
    base_url="https://api.together.ai/v1"
)
test_reviewer = TestReviewAgent(llm_client=llm_client)

# Initialize TDD agent
agent = AutonomousTDDAgent(
    ensemble_learner=ensemble,
    test_reviewer=test_reviewer,
    project_root=PROJECT_ROOT,
    test_dir=TEST_DIR,
    src_dir=SRC_DIR,
    max_iterations=10,
    review_threshold=0.5
)

print("   ✓ TDD agent ready\n")

# Run TDD workflow
print("="*80)
print("🚀 STARTING TDD WORKFLOW")
print("="*80)

try:
    result = agent.build_feature(
        requirement="Build a SuccessRateCalculator that calculates experiment success rates from PostgreSQL"
    )

    print("\n" + "="*80)
    print("✅ TDD WORKFLOW COMPLETE!")
    print("="*80)
    print(f"  • Cycles executed: {result.cycles_executed}")
    print(f"  • Tests created: {len(result.test_files)}")
    print(f"  • Implementation files: {len(result.implementation_files)}")
    print(f"  • Playbook bullets learned: {result.playbook_bullets_added}")
    print(f"  • All tests passing: {result.all_tests_passed}")
    print(f"  • Time: {result.total_time_seconds:.1f}s")
    print("="*80)

    print("\n🎯 Verifying experiment logging...")
    print("   You can check experiment_logs table to see each TDD cycle recorded!")
    print("   Run: psql -d ace_enterprise -c 'SELECT experiment_id, result, playbook_updated FROM experiment_logs ORDER BY timestamp DESC LIMIT 10;'")

except Exception as e:
    logger.error(f"\n❌ TDD workflow failed: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print()
