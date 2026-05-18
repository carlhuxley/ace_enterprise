"""
PythonLanguagePod — LanguagePod implementation for Python TDD cycles.

Two construction paths:
  PythonLanguagePod(agent)                        — wraps AutonomousTDDAgent (original path)
  PythonLanguagePod.from_worker(..., orchestrator) — uses WorkerAgent + PodmanOrchestrator
"""
import logging
import os
import re
import tempfile

from src.agents.import_filter import ForbiddenImportError, ImportFilter
from src.agents.language_pod import LanguagePod, PhaseResult, PodSpec, TokenUsage
from src.agents.podman_orchestrator import PodmanOrchestrator, SecurityBreachError

logger = logging.getLogger(__name__)

_import_filter = ImportFilter()


def commit_to_disk(code: str, dst) -> None:
    """Atomically write code to dst using os.replace."""
    from pathlib import Path
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp")
    tmp.write_text(code)
    os.replace(tmp, dst)


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
        self._orchestrator = None
        self._project_root = None
        self._token_log: list[TokenUsage] = []
        self._prompt_tokens: int = 0
        self._completion_tokens: int = 0
        self._intercept_tokens()

    @classmethod
    def from_worker(cls, worker_agent, project_root, orchestrator: PodmanOrchestrator):
        """Construct a PythonLanguagePod backed by WorkerAgent + PodmanOrchestrator."""
        pod = cls.__new__(cls)
        pod._agent = None
        pod._worker = worker_agent
        pod._orchestrator = orchestrator
        pod._project_root = project_root
        pod._token_log = []
        pod._prompt_tokens = 0
        pod._completion_tokens = 0
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
            input_tokens=self._prompt_tokens,
            output_tokens=self._completion_tokens,
        ))
        self._prompt_tokens = 0
        self._completion_tokens = 0

    def _intercept_tokens(self) -> None:
        original = self._agent.llm_client.generate

        def _tracking_generate(*args, **kwargs):
            result = original(*args, **kwargs)
            self._prompt_tokens += result.get("prompt_tokens") or result.get("tokens_used", 0)
            self._completion_tokens += result.get("completion_tokens", 0)
            return result

        self._agent.llm_client.generate = _tracking_generate

    def _intercept_worker_tokens(self) -> None:
        original = self._worker.llm_client.generate

        def _tracking_generate(*args, **kwargs):
            result = original(*args, **kwargs)
            self._prompt_tokens += result.get("prompt_tokens") or result.get("tokens_used", 0)
            self._completion_tokens += result.get("completion_tokens", 0)
            return result

        self._worker.llm_client.generate = _tracking_generate

    # --- worker-path phase implementations ---

    def _worker_run_red(self, spec: PodSpec) -> PhaseResult:
        try:
            existing = spec.test_file.read_text() if spec.test_file.exists() else ""
            code = self._worker.generate_test(spec, existing_code=existing)
            code = _ensure_test_import(code, spec.implementation_file.stem)
            _import_filter.check(code)
        except ForbiddenImportError as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=f"ForbiddenImport: {exc}")
        except Exception as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=str(exc))

        try:
            result = self._orchestrator.pulse({spec.test_file.name: code})
        except SecurityBreachError as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=f"SecurityBreach: {exc}")

        if not _is_security_failure(result):
            commit_to_disk(code, spec.test_file)

        self._record_usage(spec.cycle_number)
        return result

    def _worker_run_green(self, spec: PodSpec) -> PhaseResult:
        try:
            impl_code = self._worker.generate_implementation(
                spec,
                error_output=spec.error_output,
                failing_test_ids=[str(spec.test_file)],
            )
            _import_filter.check(impl_code)
        except ForbiddenImportError as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=f"ForbiddenImport: {exc}")
        except Exception as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=str(exc))

        test_code = spec.test_file.read_text() if spec.test_file.exists() else ""
        files = {
            spec.test_file.name: test_code,
            spec.implementation_file.name: impl_code,
        }

        try:
            result = self._orchestrator.pulse(files)
        except SecurityBreachError as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=f"SecurityBreach: {exc}")

        if result.passed:
            commit_to_disk(impl_code, spec.implementation_file)

        self._record_usage(spec.cycle_number)
        return result

    def _worker_run_refactor(self, spec: PodSpec) -> PhaseResult:
        test_code = spec.test_file.read_text() if spec.test_file.exists() else ""
        impl_code = spec.implementation_file.read_text() if spec.implementation_file.exists() else ""
        files = {
            spec.test_file.name: test_code,
            spec.implementation_file.name: impl_code,
        }
        try:
            result = self._orchestrator.pulse(files)
        except SecurityBreachError as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=f"SecurityBreach: {exc}")
        self._record_usage(spec.cycle_number)
        return result


def _is_security_failure(result: PhaseResult) -> bool:
    return result.error is not None and result.error.startswith("Bandit gate:")


def _ensure_test_import(code: str, module_name: str) -> str:
    """Prepend 'from <module_name> import *' if the module isn't imported at all."""
    import ast
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == module_name:
                    return code
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == module_name:
                return code
    return f"from {module_name} import *\n" + code
