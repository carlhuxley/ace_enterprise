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
    "a function called `word_ladder(start: str, end: str, word_list: list[str]) -> list[str]` "
    "that returns the shortest list of words transforming `start` into `end`, where each "
    "adjacent pair differs by exactly one character and every word except `start` must appear "
    "in `word_list`. Return an empty list if no transformation exists. "
    "If `start == end` return `[start]`."
)
MODEL = "deepseek/deepseek-v4-flash"
OUTPUT_DIR = Path("output/word_ladder")
PLAYBOOK_ID = "word_ladder_run_1"


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
            test_file=OUTPUT_DIR / "test_word_ladder.py",
            implementation_file=OUTPUT_DIR / "word_ladder.py",
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
