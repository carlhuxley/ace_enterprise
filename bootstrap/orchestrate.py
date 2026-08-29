"""
Bootstrap orchestrator: private repo → Gherkin → clean synthesized public repo.

Pipeline:
  Stage 1  extract    LLM reads private src/ and emits pure Gherkin feature files
  Stage 2  synthesize TDD pipeline generates fresh implementations from Gherkin
  Stage 3  verify     Clean-room AST gate — blocks any file with private-name leakage
  Stage 4  stamp      Apache-2.0 SPDX headers + LICENSE + pyproject.toml applied

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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bootstrap.audit_log import BootstrapAuditLog
from bootstrap.clean_room import verify_clean_room, verify_clean_room_cross_language, verify_ts_style
from bootstrap.extract import extract_features
from bootstrap.stamp import stamp_directory
from src.utils.llm_client import LLMQuotaExhaustedError


class BootstrapAbortError(RuntimeError):
    """Raised to stop the whole run rather than skip-and-continue per module.

    Used for failures where retrying the next module can't possibly help
    (e.g. the API key has no credit left) — continuing would just repeat the
    same doomed call ~N more times and silently produce an incomplete run
    that looks like a normal one, instead of a clear top-level error.
    """


def _abort_run(log: "BootstrapAuditLog", exc: Exception) -> None:
    """Stop the pipeline immediately with a clear top-level error, skipping
    Stage 3.5/4/5 (root-file placement, stamping, commit) — an incomplete run
    should never be silently stamped and committed as if it were a normal one.
    """
    log.record("RUN_ABORT_TERMINAL", reason=str(exc))
    print(f"\n{'=' * 70}\nBOOTSTRAP RUN ABORTED: {exc}\n"
          f"Fix the underlying issue (e.g. top up API credits) and re-run — "
          f"already-verified modules will be skipped automatically.\n{'=' * 70}")
    sys.exit(1)


def _resume_decision(
    out_dir: Path, feature_file: Path, glob_pattern: str, force: bool
) -> tuple[str, list[Path], str, str | None]:
    """Decide whether a module needs (re-)synthesis, based on a *verified*
    marker rather than output-file presence (ace_enterprise-ykl).

    .spec.sha256 is only written by the caller after the clean-room/style gate
    passes for every output file, so its presence with a hash matching the
    current spec is the real "this was verified" signal. Output files being
    present without that marker just means a prior run got as far as writing
    them — including a run that was killed (OOM, exhausted credits) before
    verification ran — so they're treated the same as "nothing here yet".

    Returns (action, existing_files, current_spec_sha, recorded_spec_sha) where
    recorded_spec_sha is only non-None for "cache_bust", and action is one of:
      "cached"      — verified marker matches current spec; caller should skip
      "cache_bust"  — verified marker present but spec changed; re-synthesise
      "unverified"  — output files present but no verified marker; re-synthesise
      "fresh"       — nothing here yet; re-synthesise
    """
    current_spec_sha = BootstrapAuditLog.sha256(feature_file)
    if force or not out_dir.exists():
        return "fresh", [], current_spec_sha, None

    existing = list(out_dir.glob(glob_pattern))
    if not existing:
        return "fresh", [], current_spec_sha, None

    spec_hash_file = out_dir / ".spec.sha256"
    if not spec_hash_file.exists():
        return "unverified", existing, current_spec_sha, None

    recorded_spec_sha = spec_hash_file.read_text().strip()
    if recorded_spec_sha != current_spec_sha:
        return "cache_bust", existing, current_spec_sha, recorded_spec_sha
    return "cached", existing, current_spec_sha, recorded_spec_sha

# ---------------------------------------------------------------------------
# Configuration — edit these before running
# ---------------------------------------------------------------------------

PRIVATE_SRC_ROOT = Path("src")           # checked against for clean-room gate

# Structural shims and Python runtime abstractions that should not cross the boundary
_SKIP_FOR_TS = {
    "language_pod",
    "python_language_pod",
    "podman_runner",
    "go_language_pod",  # feature spec too Go-toolchain-specific; see ace_enterprise-vmg
}

# Modules synthesised first so the app is functional ASAP.
# Tier 1 — foundation (everything depends on these)
# Tier 2 — storage & persistence
# Tier 3 — playbook / learning system
# Tier 4 — broker / model routing
# Tier 5 — CLI / public API surface
# Anything not listed here follows in its natural (alphabetical) order.
_SYNTHESIS_PRIORITY = [
    # Tier 1
    "llm_client",
    "id_generator",
    "file_lock",
    "settings",
    "config",
    "storage_schemas",  # storage/schemas
    "storage_models",   # storage/models
    # Tier 2
    "database",
    "repository",
    "experiment_logger",
    "store",          # audit/store
    # Tier 3
    "manager",        # playbook/manager
    "service",        # retrieval/service
    "retrieval",
    "embedding",
    # Tier 4
    "adaptive_broker",
    "bayesian",
    "capability_registry",
    "factory",
    # Tier 5
    "ace_cli",
    "api_index",
]


def _priority_sort_key(feature_file: Path) -> tuple[int, str]:
    """Sort key: priority-listed modules first (in list order), rest alphabetically."""
    stem = feature_file.stem
    try:
        return (0, str(_SYNTHESIS_PRIORITY.index(stem)).zfill(4))
    except ValueError:
        return (1, stem)


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
MODEL_EXTRACT = "anthropic/claude-haiku-4-5"    # Stage 1: Gherkin extraction
MODEL_PASS1   = "anthropic/claude-haiku-4-5"    # Pass 1: cheap synthesis
MODEL_PASS2   = "anthropic/claude-sonnet-4-5"   # Pass 2: escalate on repeated failure


def _make_llm_client(model: str, client: str):
    """Construct the LLM client for one synthesis role (extract/pass1/pass2/...).

    client="claude-cli" ignores `model` entirely and returns a fresh
    ClaudeCliClient -- it has no per-call model selection (always whatever
    the authenticated Claude Code session defaults to), so callers that
    construct two of these for cost-tier escalation (Pass1 vs Pass2) get
    two independent instances that behave identically rather than a
    literal cheap/premium distinction. That's an accepted tradeoff of
    --client claude-cli, not a bug -- see _parse_args()'s --client help.
    """
    if client == "claude-cli":
        from src.utils.claude_cli_client import ClaudeCliClient
        return ClaudeCliClient()
    from src.utils.llm_client import LLMClient
    return LLMClient(provider="openrouter", model=model)

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
    parser = argparse.ArgumentParser(description="Bootstrap pipeline: private → Gherkin → public Apache-2.0 repo")
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
    parser.add_argument(
        "--client", choices=["openrouter", "claude-cli"], default="openrouter",
        help="LLM backend for extraction and synthesis. 'openrouter' (default) requires "
             "OPENROUTER_API_KEY with remaining credit. 'claude-cli' routes every call "
             "through the local authenticated Claude Code session instead -- no API key "
             "or credits needed, but it has no per-call model selection, so the Pass1/"
             "Pass2 cost-tier escalation collapses to a single model either way."
    )
    args = parser.parse_args()
    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"Error: {p} not found", file=sys.stderr)
            sys.exit(1)
        return [p], args.lang, args.force, args.client
    return get_target_modules(PRIVATE_SRC_ROOT, args.lang), args.lang, args.force, args.client


def main() -> None:
    source_files, lang, force, client = _parse_args()
    if client == "openrouter":
        _check_openrouter_credits()
    else:
        print(f"[INFO] --client={client} — skipping OpenRouter credit check, no API key needed")
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
        llm_client=_make_llm_client(MODEL_EXTRACT, client),
        src_root=PRIVATE_SRC_ROOT,
    )
    print(f"  {len(feature_files)} feature files written to {FEATURES_DIR}/")

    # Pick up hand-authored .feature files not produced by extraction this run.
    # These are logged as GHERKIN_MANUAL so the audit trail records human authorship.
    produced_stems = {f.stem for f in feature_files}
    manual_features = sorted(
        f for f in FEATURES_DIR.glob("*.feature")
        if f.stem not in produced_stems
    )
    for mf in manual_features:
        log.record("GHERKIN_MANUAL", feature_file=str(mf), sha256=BootstrapAuditLog.sha256(mf))
        print(f"  [manual] {mf.name}")
    if manual_features:
        feature_files = feature_files + manual_features
        print(f"  +{len(manual_features)} hand-authored feature file(s) queued for synthesis")

    # Collect contract-spec files now so they are logged before synthesis begins.
    # These are routed to _contract_synth_path (no TDD container) rather than
    # _synthesis_loop_ts.  Only meaningful for the typescript target.
    contract_specs = sorted(FEATURES_DIR.glob("*.contract.yml")) if lang == "typescript" else []
    contract_stems = {cs.stem.split(".")[0] for cs in contract_specs}
    if contract_specs:
        for cs in contract_specs:
            log.record("CONTRACT_SPEC_QUEUED", contract_file=str(cs),
                       sha256=BootstrapAuditLog.sha256(cs))
        print(f"  +{len(contract_specs)} contract spec(s) queued for interface synthesis")

    # Drop any .feature files that have been superseded by a .contract.yml —
    # they would otherwise be routed to the TDD container and fail repeatedly.
    if contract_stems:
        before = len(feature_files)
        feature_files = [f for f in feature_files if f.stem not in contract_stems]
        dropped = before - len(feature_files)
        if dropped:
            print(f"  -{dropped} feature file(s) superseded by contract spec(s), removed from TDD queue")

    if not feature_files and not contract_specs:
        print("  Nothing to synthesize — aborting.")
        log.record("RUN_ABORT", reason="no feature files produced in Stage 1")
        return

    # ------------------------------------------------------------------
    # Pre-synthesis: Gherkin style precheck
    # ------------------------------------------------------------------
    warnings = _check_feature_snake_case(feature_files)
    if warnings:
        print(f"\n=== Gherkin Precheck: {len(warnings)} snake_case issue(s) found ===")
        for w in warnings:
            print(f"  {w}")
        print("  Fix these before running synthesis to avoid STYLE_BLOCK failures.\n")

    # ------------------------------------------------------------------
    # Set up this run's branch BEFORE any synthesis writes a single file --
    # see _start_run_branch's docstring for why this can't happen at
    # Stage 5 (commit time) like it used to.
    # ------------------------------------------------------------------
    _start_run_branch(OSS_DIR, log)

    # ------------------------------------------------------------------
    # Stage 2 + 3: Synthesize & Verify (Gherkin TDD path)
    # ------------------------------------------------------------------
    print(f"\n=== Stage 2+3: Synthesize & Verify ({len(feature_files)} features) ===")
    feature_files = sorted(feature_files, key=_priority_sort_key)
    priority_pending = [f.stem for f in feature_files if _priority_sort_key(f)[0] == 0]
    print(f"  Priority queue ({len(priority_pending)}): {', '.join(priority_pending)}")
    try:
        if lang == "typescript":
            passed, failed = _synthesis_loop_ts(feature_files, OSS_DIR, log, force=force, client=client)
        else:
            passed, failed = _synthesis_loop(feature_files, OSS_DIR, log, force=force, client=client)
    except BootstrapAbortError as exc:
        _abort_run(log, exc)
    print(f"  passed={passed}  blocked={failed}")

    # ------------------------------------------------------------------
    # Stage 2.5: Contract Interface Synthesis (no TDD container)
    # ------------------------------------------------------------------
    if contract_specs:
        print(f"\n=== Stage 2.5: Contract Interface Synthesis ({len(contract_specs)} specs) ===")
        try:
            c_passed, c_failed = _contract_synth_path(contract_specs, OSS_DIR, log, force=force, client=client)
        except BootstrapAbortError as exc:
            _abort_run(log, exc)
        passed += c_passed
        failed += c_failed
        print(f"  passed={c_passed}  blocked={c_failed}")

    # ------------------------------------------------------------------
    # Stage 3.5: Place root-level files
    # Certain synthesised modules must live at the repo root rather than in
    # their subdirectory (e.g. vitest.config.ts).  Copy and log on the chain.
    # ------------------------------------------------------------------
    if lang == "typescript":
        _place_root_files(OSS_DIR, log)

    # ------------------------------------------------------------------
    # Stage 4: Stamp
    # ------------------------------------------------------------------
    print("\n=== Stage 4: Stamp ===")
    stamped = stamp_directory(OSS_DIR, log, lang=lang)
    print(f"  {stamped} files stamped Apache-2.0")

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
    # Stage 5: Commit public repo (own branch off main -- never main itself)
    # ------------------------------------------------------------------
    print("\n=== Stage 5: Commit public repo ===")
    try:
        _commit_public_repo(OSS_DIR, passed, log)
    except RegressionAbortError as exc:
        log.record("RUN_ABORT_TERMINAL", reason=str(exc))
        print(f"\n{'=' * 70}\nBOOTSTRAP RUN ABORTED — REGRESSION DETECTED\n{exc}\n{'=' * 70}")
        sys.exit(1)
    except MainBranchCommitRefusedError as exc:
        log.record("RUN_ABORT_TERMINAL", reason=str(exc))
        print(f"\n{'=' * 70}\nBOOTSTRAP RUN ABORTED — MAIN CHECKED OUT\n{exc}\n{'=' * 70}")
        sys.exit(1)

    print(f"\nDone. Public repo: {OSS_DIR.resolve()}")
    print("Review and merge the run's branch into main yourself when satisfied "
          "(see the 'Committed to branch' message above for the exact commands) "
          "-- nothing pushes to origin/main automatically.")


class RegressionAbortError(RuntimeError):
    """Raised when a run would delete/empty files that main already has
    committed -- see _commit_public_repo's regression guard."""


