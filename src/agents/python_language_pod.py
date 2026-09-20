"""
PythonLanguagePod — LanguagePod implementation for Python TDD cycles.

Uses WorkerAgent for code generation and PodmanOrchestrator for isolated execution.
"""
import logging
import os

from src.agents.import_filter import ForbiddenImportError, ImportFilter
from src.agents.language_pod import PhaseResult, PodSpec, TokenUsage
from src.agents.podman_orchestrator import PodmanOrchestrator, SecurityBreachError
from src.utils.patcher import apply_patch

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
        *,
        use_patch_mode: bool = False,
        patch_escalation_threshold: int = 2,
    ) -> None:
        self._worker = worker_agent
        self._orchestrator = orchestrator
        self._project_root = project_root
        self._token_log: list[TokenUsage] = []
        self._prompt_tokens: int = 0
        self._completion_tokens: int = 0
        self._actual_model: str | None = None
        self._requested_model: str | None = None
        self._provider: str | None = None
        # Diff-based GREEN (search/replace patching instead of whole-file
        # rewrite), opt-in -- off by default so existing behavior/tests are
        # unaffected. Only used when there's an existing implementation to
        # patch against; the very first GREEN for a file always writes it
        # fresh. After `patch_escalation_threshold` consecutive patch
        # failures on the same file, falls back to whole-file generation for
        # that file until a patch attempt succeeds again.
        self._use_patch_mode = use_patch_mode
        self._patch_escalation_threshold = patch_escalation_threshold
        self._patch_failure_counts: dict[str, int] = {}
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
        pulse_files: dict[str, str] = self._sibling_files(spec)
        pulse_files[spec.test_file.name] = code
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
        test_code = spec.test_file.read_text() if spec.test_file.exists() else ""
        # The impl file holds the last committed (passing) implementation — from
        # earlier scenarios in a Gherkin-driven run. Hand it to GREEN so it
        # extends that code instead of regenerating the module from scratch and
        # losing previously-passing behaviour (issue #17).
        existing_impl = (
            spec.implementation_file.read_text()
            if spec.implementation_file.exists()
            else ""
        )

        file_key = str(spec.implementation_file)
        use_patch = (
            self._use_patch_mode
            and bool(existing_impl)
            and self._patch_failure_counts.get(file_key, 0) < self._patch_escalation_threshold
        )

        if use_patch:
            try:
                patch_text = self._worker.generate_patch(
                    spec,
                    existing_code=existing_impl,
                    error_output=spec.error_output,
                    test_code=test_code,
                )
            except Exception as exc:
                self._record_usage(spec.cycle_number)
                return PhaseResult(passed=False, output="", error=str(exc))
            patch_result = apply_patch(existing_impl, patch_text)
            if not patch_result.success:
                # Deterministic, host-side rejection -- never reaches the
                # sandbox. Counted toward escalation and fed back as normal
                # retry feedback (TDDCycleRunner threads PhaseResult.error
                # into the next attempt's spec.error_output), so the worker
                # sees exactly which SEARCH block failed and why.
                self._patch_failure_counts[file_key] = self._patch_failure_counts.get(file_key, 0) + 1
                self._record_usage(spec.cycle_number)
                return PhaseResult(passed=False, output="", error=f"PATCH_APPLY_FAILED: {patch_result.error}")
            impl_code = patch_result.code
        else:
            try:
                impl_code = self._worker.generate_implementation(
                    spec,
                    error_output=spec.error_output,
                    failing_test_ids=[str(spec.test_file)],
                    test_code=test_code,
                    existing_code=existing_impl,
                )
            except Exception as exc:
                self._record_usage(spec.cycle_number)
                return PhaseResult(passed=False, output="", error=str(exc))

        try:
            _import_filter.check(impl_code)
        except ForbiddenImportError as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=f"ForbiddenImport: {exc}")
        except Exception as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=str(exc))
        files = self._sibling_files(spec)
        files[spec.test_file.name] = test_code
        files[spec.implementation_file.name] = impl_code

        try:
            result = self._orchestrator.pulse(files)
        except SecurityBreachError as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=f"SecurityBreach: {exc}")

        if result.passed:
            commit_to_disk(impl_code, spec.implementation_file)
            self._patch_failure_counts[file_key] = 0
        self._record_usage(spec.cycle_number)
        return result

    def run_refactor(self, spec: PodSpec) -> PhaseResult:
        test_code = spec.test_file.read_text() if spec.test_file.exists() else ""
        current_code = spec.implementation_file.read_text() if spec.implementation_file.exists() else ""
        try:
            refactored_code = self._worker.generate_refactor(spec, current_code=current_code)
            _import_filter.check(refactored_code)
        except ForbiddenImportError as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=f"ForbiddenImport: {exc}")
        except Exception as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=str(exc))

        files = self._sibling_files(spec)
        files[spec.test_file.name] = test_code
        files[spec.implementation_file.name] = refactored_code
        try:
            result = self._orchestrator.pulse(files)
        except SecurityBreachError as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=f"SecurityBreach: {exc}")

        # Only keep the refactor if it didn't break the tests — a failed
        # refactor must not clobber a working implementation on disk.
        if result.passed:
            commit_to_disk(refactored_code, spec.implementation_file)
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
            # Last call's attribution wins -- model rarely changes mid-cycle,
            # and this is simpler than tracking it per-phase.
            self._actual_model = result.get("actual_model", self._actual_model)
            self._requested_model = result.get("requested_model", self._requested_model)
            self._provider = result.get("provider", self._provider)
            return result

        self._worker.llm_client.generate = _tracking_generate

    def _sibling_files(self, spec: PodSpec) -> dict[str, str]:
        """Already-built sibling project modules to pulse alongside the
        target module, so `from <sibling> import ...` resolves during
        RED/GREEN/REFACTOR instead of failing at collection every cycle
        (#61) -- mirrors module_architect.validate_module's `extra_files`
        mechanism for the batch `ace project` path (#28), which this
        iterative path never had. Keyed by filename, matching the flat
        namespace PodmanRunner mounts pulsed files into; excludes the
        target module's own implementation file, whose freshly generated
        content the caller sets separately and must win over any stale
        on-disk copy this glob would otherwise pick up.
        """
        src_dir = self._project_root / "src"
        if not src_dir.is_dir():
            src_dir = self._project_root / "lib"
        if not src_dir.is_dir():
            src_dir = self._project_root
        files: dict[str, str] = {}
        for path in sorted(src_dir.rglob("*.py")):
            if path == spec.implementation_file:
                continue
            files[path.name] = path.read_text()
        return files

    def _record_usage(self, cycle_number: int) -> None:
        self._token_log.append(TokenUsage(
            cycle_number=cycle_number,
            input_tokens=self._prompt_tokens,
            output_tokens=self._completion_tokens,
            actual_model=self._actual_model,
            requested_model=self._requested_model,
            provider=self._provider,
        ))
        self._prompt_tokens = 0
        self._completion_tokens = 0


def _is_security_failure(result: PhaseResult) -> bool:
    return result.error is not None and result.error.startswith("Security gate:")


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
