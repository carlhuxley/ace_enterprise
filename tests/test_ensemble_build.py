"""Tests for src/agents/ensemble_build.py -- the multi-candidate blind build.

The sandboxed TDD runner, BlindEvaluator and embedding-backed ConsensusBuilder
are all injected as fakes here; no Podman / LLM / model-download happens.
"""
from pathlib import Path

import pytest

from src.agents.ensemble_build import EnsembleBuildRunner
from src.agents.language_pod import PhaseResult
from src.agents.polyglot_tdd_runner import LanguageRunResult, PolyglotRunResult
from src.analytics.token_efficiency import EfficiencyReport
from src.audit.local_client import LocalAuditClient
from src.benchmark.blind_evaluation import EvaluationResult


class FakeCandidateRunner:
    """Stands in for PolyglotTDDRunner: writes canned files, reports canned outcome."""

    def __init__(self, impl: str, test: str, green: bool, refactor: bool, cycles: int):
        self._impl, self._test = impl, test
        self._green, self._refactor, self._cycles = green, refactor, cycles

    def run(self, *, feature_requirement, test_file, implementation_file, languages):
        Path(implementation_file).parent.mkdir(parents=True, exist_ok=True)
        Path(test_file).parent.mkdir(parents=True, exist_ok=True)
        Path(implementation_file).write_text(self._impl)
        Path(test_file).write_text(self._test)
        lang = languages[0]
        return PolyglotRunResult(
            language_results={
                lang: LanguageRunResult(
                    language=lang,
                    red=PhaseResult(passed=False, output="", error="expected RED"),
                    green=PhaseResult(passed=self._green, output="ok",
                                      error=None if self._green else "green failed"),
                    refactor=PhaseResult(passed=self._refactor, output="ok",
                                         error=None if self._refactor else "refactor failed"),
                    cycles_to_green=self._cycles,
                )
            },
            efficiency_report=EfficiencyReport(),
        )


class FakeEvaluator:
    """Scores by submission_id via a lookup the test controls."""

    def __init__(self, scores: dict[str, int]):
        self._scores = scores
        self.seen_submissions: list = []

    def evaluate(self, submission):
        self.seen_submissions.append(submission)
        score = self._scores.get(submission.submission_id, 50)
        return EvaluationResult(
            submission_id=submission.submission_id,
            quality_score=score,
            tests_passed=score >= 50,
            details={},
            rubric_name="code_generation",
        )


class FakeConsensusBuilder:
    def cluster_bullets(self, bullets):
        # Everything in one cluster -> models converged.
        return {"c0": list(bullets)}

    def calculate_diversity_score(self, bullets):
        return 0.0


@pytest.fixture
def audit(tmp_path):
    return LocalAuditClient(database_url=f"sqlite:///{tmp_path / 'audit.db'}")


@pytest.fixture
def project(tmp_path):
    src = tmp_path / "src"
    tests = tmp_path / "tests"
    src.mkdir()
    tests.mkdir()
    return tmp_path, src, tests


def _runner(project, audit, *, builders, evaluator, consensus=None, scratch=None):
    root, src, tests = project
    call_log = list(builders)

    def candidate_builder(**kwargs):
        return call_log.pop(0)

    return EnsembleBuildRunner(
        project_path=root, language="python", src_dir=src, test_dir=tests,
        playbook_id="pb", audit_client=audit, scratch_root=scratch,
        candidate_builder=candidate_builder, evaluator=evaluator,
        consensus_builder=consensus,
    )


def test_rejects_fewer_than_two_models(project, audit):
    r = _runner(project, audit, builders=[], evaluator=FakeEvaluator({}))
    result = r.run("do a thing", ["only/one"], "thing")
    assert result.winner_model is None
    assert "2+" in result.error


def test_rejects_unsupported_language(project, audit):
    root, src, tests = project
    r = EnsembleBuildRunner(
        project_path=root, language="go", src_dir=src, test_dir=tests, playbook_id="pb",
    )
    result = r.run("do a thing", ["a/x", "b/y"], "thing")
    assert "not supported" in result.error


def test_picks_highest_scoring_passing_candidate_and_commits(project, audit, tmp_path):
    root, src, tests = project
    builders = [
        FakeCandidateRunner("def thing():\n    return 1\n", "def test_x(): pass\n", True, True, 1),
        FakeCandidateRunner("def thing():\n    return 2\n", "def test_x(): pass\n", True, True, 3),
    ]
    r = _runner(
        project, audit,
        builders=builders,
        evaluator=FakeEvaluator({}),  # scores default 50/50 -> tiebreak on cycles
        scratch=tmp_path / "scratch",
    )
    result = r.run("do a thing", ["prov-a/m", "prov-b/m"], "thing")

    assert result.winner_model == "prov-a/m"          # fewer cycles wins the tie
    assert result.committed is True
    assert (src / "thing.py").read_text() == "def thing():\n    return 1\n"
    assert (tests / "test_thing.py").exists()
    assert {c["model"] for c in result.candidates} == {"prov-a/m", "prov-b/m"}


