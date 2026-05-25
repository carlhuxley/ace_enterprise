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

    # TypeScript target (cross-language clean-room)
    .venv/bin/python bootstrap/orchestrate.py --lang typescript --file src/agents/worker_agent.py
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bootstrap.audit_log import BootstrapAuditLog
from bootstrap.clean_room import verify_clean_room, verify_clean_room_cross_language
from bootstrap.extract import extract_features
from bootstrap.stamp import stamp_directory

# ---------------------------------------------------------------------------
# Configuration — edit these before running
# ---------------------------------------------------------------------------

PRIVATE_SRC_ROOT = Path("src")           # checked against for clean-room gate

# Structural shims and Python runtime abstractions that should not cross the boundary
_SKIP_FOR_TS = {
    "language_pod",
    "python_language_pod",
    "podman_runner",
}


def get_target_modules(src_root: Path, language: str) -> list[Path]:
    """Sweeps the src directory and filters out irrelevant modules based on target language."""
    all_files = [
        p for p in sorted(src_root.rglob("*.py"))
        if not p.name.startswith("__")
    ]

    if language == "typescript":
        return [f for f in all_files if f.stem not in _SKIP_FOR_TS]

    return all_files


OSS_DIR = Path("../ace-enterprise-oss")  # destination public repo (created if absent)
BOOTSTRAP_DIR = Path("bootstrap")
FEATURES_DIR = BOOTSTRAP_DIR / "features"
AUDIT_LOG_PATH = BOOTSTRAP_DIR / "audit.jsonl"

# Model roster — Pass 1 is cheap/fast; Pass 2 escalates on failure
MODEL_EXTRACT = "anthropic/claude-sonnet-4-5"   # Stage 1: Gherkin extraction
MODEL_PASS1   = "anthropic/claude-sonnet-4-5"   # Pass 1: fast synthesis
MODEL_PASS2   = "anthropic/claude-sonnet-4-5"   # Pass 2: fallback on failure

# ---------------------------------------------------------------------------


def _check_openrouter_credits() -> None:
    """Fail fast if OpenRouter balance is zero or the key is invalid."""
    import os
    import urllib.request
    import json as _json

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("[WARN] OPENROUTER_API_KEY not set — skipping credit check")
        return

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/auth/key",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())["data"]
        limit = data.get("limit")
        usage = data.get("usage", 0.0)
        if limit is not None:
            remaining = limit - usage
            if remaining <= 0:
                print(f"ERROR: OpenRouter credit exhausted (limit={limit}, usage={usage})", file=sys.stderr)
                sys.exit(1)
            print(f"OpenRouter credits OK — ${remaining:.4f} remaining (limit=${limit}, used=${usage:.4f})")
        else:
            print(f"OpenRouter credits OK — unlimited key (used=${usage:.4f})")
    except Exception as exc:
        print(f"[WARN] Credit check failed ({exc}) — continuing anyway")


def _parse_args():
    parser = argparse.ArgumentParser(description="Bootstrap pipeline: private → Gherkin → public AGPLv3 repo")
    parser.add_argument(
        "--file", metavar="PATH", help="Process a single source file instead of the full SOURCE_FILES list"
    )
    parser.add_argument(
        "--lang", choices=["python", "typescript"], default="python",
        help="Target synthesis language (default: python)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-synthesise modules that already have output files in the OSS dir"
    )
    args = parser.parse_args()
    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"Error: {p} not found", file=sys.stderr)
            sys.exit(1)
        return [p], args.lang, args.force
    return get_target_modules(PRIVATE_SRC_ROOT, args.lang), args.lang, args.force