class MainBranchCommitRefusedError(RuntimeError):
    """Raised when _commit_public_repo finds main checked out instead of a
    bootstrap/<timestamp> run branch -- see its docstring for why this is
    a hard refusal rather than a fall-through to committing on main."""


def _git_oss(oss_dir: Path, *args: str) -> "subprocess.CompletedProcess":
    import subprocess
    return subprocess.run(["git", *args], cwd=oss_dir, capture_output=True, text=True, check=True)


def _start_run_branch(oss_dir: Path, log: BootstrapAuditLog) -> str:
    """Create and check out this run's branch off main's current tip --
    called BEFORE Stage 2 writes a single file into oss_dir, not at Stage 5
    (commit time) like a first version of this fix did.

    Discovered live why the ordering matters: branch creation used to
    happen in _commit_public_repo, at the very end of a run. But nothing
    resets the working tree to main at the *start* of a run -- whatever
    branch the previous run's Stage 5 left checked out (by design; merging
    to main is a deliberate human step) is still checked out when the next
    run's Stage 2 starts writing files on top of it. By the time that next
    run reached its own Stage 5 and tried `git checkout main`, git
    correctly refused ("local changes would be overwritten") rather than
    silently discard 17 modules' worth of real, uncommitted progress --
    but that's a crash with real work stranded, not what "every run gets
    its own clean branch" was supposed to guarantee.

    Now: whatever's on disk when a run starts (any leftover uncommitted
    changes from an interrupted previous run) gets committed to whatever
    branch is currently checked out FIRST -- preserving it, never
    discarding -- then main is checked out cleanly and a fresh
    bootstrap/<UTC timestamp>-<uuid> branch is cut from its tip for this
    run to write into from a known-clean baseline.
    """
    import subprocess
    import uuid
    from datetime import datetime, timezone

    is_new = not (oss_dir / ".git").exists()
    if is_new:
        _git_oss(oss_dir, "init", "-b", "main")
        _git_oss(oss_dir, "config", "user.name", "ace-bootstrap")
        _git_oss(oss_dir, "config", "user.email", "bootstrap@ace-enterprise")
        _git_oss(oss_dir, "commit", "--allow-empty", "-m", "Initial empty commit")

    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=oss_dir, capture_output=True, text=True
    )
    if status.stdout.strip():
        current = subprocess.run(
            ["git", "branch", "--show-current"], cwd=oss_dir, capture_output=True, text=True
        ).stdout.strip()
        print(f"  [WARN] Uncommitted changes found on '{current}' from a previous run -- "
              f"committing them there before starting this run's branch, to avoid losing them.")
        _git_oss(oss_dir, "add", "-A")
        _git_oss(oss_dir, "commit", "-m", f"Recovered uncommitted changes from previous run on {current}")
        log.record("PREVIOUS_RUN_RECOVERED", oss_dir=str(oss_dir), branch=current)

    # uuid suffix guards against two runs landing in the same second (the
    # timestamp alone collided immediately in testing -- consecutive calls
    # with no real work between them).
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    branch = f"bootstrap/{run_id}-{uuid.uuid4().hex[:6]}"
    _git_oss(oss_dir, "checkout", "main")
    _git_oss(oss_dir, "checkout", "-b", branch)
    log.record("RUN_BRANCH_STARTED", oss_dir=str(oss_dir), branch=branch)
    print(f"  Run branch: {branch}")
    return branch


