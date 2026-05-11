"""
PythonLanguagePod — LanguagePod implementation for Python TDD cycles.

Two construction paths:
  PythonLanguagePod(agent)           — wraps AutonomousTDDAgent (original path)
  PythonLanguagePod.from_worker(...) — uses WorkerAgent + subprocess pytest
"""
import logging
import re
import subprocess
import sys

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
        self._worker = None
        self._project_root = None
        self._token_log: list[TokenUsage] = []
        self._cycle_tokens: int = 0
        self._intercept_tokens()

    @classmethod
    def from_worker(cls, worker_agent, project_root):
        """Construct a PythonLanguagePod backed by WorkerAgent + subprocess pytest."""
        pod = cls.__new__(cls)
        pod._agent = None
        pod._worker = worker_agent
        pod._project_root = project_root
        pod._token_log = []
        pod._cycle_tokens = 0
        pod._intercept_worker_tokens()
        return pod

    def run_red(self, spec: PodSpec) -> PhaseResult:
        self._cycle_tokens = 0
        if self._worker is not None:
            return self._worker_run_red(spec)
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
        if self._worker is not None:
            return self._worker_run_green(spec)
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
        if self._worker is not None:
            return self._worker_run_refactor(spec)
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

    def _intercept_worker_tokens(self) -> None:
        original = self._worker.llm_client.generate

        def _tracking_generate(*args, **kwargs):
            result = original(*args, **kwargs)
            self._cycle_tokens += result.get("tokens_used", 0)
            return result

        self._worker.llm_client.generate = _tracking_generate

    # --- worker-path phase implementations ---

    def _worker_run_red(self, spec: PodSpec) -> PhaseResult:
        try:
            existing = spec.test_file.read_text() if spec.test_file.exists() else ""
            code = self._worker.generate_test(spec, existing_code=existing)
            spec.test_file.parent.mkdir(parents=True, exist_ok=True)
            spec.test_file.write_text(code)
        except Exception as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=str(exc))

        result = self._run_pytest(spec)
        self._record_usage(spec.cycle_number)
        return PhaseResult(
            passed=result.returncode == 0,
            output=result.stdout,
            error=result.stderr if result.returncode != 0 else None,
        )

    def _worker_run_green(self, spec: PodSpec) -> PhaseResult:
        error_output = ""
        if spec.test_file.exists():
            probe = self._run_pytest(spec)
            error_output = probe.stderr or probe.stdout

        current = spec.implementation_file.read_text() if spec.implementation_file.exists() else ""
        test_id = f"{spec.test_file}::*"
        code = self._worker.generate_implementation(
            spec,
            error_output=error_output,
            failing_test_ids=[str(spec.test_file)],
        )
        spec.implementation_file.parent.mkdir(parents=True, exist_ok=True)
        spec.implementation_file.write_text(code)

        result = self._run_pytest(spec)
        self._record_usage(spec.cycle_number)
        return PhaseResult(
            passed=result.returncode == 0,
            output=result.stdout,
            error=result.stderr if result.returncode != 0 else None,
        )

    def _worker_run_refactor(self, spec: PodSpec) -> PhaseResult:
        result = self._run_pytest(spec)
        self._record_usage(spec.cycle_number)
        return PhaseResult(
            passed=result.returncode == 0,
            output=result.stdout,
            error=result.stderr if result.returncode != 0 else None,
        )

    def _run_pytest(self, spec: PodSpec):
        import os
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self._project_root)
        return subprocess.run(
            [sys.executable, "-m", "pytest", str(spec.test_file), "-v", "--tb=short"],
            capture_output=True,
            text=True,
            cwd=self._project_root,
            env=env,
            timeout=30,
        )