def main() -> None:
    source_files, lang, force = _parse_args()
    _check_openrouter_credits()
    OSS_DIR.mkdir(parents=True, exist_ok=True)
    log = BootstrapAuditLog(AUDIT_LOG_PATH)

    log.record(
        "RUN_START",
        private_src=str(PRIVATE_SRC_ROOT),
        oss_dir=str(OSS_DIR),
        model_pass1=MODEL_PASS1,
        model_pass2=MODEL_PASS2,
        lang=lang,
        source_file_count=len(source_files),
    )
    print(f"Bootstrap pipeline — audit log: {AUDIT_LOG_PATH.resolve()}")
    print(f"Private src : {PRIVATE_SRC_ROOT.resolve()}")
    print(f"Public repo : {OSS_DIR.resolve()}")
    print(f"Target lang : {lang}")

    # ------------------------------------------------------------------
    # Stage 1: Extract Gherkin
    # ------------------------------------------------------------------
    print(f"\n=== Stage 1: Extract Gherkin ({len(source_files)} source files) ===")
    feature_files = extract_features(
        src_files=source_files,
        features_dir=FEATURES_DIR,
        log=log,
        model=MODEL_EXTRACT,
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
    if lang == "typescript":
        passed, failed = _synthesis_loop_ts(feature_files, OSS_DIR, log, force=force)
    else:
        passed, failed = _synthesis_loop(feature_files, OSS_DIR, log, force=force)
    print(f"  passed={passed}  blocked={failed}")

    # ------------------------------------------------------------------
    # Stage 4: Stamp
    # ------------------------------------------------------------------
    print("\n=== Stage 4: Stamp ===")
    stamped = stamp_directory(OSS_DIR, log, lang=lang)
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

    # ------------------------------------------------------------------
    # Stage 5: Commit public repo
    # ------------------------------------------------------------------
    print("\n=== Stage 5: Commit public repo ===")
    _commit_public_repo(OSS_DIR, passed, log)

    print(f"\nDone. Public repo: {OSS_DIR.resolve()}")
    print("Next: cd ../ace-enterprise-oss && git remote add origin <url> && git push -u origin main")


def _commit_public_repo(oss_dir: Path, module_count: int, log: BootstrapAuditLog) -> None:
    import subprocess
    from datetime import datetime

    def _git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=oss_dir, capture_output=True, text=True, check=True
        )

    is_new = not (oss_dir / ".git").exists()

    if is_new:
        _git("init", "-b", "main")
        _git("config", "user.name", "ace-bootstrap")
        _git("config", "user.email", "bootstrap@ace-enterprise")

    _git("add", ".")

    # Check whether there's anything to commit
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=oss_dir, capture_output=True, text=True
    )
    if not status.stdout.strip():
        print("  Nothing new to commit — public repo already up to date.")
        return

    # Audit manifest — every file about to be committed, with sha256
    manifest = {}
    for f in sorted(oss_dir.rglob("*")):
        if f.is_file() and ".git" not in f.parts:
            manifest[str(f.relative_to(oss_dir))] = BootstrapAuditLog.sha256(f)
    log.record("REPO_CONTENTS", oss_dir=str(oss_dir), file_count=len(manifest), files=manifest)

    from datetime import timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if is_new:
        msg = f"Initial clean-room synthesized release ({module_count} modules, {ts})"
    else:
        msg = f"Synthesized update: {module_count} modules ({ts})"

    _git("commit", "-m", msg)
    result = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=oss_dir, capture_output=True, text=True
    )
    print(f"  Committed: {result.stdout.strip()}")
    log.record("GIT_COMMIT", oss_dir=str(oss_dir), message=msg, is_new_repo=is_new)


