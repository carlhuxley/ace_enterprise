"""
PolyglotTDDRunner — orchestrates RED→GREEN→REFACTOR across multiple LanguagePods
and reports per-language token efficiency via TokenEfficiencyReporter.

This is the entry point that wires together:
  LanguagePod (protocol) → PythonLanguagePod / GoLanguagePod
  TokenEfficiencyReporter → EfficiencyReport
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.agents.language_pod import PhaseResult, PodSpec
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
                playbook_manager=kwargs.get("playbook_manager"),
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

    def __init__(self, pod_factory, max_cycles: int = 5, reporter=None) -> None:
        self._factory = pod_factory
        self._max_cycles = max_cycles
        self._reporter = reporter or TokenEfficiencyReporter

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
            pod = self._factory.create(language)
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
        spec = PodSpec(
            feature_requirement=feature_requirement,
            test_file=test_file,
            implementation_file=implementation_file,
            cycle_number=1,
        )

        logger.info("RED  [%s] %s", language, feature_requirement)
        red_result = pod.run_red(spec)

        green_result = PhaseResult(passed=False, output="")
        cycles_to_green = 0
        for cycle in range(1, self._max_cycles + 1):
            spec = PodSpec(
                feature_requirement=feature_requirement,
                test_file=test_file,
                implementation_file=implementation_file,
                cycle_number=cycle,
            )
            logger.info("GREEN [%s] cycle %d", language, cycle)
            green_result = pod.run_green(spec)
            cycles_to_green = cycle
            if green_result.passed:
                break

        logger.info("REFACTOR [%s]", language)
        refactor_result = pod.run_refactor(spec)

        run_result = LanguageRunResult(
            language=language,
            red=red_result,
            green=green_result,
            refactor=refactor_result,
            cycles_to_green=cycles_to_green,
        )
        pod_run = PodRun(
            language=language,
            feature_requirement=feature_requirement,
            token_usage=pod.token_usage(),
            cycles_to_green=cycles_to_green,
        )
        return run_result, pod_run