def _commit_public_repo(oss_dir: Path, module_count: int, log: BootstrapAuditLog) -> None:
    """Commit this run's output to the branch _start_run_branch already
    checked out -- never directly to main, which is what gets pushed to
    the public GitHub repo (origin/main); nothing should land there
    without a human reviewing the diff first.

    The regression guard is the second, independent safeguard: before
    committing, every file main's tip already tracks is checked for
    continued presence. Discovered live why this matters too -- a run can
    silently overwrite-then-delete previously-good, already-committed
    files when fresh synthesis fails clean-room/style verification against
    a stale spec (orphaned .feature files from a naming-scheme change
    queued themselves for re-synthesis and clobbered 34 modules' worth of
    good output). A missing file aborts with RegressionAbortError and the
    full list -- a hard failure surfaced at the top level, not a line in a
    100+-module printout to notice or miss.

    Merging this run's branch into main is a separate, deliberate step
    left to a human (or a future --merge flag), never automatic.

    Third, independent safeguard, added after live fallout from the first
    two: a run committed straight onto main despite _start_run_branch
    correctly creating and checking out a bootstrap/<timestamp> branch at
    the start (confirmed via RUN_BRANCH_STARTED in the audit log) -- no
    checkout call anywhere in this file's code path can explain the branch
    being back on main by the time this function ran hours later, so the
    most likely cause is something external touching the checked-out
    branch in that window (this is a real directory on a real filesystem;
    nothing stops another process or a human `cd`-ing in and running
    `git checkout main` themselves while a run is still in progress). Root
    cause aside, the fix that actually matters is structural: this
    function now refuses outright to commit while main is checked out,
    regardless of how it got that way. No content was lost that time (the
    regression guard below still held), but "never lands on main
    unreviewed" should not depend on nothing-external-ever-touching-the-
    directory for hours.
    """
    import subprocess
    from datetime import datetime, timezone

    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=oss_dir, capture_output=True, text=True
    ).stdout.strip()
    if branch == "main":
        raise MainBranchCommitRefusedError(
            "Refusing to commit: main is checked out in the public repo, but "
            "_commit_public_repo() must only ever commit to a bootstrap/<timestamp> "
            "run branch. Something switched the checked-out branch back to main "
            "after _start_run_branch ran -- nothing in orchestrate.py's own code "
            "path does this, so check for another process or a manual `git "
            f"checkout` in {oss_dir} during this run. Nothing was committed."
        )

    # main tip's tracked files -- the baseline the regression guard checks
    # the new manifest against. Empty for a brand-new repo (nothing to regress).
    ls_tree = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "main"],
        cwd=oss_dir, capture_output=True, text=True,
    )
    main_files = {line for line in ls_tree.stdout.splitlines() if line}
    is_new = len(main_files) == 0

    _git_oss(oss_dir, "add", ".")

    # Check whether there's anything to commit
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=oss_dir, capture_output=True, text=True
    )
    if not status.stdout.strip():
        print("  Nothing new to commit — public repo already up to date.")
        _git_oss(oss_dir, "checkout", "main")
        _git_oss(oss_dir, "branch", "-d", branch)
        return

    # Audit manifest — every file about to be committed, with sha256
    manifest = {}
    for f in sorted(oss_dir.rglob("*")):
        if f.is_file() and ".git" not in f.parts:
            manifest[str(f.relative_to(oss_dir))] = BootstrapAuditLog.sha256(f)
    log.record("REPO_CONTENTS", oss_dir=str(oss_dir), file_count=len(manifest), files=manifest)

    # Regression guard: every file main's tip already tracks must still be
    # present. A missing one means this run overwrote-then-deleted it
    # (failed re-verification against a stale spec, wrong routing, etc.) --
    # abort rather than let that land in a branch that looks like a normal
    # successful run.
    missing = sorted(main_files - set(manifest))
    if missing:
        log.record("REGRESSION_ABORT", oss_dir=str(oss_dir), branch=branch, missing_files=missing)
        raise RegressionAbortError(
            f"{len(missing)} file(s) tracked on main are missing from this run's output "
            f"(would be deleted if committed):\n  " + "\n  ".join(missing) +
            f"\n\nLeft uncommitted on branch '{branch}' for inspection -- "
            f"main is untouched. Fix the cause (or discard this branch) before retrying."
        )

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if is_new:
        msg = f"Initial clean-room synthesized release ({module_count} modules, {ts})"
    else:
        msg = f"Synthesized update: {module_count} modules ({ts})"

    _git_oss(oss_dir, "commit", "-m", msg)
    result = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=oss_dir, capture_output=True, text=True
    )
    print(f"  Committed to branch '{branch}': {result.stdout.strip()}")
    print(f"  main is untouched. Review with: cd {oss_dir} && git diff main {branch}")
    print(f"  Merge when satisfied: git checkout main && git merge {branch}")
    log.record("GIT_COMMIT", oss_dir=str(oss_dir), branch=branch, message=msg, is_new_repo=is_new)


