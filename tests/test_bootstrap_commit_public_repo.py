"""Tests for _start_run_branch() + _commit_public_repo()'s branch-per-run +
regression guard.

Regression coverage for two near-misses discovered live in the same
evening:

1. A run can silently overwrite-then-delete previously-good, already-
   committed files (a stale spec's synthesis attempt failing verification
   against content that used to pass). The old implementation committed
   straight onto main every time -- that damage would have landed in
   main's history under an innocuous "Synthesized update" message,
   indistinguishable from a normal run.

2. The first fix for #1 created the run's branch at commit time (Stage 5,
   end of a run) -- but nothing resets the working tree to main at the
   *start* of a run, so the next run's Stage 2 wrote new files on top of
   whatever branch the previous run's Stage 5 had left checked out. When
   that next run reached its own Stage 5 and tried `git checkout main`,
   git correctly refused (uncommitted local changes would be overwritten)
   -- but that's a crash with real synthesized work stranded, not "every
   run gets a clean branch". Branch creation now happens BEFORE Stage 2
   writes anything (_start_run_branch), and any leftover uncommitted
   changes from an interrupted previous run get committed to preserve
   them before starting fresh.

3. Even with #2 fixed, a live run still ended up committing straight onto
   main -- _start_run_branch correctly created and checked out a
   bootstrap/<timestamp> branch at the start (confirmed via
   RUN_BRANCH_STARTED in the audit log), but ~3.5 hours later, by the time
   _commit_public_repo ran, main was checked out again. No checkout call
   anywhere in orchestrate.py's code path explains it; the most likely
   cause is something external touching the checked-out branch during
   that window (a real directory on a real filesystem, nothing stops
   another process or a human `cd`-ing in). Root cause aside, the fix that
   matters is structural: _commit_public_repo now refuses outright to
   commit while main is checked out, regardless of how it got that way.

Uses a real git repo per test (subprocess, not mocked) -- this is
fundamentally about git plumbing correctness (branch state, what's on
main vs. the run branch), which a mock can't meaningfully verify.
"""
import subprocess
from pathlib import Path

import pytest

from bootstrap.audit_log import BootstrapAuditLog
from bootstrap.orchestrate import (
    MainBranchCommitRefusedError,
    RegressionAbortError,
    _commit_public_repo,
    _start_run_branch,
)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _current_branch(oss_dir: Path) -> str:
    return _git(oss_dir, "branch", "--show-current").stdout.strip()


def _tracked_files(oss_dir: Path, ref: str) -> set[str]:
    result = _git(oss_dir, "ls-tree", "-r", "--name-only", ref)
    return {line for line in result.stdout.splitlines() if line}


@pytest.fixture
def log(tmp_path):
    return BootstrapAuditLog(tmp_path / "audit.jsonl")


def _run(oss_dir: Path, log, module_count: int, write_files) -> None:
    """Simulates one full run: start the branch, THEN write files (matching
    real ordering -- _start_run_branch runs before Stage 2 in main())."""
    oss_dir.mkdir(exist_ok=True)
    _start_run_branch(oss_dir, log)
    write_files()
    _commit_public_repo(oss_dir, module_count=module_count, log=log)


def test_fresh_repo_commits_to_a_run_branch_not_main(tmp_path, log):
    oss_dir = tmp_path / "oss"

    def write():
        (oss_dir / "widget").mkdir()
        (oss_dir / "widget" / "widget.ts").write_text("export const widget = 1;\n")

    _run(oss_dir, log, 1, write)

    branch = _current_branch(oss_dir)
    assert branch.startswith("bootstrap/")
    assert "widget/widget.ts" in _tracked_files(oss_dir, branch)
    # main only has the initial empty commit -- no synthesized content on it.
    assert "widget/widget.ts" not in _tracked_files(oss_dir, "main")


def test_existing_repo_new_run_branches_off_current_main(tmp_path, log):
    oss_dir = tmp_path / "oss"
    _run(oss_dir, log, 1, lambda: ((oss_dir / "a").mkdir(), (oss_dir / "a" / "a.ts").write_text("export const a = 1;\n")))
    first_branch = _current_branch(oss_dir)
    _git(oss_dir, "checkout", "main")
    _git(oss_dir, "merge", first_branch, "--no-edit")
    main_head_before = _git(oss_dir, "rev-parse", "main").stdout.strip()

    def write():
        (oss_dir / "b").mkdir()
        (oss_dir / "b" / "b.ts").write_text("export const b = 1;\n")

    _run(oss_dir, log, 2, write)

    second_branch = _current_branch(oss_dir)
    assert second_branch != first_branch
    assert second_branch.startswith("bootstrap/")
    # main's ref is completely unchanged by the second run.
    assert _git(oss_dir, "rev-parse", "main").stdout.strip() == main_head_before
    # New branch has both modules (branched from main's tip, which had 'a').
    tracked = _tracked_files(oss_dir, second_branch)
    assert "a/a.ts" in tracked
    assert "b/b.ts" in tracked