def _synthesis_loop(
    feature_files: list[Path],
    oss_dir: Path,
    log: BootstrapAuditLog,
    *,
    force: bool = False,
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

    llm = LLMClient(provider="openrouter", model=MODEL_PASS1)
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

            # Resume: skip if output already exists and --force not set
            if not force and out_dir.exists() and any(out_dir.glob("*.py")):
                existing = list(out_dir.glob("*.py"))
                print(f"  [{stem}] skipping — {len(existing)} .py file(s) already present (--force to re-run)")
                log.record("SYNTHESIS_CACHED", feature=str(feature_file), out_dir=str(out_dir),
                           existing_files=[f.name for f in existing])
                passed += len(existing)
                continue

            out_dir.mkdir(parents=True, exist_ok=True)

            try:
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
                    cr = verify_clean_room(synth_file, PRIVATE_SRC_ROOT)
                    event = "CLEAN_ROOM_PASS" if cr.passed else "CLEAN_ROOM_FAIL"
                    log.record(
                        event,
                        feature=str(feature_file),
                        file=str(synth_file),
                        sha256=BootstrapAuditLog.sha256(synth_file),
                        model=MODEL_PASS1,
                        input_tokens=token_in,
                        output_tokens=token_out,
                        payload=cr.as_log_payload(
                            module=synth_file.stem,
                            input_language="Python (Source AST)",
                            output_language="Python (Target AST)",
                        ),
                    )
                    if not cr.passed:
                        print(f"    [BLOCKED] {synth_file.name}")
                        for v in cr.violations:
                            print(f"      {v}")
                        synth_file.unlink()
                        failed += 1
                    else:
                        passed += 1

            except Exception as exc:
                reason = str(exc)
                print(f"  [{stem}] SKIPPED — {reason[:120]}")
                log.record("SYNTHESIS_SKIP", feature=str(feature_file), reason=reason)

    finally:
        container.stop()
        print("  Container stopped.")

    return passed, failed


def _synthesis_loop_ts(
    feature_files: list[Path],
    oss_dir: Path,
    log: BootstrapAuditLog,
    *,
    force: bool = False,
) -> tuple[int, int]:
    from src.agents.incremental_planner import IncrementalPlanner
    from src.agents.iterative_tdd_runner import IterativeTDDRunner
    from src.agents.podman_orchestrator import PodmanOrchestrator
    from src.agents.typescript_language_pod import TypeScriptLanguagePod
    from src.agents.typescript_runner import TypeScriptRunner, build_ts_image
    from src.agents.typescript_worker_agent import TypeScriptWorkerAgent
    from src.playbook.manager import PlaybookManager
    from src.storage.experiment_logger import ExperimentLogger
    from src.utils.llm_client import LLMClient

    print("  Building TypeScript harness image...")
    build_ts_image()
    print("  Image ready.")

    llm_fast     = LLMClient(provider="openrouter", model=MODEL_PASS1)
    llm_fallback = LLMClient(provider="openrouter", model=MODEL_PASS2)
    playbook_manager = PlaybookManager()
    experiment_logger = ExperimentLogger(playbook_version="bootstrap-ts-1.0")

    container = TypeScriptRunner(container_name="ace_ts_bootstrap")
    container.start()
    print("  Container started.")

    passed = failed = 0

    try:
        for feature_file in feature_files:
            stem = feature_file.stem
            out_dir = oss_dir / stem

            # Resume: skip if output already exists and --force not set
            if not force and out_dir.exists() and any(out_dir.glob("*.ts")):
                existing = list(out_dir.glob("*.ts"))
                print(f"  [{stem}] skipping — {len(existing)} .ts file(s) already present (--force to re-run)")
                log.record("SYNTHESIS_CACHED", feature=str(feature_file), out_dir=str(out_dir),
                           existing_files=[f.name for f in existing])
                passed += len(existing)
                continue

            out_dir.mkdir(parents=True, exist_ok=True)

            try:
                playbook_id = f"bootstrap_ts_{stem}"
                playbook_manager.get_or_create_playbook(playbook_id)

                worker = TypeScriptWorkerAgent(
                    llm_fast, playbook_manager=playbook_manager, fallback_client=llm_fallback
                )
                planner = IncrementalPlanner(
                    llm_client=llm_fast,
                    test_dir=out_dir,
                    src_dir=out_dir,
                    playbook_manager=playbook_manager,
                    playbook_id=playbook_id,
                    target_language="typescript",
                )
                orchestrator = PodmanOrchestrator(
                    runner=container,
                    work_dir=out_dir / "harness",
                    started=True,
                )
                pod = TypeScriptLanguagePod(worker, out_dir, orchestrator)
                runner = IterativeTDDRunner(
                    pod=pod,
                    planner=planner,
                    max_iterations=10,
                    max_green_attempts=5,
                    experiment_logger=experiment_logger,
                    playbook_id=playbook_id,
                )

                print(f"  [{stem}] synthesizing (TypeScript)...", end=" ", flush=True)
                result = runner.run_from_feature(feature_file)
                status = "✓" if result.success else "✗"
                print(f"{status} ({result.iterations} cycles)")

                token_in = sum(u.input_tokens for c in result.cycles for u in c.token_usage)
                token_out = sum(u.output_tokens for c in result.cycles for u in c.token_usage)

                # Remove any stale .py files the planner may have written before
                # the TypeScript path normalisation kicked in.
                for stale in out_dir.glob("*.py"):
                    stale.unlink()

                for synth_file in sorted(out_dir.glob("*.ts")):
                    cr = verify_clean_room_cross_language(synth_file, PRIVATE_SRC_ROOT)
                    event = "CLEAN_ROOM_PASS" if cr.passed else "CLEAN_ROOM_FAIL"
                    log.record(
                        event,
                        feature=str(feature_file),
                        file=str(synth_file),
                        sha256=BootstrapAuditLog.sha256(synth_file),
                        model=MODEL_PASS1,
                        input_tokens=token_in,
                        output_tokens=token_out,
                        payload=cr.as_log_payload(
                            module=synth_file.stem,
                            input_language="Python (Source AST)",
                            output_language="TypeScript (Target AST via Vitest)",
                        ),
                    )
                    if not cr.passed:
                        print(f"    [BLOCKED] {synth_file.name}")
                        for v in cr.violations:
                            print(f"      {v}")
                        synth_file.unlink()
                        failed += 1
                    else:
                        passed += 1

            except Exception as exc:
                reason = str(exc)
                print(f"  [{stem}] SKIPPED — {reason[:120]}")
                log.record("SYNTHESIS_SKIP", feature=str(feature_file), reason=reason)

    finally:
        container.stop()
        print("  Container stopped.")

    return passed, failed


if __name__ == "__main__":
    main()