# Maps synthesised module stem → destination filename at the repo root.
_ROOT_FILE_PLACEMENTS: dict[str, str] = {
    "vitest_config": "vitest.config.ts",
}


def _place_root_files(oss_dir: Path, log: BootstrapAuditLog) -> None:
    """Copy designated synthesised modules to their repo-root destination."""
    import shutil
    for stem, dest_name in _ROOT_FILE_PLACEMENTS.items():
        src = oss_dir / stem / f"{stem}.ts"
        dest = oss_dir / dest_name
        if not src.exists():
            print(f"  [root-place] {dest_name} — source not yet synthesised, skipping")
            continue
        shutil.copy2(src, dest)
        log.record(
            "ROOT_FILE_PLACED",
            src=str(src),
            dest=str(dest),
            sha256=BootstrapAuditLog.sha256(dest),
        )
        print(f"  [root-place] {stem}/{stem}.ts → {dest_name}")


def _synthesis_loop(
    feature_files: list[Path],
    oss_dir: Path,
    log: BootstrapAuditLog,
    *,
    force: bool = False,
    client: str = "openrouter",
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

    llm = _make_llm_client(MODEL_PASS1, client)
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

            # Resume: skip only if a *verified* prior run exists for the current
            # spec (ace_enterprise-ykl) — see _resume_decision docstring.
            action, existing, current_spec_sha, recorded_spec_sha = _resume_decision(
                out_dir, feature_file, "*.py", force
            )
            if action == "cached":
                print(f"  [{stem}] skipping — {len(existing)} verified .py file(s) present, spec unchanged")
                log.record("SYNTHESIS_CACHED", feature=str(feature_file), out_dir=str(out_dir),
                           existing_files=[f.name for f in existing],
                           file_hashes={f.name: BootstrapAuditLog.sha256(f) for f in existing},
                           spec_sha=current_spec_sha)
                passed += len(existing)
                continue
            elif action == "cache_bust":
                print(f"  [{stem}] spec changed — re-synthesising")
                log.record("CACHE_BUST", feature=str(feature_file),
                           recorded_spec_sha=recorded_spec_sha, current_spec_sha=current_spec_sha)
            elif action == "unverified":
                print(f"  [{stem}] {len(existing)} unverified .py file(s) present (no .spec.sha256) — re-synthesising")
                log.record("SYNTHESIS_UNVERIFIED_RESYNTH", feature=str(feature_file), out_dir=str(out_dir),
                           existing_files=[f.name for f in existing])

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
                    max_iterations=6,
                    max_green_attempts=3,
                    experiment_logger=experiment_logger,
                    playbook_id=playbook_id,
                )

                print(f"  [{stem}] synthesizing...", end=" ", flush=True)
                result = runner.run_from_feature(feature_file)
                status = "✓" if result.success else "✗"
                print(f"{status} ({result.iterations} cycles)")

                token_in = sum(u.input_tokens for c in result.cycles for u in c.token_usage)
                token_out = sum(u.output_tokens for c in result.cycles for u in c.token_usage)

                module_ok = True
                for synth_file in sorted(out_dir.glob("*.py")):
                    cr = verify_clean_room(synth_file, PRIVATE_SRC_ROOT)
                    event = "CLEAN_ROOM_PASS" if cr.passed else "CLEAN_ROOM_FAIL"
                    log.record(
                        event,
                        feature=str(feature_file),
                        file=str(synth_file),
                        sha256=BootstrapAuditLog.sha256(synth_file),
                        model=llm.model,
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
                        module_ok = False
                    else:
                        passed += 1

                if module_ok and any(out_dir.glob("*.py")):
                    (out_dir / ".spec.sha256").write_text(current_spec_sha)

            except LLMQuotaExhaustedError as exc:
                # Fatal for the whole run, not just this module — every remaining
                # module would fail the same way. Stop instead of skip-and-continue
                # (ace_enterprise-wki).
                log.record("RUN_ABORT", reason=f"LLM quota exhausted: {exc}",
                           feature=str(feature_file), modules_completed=passed)
                print(f"\nABORT: LLM quota/credit exhausted while synthesising [{stem}]: {exc}")
                raise BootstrapAbortError(str(exc)) from exc

            except Exception as exc:
                reason = str(exc)
                print(f"  [{stem}] SKIPPED — {reason[:120]}")
                log.record("SYNTHESIS_SKIP", feature=str(feature_file), reason=reason)

    finally:
        container.stop()
        print("  Container stopped.")

    return passed, failed


_SHARED_PLAYBOOK_ID = "bootstrap_ts_shared"

# Seed bullets written once into the shared playbook at run start.
# Encode known-good patterns for TypeScript synthesis derived from observed failures.
_BOOTSTRAP_TS_SEED_BULLETS = [
    # --- test assertion rules ---
    (
        "Test structural shape, not exact string content — use `typeof result === 'string'`, "
        "`result.length > 0`, or regex patterns instead of asserting hardcoded literal strings. "
        "Exact string assertions almost always fail in TypeScript synthesis.",
        "test_assertion_rules",
    ),
    (
        "Import vitest globals explicitly when needed: "
        "`import { describe, it, expect, beforeEach, afterEach } from 'vitest'` — "
        "or rely on globals:true in vitest.config.ts. Never assume they are ambient.",
        "test_assertion_rules",
    ),
    (
        "Keep each test independent — use `beforeEach` to reset fixtures and avoid shared "
        "mutable state between `it` blocks. TypeScript synthesis fails when test order matters.",
        "test_assertion_rules",
    ),
    # --- strategies and hard rules ---
    (
        "Avoid Python-specific test idioms — translate to TypeScript equivalents: "
        "use `expect(fn).toThrow()` not `pytest.raises`, `vi.fn()` not `unittest.mock.patch`, "
        "`.ts` file extensions not `.py`.",
        "strategies_and_hard_rules",
    ),
    (
        "Spec observable behaviour via interface contracts, not implementation internals — "
        "assert what goes in and what comes out; never assert private method names, "
        "internal class hierarchies, or exact prompt strings.",
        "strategies_and_hard_rules",
    ),
    # --- TypeScript conventions (also enforced by the Stage 3 style gate) ---
    (
        "Use camelCase for ALL TypeScript identifiers — variables, parameters, properties, "
        "and private fields. Never use snake_case, even for internal state "
        "(e.g. `helpfulCount` not `helpful_count`, `totalBullets` not `total_bullets`). "
        "Files synthesised with snake_case identifiers are rejected at the style gate.",
        "strategies_and_hard_rules",
    ),
    (
        "Never use Math.random() as a default field value or fallback — it makes tests "
        "non-deterministic and the synthesised file will be rejected. Callers must provide "
        "values, or the constructor should require them explicitly.",
        "strategies_and_hard_rules",
    ),
    (
        "Never write a custom hash function (no djb2, no bitwise hash, no charCodeAt loops). "
        "Use `import { createHash } from 'crypto'; createHash('sha256').update(content).digest('hex')` "
        "only when the spec explicitly requires content hashing. "
        "For unique IDs use `crypto.randomUUID()`. "
        "Custom hash implementations are rejected at the style gate.",
        "strategies_and_hard_rules",
    ),
    (
        "The test harness only has vitest and Node built-ins. Never import express, hono, fastify, "
        "supertest, axios, or any HTTP framework or client — they are not installed. "
        "Implement HTTP-style route handlers as plain exported functions that accept typed request "
        "objects and return typed response objects; tests call them directly without a running server.",
        "strategies_and_hard_rules",
    ),
    (
        "Provide real implementation logic — do not stub methods with hardcoded return values "
        "like `id: 'ctx-001'` or `id: 'pb-existing'`. Hardcoded stub IDs are rejected at the "
        "style gate. Generate IDs from a counter, uuid, or hash of the content.",
        "strategies_and_hard_rules",
    ),
    (
        "Prefer `interface` over `class` for pure data shapes — use a class only when the "
        "type needs methods or encapsulation. Plain data transfer objects should be interfaces "
        "so callers can construct them with object literals.",
        "strategies_and_hard_rules",
    ),
    # --- rule-ts-001: Language & Idioms ---
    (
        "Never use Python context-manager patterns (`__enter__`/`__exit__` methods or "
        "`with` statements). Use TypeScript `try/finally` blocks for cleanup, or Explicit "
        "Resource Management (`using` / `await using` with `Symbol.dispose` / `AsyncDisposable`). "
        "Files containing `__enter__` or `__exit__` are rejected at the style gate.",
        "strategies_and_hard_rules",
    ),
    (
        "Throw native JavaScript error types only — `Error`, `TypeError`, `RangeError`. "
        "Never reference Python exception names such as `RuntimeError`, `ValueError`, or "
        "`KeyError`. Python exception names in synthesised TypeScript are rejected at the style gate.",
        "strategies_and_hard_rules",
    ),
    (
        "Do not use `to_dict()` or `from_dict()` for serialization — these are Python idioms. "
        "Use TypeScript-native patterns instead: object spreading (`{ ...obj }`), "
        "`JSON.parse`/`JSON.stringify`, or explicit property mapping in a plain function.",
        "strategies_and_hard_rules",
    ),
    # --- rule-ts-003: Types & Architecture ---
    (
        "Ban `any` in all forms — implicit or explicit. All caught exceptions must be typed "
        "as `unknown` and type-guarded before access "
        "(e.g. `if (err instanceof Error) { msg = err.message; }`). "
        "Files containing `any` or unguarded `catch (e)` are rejected at the style gate.",
        "strategies_and_hard_rules",
    ),
    (
        "All core domain types and interfaces (e.g. `Bullet`, `Playbook`, `PodSpec`) must be "
        "imported from a single unified type registry file. Never redefine these shapes inline "
        "across multiple modules — duplicate definitions cause drift and are rejected.",
        "strategies_and_hard_rules",
    ),
]


_GHERKIN_SNAKE_KEY = re.compile(r'\{[^}]*"([a-z][a-z0-9]+(?:_[a-z0-9]+)+)"\s*:')
_GHERKIN_SNAKE_VAL = re.compile(r'(?:taskType|eventType|type|kind)\s+"([a-z][a-z0-9]+(?:_[a-z0-9]+)+)"')


def _check_feature_snake_case(feature_files: list) -> list[str]:
    """Scan feature files for snake_case JSON keys and type-discriminator values.

    These leak into generated TypeScript as identifiers and cause STYLE_BLOCK
    failures at the style gate. Returns a list of human-readable warning strings.
    """
    warnings = []
    for path in sorted(feature_files):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in _GHERKIN_SNAKE_KEY.finditer(line):
                warnings.append(f"{path.name}:{lineno}: JSON key '{m.group(1)}' is snake_case → rename to camelCase")
            for m in _GHERKIN_SNAKE_VAL.finditer(line):
                warnings.append(f"{path.name}:{lineno}: type-discriminator value '{m.group(1)}' is snake_case → rename to camelCase")
    return warnings


def _seed_shared_playbook(playbook_manager, log: BootstrapAuditLog) -> None:
    """Ensure the shared bootstrap playbook contains all expected seed bullets.

    Content-deduplicating: safe to call when the playbook already has bullets
    from a previous run — only missing entries are added.
    """
    from src.storage.schemas import BulletCreate
    pb = playbook_manager.get_or_create_playbook(_SHARED_PLAYBOOK_ID)

    existing_contents = {
        b.content
        for section_bullets in pb.sections.values()
        for b in section_bullets
    }

    added = 0
    for content, section in _BOOTSTRAP_TS_SEED_BULLETS:
        if content not in existing_contents:
            playbook_manager.add_bullet(_SHARED_PLAYBOOK_ID, BulletCreate(content=content, section=section))
            added += 1

    pb = playbook_manager.get_or_create_playbook(_SHARED_PLAYBOOK_ID)
    total = sum(len(v) for v in pb.sections.values())
    if added:
        log.record("PLAYBOOK_SEEDED", playbook_id=_SHARED_PLAYBOOK_ID, bullets_added=added, total=total)
        print(f"  Shared playbook '{_SHARED_PLAYBOOK_ID}': added {added} bullet(s) → {total} total")
    else:
        print(f"  Shared playbook '{_SHARED_PLAYBOOK_ID}': {total} bullets (already complete)")


def _parse_ts_blocks(response: str) -> dict[str, str]:
    """Extract named TypeScript fenced blocks from an LLM response.

    Matches both ```typescript filename.ts and ```ts filename.ts openers.
    Returns {filename: code} with trailing whitespace stripped from each block.
    """
    blocks: dict[str, str] = {}
    for m in re.finditer(r"```(?:typescript|ts) (\S+\.ts)\n(.*?)```", response, re.DOTALL):
        blocks[m.group(1)] = m.group(2).rstrip()
    return blocks


def _build_contract_synth_prompt(python_source: str, contract_spec: str) -> str:
    """Build the single-shot synthesis prompt for the contract interface path.

    Concatenation avoids str.format() breakage when python_source or
    contract_spec contain literal braces.
    """
    return (
        "You are a TypeScript interface synthesiser. Produce clean-room TypeScript "
        "from a Python source file and a contract specification.\n\n"
        "CLEAN-ROOM RULES (enforced by automated gate — violations cause rejection):\n"
        "1. Do NOT copy names, comments, docstrings, or identifiers verbatim from the "
        "Python source. Translate concepts; do not transcribe them.\n"
        "2. Use camelCase for ALL TypeScript identifiers. Never snake_case.\n"
        "3. Only native JS error types: Error, TypeError, RangeError. Never Python "
        "names (ValueError, RuntimeError, KeyError, etc.).\n"
        "4. No `any`. Type caught exceptions as `unknown` and type-guard before access.\n"
        "5. No Python idioms: no __enter__/__exit__, no to_dict/from_dict.\n"
        "6. Use crypto.createHash('sha256') for hashing. Never djb2-style bitwise hash.\n"
        "7. No hardcoded stub IDs — derive from content, counter, or crypto.randomUUID().\n"
        "8. Prefer `interface` over `class` for pure data shapes.\n\n"
        "PYTHON SOURCE (understand the intent; do not copy):\n"
        "---\n"
        + python_source
        + "\n---\n\n"
        "CONTRACT SPECIFICATION (defines exactly what TypeScript to produce):\n"
        "---\n"
        + contract_spec
        + "\n---\n\n"
        "OUTPUT FORMAT:\n"
        "Emit each TypeScript file as a named fenced code block. "
        "Produce ONLY the files listed in typescript_output. No test files. "
        "No prose between blocks.\n\n"
        "```typescript <filename>.ts\n"
        "// implementation\n"
        "```\n"
    )


def _contract_synth_path(
    contract_files: list[Path],
    oss_dir: Path,
    log: BootstrapAuditLog,
    *,
    force: bool = False,
    client: str = "openrouter",
) -> tuple[int, int]:
    """Synthesise TypeScript from .contract.yml specs without a TDD container.

    Used for IO-wiring and schema modules whose behaviour cannot be exercised
    in a sandboxed Vitest container. A single LLM call generates the TypeScript
    directly from the Python source + YAML contract spec. The same clean-room
    and style gates apply; results land on the audit chain as CONTRACT_SYNTH_PASS
    or CONTRACT_SYNTH_FAIL instead of CLEAN_ROOM_PASS.
    """
    import yaml as _yaml

    llm = _make_llm_client(MODEL_PASS1, client)
    passed = failed = 0

    for contract_file in contract_files:
        spec = _yaml.safe_load(contract_file.read_text())
        stem = spec.get("module", contract_file.stem.split(".")[0])
        out_dir = oss_dir / stem

        # --- caching: same verified-marker logic as _synthesis_loop_ts (ace_enterprise-ykl) ---
        action, existing, current_spec_sha, recorded_spec_sha = _resume_decision(
            out_dir, contract_file, "*.ts", force
        )
        if action == "cached":
            print(f"  [{stem}] skipping — {len(existing)} verified .ts file(s) present, spec unchanged")
            log.record(
                "SYNTHESIS_CACHED", feature=str(contract_file), out_dir=str(out_dir),
                existing_files=[f.name for f in existing],
                file_hashes={f.name: BootstrapAuditLog.sha256(f) for f in existing},
                spec_sha=current_spec_sha,
            )
            passed += len(existing)
            continue
        elif action == "cache_bust":
            print(f"  [{stem}] spec changed — re-synthesising (contract path)")
            log.record("CACHE_BUST", feature=str(contract_file),
                       recorded_spec_sha=recorded_spec_sha, current_spec_sha=current_spec_sha)
        elif action == "unverified":
            print(f"  [{stem}] {len(existing)} unverified .ts file(s) present (no .spec.sha256) — re-synthesising")
            log.record("SYNTHESIS_UNVERIFIED_RESYNTH", feature=str(contract_file), out_dir=str(out_dir),
                       existing_files=[f.name for f in existing])

        source_file = Path(spec.get("source_file", ""))
        if not source_file.exists():
            reason = f"source_file not found: {source_file}"
            print(f"  [{stem}] SKIPPED — {reason}")
            log.record("SYNTHESIS_SKIP", feature=str(contract_file), reason=reason)
            continue

        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            prompt = _build_contract_synth_prompt(
                python_source=source_file.read_text(),
                contract_spec=contract_file.read_text(),
            )

            print(f"  [{stem}] synthesizing (contract path)...", end=" ", flush=True)
            result = llm.generate(prompt)
            token_in  = result.get("prompt_tokens", 0) or result.get("input_tokens", 0)
            token_out = result.get("completion_tokens", 0) or result.get("output_tokens", 0)

            ts_blocks = _parse_ts_blocks(result["content"])
            if not ts_blocks:
                print("✗ (no named TypeScript blocks in response)")
                log.record("SYNTHESIS_SKIP", feature=str(contract_file),
                           reason="no named TypeScript blocks in LLM response")
                failed += 1
                continue

            print(f"✓ ({len(ts_blocks)} file(s))")

            module_ok = True
            for filename, code in sorted(ts_blocks.items()):
                synth_file = out_dir / filename
                synth_file.write_text(code + "\n")

                cr = verify_clean_room_cross_language(synth_file, PRIVATE_SRC_ROOT)
                if not cr.passed:
                    log.record(
                        "CONTRACT_SYNTH_FAIL",
                        feature=str(contract_file),
                        file=str(synth_file),
                        sha256=BootstrapAuditLog.sha256(synth_file),
                        model=llm.model,
                        input_tokens=token_in,
                        output_tokens=token_out,
                        reason="clean_room",
                        payload=cr.as_log_payload(
                            module=synth_file.stem,
                            input_language="Python (Source AST)",
                            output_language="TypeScript (Contract Interface)",
                        ),
                    )
                    print(f"    [CONTRACT_SYNTH_FAIL] {filename} — clean-room")
                    for v in cr.violations:
                        print(f"      {v}")
                    synth_file.unlink()
                    failed += 1
                    module_ok = False
                    continue

                sr = verify_ts_style(synth_file)
                if not sr.passed:
                    log.record(
                        "STYLE_BLOCK",
                        feature=str(contract_file),
                        file=str(synth_file),
                        sha256=BootstrapAuditLog.sha256(synth_file),
                        model=llm.model,
                        payload=sr.as_log_payload(module=synth_file.stem),
                    )
                    print(f"    [STYLE_BLOCK] {filename}")
                    for v in sr.violations:
                        print(f"      {v}")
                    synth_file.unlink()
                    failed += 1
                    module_ok = False
                    continue

                log.record(
                    "CONTRACT_SYNTH_PASS",
                    feature=str(contract_file),
                    file=str(synth_file),
                    sha256=BootstrapAuditLog.sha256(synth_file),
                    model=llm.model,
                    input_tokens=token_in,
                    output_tokens=token_out,
                    payload=cr.as_log_payload(
                        module=synth_file.stem,
                        input_language="Python (Source AST)",
                        output_language="TypeScript (Contract Interface)",
                    ),
                )
                passed += 1

            if module_ok and any(out_dir.glob("*.ts")):
                (out_dir / ".spec.sha256").write_text(BootstrapAuditLog.sha256(contract_file))

        except LLMQuotaExhaustedError as exc:
            log.record("RUN_ABORT", reason=f"LLM quota exhausted: {exc}",
                       feature=str(contract_file), modules_completed=passed)
            print(f"\nABORT: LLM quota/credit exhausted while synthesising [{stem}]: {exc}")
            raise BootstrapAbortError(str(exc)) from exc

        except Exception as exc:
            print(f"✗ SKIPPED — {str(exc)[:120]}")
            log.record("SYNTHESIS_SKIP", feature=str(contract_file), reason=str(exc))

    return passed, failed


def _synthesis_loop_ts(
    feature_files: list[Path],
    oss_dir: Path,
    log: BootstrapAuditLog,
    *,
    force: bool = False,
    client: str = "openrouter",
) -> tuple[int, int]:
    from src.agents.incremental_planner import IncrementalPlanner
    from src.agents.iterative_tdd_runner import IterativeTDDRunner
    from src.agents.podman_orchestrator import PodmanOrchestrator
    from src.agents.typescript_language_pod import TypeScriptLanguagePod
    from src.agents.typescript_runner import TypeScriptRunner, build_ts_image
    from src.agents.typescript_worker_agent import TypeScriptWorkerAgent
    from src.playbook.manager import PlaybookManager
    from src.storage.experiment_logger import ExperimentLogger
    from bootstrap.synthesis_router import SynthesisRouter

    print("  Building TypeScript harness image...")
    build_ts_image()
    print("  Image ready.")

    llm_fallback = _make_llm_client(MODEL_PASS2, client)
    playbook_manager = PlaybookManager()
    experiment_logger = ExperimentLogger(playbook_version="bootstrap-ts-1.0")

    router = SynthesisRouter(
        audit_log=Path("bootstrap/audit.jsonl"),
        cheap_model=MODEL_PASS1,
        premium_model=MODEL_PASS2,
    )
    router.print_plan()

    _seed_shared_playbook(playbook_manager, log)

    container = TypeScriptRunner(container_name="ace_ts_bootstrap")
    container.start()
    print("  Container started.")

    passed = failed = 0

    try:
        for feature_file in feature_files:
            stem = feature_file.stem
            out_dir = oss_dir / stem

            # Resume: skip only if a *verified* prior run exists for the current
            # spec (ace_enterprise-ykl) — see _resume_decision docstring. An
            # absent marker used to mean "adopt current spec as baseline, trust
            # existing files", which silently trusted files that could just as
            # easily be leftovers from a run killed mid-iteration, before
            # verification ran.
            action, existing, current_spec_sha, recorded_spec_sha = _resume_decision(
                out_dir, feature_file, "*.ts", force
            )
            if action == "cached":
                print(f"  [{stem}] skipping — {len(existing)} verified .ts file(s) present, spec unchanged")
                log.record("SYNTHESIS_CACHED", feature=str(feature_file), out_dir=str(out_dir),
                           existing_files=[f.name for f in existing],
                           file_hashes={f.name: BootstrapAuditLog.sha256(f) for f in existing},
                           spec_sha=current_spec_sha)
                passed += len(existing)
                continue
            elif action == "cache_bust":
                print(f"  [{stem}] spec changed — re-synthesising")
                log.record("CACHE_BUST", feature=str(feature_file),
                           recorded_spec_sha=recorded_spec_sha, current_spec_sha=current_spec_sha)
            elif action == "unverified":
                print(f"  [{stem}] {len(existing)} unverified .ts file(s) present (no .spec.sha256) — re-synthesising")
                log.record("SYNTHESIS_UNVERIFIED_RESYNTH", feature=str(feature_file), out_dir=str(out_dir),
                           existing_files=[f.name for f in existing])
                    # fall through to synthesis

            out_dir.mkdir(parents=True, exist_ok=True)

            try:
                playbook_id = _SHARED_PLAYBOOK_ID

                primary_model, escalate_after = router.recommend(stem)
                llm_primary = _make_llm_client(primary_model, client)
                worker = TypeScriptWorkerAgent(
                    llm_primary, playbook_manager=playbook_manager,
                    fallback_client=llm_fallback,
                    escalate_after=escalate_after,
                )
                planner = IncrementalPlanner(
                    llm_client=llm_primary,
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
                    max_iterations=6,
                    max_green_attempts=3,
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

                module_ok = True
                for synth_file in sorted(out_dir.glob("*.ts")):
                    cr = verify_clean_room_cross_language(synth_file, PRIVATE_SRC_ROOT)
                    if not cr.passed:
                        log.record(
                            "CLEAN_ROOM_FAIL",
                            feature=str(feature_file),
                            file=str(synth_file),
                            sha256=BootstrapAuditLog.sha256(synth_file),
                            model=llm_primary.model,
                            input_tokens=token_in,
                            output_tokens=token_out,
                            payload=cr.as_log_payload(
                                module=synth_file.stem,
                                input_language="Python (Source AST)",
                                output_language="TypeScript (Target AST via Vitest)",
                            ),
                        )
                        print(f"    [CLEAN_ROOM_FAIL] {synth_file.name}")
                        for v in cr.violations:
                            print(f"      {v}")
                        synth_file.unlink()
                        failed += 1
                        module_ok = False
                        continue

                    sr = verify_ts_style(synth_file)
                    if not sr.passed:
                        log.record(
                            "STYLE_BLOCK",
                            feature=str(feature_file),
                            file=str(synth_file),
                            sha256=BootstrapAuditLog.sha256(synth_file),
                            model=llm_primary.model,
                            payload=sr.as_log_payload(module=synth_file.stem),
                        )
                        print(f"    [STYLE_BLOCK] {synth_file.name}")
                        for v in sr.violations:
                            print(f"      {v}")
                        synth_file.unlink()
                        failed += 1
                        module_ok = False
                        continue

                    log.record(
                        "CLEAN_ROOM_PASS",
                        feature=str(feature_file),
                        file=str(synth_file),
                        sha256=BootstrapAuditLog.sha256(synth_file),
                        model=llm_primary.model,
                        input_tokens=token_in,
                        output_tokens=token_out,
                        payload=cr.as_log_payload(
                            module=synth_file.stem,
                            input_language="Python (Source AST)",
                            output_language="TypeScript (Target AST via Vitest)",
                        ),
                    )
                    passed += 1

                if module_ok and any(out_dir.glob("*.ts")):
                    (out_dir / ".spec.sha256").write_text(
                        BootstrapAuditLog.sha256(feature_file)
                    )

            except LLMQuotaExhaustedError as exc:
                log.record("RUN_ABORT", reason=f"LLM quota exhausted: {exc}",
                           feature=str(feature_file), modules_completed=passed)
                print(f"\nABORT: LLM quota/credit exhausted while synthesising [{stem}]: {exc}")
                raise BootstrapAbortError(str(exc)) from exc

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
