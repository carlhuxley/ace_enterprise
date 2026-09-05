"""
SimulationPod — LanguagePod implementation proving the ACE TDD harness
(TDDCycleRunner -> Reflector -> Curator -> Playbook) is domain-agnostic.

Every other pod (Python/Go/TypeScript) treats a CLI test runner (pytest,
go test, vitest) as its execution oracle. SimulationPod swaps that oracle
for a headless PyBullet physics simulation of a pluggable SimulationScenario
(src/agents/simulation_scenario.py) -- peg-in-hole insertion, trajectory
following, or any other physical task a scenario module defines. run_green's
"implementation" is a Python controller script, and passing/failing is
decided by MetricBound thresholds (src/agents/simulation_invariants.py)
extracted from a Gherkin spec rather than by assertions in a test file.

SimulationPod itself knows nothing about pegs, holes, or any other physical
specifics -- all of that lives in the scenario it's constructed with.

Structured like GoLanguagePod (LLM prompts built and called directly, no
separate WorkerAgent) rather than PythonLanguagePod, since there's no
existing worker abstraction for controller-script generation.
"""
import dataclasses
import json
import logging
import os
import re
from pathlib import Path

from src.agents.import_filter import ForbiddenImportError, ImportFilter
from src.agents.language_pod import PhaseResult, PodSpec, TokenUsage
from src.agents.simulation_invariants import MetricBound, extract_invariants
from src.agents.simulation_oracle import SimulationEnvironmentError, SimulationOracle
from src.agents.simulation_runner import summarize_telemetry
from src.agents.simulation_scenario import SimulationScenario

logger = logging.getLogger(__name__)

_import_filter = ImportFilter()


