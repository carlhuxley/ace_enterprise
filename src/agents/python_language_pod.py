"""
PythonLanguagePod — LanguagePod implementation for Python TDD cycles.

Uses WorkerAgent for code generation and PodmanOrchestrator for isolated execution.
"""
import logging
import os

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

    Delegates code generation to WorkerAgent and test execution to
    PodmanOrchestrator. File I/O uses atomic writes via commit_to_disk.
    """

    def __init__(
        self,
        worker_agent,
        project_root,
        orchestrator: PodmanOrchestrator,
    ) -> None:
        self._worker = worker_agent
        self._orchestrator = orchestrator
        self._project_root = project_root
        self._token_log: list[TokenUsage] = []
        self._prompt_tokens: int = 0
        self._completion_tokens: int = 0
        self._intercept_tokens()

    def run_red(self, spec: PodSpec) -> PhaseResult:
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

        # Include existing implementation so the workspace-clear in send_pulse
        # doesn't break imports when the impl already exists from a prior cycle.
        pulse_files: dict[str, str] = {spec.test_file.name: code}
        if spec.implementation_file.exists():
            pulse_files[spec.implementation_file.name] = spec.implementation_file.read_text()

        try:
            result = self._orchestrator.pulse(pulse_files)
        except SecurityBreachError as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=f"SecurityBreach: {exc}")

        if not _is_security_failure(result):
            commit_to_disk(code, spec.test_file)

        self._record_usage(spec.cycle_number)
        return result

    def run_green(self, spec: PodSpec) -> PhaseResult:
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

    def run_refactor(self, spec: PodSpec) -> PhaseResult:
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

    def token_usage(self) -> list[TokenUsage]:
        return list(self._token_log)

    def _intercept_tokens(self) -> None:
        original = self._worker.llm_client.generate

        def _tracking_generate(*args, **kwargs):
            result = original(*args, **kwargs)
            self._prompt_tokens += result.get("prompt_tokens") or result.get("tokens_used", 0)
            self._completion_tokens += result.get("completion_tokens", 0)
            return result

        self._worker.llm_client.generate = _tracking_generate

    def _record_usage(self, cycle_number: int) -> None:
        self._token_log.append(TokenUsage(
            cycle_number=cycle_number,
            input_tokens=self._prompt_tokens,
            output_tokens=self._completion_tokens,
        ))
        self._prompt_tokens = 0
        self._completion_tokens = 0


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
