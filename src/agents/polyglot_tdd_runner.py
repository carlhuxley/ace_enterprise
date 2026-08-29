"""
PolyglotTDDRunner — orchestrates RED→GREEN→REFACTOR across multiple LanguagePods
and reports per-language token efficiency via TokenEfficiencyReporter.

This is the entry point that wires together:
  LanguagePod (protocol) → PythonLanguagePod / GoLanguagePod
  TokenEfficiencyReporter → EfficiencyReport

Each language's cycle runs through the exact same TDDCycleRunner engine
IterativeTDDRunner uses (not a parallel reimplementation) -- so audit_client
events, GREEN-retry error feedback, and the reflector/curator learning hook
all behave identically here. The AST redundancy pre-check (RedundancyPreChecker)
runs before TDDCycleRunner is even invoked, same as IterativeTDDRunner's.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.agents.language_pod import PhaseResult, PodSpec
from src.agents.redundancy_checker import ProposedTest, existing_tests_from_file
from src.agents.tdd_cycle_runner import TDDCycleRunner
from src.analytics.token_efficiency import (
    EfficiencyReport,
    PodRun,
    TokenEfficiencyReporter,
)

logger = logging.getLogger(__name__)


@dataclass
class LanguageRunResult:
    """Outcome of a full RED→GREEN→REFACTOR run for one language."""

    language: str
    red: PhaseResult
    green: PhaseResult
    refactor: PhaseResult
    cycles_to_green: int


@dataclass
class PolyglotRunResult:
    """Combined results for all languages, including token efficiency comparison."""

    language_results: dict[str, LanguageRunResult] = field(default_factory=dict)
    efficiency_report: EfficiencyReport = field(default_factory=EfficiencyReport)


class PodFactory:
    """Creates LanguagePod instances for a given language identifier."""

    @staticmethod
    def create(language: str, **kwargs):
        if language == "python":
            from src.agents.python_language_pod import PythonLanguagePod
            return PythonLanguagePod(
                worker_agent=kwargs["worker"],
                project_root=kwargs["project_root"],
                orchestrator=kwargs["orchestrator"],
            )
        if language == "go":
            from src.agents.go_language_pod import GoLanguagePod
            return GoLanguagePod(
                llm_client=kwargs["llm_client"],
                project_root=kwargs["project_root"],
                orchestrator=kwargs["orchestrator"],
                playbook_manager=kwargs.get("playbook_manager"),
            )
        if language == "typescript":
            from src.agents.typescript_language_pod import TypeScriptLanguagePod
            return TypeScriptLanguagePod(
                worker_agent=kwargs["worker"],
                project_root=kwargs["project_root"],
                orchestrator=kwargs["orchestrator"],
            )
        raise ValueError(f"Unsupported language: {language}")


class PolyglotTDDRunner:
    """
    Drives a RED→GREEN→REFACTOR loop for each requested language and
    aggregates token efficiency across languages.

    GREEN is retried up to max_cycles times per language. A language run that
    never goes green still records its token usage and proceeds to REFACTOR,
    so other languages are not affected by one language's failures.
    """

    def __init__(
        self,
        pod_factory,
        max_cycles: int = 5,
        reporter=None,
        pod_kwargs: dict[str, dict] | None = None,
        audit_client=None,
        redundancy_checker=None,
        playbook_id: str = "polyglot",
        max_red_attempts: int = 2,
        team_id: str | None = None,
        model_id: str | None = None,
    ) -> None:
        self._factory = pod_factory
        self._max_cycles = max_cycles
        self._reporter = reporter or TokenEfficiencyReporter
        # Per-language construction args (worker/orchestrator/project_root/...)
        # forwarded to pod_factory.create(language, **kwargs) — PodFactory.create
        # requires these; without them it raises KeyError.
        self._pod_kwargs = pod_kwargs or {}
        self._audit_client = audit_client
        self._redundancy_checker = redundancy_checker
        self._playbook_id = playbook_id
        self._max_red_attempts = max_red_attempts
        self._team_id = team_id
        # Real model/agent identity, forwarded as the audit actor_id for
        # every language's TDDCycleRunner (see tdd_cycle_runner.py).
        self._model_id = model_id

    def run_from_feature(
        self,
        feature_path: Path,
        languages: list[str],
        test_file: Path,
        implementation_file: Path,
    ) -> PolyglotRunResult:
        """Parse a Gherkin .feature file and run the polyglot TDD loop."""
        from src.agents.gherkin_feature_bridge import GherkinFeatureBridge
        spec = GherkinFeatureBridge.parse(Path(feature_path))
        return self.run(
            feature_requirement=spec.as_requirement(),
            test_file=test_file,
            implementation_file=implementation_file,
            languages=languages,
        )

    def run(
        self,
        feature_requirement: str,
        test_file: Path,
        implementation_file: Path,
        languages: list[str],
    ) -> PolyglotRunResult:
        pod_runs: list[PodRun] = []
        language_results: dict[str, LanguageRunResult] = {}

        for language in languages:
            pod = self._factory.create(language, **self._pod_kwargs.get(language, {}))
            run_result, pod_run = self._run_one(
                pod=pod,
                language=language,
                feature_requirement=feature_requirement,
                test_file=test_file,
                implementation_file=implementation_file,
            )
            language_results[language] = run_result
            pod_runs.append(pod_run)

        efficiency_report = self._reporter.score(pod_runs)
        return PolyglotRunResult(
            language_results=language_results,
            efficiency_report=efficiency_report,
        )

    # --- private ---

    def _run_one(
        self,
        pod,
        language: str,
        feature_requirement: str,
        test_file: Path,
        implementation_file: Path,
    ) -> tuple[LanguageRunResult, PodRun]:
        skipped = self._redundancy_skip(language, feature_requirement, test_file)
        if skipped is not None:
            return skipped

        spec = PodSpec(
            feature_requirement=feature_requirement,
            test_file=test_file,
            implementation_file=implementation_file,
            cycle_number=1,
        )

        # Same engine IterativeTDDRunner uses for every phase: RED, GREEN
        # (retried with error feedback, up to max_cycles), REFACTOR (skipped
        # if GREEN never passed), audit events, reflector/curator hook.
        cycle_runner = TDDCycleRunner(
            pod,
            max_green_attempts=self._max_cycles,
            playbook_id=self._playbook_id,
            audit_client=self._audit_client,
            max_red_attempts=self._max_red_attempts,
            team_id=self._team_id,
            model_id=self._model_id,
            task_type=language,
        )
        logger.info("TDD cycle [%s] %s", language, feature_requirement)
        cycle_result = cycle_runner.run(spec)

        run_result = LanguageRunResult(
            language=language,
            red=cycle_result.red_result,
            green=cycle_result.green_result,
            refactor=cycle_result.refactor_result
            or PhaseResult(passed=False, output="", error=cycle_result.error),
            cycles_to_green=cycle_result.green_attempts,
        )
        pod_run = PodRun(
            language=language,
            feature_requirement=feature_requirement,
            token_usage=pod.token_usage(),
            cycles_to_green=cycle_result.green_attempts,
        )
        return run_result, pod_run

    def _redundancy_skip(
        self, language: str, feature_requirement: str, test_file: Path
    ) -> tuple[LanguageRunResult, PodRun] | None:
        """Pre-check test_file for a test equivalent to feature_requirement.

        Static AST scan only (existing_tests_from_file never executes the
        file) -- returns a skipped result without ever pulsing into the
        sandbox if redundant, same as IterativeTDDRunner's pre-check.
        """
        if self._redundancy_checker is None:
            return None
        existing = existing_tests_from_file(test_file)
        proposed = ProposedTest(name=test_file.stem, description=feature_requirement)
        verdict = self._redundancy_checker.check(existing, proposed)
        if not verdict.is_redundant:
            return None
        logger.info(
            "PolyglotTDDRunner: skipping redundant test [%s] (confidence %.0f%%) — %s",
            language, verdict.confidence * 100, verdict.reason,
        )
        skip_result = PhaseResult(passed=True, output=f"Pre-check: {verdict.reason}")
        run_result = LanguageRunResult(
            language=language, red=skip_result, green=skip_result,
            refactor=skip_result, cycles_to_green=0,
        )
        pod_run = PodRun(
            language=language, feature_requirement=feature_requirement,
            token_usage=[], cycles_to_green=0,
        )
        return run_result, pod_run