def test_leftover_uncommitted_run_is_preserved_not_lost(tmp_path, log):
    """The actual bug: a previous run's branch left checked out with
    uncommitted changes on it (crashed before its own Stage 5, or -- as
    happened live -- Stage 5 itself crashed) must not block or discard the
    next run's branch setup."""
    oss_dir = tmp_path / "oss"
    _run(oss_dir, log, 1, lambda: ((oss_dir / "a").mkdir(), (oss_dir / "a" / "a.ts").write_text("export const a = 1;\n")))
    stranded_branch = _current_branch(oss_dir)

    # Simulate an interrupted run: new files written, never committed,
    # branch left checked out -- exactly the live crash scenario.
    (oss_dir / "b").mkdir()
    (oss_dir / "b" / "b.ts").write_text("export const b = 1;\n")
    assert _git(oss_dir, "status", "--porcelain").stdout.strip()

    # Next run must not crash, and must not lose 'b' -- it gets committed
    # to the stranded branch before the new run's branch is cut from main.
    new_branch = _start_run_branch(oss_dir, log)

    assert new_branch != stranded_branch
    assert _git(oss_dir, "status", "--porcelain").stdout.strip() == ""  # clean baseline for the new run
    # 'b' survived, committed onto the branch it was stranded on.
    assert "b/b.ts" in _tracked_files(oss_dir, stranded_branch)
    # But it did NOT leak into the new run's branch or main.
    assert "b/b.ts" not in _tracked_files(oss_dir, new_branch)
    assert "b/b.ts" not in _tracked_files(oss_dir, "main")


def test_regression_missing_file_aborts_before_commit(tmp_path, log):
    oss_dir = tmp_path / "oss"
    _run(oss_dir, log, 1, lambda: ((oss_dir / "keeper").mkdir(), (oss_dir / "keeper" / "keeper.ts").write_text("export const keeper = 1;\n")))
    first_branch = _current_branch(oss_dir)
    _git(oss_dir, "checkout", "main")
    _git(oss_dir, "merge", first_branch, "--no-edit")
    main_head_before = _git(oss_dir, "rev-parse", "main").stdout.strip()

    _start_run_branch(oss_dir, log)
    branch = _current_branch(oss_dir)

    # Simulate a run whose output lost keeper.ts (failed re-verification
    # against a stale spec, wrong routing, etc.).
    (oss_dir / "keeper" / "keeper.ts").unlink()
    (oss_dir / "other").mkdir()
    (oss_dir / "other" / "other.ts").write_text("export const other = 1;\n")

    with pytest.raises(RegressionAbortError, match="keeper/keeper.ts"):
        _commit_public_repo(oss_dir, module_count=2, log=log)

    # main is completely untouched -- no commit happened anywhere.
    assert _git(oss_dir, "rev-parse", "main").stdout.strip() == main_head_before
    assert "keeper/keeper.ts" in _tracked_files(oss_dir, "main")
    # Left on the run branch, uncommitted, for inspection.
    assert _current_branch(oss_dir) == branch


def test_nothing_to_commit_cleans_up_its_branch(tmp_path, log):
    oss_dir = tmp_path / "oss"
    _run(oss_dir, log, 1, lambda: ((oss_dir / "widget").mkdir(), (oss_dir / "widget" / "widget.ts").write_text("export const widget = 1;\n")))
    first_branch = _current_branch(oss_dir)
    _git(oss_dir, "checkout", "main")
    _git(oss_dir, "merge", first_branch, "--no-edit")
    branches_before = set(_git(oss_dir, "branch", "--list").stdout.split())

    # Identical content, nothing changed -- must not leave a stray branch behind.
    _run(oss_dir, log, 1, lambda: None)

    assert _current_branch(oss_dir) == "main"
    branches_after = set(_git(oss_dir, "branch", "--list").stdout.split())
    assert branches_after == branches_before


def test_refuses_to_commit_if_main_is_checked_out(tmp_path, log):
    """The actual live incident: whatever the cause, _commit_public_repo
    must never let a commit land on main. Simulated here by switching back
    to main after _start_run_branch ran -- exactly the state a live run
    ended up in hours later, root cause unknown."""
    oss_dir = tmp_path / "oss"
    oss_dir.mkdir()
    _start_run_branch(oss_dir, log)

    (oss_dir / "widget").mkdir()
    (oss_dir / "widget" / "widget.ts").write_text("export const widget = 1;\n")

    # Something switches back to main mid-run, same as what happened live.
    _git(oss_dir, "checkout", "main")

    with pytest.raises(MainBranchCommitRefusedError, match="main is checked out"):
        _commit_public_repo(oss_dir, module_count=1, log=log)

    # Nothing committed anywhere -- main still only has the initial empty commit.
    assert _tracked_files(oss_dir, "main") == set()
