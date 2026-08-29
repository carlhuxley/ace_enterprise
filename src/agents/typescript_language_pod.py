"""
TypeScriptLanguagePod — LanguagePod implementation for TypeScript TDD cycles.

Mirrors PythonLanguagePod but uses TypeScriptWorkerAgent for code generation
and TypeScriptRunner for isolated vitest execution. File extensions are .ts
and test files follow the {stem}.test.ts convention.
"""
import logging
import os
from pathlib import Path

from src.agents.language_pod import PhaseResult, PodSpec, TokenUsage
from src.agents.podman_orchestrator import PodmanOrchestrator, SecurityBreachError

logger = logging.getLogger(__name__)


def commit_to_disk(code: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp")
    tmp.write_text(code, encoding="utf-8")
    os.replace(tmp, dst)


class TypeScriptLanguagePod:
    """LanguagePod for TypeScript TDD cycles via vitest in a rootless Podman container."""

    def __init__(
        self,
        worker_agent,
        project_root: Path,
        orchestrator: PodmanOrchestrator,
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
        self._intercept_tokens()

    @staticmethod
    def _ts_spec(spec: PodSpec) -> PodSpec:
        """Normalise PodSpec file paths to TypeScript extensions.

        The planner is language-agnostic and may return Python-style paths
        (test_foo.py / foo.py). Convert them to vitest convention (foo.test.ts / foo.ts).
        """
        import re as _re
        from dataclasses import replace

        impl = spec.implementation_file
        test = spec.test_file

        # impl: anything.py → anything.ts
        if impl.suffix == ".py":
            impl = impl.with_suffix(".ts")

        # test: test_foo.py or foo_test.py → foo.test.ts; foo.py → foo.test.ts
        if test.suffix == ".py":
            stem = _re.sub(r"^test_|_test$", "", test.stem)
            test = test.parent / f"{stem}.test.ts"

        return replace(spec, test_file=test, implementation_file=impl)

    def run_red(self, spec: PodSpec) -> PhaseResult:
        spec = self._ts_spec(spec)
        try:
            existing = spec.test_file.read_text(encoding="utf-8") if spec.test_file.exists() else ""
            code = self._worker.generate_test(spec, existing_code=existing)
            code = _ensure_test_import(code, spec.implementation_file.stem)
        except Exception as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=str(exc))

        pulse_files: dict[str, str] = {spec.test_file.name: code}
        if spec.implementation_file.exists():
            pulse_files[spec.implementation_file.name] = spec.implementation_file.read_text(encoding="utf-8")

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
        spec = self._ts_spec(spec)
        test_code = spec.test_file.read_text(encoding="utf-8") if spec.test_file.exists() else ""
        try:
            impl_code = self._worker.generate_implementation(
                spec,
                error_output=spec.error_output,
                test_code=test_code,
            )
        except Exception as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=str(exc))

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
        spec = self._ts_spec(spec)
        test_code = spec.test_file.read_text(encoding="utf-8") if spec.test_file.exists() else ""
        current_code = spec.implementation_file.read_text(encoding="utf-8") if spec.implementation_file.exists() else ""
        try:
            refactored_code = self._worker.generate_refactor(spec, current_code=current_code)
        except Exception as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=str(exc))

        files = {
            spec.test_file.name: test_code,
            spec.implementation_file.name: refactored_code,
        }
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


def _ensure_test_import(code: str, stem: str) -> str:
    """Prepend a namespace import if the test file has no import from the impl module."""
    import re
    if re.search(rf"""from\s+['"]\./\s*{re.escape(stem)}['"]""", code):
        return code
    # Safety net: namespace import so vitest can at least resolve the module
    return f"import * as {stem} from './{stem}';\n" + code
