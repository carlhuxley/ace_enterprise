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


def _runner(project, audit, *, builders, evaluator, consensus=None, scratch=None, learner_factory=None):
    root, src, tests = project
    call_log = list(builders)

    def candidate_builder(**kwargs):
        return call_log.pop(0)

    return EnsembleBuildRunner(
        project_path=root, language="python", src_dir=src, test_dir=tests,
        playbook_id="pb", audit_client=audit, scratch_root=scratch,
        candidate_builder=candidate_builder, evaluator=evaluator,
        consensus_builder=consensus, ensemble_learner_factory=learner_factory,
    )


def test_rejects_fewer_than_two_models(project, audit):
    r = _runner(project, audit, builders=[], evaluator=FakeEvaluator({}))
    result = r.run("do a thing", ["only/one"], "thing")
    assert result.winner_model is None
    assert "2+" in result.error


def test_rejects_unsupported_language(project, audit):
    root, src, tests = project
    r = EnsembleBuildRunner(
        project_path=root, language="rust", src_dir=src, test_dir=tests, playbook_id="pb",
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


# --- EnsembleLearner wiring (#6) ---------------------------------------------

def _ensemble_result(*, approved=1, rejected=0, models_used=("a/m", "b/m")):
    from datetime import datetime

    from src.ensemble.models import (
        BulletSection,
        ConsensusBullet,
        EnsembleResult,
        VoteResults,
    )

    bullets = [
        ConsensusBullet(
            content=f"bullet {i}", section=BulletSection.STRATEGIES,
            proposed_by=models_used[0], proposal_reasoning="because",
            approved=True,
        )
        for i in range(approved)
    ] + [
        ConsensusBullet(
            content=f"rejected {i}", section=BulletSection.STRATEGIES,
            proposed_by=models_used[0], proposal_reasoning="because",
            approved=False,
        )
        for i in range(rejected)
    ]
    now = datetime.now()
    return EnsembleResult(
        task_description="do a thing",
        models_used=list(models_used),
        voting_strategy="majority",
        bullets=bullets,
        vote_results=VoteResults(
            total_bullets=len(bullets), approved=approved, rejected=rejected, pending=0,
        ),
        model_performance={},
        started_at=now,
        completed_at=now,
        diversity_score=0.5,
        consensus_strength=0.75,
    )


class FakeEnsembleLearner:
    def __init__(self, result, added=1, raise_on_learn=None):
        self._result = result
        self._added = added
        self._raise_on_learn = raise_on_learn
        self.learn_calls: list[tuple] = []
        self.playback_calls: list = []

    def learn_from_task(self, task, environment_feedback, parallel=True):
        self.learn_calls.append((task, environment_feedback))
        if self._raise_on_learn:
            raise self._raise_on_learn
        return self._result

    def add_approved_bullets_to_playbook(self, result):
        self.playback_calls.append(result)
        return self._added


def _learn_builders():
    return [
        FakeCandidateRunner("def thing(): return 1\n", "t\n", True, True, 1),
        FakeCandidateRunner("def thing(): return 2\n", "t\n", True, True, 1),
    ]


def test_learn_false_by_default_never_touches_the_learner(project, audit, tmp_path):
    learner = FakeEnsembleLearner(_ensemble_result())
    r = _runner(project, audit, builders=_learn_builders(), evaluator=FakeEvaluator({}),
                scratch=tmp_path / "s", learner_factory=lambda refs: learner)
    result = r.run("do a thing", ["a/m", "b/m"], "thing")
    assert result.learning is None
    assert learner.learn_calls == []


def test_learn_true_runs_the_learner_and_summarizes_the_result(project, audit, tmp_path):
    learner = FakeEnsembleLearner(_ensemble_result(approved=2, rejected=1), added=2)
    r = _runner(project, audit, builders=_learn_builders(), evaluator=FakeEvaluator({}),
                scratch=tmp_path / "s", learner_factory=lambda refs: learner)
    result = r.run("do a thing", ["a/m", "b/m"], "thing", learn=True)

    assert len(learner.learn_calls) == 1
    assert len(learner.playback_calls) == 1
    assert result.learning == {
        "approved_bullets": 2,
        "rejected_bullets": 1,
        "bullets_added_to_playbook": 2,
        "consensus_strength": 0.75,
        "diversity_score": 0.5,
    }


def test_learner_factory_receives_the_candidate_model_refs(project, audit, tmp_path):
    seen_refs = []

    def factory(refs):
        seen_refs.append(refs)
        return FakeEnsembleLearner(_ensemble_result())

    r = _runner(project, audit, builders=_learn_builders(), evaluator=FakeEvaluator({}),
                scratch=tmp_path / "s", learner_factory=factory)
    r.run("do a thing", ["prov-a/m", "prov-b/m"], "thing", learn=True)
    assert seen_refs == [["prov-a/m", "prov-b/m"]]


def test_default_learner_factory_parses_provider_model_tuples(project, audit, tmp_path):
    r = _runner(project, audit, builders=_learn_builders(), evaluator=FakeEvaluator({}),
                scratch=tmp_path / "s")
    learner = r._make_ensemble_learner(["openrouter/qwen/qwen3-coder:free", "prov-b/m"])
    assert learner.models == [
        ("openrouter", "qwen/qwen3-coder:free"),
        ("prov-b", "m"),
    ]
    assert learner.playbook_id == "pb"


def test_learning_failure_does_not_sink_an_otherwise_successful_build(project, audit, tmp_path):
    learner = FakeEnsembleLearner(_ensemble_result(), raise_on_learn=RuntimeError("voting API down"))
    r = _runner(project, audit, builders=_learn_builders(), evaluator=FakeEvaluator({}),
                scratch=tmp_path / "s", learner_factory=lambda refs: learner)
    result = r.run("do a thing", ["a/m", "b/m"], "thing", learn=True)

    assert result.committed is True
    assert result.learning is None


def test_learn_reaches_the_learner_even_when_no_candidate_wins(project, audit, tmp_path):
    builders = [
        FakeCandidateRunner("def thing(): return 1\n", "t\n", False, False, 1),
        FakeCandidateRunner("def thing(): return 2\n", "t\n", False, False, 1),
    ]
    learner = FakeEnsembleLearner(_ensemble_result())
    r = _runner(project, audit, builders=builders, evaluator=FakeEvaluator({}),
                scratch=tmp_path / "s", learner_factory=lambda refs: learner)
    result = r.run("do a thing", ["a/m", "b/m"], "thing", learn=True)

    assert result.committed is False
    assert len(learner.learn_calls) == 1
    task, feedback = learner.learn_calls[0]
    assert feedback.result == "FAILED"


# --- TypeScript / Go support (#7) --------------------------------------------

class RecordingCandidateRunner(FakeCandidateRunner):
    """Same behavior as FakeCandidateRunner, but records the exact
    test_file/implementation_file paths the caller passed in."""

    def __init__(self, *args, seen: list, **kwargs):
        super().__init__(*args, **kwargs)
        self._seen = seen

    def run(self, *, feature_requirement, test_file, implementation_file, languages):
        self._seen.append((Path(test_file).name, Path(implementation_file).name))
        return super().run(
            feature_requirement=feature_requirement, test_file=test_file,
            implementation_file=implementation_file, languages=languages,
        )


def _lang_runner(project, audit, language, *, builders, evaluator, scratch):
    root, src, tests = project
    call_log = list(builders)

    def candidate_builder(**kwargs):
        return call_log.pop(0)

    return EnsembleBuildRunner(
        project_path=root, language=language, src_dir=src, test_dir=tests,
        playbook_id="pb", audit_client=audit, scratch_root=scratch,
        candidate_builder=candidate_builder, evaluator=evaluator,
    )


def test_typescript_is_a_supported_language(project, audit, tmp_path):
    seen: list = []
    builders = [
        RecordingCandidateRunner(
            "export function thing() { return 1; }", "test('x', () => {})", True, True, 1, seen=seen,
        ),
        RecordingCandidateRunner(
            "export function thing() { return 2; }", "test('x', () => {})", True, True, 1, seen=seen,
        ),
    ]
    r = _lang_runner(project, audit, "typescript", builders=builders,
                      evaluator=FakeEvaluator({}), scratch=tmp_path / "s")
    result = r.run("do a thing", ["a/m", "b/m"], "thing")

    assert result.error != "ensemble build not supported for 'typescript' yet"
    assert seen == [("candidate.test.ts", "candidate.ts"), ("candidate.test.ts", "candidate.ts")]
    assert result.committed is True
    assert (project[1] / "thing.ts").exists()
    assert (project[2] / "thing.test.ts").exists()


def test_go_is_a_supported_language(project, audit, tmp_path):
    seen: list = []
    builders = [
        RecordingCandidateRunner(
            "package pulse\nfunc Thing() int { return 1 }", "func TestThing(t *testing.T) {}",
            True, True, 1, seen=seen,
        ),
        RecordingCandidateRunner(
            "package pulse\nfunc Thing() int { return 2 }", "func TestThing(t *testing.T) {}",
            True, True, 1, seen=seen,
        ),
    ]
    r = _lang_runner(project, audit, "go", builders=builders,
                      evaluator=FakeEvaluator({}), scratch=tmp_path / "s")
    result = r.run("do a thing", ["a/m", "b/m"], "thing")

    assert result.error != "ensemble build not supported for 'go' yet"
    assert seen == [("candidate_test.go", "candidate.go"), ("candidate_test.go", "candidate.go")]
    assert result.committed is True
    assert (project[1] / "thing.go").exists()
    assert (project[2] / "thing_test.go").exists()


def test_typescript_blind_evaluation_uses_the_typescript_output_type(project, audit, tmp_path):
    builders = [
        FakeCandidateRunner("export function thing() { return 1; }", "t", True, True, 1),
        FakeCandidateRunner("export function thing() { return 2; }", "t", True, True, 1),
    ]
    ev = FakeEvaluator({})
    r = _lang_runner(project, audit, "typescript", builders=builders, evaluator=ev, scratch=tmp_path / "s")
    r.run("do a thing", ["a/m", "b/m"], "thing")
    assert {s.output_type for s in ev.seen_submissions} == {"code_typescript"}


def test_go_blind_evaluation_uses_the_go_output_type(project, audit, tmp_path):
    builders = [
        FakeCandidateRunner("package pulse\nfunc Thing() int { return 1 }", "t", True, True, 1),
        FakeCandidateRunner("package pulse\nfunc Thing() int { return 2 }", "t", True, True, 1),
    ]
    ev = FakeEvaluator({})
    r = _lang_runner(project, audit, "go", builders=builders, evaluator=ev, scratch=tmp_path / "s")
    r.run("do a thing", ["a/m", "b/m"], "thing")
    assert {s.output_type for s in ev.seen_submissions} == {"code_go"}
