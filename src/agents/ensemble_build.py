"""Multi-candidate ("double-blind") feature build.

The live entry point for the Blind Evaluation subsystem (`src/benchmark/`,
`src/ensemble/`). It:

  1. Runs the same sandboxed RED->GREEN->REFACTOR TDD cycle once per candidate
     model, each in its own throwaway working copy so candidates never see or
     clobber each other.
  2. Hands each resulting implementation to `BlindEvaluator` under an opaque
     `submission_id` -- the evaluator never learns which model produced which
     candidate. The `submission_id -> model` map stays here.
  3. Ranks candidates (sandbox pass > blind quality score > fewer cycles) and
     picks a winner.
  4. Uses `ConsensusBuilder` to measure how far the models' solutions
     converged -- a real signal for how much to trust the winner.
  5. Reveals attribution only after selection, commits the winning
     implementation into the target project, and emits `BLIND_EVALUATION`
     (no attribution) + `ENSEMBLE_SELECTION` (winner revealed) audit events.

Generation and blind scoring both run inside PodmanOrchestrator-backed
sandboxes; no candidate code is ever executed or written to the target
project until it has won.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("python", "typescript", "go")

# File names used for the THROWAWAY generation/blind-eval sandbox for one
# candidate -- deliberately NOT the eventual feature name (that's
# _final_file_names, used only by _commit once a winner is picked). Keeping
# this fixed across every candidate/language means a rubric's own sandboxed
# "tests" dimension (src/benchmark/rubrics/*) can reconstruct the exact same
# {impl_name: test_name} pairing independently and get files whose import
# statements (TypeScriptWorkerAgent writes `from './candidate'`-style
# imports keyed off the impl file's own stem) still resolve correctly, with
# no filename metadata needing to travel through Submission/RubricResult.
_CANDIDATE_FILE_NAMES: dict[str, tuple[str, str]] = {
    "python": ("candidate.py", "test_candidate.py"),
    "typescript": ("candidate.ts", "candidate.test.ts"),
    "go": ("candidate.go", "candidate_test.go"),
}


def _final_file_names(language: str, name: str) -> tuple[str, str]:
    """Impl/test file names for the WINNING candidate once committed into
    the real project -- uses the caller's feature `name`, unlike the fixed
    throwaway names above."""
    if language == "typescript":
        return f"{name}.ts", f"{name}.test.ts"
    if language == "go":
        return f"{name}.go", f"{name}_test.go"
    return f"{name}.py", f"test_{name}.py"


@dataclass
class EnsembleCandidate:
    """One model's attempt at the feature. `model` is kept out of anything
    handed to the blind evaluator."""

    model: str
    submission_id: str
    implementation_code: str
    test_code: str
    sandbox_passed: bool          # GREEN and REFACTOR both passed in the container
    cycles_to_green: int
    error: str | None = None
    quality_score: int | None = None      # filled in after blind evaluation
    tests_passed: bool | None = None
    rubric_name: str | None = None

    def public_view(self) -> dict:
        """Candidate data safe to log/return with attribution revealed."""
        return {
            "model": self.model,
            "submission_id": self.submission_id,
            "sandbox_passed": self.sandbox_passed,
            "cycles_to_green": self.cycles_to_green,
            "quality_score": self.quality_score,
            "tests_passed": self.tests_passed,
            "rubric_name": self.rubric_name,
            "error": self.error,
        }


@dataclass
class ConsensusReport:
    """How much the candidate solutions converged (ConsensusBuilder over the
    implementation texts, not playbook bullets)."""

    num_candidates: int
    num_distinct_approaches: int      # clusters of similar implementations
    largest_cluster_size: int
    diversity_score: float            # 0 = all identical, 1 = all distinct
    winner_in_majority: bool          # winner clustered with >=half the field


@dataclass
class EnsembleBuildResult:
    requirement: str
    language: str
    winner_model: str | None
    winner_submission_id: str | None
    committed: bool
    candidates: list[dict] = field(default_factory=list)
    consensus: dict | None = None
    # Summary of the opt-in EnsembleLearner pass (#6) -- None when learn=False
    # was passed to run(), or the pass ran but hit an error (best-effort,
    # like consensus analysis: a learning failure must never sink an
    # otherwise-successful build).
    learning: dict | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class EnsembleBuildRunner:
    """Drives a multi-candidate blind build for one feature in one language."""

    def __init__(
        self,
        project_path: Path,
        language: str,
        src_dir: Path,
        test_dir: Path,
        playbook_id: str,
        *,
        audit_client=None,
        team_id: str | None = None,
        max_cycles: int = 5,
        scratch_root: Path | None = None,
        cgr3_retrieval: bool = False,
        candidate_builder=None,
        evaluator=None,
        consensus_builder=None,
        ensemble_learner_factory=None,
    ) -> None:
        self._project_path = Path(project_path)
        self._language = language
        self._src_dir = Path(src_dir)
        self._test_dir = Path(test_dir)
        self._playbook_id = playbook_id
        self._audit = audit_client
        self._team_id = team_id
        self._max_cycles = max_cycles
        # #67: opt-in CGR3 retrieval for candidate generation, mirrors
        # ProjectConfig.cgr3_retrieval (src/cli/config.py). Every candidate
        # model still gets equal access to the same shared playbook either
        # way ("blind" here means candidates never see each other, not that
        # they're blind to institutional knowledge) -- this was in fact a
        # real, separate gap even without CGR3: _build_sandboxed_candidate_
        # runner never wired a playbook_manager into any candidate at all
        # before this, so candidates got zero playbook bullets, unlike an
        # equivalent single-model `ace tdd` run.
        self._cgr3_retrieval = cgr3_retrieval
        self._scratch_root = scratch_root
        # Seams for tests: default to the real sandboxed implementations.
        self._candidate_builder = candidate_builder or _build_sandboxed_candidate_runner
        self._evaluator = evaluator
        self._consensus_builder = consensus_builder
        # model_refs -> EnsembleLearner -- overridable so tests can inject a
        # fake without real LLM clients/voting calls (#6 needs 2N+ extra LLM
        # calls: each model runs its own Generator/Reflector/Curator, then
        # cross-votes on every model's proposals).
        self._make_ensemble_learner = ensemble_learner_factory or self._default_ensemble_learner

    def _default_ensemble_learner(self, model_refs: list[str]):
        from src.ensemble.learner import EnsembleLearner

        models = [tuple(ref.partition("/")[::2]) for ref in model_refs]
        return EnsembleLearner(models=models, playbook_id=self._playbook_id)

    # ------------------------------------------------------------------

    def run(
        self,
        requirement: str,
        model_refs: list[str],
        name: str,
        *,
        gherkin_context: str | None = None,
        learn: bool = False,
    ) -> EnsembleBuildResult:
        if self._language not in SUPPORTED_LANGUAGES:
            return EnsembleBuildResult(
                requirement=requirement, language=self._language,
                winner_model=None, winner_submission_id=None, committed=False,
                error=(
                    f"ensemble build not supported for {self._language!r} yet "
                    f"(supported: {', '.join(SUPPORTED_LANGUAGES)})"
                ),
            )
        if len({*model_refs}) < 2:
            return EnsembleBuildResult(
                requirement=requirement, language=self._language,
                winner_model=None, winner_submission_id=None, committed=False,
                error="an ensemble build needs 2+ distinct candidate models",
            )

        scratch = self._scratch_root or (self._project_path / ".ace" / "ensemble")
        scratch.mkdir(parents=True, exist_ok=True)
        run_dir = scratch / uuid.uuid4().hex[:12]
        run_dir.mkdir()

        try:
            candidates = self._generate_candidates(
                requirement, model_refs, name, run_dir, gherkin_context
            )
            self._blind_evaluate(candidates, task_id=name)
            consensus = self._analyse_consensus(candidates)
            winner = self._pick_winner(candidates)

            committed = False
            if winner is not None and winner.sandbox_passed:
                self._commit(winner, name)
                committed = True

            self._audit_selection(requirement, name, candidates, winner, consensus)

            learning = None
            if learn:
                learning = self._run_ensemble_learning(requirement, model_refs, name, candidates, committed)

            return EnsembleBuildResult(
                requirement=requirement,
                language=self._language,
                winner_model=winner.model if winner else None,
                winner_submission_id=winner.submission_id if winner else None,
                committed=committed,
                candidates=[c.public_view() for c in candidates],
                consensus=asdict(consensus) if consensus else None,
                learning=learning,
                error=None if winner else "no candidate produced a usable implementation",
            )
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    # ------------------------------------------------------------------

    def _generate_candidates(
        self,
        requirement: str,
        model_refs: list[str],
        name: str,
        run_dir: Path,
        gherkin_context: str | None,
    ) -> list[EnsembleCandidate]:
        from src.agents.polyglot_tdd_runner import PolyglotRunResult

        candidates: list[EnsembleCandidate] = []
        for i, model_ref in enumerate(model_refs):
            cand_root = run_dir / f"cand_{i}"
            cand_src = cand_root / "src"
            cand_test = cand_root / "tests"
            cand_src.mkdir(parents=True)
            cand_test.mkdir(parents=True)
            # Seed the candidate workspace with the project's existing source so
            # generated code has the same context every non-ensemble build gets.
            _copy_tree(self._src_dir, cand_src)

            impl_name, test_name = _CANDIDATE_FILE_NAMES[self._language]
            test_file = cand_test / test_name
            impl_file = cand_src / impl_name

            try:
                runner = self._candidate_builder(
                    model_ref=model_ref,
                    language=self._language,
                    project_path=cand_root,
                    src_dir=cand_src,
                    playbook_id=self._playbook_id,
                    audit_client=self._audit,
                    team_id=self._team_id,
                    max_cycles=self._max_cycles,
                    cgr3_retrieval=self._cgr3_retrieval,
                )
                result: PolyglotRunResult = runner.run(
                    feature_requirement=requirement,
                    test_file=test_file,
                    implementation_file=impl_file,
                    languages=[self._language],
                )
                lang_result = result.language_results[self._language]
                passed = bool(lang_result.green.passed and lang_result.refactor.passed)
                error = None if passed else (
                    lang_result.green.error or lang_result.refactor.error
                )
                cycles = lang_result.cycles_to_green
            except Exception as exc:  # noqa: BLE001 -- one model failing must not sink the run
                logger.warning("ensemble: candidate %s failed to generate: %s", model_ref, exc)
                passed, error, cycles = False, str(exc), 0

            candidates.append(
                EnsembleCandidate(
                    model=model_ref,
                    submission_id=uuid.uuid4().hex,
                    implementation_code=_read(impl_file),
                    test_code=_read(test_file),
                    sandbox_passed=passed,
                    cycles_to_green=cycles,
                    error=error,
                )
            )
        return candidates

    def _blind_evaluate(self, candidates: list[EnsembleCandidate], task_id: str) -> None:
        from src.benchmark.blind_evaluation import BlindEvaluator, Submission

        evaluator = self._evaluator or BlindEvaluator()
        for cand in candidates:
            if not cand.implementation_code.strip():
                continue
            # The evaluator sees only the opaque submission_id.
            submission = Submission(
                task_id=task_id,
                submission_id=cand.submission_id,
                output_type=f"code_{self._language}",
                output_content=cand.implementation_code,
                test_content=cand.test_code or None,
            )
            try:
                res = evaluator.evaluate(submission)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ensemble: blind evaluation failed for a submission: %s", exc)
                continue
            cand.quality_score = res.quality_score
            cand.tests_passed = res.tests_passed
            cand.rubric_name = res.rubric_name
            self._audit_blind_evaluation(task_id, res)

    def _analyse_consensus(
        self, candidates: list[EnsembleCandidate]
    ) -> ConsensusReport | None:
        impls = [(c, c.implementation_code) for c in candidates if c.implementation_code.strip()]
        if len(impls) < 2:
            return None
        try:
            from src.ensemble.consensus import ConsensusBuilder
            from src.ensemble.models import BulletSection, ConsensusBullet

            builder = self._consensus_builder or ConsensusBuilder()
            bullets = [
                ConsensusBullet(
                    content=code,
                    section=BulletSection.CODE_SNIPPETS,
                    proposed_by=cand.submission_id,
                    proposal_reasoning="candidate implementation",
                )
                for cand, code in impls
            ]
            clusters = builder.cluster_bullets(bullets)
            sizes = [len(c) for c in clusters.values()]
            largest = max(sizes) if sizes else 0

            winner = self._pick_winner(candidates)
            winner_cluster_size = 0
            if winner is not None:
                for members in clusters.values():
                    if any(b.proposed_by == winner.submission_id for b in members):
                        winner_cluster_size = len(members)
                        break

            return ConsensusReport(
                num_candidates=len(impls),
                num_distinct_approaches=len(clusters),
                largest_cluster_size=largest,
                diversity_score=builder.calculate_diversity_score(bullets),
                winner_in_majority=winner_cluster_size * 2 >= len(impls),
            )
        except Exception as exc:  # noqa: BLE001 -- consensus is a nice-to-have signal
            logger.warning("ensemble: consensus analysis skipped: %s", exc)
            return None

    @staticmethod
    def _pick_winner(candidates: list[EnsembleCandidate]) -> EnsembleCandidate | None:
        scored = [c for c in candidates if c.implementation_code.strip()]
        if not scored:
            return None
        return max(
            scored,
            key=lambda c: (
                c.sandbox_passed,
                c.quality_score if c.quality_score is not None else -1,
                -c.cycles_to_green,
            ),
        )

    def _commit(self, winner: EnsembleCandidate, name: str) -> None:
        self._src_dir.mkdir(parents=True, exist_ok=True)
        self._test_dir.mkdir(parents=True, exist_ok=True)
        impl_name, test_name = _final_file_names(self._language, name)
        (self._src_dir / impl_name).write_text(winner.implementation_code)
        if winner.test_code.strip():
            (self._test_dir / test_name).write_text(winner.test_code)

    def _run_ensemble_learning(
        self,
        requirement: str,
        model_refs: list[str],
        name: str,
        candidates: list[EnsembleCandidate],
        committed: bool,
    ) -> dict | None:
        """#6: opt-in EnsembleLearner pass over this build's outcome. Every
        candidate model independently runs its own Generator/Reflector/
        Curator on the SAME shared feedback (learn_from_task's existing
        design, from #3/PR #4 -- not this build's own sandboxed candidate
        code), then cross-votes on the resulting bullets; approved ones are
        written to the shared playbook. Real LLM calls (2N+ per model:
        generation, reflection, curation, voting) -- best-effort like
        consensus analysis, since a learning failure must never sink an
        otherwise-successful build.
        """
        try:
            from src.storage.schemas import EnvironmentFeedback, TaskInput

            summary_lines = [
                f"{c.model}: {'passed' if c.sandbox_passed else 'failed'} sandbox "
                f"in {c.cycles_to_green} cycle(s)"
                + (f", quality_score={c.quality_score}" if c.quality_score is not None else "")
                + (f" -- {c.error}" if c.error else "")
                for c in candidates
            ]
            task = TaskInput(id=name, query=requirement, context={"language": self._language})
            feedback = EnvironmentFeedback(
                result="SUCCESS" if committed else "FAILED",
                feedback="Ensemble build outcome:\n" + "\n".join(summary_lines),
                test_report={"candidates": [c.public_view() for c in candidates]},
            )

            learner = self._make_ensemble_learner(model_refs)
            result = learner.learn_from_task(task, feedback)
            added = learner.add_approved_bullets_to_playbook(result)

            return {
                "approved_bullets": len(result.approved_bullets),
                "rejected_bullets": len(result.rejected_bullets),
                "bullets_added_to_playbook": added,
                "consensus_strength": result.consensus_strength,
                "diversity_score": result.diversity_score,
            }
        except Exception as exc:  # noqa: BLE001 -- learning is a nice-to-have signal
            logger.warning("ensemble: EnsembleLearner pass skipped: %s", exc)
            return None

    # --- audit --------------------------------------------------------

    def _audit_blind_evaluation(self, task_id: str, res) -> None:
        if self._audit is None:
            return
        from src.audit.schemas import AuditEventType

        try:
            self._audit.emit_simple(
                event_type=AuditEventType.BLIND_EVALUATION,
                actor_id="blind-evaluator",
                payload={
                    "task_id": task_id,
                    "submission_id": res.submission_id,   # opaque -- no model
                    "quality_score": res.quality_score,
                    "tests_passed": res.tests_passed,
                    "rubric_name": res.rubric_name,
                },
                playbook_id=self._playbook_id,
            )
        except Exception:  # noqa: BLE001
            logger.debug("blind-evaluation audit emit failed", exc_info=True)

    def _audit_selection(
        self,
        requirement: str,
        name: str,
        candidates: list[EnsembleCandidate],
        winner: EnsembleCandidate | None,
        consensus: ConsensusReport | None,
    ) -> None:
        if self._audit is None:
            return
        from src.audit.schemas import AuditEventType

        try:
            self._audit.emit_simple(
                event_type=AuditEventType.ENSEMBLE_SELECTION,
                actor_id=winner.model if winner else "ensemble",
                payload={
                    "feature": name,
                    "requirement": requirement,
                    "language": self._language,
                    "winner_model": winner.model if winner else None,
                    "winner_submission_id": winner.submission_id if winner else None,
                    # attribution revealed here, post-selection
                    "candidates": [c.public_view() for c in candidates],
                    "consensus": asdict(consensus) if consensus else None,
                },
                playbook_id=self._playbook_id,
            )
        except Exception:  # noqa: BLE001
            logger.debug("ensemble-selection audit emit failed", exc_info=True)


# ----------------------------------------------------------------------
# Default (real) candidate runner
# ----------------------------------------------------------------------

def _build_sandboxed_candidate_runner(
    *,
    model_ref: str,
    language: str,
    project_path: Path,
    src_dir: Path,
    playbook_id: str,
    audit_client,
    team_id: str | None,
    max_cycles: int,
    cgr3_retrieval: bool = False,
):
    """Build a real PolyglotTDDRunner for one candidate model.

    `model_ref` is "<provider>/<model>"; the model half may contain slashes.

    Every candidate shares the same playbook_manager (and, if cgr3_retrieval
    is set, the same retrieval_service) -- "blind" only means candidates
    never see each other's generated code, not that they're blind to
    institutional knowledge (ace_enterprise#67).
    """
    from src.agents.polyglot_pod_builder import build_pod_kwargs
    from src.agents.polyglot_tdd_runner import PodFactory, PolyglotTDDRunner
    from src.agents.redundancy_checker import RedundancyPreChecker
    from src.playbook.manager import PlaybookManager
    from src.utils.llm_client import LLMClient

    provider, _, model = model_ref.partition("/")
    if not model:
        raise ValueError(f"candidate model {model_ref!r} must be '<provider>/<model>'")
    llm_client = LLMClient(provider=provider, model=model)

    playbook_manager = PlaybookManager()
    playbook_manager.get_or_create_playbook(playbook_id)
    retrieval_service = None
    if cgr3_retrieval:
        from src.retrieval.service import InstitutionalKnowledgeService
        retrieval_service = InstitutionalKnowledgeService(
            playbook_manager=playbook_manager, default_playbook_id=playbook_id,
        )

    pod_kwargs = {
        language: build_pod_kwargs(
            language, project_path, llm_client, src_dir=src_dir,
            playbook_manager=playbook_manager, retrieval_service=retrieval_service,
            team_id=team_id, project_id=playbook_id,
        )
    }
    return PolyglotTDDRunner(
        PodFactory,
        max_cycles=max_cycles,
        pod_kwargs=pod_kwargs,
        audit_client=audit_client,
        redundancy_checker=RedundancyPreChecker(),
        playbook_id=playbook_id,
        team_id=team_id,
        model_id=model_ref,
    )


def _copy_tree(src: Path, dst: Path) -> None:
    if not src.is_dir():
        return
    for item in src.rglob("*"):
        if item.is_file():
            target = dst / item.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _read(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""
