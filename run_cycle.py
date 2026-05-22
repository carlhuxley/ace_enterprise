"""End-to-end iterative TDD cycle run with real LLM + real Podman container.

Uses IterativeTDDRunner (IncrementalPlanner → TDDCycleRunner loop) for
Kent Beck-style RED→GREEN→REFACTOR until the planner says COMPLETE.

Usage:
    .venv/bin/python run_cycle.py
"""
import sys
from pathlib import Path

from src.agents.incremental_planner import IncrementalPlanner
from src.agents.iterative_tdd_runner import IterativeTDDRunner
from src.agents.podman_orchestrator import PodmanOrchestrator
from src.agents.podman_runner import PodmanRunner
from src.agents.python_language_pod import PythonLanguagePod
from src.agents.worker_agent import WorkerAgent, _DEFAULT_TEST_RULES, _TEST_RULES_SECTION
from src.playbook.manager import PlaybookManager
from src.storage.experiment_logger import ExperimentLogger
from src.storage.schemas import BulletCreate
from src.utils.llm_client import LLMClient

FEATURE = (
    "A function called `migrate_and_sanitize_payload(raw_json_str: str, target_schema_version: int) -> dict`. "
    "It must: "
    "(1) Parse `raw_json_str`, which may contain trailing commas, single-quoted strings, or other minor "
    "JSON syntax errors — use a best-effort parser (try json.loads first, then fall back to ast.literal_eval "
    "after normalising quotes, then return {} on total failure); "
    "(2) Strip any keys not in the whitelist ALLOWED_KEYS = {'user_id', 'email', 'name', 'age', 'address', "
    "'preferences', 'schema_version', 'created_at', 'updated_at'} — recursively for nested dicts; "
    "(3) Apply v1→v2 field renames when target_schema_version == 2: rename 'username' → 'name', "
    "'addr' → 'address', 'prefs' → 'preferences' (before the whitelist pass, so renamed keys survive); "
    "(4) Apply fallback defaults for missing top-level keys: "
    "name defaults to 'anonymous', age defaults to 0, preferences defaults to {}; "
    "(5) Set 'schema_version' in the output to target_schema_version; "
    "SECURITY INVARIANT: the key 'password', 'token', 'secret', and 'ssn' must NEVER appear "
    "anywhere in the returned dict, even if nested. "
    "The function must never raise — all errors are swallowed and produce a safe partial result."
)
MODEL = "deepseek/deepseek-v4-flash"
OUTPUT_DIR = Path("output/json_migrator")
PLAYBOOK_ID = "json_migrator_run_1"
MAX_ITERATIONS = 8


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Model  : {MODEL}")
    print(f"Feature: {FEATURE[:80]}...")
    print(f"Output : {OUTPUT_DIR.resolve()}")
    print()

    llm = LLMClient(provider="openrouter", model=MODEL)

    playbook_manager = PlaybookManager()
    playbook = playbook_manager.get_or_create_playbook(PLAYBOOK_ID)
    if not playbook.sections.get(_TEST_RULES_SECTION):
        for rule in _DEFAULT_TEST_RULES:
            playbook_manager.add_bullet(
                PLAYBOOK_ID,
                BulletCreate(content=rule, section=_TEST_RULES_SECTION),
            )
        print(f"Seeded {len(_DEFAULT_TEST_RULES)} assertion rules into playbook.")

    worker = WorkerAgent(llm, playbook_manager=playbook_manager)
    experiment_logger = ExperimentLogger(playbook_version="1.0.0")

    planner = IncrementalPlanner(
        llm_client=llm,
        test_dir=OUTPUT_DIR,
        src_dir=OUTPUT_DIR,
        playbook_manager=playbook_manager,
        playbook_id=PLAYBOOK_ID,
    )

    runner_container = PodmanRunner(container_name="ace_e2e_cycle")
    runner_container.start()
    print("Container started.")

    try:
        orchestrator = PodmanOrchestrator(
            runner=runner_container,
            work_dir=OUTPUT_DIR / "harness",
        )
        pod = PythonLanguagePod(worker, OUTPUT_DIR, orchestrator)

        runner = IterativeTDDRunner(
            pod=pod,
            planner=planner,
            max_iterations=MAX_ITERATIONS,
            max_green_attempts=5,
            experiment_logger=experiment_logger,
            playbook_id=PLAYBOOK_ID,
        )

        print(f"Running iterative TDD (max {MAX_ITERATIONS} cycles)...")
        sys.stdout.flush()
        result = runner.run(FEATURE)

        print(f"\n=== RESULT ===")
        print(f"Complete      : {result.complete}")
        print(f"Success       : {result.success}")
        print(f"Cycles run    : {result.iterations}")

        for i, cycle in enumerate(result.cycles, 1):
            status = "✓" if cycle.success else "✗"
            req = cycle.feature_requirement[:60]
            attempts = cycle.green_attempts
            print(f"  {status} Cycle {i}: {req}  (GREEN in {attempts} attempt{'s' if attempts != 1 else ''})")

        total_in = sum(u.input_tokens for c in result.cycles for u in c.token_usage)
        total_out = sum(u.output_tokens for c in result.cycles for u in c.token_usage)
        print(f"\nTokens in={total_in}  out={total_out}")

        print(f"\nOutput files in: {OUTPUT_DIR.resolve()}")
        for f in sorted(OUTPUT_DIR.glob("*.py")):
            print(f"  {f.name}  ({f.stat().st_size} bytes)")

    finally:
        runner_container.stop()
        print("\nContainer stopped.")


if __name__ == "__main__":
    main()
