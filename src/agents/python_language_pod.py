"""
PythonLanguagePod — LanguagePod implementation wrapping AutonomousTDDAgent.

Adapts the existing TDD agent's phase methods to the LanguagePod protocol.
No behavioural changes to the underlying agent; this is a thin adapter.
"""
import logging
import re

from src.agents.language_pod import LanguagePod, PhaseResult, PodSpec, TokenUsage

logger = logging.getLogger(__name__)


class PythonLanguagePod:
    """
    LanguagePod implementation for Python TDD cycles.

    Wraps AutonomousTDDAgent._write_test, _write_minimal_code, _refactor_code,
    and _run_tests. Intercepts llm_client.generate() calls to accumulate per-cycle
    token usage without modifying the underlying agent.
    """

    def __init__(self, agent) -> None:
        self._agent = agent
        self._token_log: list[TokenUsage] = []
        self._cycle_tokens: int = 0
        self._intercept_tokens()

    def run_red(self, spec: PodSpec) -> PhaseResult:
        self._cycle_tokens = 0
        increment = self._make_increment(spec)
        try:
            self._agent._write_test(increment, spec.cycle_number)
        except Exception as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=str(exc))

        result = self._agent._run_tests()
        self._record_usage(spec.cycle_number)
        return PhaseResult(
            passed=not result.failed,
            output=result.output,
            error=result.error,
        )

    def run_green(self, spec: PodSpec) -> PhaseResult:
        self._cycle_tokens = 0
        increment = self._make_increment(spec)
        red_result = self._agent._run_tests()
        self._agent._write_minimal_code(increment, red_result)
        result = self._agent._run_tests()
        self._record_usage(spec.cycle_number)
        return PhaseResult(
            passed=result.all_passed,
            output=result.output,
            error=result.error,
        )

    def run_refactor(self, spec: PodSpec) -> PhaseResult:
        self._cycle_tokens = 0
        self._agent._refactor_code(spec.implementation_file)
        result = self._agent._run_tests()
        self._record_usage(spec.cycle_number)
        return PhaseResult(
            passed=result.all_passed,
            output=result.output,
            error=result.error,
        )

    def token_usage(self) -> list[TokenUsage]:
        return list(self._token_log)

    # --- internal helpers ---

    def _make_increment(self, spec: PodSpec):
        from src.agents.autonomous_tdd_agent import TestIncrement

        test_name = "test_" + re.sub(r"\W+", "_", spec.feature_requirement.lower())[:40].strip("_")
        return TestIncrement(
            test_name=test_name,
            description=spec.feature_requirement,
            test_file=spec.test_file,
            implementation_file=spec.implementation_file,
        )

    def _record_usage(self, cycle_number: int) -> None:
        self._token_log.append(TokenUsage(
            cycle_number=cycle_number,
            input_tokens=self._cycle_tokens,
            output_tokens=0,
        ))
        self._cycle_tokens = 0

    def _intercept_tokens(self) -> None:
        original = self._agent.llm_client.generate

        def _tracking_generate(*args, **kwargs):
            result = original(*args, **kwargs)
            self._cycle_tokens += result.get("tokens_used", 0)
            return result

        self._agent.llm_client.generate = _tracking_generate
