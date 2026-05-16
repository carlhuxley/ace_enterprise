"""
TDDCycleRunner — orchestrates RED → GREEN → REFACTOR for one feature.

Handles GREEN retries with error feedback and aborts on security/policy failures.
"""
import dataclasses
from dataclasses import dataclass

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
    """

    def __init__(self, pod, max_green_attempts: int = 3) -> None:
        self._pod = pod
        self._max_green_attempts = max_green_attempts

    def run(self, spec: PodSpec) -> CycleResult:
        token_start = len(self._pod.token_usage())

        # --- RED ---
        red_result = self._pod.run_red(spec)
        if _is_abort(red_result):
            return CycleResult(
                success=False,
                feature_requirement=spec.feature_requirement,
                red_result=red_result,
                green_result=PhaseResult(passed=False, output="", error="skipped"),
                refactor_result=None,
                green_attempts=0,
                token_usage=self._pod.token_usage()[token_start:],
                error=f"RED aborted: {red_result.error}",
            )

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
            return CycleResult(
                success=False,
                feature_requirement=spec.feature_requirement,
                red_result=red_result,
                green_result=green_result,
                refactor_result=None,
                green_attempts=green_attempts,
                token_usage=self._pod.token_usage()[token_start:],
                error=green_result.error or "GREEN phase failed",
            )

        # --- REFACTOR ---
        refactor_result = self._pod.run_refactor(spec)

        return CycleResult(
            success=refactor_result.passed,
            feature_requirement=spec.feature_requirement,
            red_result=red_result,
            green_result=green_result,
            refactor_result=refactor_result,
            green_attempts=green_attempts,
            token_usage=self._pod.token_usage()[token_start:],
            error=None if refactor_result.passed else (refactor_result.error or "REFACTOR phase failed"),
        )


def _is_abort(result: PhaseResult) -> bool:
    """True for security/policy failures that cannot be fixed by retry."""
    if result.error is None:
        return False
    for prefix in ("ForbiddenImport:", "SecurityBreach:", "Bandit gate:"):
        if result.error.startswith(prefix):
            return True
    return False
