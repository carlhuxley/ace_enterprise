"""End-to-end TDD cycle run with real LLM + real Podman container.

Uses TDDCycleRunner (RED → GREEN with retry → REFACTOR) wired to
ExperimentLogger (SQLite fallback when Postgres is unavailable).

Usage:
    .venv/bin/python run_cycle.py
"""
import sys
from pathlib import Path

from src.agents.language_pod import PodSpec
from src.agents.podman_orchestrator import PodmanOrchestrator
from src.agents.podman_runner import PodmanRunner
from src.agents.python_language_pod import PythonLanguagePod
from src.agents.tdd_cycle_runner import TDDCycleRunner
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


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Model  : {MODEL}")
    print(f"Feature: {FEATURE}")
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

    runner_container = PodmanRunner(container_name="ace_e2e_cycle")
    runner_container.start()
    print("Container started.")

    try:
        orchestrator = PodmanOrchestrator(
            runner=runner_container,
            work_dir=OUTPUT_DIR / "harness",
        )
        pod = PythonLanguagePod.from_worker(worker, OUTPUT_DIR, orchestrator)

        spec = PodSpec(
            feature_requirement=FEATURE,
            test_file=OUTPUT_DIR / "test_json_migrator.py",
            implementation_file=OUTPUT_DIR / "json_migrator.py",
            cycle_number=1,
        )

        runner = TDDCycleRunner(
            pod,
            max_green_attempts=5,
            experiment_logger=experiment_logger,
            playbook_id=PLAYBOOK_ID,
        )

        print("Running TDD cycle...")
        sys.stdout.flush()
        result = runner.run(spec)

        print(f"\n=== RESULT ===")
        print(f"Success       : {result.success}")
        print(f"GREEN attempts: {result.green_attempts}")
        if result.error:
            print(f"Error         : {result.error}")

        print(f"\nRED   passed={result.red_result.passed}  error={result.red_result.error}")
        print(f"GREEN passed={result.green_result.passed}  error={result.green_result.error}")
        if result.refactor_result:
            print(f"REFAC passed={result.refactor_result.passed}  error={result.refactor_result.error}")

        total_input = sum(u.input_tokens for u in result.token_usage)
        total_output = sum(u.output_tokens for u in result.token_usage)
        print(f"\nTokens in={total_input}  out={total_output}")

        if spec.test_file.exists():
            print(f"\n--- generated test ({spec.test_file.stat().st_size} bytes) ---")
            print(spec.test_file.read_text())

        if spec.implementation_file.exists():
            print(f"\n--- generated implementation ({spec.implementation_file.stat().st_size} bytes) ---")
            print(spec.implementation_file.read_text())

        print(f"\nOutput files in: {OUTPUT_DIR.resolve()}")
        for f in sorted(OUTPUT_DIR.glob("*.py")):
            print(f"  {f.name}  ({f.stat().st_size} bytes)")

    finally:
        runner_container.stop()
        print("\nContainer stopped.")


if __name__ == "__main__":
    main()