def commit_to_disk(code: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp")
    tmp.write_text(code, encoding="utf-8")
    os.replace(tmp, dst)


class SimulationPod:
    """
    LanguagePod implementation for a PyBullet-backed TDD cycle, parameterized
    by a SimulationScenario.

    run_red writes the extracted MetricBounds to spec.test_file (the
    scenario's "test") and proves they fail against the scenario's null
    controller. run_green asks the LLM for a controller script and executes
    it through SimulationOracle. run_refactor asks the LLM to refactor the
    controller, re-verifying through the same oracle since (unlike gofmt) an
    LLM refactor of physics control code isn't semantics-preserving by
    construction.
    """

    def __init__(
        self,
        llm_client,
        project_root: Path,
        scenario: SimulationScenario,
        oracle: SimulationOracle | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._project_root = project_root
        self._scenario = scenario
        self._oracle = oracle or SimulationOracle(scenario)
        self._token_log: list[TokenUsage] = []
        self._cycle_tokens: int = 0
        self._actual_model: str | None = None
        self._requested_model: str | None = None
        self._provider: str | None = None
        # Every GREEN/REFACTOR attempt is archived regardless of outcome (see
        # _archive_attempt) -- a failing attempt's code would otherwise be
        # lost entirely, since commit_to_disk only ever writes the winner.
        self._attempt_counter: int = 0
        # Last attempt's diagnosis per cycle, used to detect a retry loop
        # stuck reproducing the identical failure (see _with_stagnation_note).
        self._last_diagnostic: dict[int, str] = {}
        self._intercept_tokens()

    def run_red(self, spec: PodSpec) -> PhaseResult:
        self._cycle_tokens = 0
        invariants = self._invariants_for(spec)

        try:
            telemetry = self._oracle.run(self._scenario.null_action_source(), invariants)
        except SimulationEnvironmentError as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=f"SimulationEnvironment: {exc}")

        commit_to_disk(_invariants_to_json(invariants), spec.test_file)
        self._record_usage(spec.cycle_number)
        return PhaseResult(
            passed=telemetry.success,
            output=summarize_telemetry(telemetry, invariants),
            error=None if not telemetry.success else "RED phase unexpectedly succeeded with no controller",
        )

    def run_green(self, spec: PodSpec) -> PhaseResult:
        self._cycle_tokens = 0
        invariants = self._invariants_for(spec)

        try:
            prompt = self._green_prompt(spec)
            response = self._llm_client.generate(prompt)
            controller_code = _extract_code(response.get("content", ""))
        except Exception as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=str(exc))

        self._archive_attempt(spec, "green", controller_code)

        try:
            _import_filter.check(controller_code)
        except ForbiddenImportError as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=f"ForbiddenImport: {exc}")

        result = self._run_oracle(spec, controller_code, invariants)
        if result.passed:
            commit_to_disk(controller_code, spec.implementation_file)
        self._record_usage(spec.cycle_number)
        return result

    def run_refactor(self, spec: PodSpec) -> PhaseResult:
        self._cycle_tokens = 0
        invariants = self._invariants_for(spec)
        current_code = (
            spec.implementation_file.read_text(encoding="utf-8")
            if spec.implementation_file.exists()
            else ""
        )

        try:
            prompt = self._refactor_prompt(current_code)
            response = self._llm_client.generate(prompt)
            refactored_code = _extract_code(response.get("content", ""))
        except Exception as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=str(exc))

        self._archive_attempt(spec, "refactor", refactored_code)

        try:
            _import_filter.check(refactored_code)
        except ForbiddenImportError as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=f"ForbiddenImport: {exc}")

        result = self._run_oracle(spec, refactored_code, invariants)
        # A failed refactor must not clobber a working controller on disk.
        if result.passed:
            commit_to_disk(refactored_code, spec.implementation_file)
        self._record_usage(spec.cycle_number)
        return result

    def token_usage(self) -> list[TokenUsage]:
        return list(self._token_log)

    # --- internal helpers ---

    def _invariants_for(self, spec: PodSpec) -> list[MetricBound]:
        extracted = extract_invariants(spec.gherkin_context or spec.feature_requirement)
        return extracted if extracted else self._scenario.default_invariants()

    def _run_oracle(self, spec: PodSpec, controller_code: str, invariants: list[MetricBound]) -> PhaseResult:
        try:
            telemetry = self._oracle.run(controller_code, invariants)
        except SimulationEnvironmentError as exc:
            return PhaseResult(passed=False, output="", error=f"SimulationEnvironment: {exc}")
        summary = summarize_telemetry(telemetry, invariants)
        if not telemetry.success:
            summary = self._with_stagnation_note(spec.cycle_number, summary)
        return PhaseResult(
            passed=telemetry.success,
            output=summary,
            error=None if telemetry.success else telemetry.failure_reason,
        )

    def _archive_attempt(self, spec: PodSpec, phase: str, code: str) -> None:
        self._attempt_counter += 1
        attempts_dir = spec.implementation_file.parent / "attempts"
        filename = f"{spec.implementation_file.stem}_cycle{spec.cycle_number}_{phase}_attempt{self._attempt_counter}.py"
        commit_to_disk(code, attempts_dir / filename)

    def _with_stagnation_note(self, cycle_number: int, summary: str) -> str:
        """At temperature 0, an identical diagnosis fed back verbatim
        produces an identical prompt next attempt, which produces identical
        code, which produces the identical diagnosis again -- a retry loop
        that repeats forever without this. Detecting a repeat and saying so
        explicitly is what actually breaks it."""
        previous = self._last_diagnostic.get(cycle_number)
        self._last_diagnostic[cycle_number] = summary
        if previous == summary:
            return (
                summary
                + "\n\nNOTE: this exact outcome also occurred on the previous attempt -- "
                  "repeating the same control strategy will not work. Try a materially "
                  "different approach (e.g. if your controller pauses all motion once it "
                  "detects resistance, make sure it explicitly resumes exploratory motion "
                  "afterward instead of remaining still)."
            )
        return summary

    def _green_prompt(self, spec: PodSpec) -> str:
        gherkin_section = f"\n\nGherkin spec:\n{spec.gherkin_context}" if spec.gherkin_context else ""
        error_section = f"\n\nPrevious attempt failed: {spec.error_output}" if spec.error_output else ""
        return (
            f"Feature: {spec.feature_requirement}\n\n"
            f"{self._scenario.controller_contract()}"
            f"{gherkin_section}{error_section}"
        )

    def _refactor_prompt(self, current_code: str) -> str:
        return (
            f"Refactor this controller for clarity and smoother, more direct "
            f"motion, without changing its control strategy or breaking the "
            f"contract below.\n\n{self._scenario.controller_contract()}\n\n"
            f"Current controller:\n```python\n{current_code}\n```"
        )

    def _record_usage(self, cycle_number: int) -> None:
        self._token_log.append(TokenUsage(
            cycle_number=cycle_number,
            input_tokens=self._cycle_tokens,
            output_tokens=0,
            actual_model=self._actual_model,
            requested_model=self._requested_model,
            provider=self._provider,
        ))
        self._cycle_tokens = 0

    def _intercept_tokens(self) -> None:
        original = self._llm_client.generate

        def _tracking_generate(*args, **kwargs):
            result = original(*args, **kwargs)
            self._cycle_tokens += result.get("tokens_used", 0)
            self._actual_model = result.get("actual_model", self._actual_model)
            self._requested_model = result.get("requested_model", self._requested_model)
            self._provider = result.get("provider", self._provider)
            return result

        self._llm_client.generate = _tracking_generate


_PY_CODE_START = re.compile(r"^(import\s|from\s|def\s|class\s)", re.MULTILINE)


def _extract_code(content: str) -> str:
    match = re.search(r"```(?:python)?\n(.*?)```", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    code_match = _PY_CODE_START.search(content)
    if code_match:
        return content[code_match.start():].strip()
    return content.strip()


def _invariants_to_json(invariants: list[MetricBound]) -> str:
    return json.dumps([dataclasses.asdict(b) for b in invariants])
