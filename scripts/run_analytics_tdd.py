#!/usr/bin/env python3
"""
Run TDD workflow to build analytics feature.

This demonstrates the complete ACE system working end-to-end:
1. TDD agent builds feature incrementally, RED/GREEN/REFACTOR executing
   inside a rootless Podman container (see src/agents/podman_orchestrator.py)
2. Each cycle is logged to experiment_logs (PostgreSQL, falls back to SQLite)
3. Playbook is updated with learned patterns via Reflector/Curator
4. Every phase is on the audit trail (src/audit/)

Ported from AutonomousTDDAgent (removed) to the sandboxed IterativeTDDRunner
engine -- same one bootstrap/orchestrate.py and `ace tdd` use. Generated code
is only ever written to SRC_DIR/TEST_DIR after it passes inside the container.
"""
import logging
from pathlib import Path

from src.agents.iterative_tdd_runner import IterativeTDDRunner
from src.agents.incremental_planner import IncrementalPlanner
from src.agents.podman_orchestrator import PodmanOrchestrator
from src.agents.podman_runner import PodmanRunner
from src.agents.python_language_pod import PythonLanguagePod
from src.agents.redundancy_checker import RedundancyPreChecker
from src.agents.worker_agent import WorkerAgent
from src.audit.local_client import LocalAuditClient
from src.core.curator.module import Curator
from src.core.reflector.module import Reflector
from src.playbook.postgres_adapter import PostgresPlaybookAdapter
from src.storage.experiment_logger import ExperimentLogger
from src.storage.schemas import PlaybookCreate
from src.utils.context_map import ContextMapBuilder
from src.utils.llm_client import LLMClient

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Project paths
PROJECT_ROOT = Path(__file__).parent
TEST_DIR = PROJECT_ROOT / "analytics_tests"
SRC_DIR = PROJECT_ROOT / "src" / "analytics"
TEST_DIR.mkdir(exist_ok=True)
SRC_DIR.mkdir(exist_ok=True, parents=True)

print("\n" + "=" * 80)
print("TDD WORKFLOW: Building Analytics Feature")
print("=" * 80)

requirement_file = PROJECT_ROOT / "analytics_requirement.txt"
requirement = (
    requirement_file.read_text()
    if requirement_file.exists()
    else "Build a SuccessRateCalculator that calculates experiment success rates from PostgreSQL"
)
print(f"\n📋 Requirement:\n{requirement}\n")

print("🔧 Initializing sandboxed TDD engine...")

playbook_manager = PostgresPlaybookAdapter()
analytics_playbook = playbook_manager.create_playbook(
    PlaybookCreate(domain="analytics", base_model="Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8")
)
playbook_id = analytics_playbook.playbook_id
print(f"   ✓ Created playbook: {playbook_id}")

llm_client = LLMClient(
    provider="togetherai",
    model="Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8",
    base_url="https://api.together.ai/v1",
)

context_map = ContextMapBuilder().build(sorted(SRC_DIR.rglob("*.py")))
worker = WorkerAgent(llm_client, playbook_manager=playbook_manager, context_map=context_map)
planner = IncrementalPlanner(
    llm_client=llm_client,
    test_dir=TEST_DIR,
    src_dir=SRC_DIR,
    playbook_manager=playbook_manager,
    playbook_id=playbook_id,
)
orchestrator = PodmanOrchestrator(runner=PodmanRunner())
pod = PythonLanguagePod(worker, PROJECT_ROOT, orchestrator)

runner = IterativeTDDRunner(
    pod=pod,
    planner=planner,
    max_iterations=10,
    playbook_id=playbook_id,
    reflector=Reflector(llm_client=llm_client),
    curator=Curator(playbook_manager=playbook_manager, llm_client=llm_client),
    audit_client=LocalAuditClient(),
    redundancy_checker=RedundancyPreChecker(),
    experiment_logger=ExperimentLogger(playbook_version="1.0"),
)

print("   ✓ TDD engine ready\n")

print("=" * 80)
print("🚀 STARTING TDD WORKFLOW")
print("=" * 80)

try:
    result = runner.run(requirement=requirement)

    print("\n" + "=" * 80)
    print("✅ TDD WORKFLOW COMPLETE!" if result.success else "⚠️  TDD WORKFLOW INCOMPLETE")
    print("=" * 80)
    bullets_learned = sum(len(c.learned_bullets) for c in result.cycles)
    print(f"  • Cycles executed: {result.iterations}")
    print(f"  • Cycles passed: {sum(1 for c in result.cycles if c.success)}/{len(result.cycles)}")
    print(f"  • Playbook bullets learned: {bullets_learned}")
    print("=" * 80)

    print("\n🎯 Verifying experiment logging...")
    print("   You can check experiment_logs table to see each TDD cycle recorded!")
    print("   Run: psql -d ace_enterprise -c 'SELECT experiment_id, result, playbook_updated FROM experiment_logs ORDER BY timestamp DESC LIMIT 10;'")

except Exception as e:
    logger.error(f"\n❌ TDD workflow failed: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
finally:
    orchestrator.stop()

print()
