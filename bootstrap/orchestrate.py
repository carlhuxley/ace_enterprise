"""
Bootstrap orchestrator: private repo → Gherkin → clean synthesized public repo.

Pipeline:
  Stage 1  extract    LLM reads private src/ and emits pure Gherkin feature files
  Stage 2  synthesize TDD pipeline generates fresh implementations from Gherkin
  Stage 3  verify     Clean-room AST gate — blocks any file with private-name leakage
  Stage 4  stamp      AGPLv3 SPDX headers + LICENSE + pyproject.toml applied

Every stage event is recorded in bootstrap/audit.jsonl with a tamper-evident
chain hash. The log file is the paper trail for a corporate IP audit.

Usage:
    # Full run (all configured source files)
    .venv/bin/python bootstrap/orchestrate.py

    # Single-file run (useful for testing or incremental updates)
    .venv/bin/python bootstrap/orchestrate.py --file src/agents/language_pod.py
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bootstrap.audit_log import BootstrapAuditLog
from bootstrap.clean_room import verify_clean_room
from bootstrap.extract import extract_features
from bootstrap.stamp import stamp_directory

# ---------------------------------------------------------------------------
# Configuration — edit these before running
# ---------------------------------------------------------------------------

# Source modules to translate. Extend / restrict as needed.
SOURCE_FILES: list[Path] = [
    p for p in sorted(Path("src/agents").rglob("*.py"))
    if not p.name.startswith("__")
] + [
    Path("src/utils/llm_client.py"),
    Path("src/playbook/manager.py"),
]

PRIVATE_SRC_ROOT = Path("src")           # checked against for clean-room gate
OSS_DIR = Path("../ace-enterprise-oss")  # destination public repo (created if absent)
BOOTSTRAP_DIR = Path("bootstrap")
FEATURES_DIR = BOOTSTRAP_DIR / "features"
AUDIT_LOG_PATH = BOOTSTRAP_DIR / "audit.jsonl"
MODEL = "deepseek/deepseek-v4-flash"

# ---------------------------------------------------------------------------


def _parse_args() -> list[Path]:
    parser = argparse.ArgumentParser(description="Bootstrap pipeline: private → Gherkin → public AGPLv3 repo")
    parser.add_argument(
        "--file", metavar="PATH", help="Process a single source file instead of the full SOURCE_FILES list"
    )
    args = parser.parse_args()
    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"Error: {p} not found", file=sys.stderr)
            sys.exit(1)
        return [p]
    return SOURCE_FILES


def main() -> None:
    source_files = _parse_args()
    OSS_DIR.mkdir(parents=True, exist_ok=True)
    log = BootstrapAuditLog(AUDIT_LOG_PATH)

    log.record(
        "RUN_START",
        private_src=str(PRIVATE_SRC_ROOT),
        oss_dir=str(OSS_DIR),
        model=MODEL,
        source_file_count=len(source_files),
    )
    print(f"Bootstrap pipeline — audit log: {AUDIT_LOG_PATH.resolve()}")
    print(f"Private src : {PRIVATE_SRC_ROOT.resolve()}")
    print(f"Public repo : {OSS_DIR.resolve()}")

    # ------------------------------------------------------------------
    # Stage 1: Extract Gherkin
    # ------------------------------------------------------------------
    print(f"\n=== Stage 1: Extract Gherkin ({len(source_files)} source files) ===")
    feature_files = extract_features(
        src_files=source_files,
        features_dir=FEATURES_DIR,
        log=log,
        model=MODEL,
    )
    print(f"  {len(feature_files)} feature files written to {FEATURES_DIR}/")

    if not feature_files:
        print("  Nothing to synthesize — aborting.")
        log.record("RUN_ABORT", reason="no feature files produced in Stage 1")
        return

    # ------------------------------------------------------------------
    # Stage 2 + 3: Synthesize & Verify
    # ------------------------------------------------------------------
    print(f"\n=== Stage 2+3: Synthesize & Verify ({len(feature_files)} features) ===")
    passed, failed = _synthesis_loop(feature_files, OSS_DIR, log)
    print(f"  passed={passed}  blocked={failed}")

    # ------------------------------------------------------------------
    # Stage 4: Stamp
    # ------------------------------------------------------------------
    print("\n=== Stage 4: Stamp ===")
    stamped = stamp_directory(OSS_DIR, log)
    print(f"  {stamped} files stamped AGPL-3.0-only")

    log.record("RUN_COMPLETE", oss_dir=str(OSS_DIR), passed=passed, blocked=failed, stamped=stamped)

    # ------------------------------------------------------------------
    # Chain verification
    # ------------------------------------------------------------------
    ok, mismatch = log.verify_chain()
    if ok:
        print(f"\nAudit chain verified  ({AUDIT_LOG_PATH})")
    else:
        print(f"\n[WARN] Audit chain mismatch at: {mismatch}")

    # ------------------------------------------------------------------
    # Publish audit log into the public repo
    # ------------------------------------------------------------------
    import shutil
    dest = OSS_DIR / "audit.jsonl"
    shutil.copy2(AUDIT_LOG_PATH, dest)
    print(f"Audit log copied → {dest}")

    print(f"\nDone. Public repo: {OSS_DIR.resolve()}")


def _synthesis_loop(
    feature_files: list[Path],
    oss_dir: Path,
    log: BootstrapAuditLog,
) -> tuple[int, int]:
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

    llm = LLMClient(provider="openrouter", model=MODEL)
    playbook_manager = PlaybookManager()
    experiment_logger = ExperimentLogger(playbook_version="bootstrap-1.0")

    container = PodmanRunner(container_name="ace_bootstrap")
    container.start()
    print("  Container started.")

    passed = failed = 0

    try:
        for feature_file in feature_files:
            stem = feature_file.stem
            out_dir = oss_dir / stem
            out_dir.mkdir(parents=True, exist_ok=True)

            playbook_id = f"bootstrap_{stem}"
            pb = playbook_manager.get_or_create_playbook(playbook_id)
            if not pb.sections.get(_TEST_RULES_SECTION):
                for rule in _DEFAULT_TEST_RULES:
                    playbook_manager.add_bullet(
                        playbook_id, BulletCreate(content=rule, section=_TEST_RULES_SECTION)
                    )

            worker = WorkerAgent(llm, playbook_manager=playbook_manager)
            planner = IncrementalPlanner(
                llm_client=llm,
                test_dir=out_dir,
                src_dir=out_dir,
                playbook_manager=playbook_manager,
                playbook_id=playbook_id,
            )
            orchestrator = PodmanOrchestrator(
                runner=container,
                work_dir=out_dir / "harness",
                started=True,
            )
            pod = PythonLanguagePod(worker, out_dir, orchestrator)
            runner = IterativeTDDRunner(
                pod=pod,
                planner=planner,
                max_iterations=10,
                max_green_attempts=5,
                experiment_logger=experiment_logger,
                playbook_id=playbook_id,
            )

            print(f"  [{stem}] synthesizing...", end=" ", flush=True)
            result = runner.run_from_feature(feature_file)
            status = "✓" if result.success else "✗"
            print(f"{status} ({result.iterations} cycles)")

            token_in = sum(u.input_tokens for c in result.cycles for u in c.token_usage)
            token_out = sum(u.output_tokens for c in result.cycles for u in c.token_usage)

            for synth_file in sorted(out_dir.glob("*.py")):
                violations = verify_clean_room(synth_file, PRIVATE_SRC_ROOT)

                if violations:
                    log.record(
                        "CLEAN_ROOM_FAIL",
                        feature=str(feature_file),
                        file=str(synth_file),
                        sha256=BootstrapAuditLog.sha256(synth_file),
                        violations=violations,
                    )
                    print(f"    [BLOCKED] {synth_file.name}")
                    for v in violations:
                        print(f"      {v}")
                    synth_file.unlink()
                    failed += 1
                else:
                    log.record(
                        "CLEAN_ROOM_PASS",
                        feature=str(feature_file),
                        file=str(synth_file),
                        sha256=BootstrapAuditLog.sha256(synth_file),
                        checks=["private_function_names", "docstring_tokens"],
                        model=MODEL,
                        input_tokens=token_in,
                        output_tokens=token_out,
                    )
                    passed += 1

    finally:
        container.stop()
        print("  Container stopped.")

    return passed, failed


if __name__ == "__main__":
    main()
