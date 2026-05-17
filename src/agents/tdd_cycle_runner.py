"""
TDDCycleRunner — orchestrates RED → GREEN → REFACTOR for one feature.

Handles GREEN retries with error feedback and aborts on security/policy failures.
"""
import dataclasses
from dataclasses import dataclass
from pathlib import Path

from src.agents.language_pod import PhaseResult, PodSpec, TokenUsage


@dataclass
class CycleResult:
    """Outcome of a complete TDD cycle."""

    success: bool
    feature_requirement: str
    red_result: PhaseResult
    green_result: PhaseResult
    refactor_result: PhaseResult | None
    green_attempts: int
    token_usage: list[TokenUsage]
    error: str | None = None


class TDDCycleRunner:
    """
    Runs one complete TDD cycle: RED → GREEN (with retry) → REFACTOR.

    GREEN is retried up to max_green_attempts times, passing the previous
    failure output back to the pod so the LLM can learn from the error.
    Any security or policy failure (ForbiddenImport, SecurityBreach, Bandit gate)
    aborts the cycle immediately without retrying.

    If experiment_logger is provided, each completed cycle is persisted via
    ExperimentLogger.log_tdd_cycle().
    """

    def __init__(
        self,
        pod,
        max_green_attempts: int = 3,
        experiment_logger=None,
        playbook_id: str = "podman_harness",
    ) -> None:
        self._pod = pod
        self._max_green_attempts = max_green_attempts
        self._experiment_logger = experiment_logger
        self._playbook_id = playbook_id

    def run(self, spec: PodSpec) -> CycleResult:
        token_start = len(self._pod.token_usage())

        # --- RED ---
        red_result = self._pod.run_red(spec)
        if _is_abort(red_result):
            cycle_result = CycleResult(
                success=False,
                feature_requirement=spec.feature_requirement,
                red_result=red_result,
                green_result=PhaseResult(passed=False, output="", error="skipped"),
                refactor_result=None,
                green_attempts=0,
                token_usage=self._pod.token_usage()[token_start:],
                error=f"RED aborted: {red_result.error}",
            )
            self._log(spec, cycle_result)
            return cycle_result

        # --- GREEN with retries ---
        green_result = PhaseResult(passed=False, output="", error=None)
        green_attempts = 0
        error_feedback = ""
        for _ in range(self._max_green_attempts):
            green_attempts += 1
            retry_spec = dataclasses.replace(spec, error_output=error_feedback)
            green_result = self._pod.run_green(retry_spec)
            if green_result.passed or _is_abort(green_result):
                break
            error_feedback = green_result.output or green_result.error or ""

        if not green_result.passed:
            cycle_result = CycleResult(
                success=False,
                feature_requirement=spec.feature_requirement,
                red_result=red_result,
                green_result=green_result,
                refactor_result=None,
                green_attempts=green_attempts,
                token_usage=self._pod.token_usage()[token_start:],
                error=green_result.error or "GREEN phase failed",
            )
            self._log(spec, cycle_result)
            return cycle_result

        # --- REFACTOR ---
        refactor_result = self._pod.run_refactor(spec)

        cycle_result = CycleResult(
            success=refactor_result.passed,
            feature_requirement=spec.feature_requirement,
            red_result=red_result,
            green_result=green_result,
            refactor_result=refactor_result,
            green_attempts=green_attempts,
            token_usage=self._pod.token_usage()[token_start:],
            error=None if refactor_result.passed else (refactor_result.error or "REFACTOR phase failed"),
        )
        self._log(spec, cycle_result)
        return cycle_result


    def _log(self, spec: PodSpec, result: CycleResult) -> None:
        if self._experiment_logger is None:
            return
        total_tokens = sum(
            u.input_tokens + u.output_tokens for u in result.token_usage
        )
        test_code = _read_if_exists(spec.test_file)
        impl_code = _read_if_exists(spec.implementation_file)
        self._experiment_logger.log_tdd_cycle(
            cycle_number=spec.cycle_number,
            requirement=spec.feature_requirement,
            test_name=spec.test_file.stem,
            test_code=test_code,
            implementation_code=impl_code,
            red_passed=result.red_result.passed,
            green_passed=result.green_result.passed,
            red_output=result.red_result.output or "",
            green_output=result.green_result.output or "",
            learned_bullets=[],
            playbook_id=self._playbook_id,
            tokens_used=total_tokens,
            retry_count=result.green_attempts,
            harness_metadata={
                "green_attempts": result.green_attempts,
                "refactor_passed": result.refactor_result.passed if result.refactor_result else None,
                "error": result.error,
            },
        )


def _read_if_exists(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


def _is_abort(result: PhaseResult) -> bool:
    """True for security/policy failures that cannot be fixed by retry."""
    if result.error is None:
        return False
    for prefix in ("ForbiddenImport:", "SecurityBreach:", "Bandit gate:"):
        if result.error.startswith(prefix):
            return True
    return False