def test_quality_score_beats_cycle_count(project, audit, tmp_path):
    builders = [
        FakeCandidateRunner("def thing():\n    return 1\n", "t\n", True, True, 1),
        FakeCandidateRunner("def thing():\n    return 2\n", "t\n", True, True, 5),
    ]
    ev = FakeEvaluator({})
    r = _runner(project, audit, builders=builders, evaluator=ev, scratch=tmp_path / "s")
    # Make the slower candidate score higher.
    def scoring_evaluate(submission):
        ev.seen_submissions.append(submission)
        score = 90 if "return 2" in submission.output_content else 40
        return EvaluationResult(submission.submission_id, score, True, {}, rubric_name="x")

    ev.evaluate = scoring_evaluate
    result = r.run("do a thing", ["a/m", "b/m"], "thing")
    assert result.winner_model == "b/m"
    assert (project[1] / "thing.py").read_text() == "def thing():\n    return 2\n"


def test_no_passing_candidate_does_not_commit(project, audit, tmp_path):
    builders = [
        FakeCandidateRunner("def thing():\n    return 1\n", "t\n", False, False, 5),
        FakeCandidateRunner("def thing():\n    return 2\n", "t\n", True, False, 5),
    ]
    r = _runner(project, audit, builders=builders, evaluator=FakeEvaluator({}),
                scratch=tmp_path / "s")
    result = r.run("do a thing", ["a/m", "b/m"], "thing")
    assert result.committed is False
    assert not (project[1] / "thing.py").exists()
    # A winner is still identified (best of a bad lot) for the audit trail.
    assert result.winner_model in {"a/m", "b/m"}


def test_blind_evaluator_never_sees_the_model(project, audit, tmp_path):
    builders = [
        FakeCandidateRunner("def thing(): return 1\n", "t\n", True, True, 1),
        FakeCandidateRunner("def thing(): return 2\n", "t\n", True, True, 1),
    ]
    ev = FakeEvaluator({})
    r = _runner(project, audit, builders=builders, evaluator=ev, scratch=tmp_path / "s")
    r.run("do a thing", ["secret-vendor/model-x", "other/model-y"], "thing")

    for sub in ev.seen_submissions:
        # Submission carries an opaque id and content only -- no model field,
        # and the vendor name must not have leaked into any field.
        assert not hasattr(sub, "model")
        assert "secret-vendor" not in (sub.output_content + sub.submission_id + sub.task_id)


def test_emits_blind_evaluation_and_selection_audit_events(project, audit, tmp_path):
    from src.audit.schemas import AuditEventType
    from src.audit.store import AuditQuery

    builders = [
        FakeCandidateRunner("def thing(): return 1\n", "t\n", True, True, 1),
        FakeCandidateRunner("def thing(): return 2\n", "t\n", True, True, 2),
    ]
    r = _runner(project, audit, builders=builders, evaluator=FakeEvaluator({}),
                consensus=FakeConsensusBuilder(), scratch=tmp_path / "s")
    r.run("do a thing", ["a/m", "b/m"], "thing")

    store = audit._store
    blind = store.query(AuditQuery(event_types=[AuditEventType.BLIND_EVALUATION], limit=50)).events
    sel = store.query(AuditQuery(event_types=[AuditEventType.ENSEMBLE_SELECTION], limit=50)).events

    assert len(blind) == 2
    for ev in blind:
        assert "submission_id" in ev.payload
        assert "model" not in ev.payload            # attribution withheld
    assert len(sel) == 1
    assert sel[0].payload["winner_model"] in {"a/m", "b/m"}
    assert sel[0].payload["consensus"]["num_candidates"] == 2


def test_consensus_report_flags_winner_in_majority(project, audit, tmp_path):
    builders = [
        FakeCandidateRunner("def thing(): return 1\n", "t\n", True, True, 1),
        FakeCandidateRunner("def thing(): return 1\n", "t\n", True, True, 1),
    ]
    r = _runner(project, audit, builders=builders, evaluator=FakeEvaluator({}),
                consensus=FakeConsensusBuilder(), scratch=tmp_path / "s")
    result = r.run("do a thing", ["a/m", "b/m"], "thing")
    assert result.consensus["winner_in_majority"] is True
    assert result.consensus["num_distinct_approaches"] == 1
