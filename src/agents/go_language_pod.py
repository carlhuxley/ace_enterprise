"""
GoLanguagePod — LanguagePod implementation for Go TDD cycles.

Executes inside a rootless Podman container via PodmanOrchestrator + GoRunner
(ace_enterprise-jww) — previously ran go test/gofmt/go vet directly on the
host via subprocess, with none of the isolation Python and TypeScript pods
get (--network none, --cap-drop=all, read-only workspace, gosec static
scanning). LLM generates Go test stubs (run_red) and implementation code
(run_green) directly (no separate GoWorkerAgent, matching the pre-existing
convention). run_refactor runs gofmt + go vet inside the sandbox, without
LLM involvement — gofmt's reformatting is captured via GoRunner's
formatted_files and committed directly, since gofmt is semantics-preserving
by construction (it never needs re-verification against go vet/test).
"""
import logging
import os
import re
from pathlib import Path

from src.agents.language_pod import LanguagePod, PhaseResult, PodSpec, TokenUsage
from src.agents.podman_orchestrator import PodmanOrchestrator, SecurityBreachError

logger = logging.getLogger(__name__)

_GO_BULLETS_SECTION = "global-go-bullets"

_DEFAULT_GO_BULLETS = [
    "use errors.New or fmt.Errorf for sentinel errors, not panic",
    "satisfy interfaces implicitly — define the interface at the call site, not the implementation site",
    "prefer channels and goroutines over shared memory for concurrency",
]

# Every pulse is a fresh, ephemeral workspace (see GoRunner's go.mod), so all
# generated files must agree on one package name regardless of what the LLM
# would otherwise guess.
_PACKAGE_NAME = "pulse"


def commit_to_disk(code: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp")
    tmp.write_text(code, encoding="utf-8")
    os.replace(tmp, dst)


class GoLanguagePod:
    """
    LanguagePod implementation for Go TDD cycles.

    LLM generates Go test stubs (run_red) and implementation code (run_green).
    run_refactor runs gofmt + go vet without LLM involvement.
    Injects global-go-bullets from PlaybookManager into the GREEN prompt when available.
    """

    def __init__(
        self,
        llm_client,
        project_root: Path,
        orchestrator: PodmanOrchestrator,
        playbook_manager=None,
    ) -> None:
        self._llm_client = llm_client
        self._project_root = project_root
        self._orchestrator = orchestrator
        self._playbook_manager = playbook_manager
        self._token_log: list[TokenUsage] = []
        self._cycle_tokens: int = 0
        self._intercept_tokens()

    def run_red(self, spec: PodSpec) -> PhaseResult:
        self._cycle_tokens = 0
        try:
            prompt = self._red_prompt(spec)
            response = self._llm_client.generate(prompt)
            test_code = _extract_code(response.get("content", ""))
        except Exception as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=str(exc))

        files: dict[str, str] = {spec.test_file.name: test_code}
        if spec.implementation_file.exists():
            files[spec.implementation_file.name] = spec.implementation_file.read_text(encoding="utf-8")

        try:
            result = self._orchestrator.pulse(files)
        except SecurityBreachError as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=f"SecurityBreach: {exc}")

        if not _is_security_failure(result):
            commit_to_disk(test_code, spec.test_file)
        self._record_usage(spec.cycle_number)
        return result

    def run_green(self, spec: PodSpec) -> PhaseResult:
        self._cycle_tokens = 0
        test_code = spec.test_file.read_text(encoding="utf-8") if spec.test_file.exists() else ""
        try:
            bullets = self._get_go_bullets()
            prompt = self._green_prompt(spec, bullets)
            response = self._llm_client.generate(prompt)
            impl_code = _extract_code(response.get("content", ""))
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
        self._cycle_tokens = 0
        test_code = spec.test_file.read_text(encoding="utf-8") if spec.test_file.exists() else ""
        impl_code = spec.implementation_file.read_text(encoding="utf-8") if spec.implementation_file.exists() else ""
        files = {
            spec.test_file.name: test_code,
            spec.implementation_file.name: impl_code,
        }
        try:
            result = self._orchestrator.pulse(files)
        except SecurityBreachError as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=f"SecurityBreach: {exc}")

        # gofmt is semantics-preserving by construction (whitespace/style
        # only) — the vet/test pass we just verified against the original
        # source still holds for the reformatted version, no second
        # round-trip needed. Only keep it if the refactor pulse passed; a
        # failed pulse must not clobber a working implementation.
        if result.passed and result.formatted_files:
            formatted_impl = result.formatted_files.get(spec.implementation_file.name)
            if formatted_impl:
                commit_to_disk(formatted_impl, spec.implementation_file)

        self._record_usage(spec.cycle_number)
        return result

    def token_usage(self) -> list[TokenUsage]:
        return list(self._token_log)

    # --- internal helpers ---

    def _red_prompt(self, spec: PodSpec) -> str:
        return (
            f"Write a failing Go test for this feature: {spec.feature_requirement}\n"
            f"Output only valid Go code for {spec.test_file.name}. "
            f"Use the standard 'testing' package. The test must fail in the RED phase. "
            f"Do not include an implementation. "
            f"The file must declare 'package {_PACKAGE_NAME}' as its package."
        )

    def _green_prompt(self, spec: PodSpec, bullets: list[str]) -> str:
        bullets_section = ""
        if bullets:
            bullets_section = "\n\nGo idioms to apply:\n" + "\n".join(f"- {b}" for b in bullets)
        return (
            f"Write a minimal Go implementation to make the tests pass.\n"
            f"Feature: {spec.feature_requirement}\n"
            f"Test file: {spec.test_file.name}\n"
            f"Implementation file: {spec.implementation_file.name}"
            f"{bullets_section}\n"
            f"Output only valid Go code. "
            f"The file must declare 'package {_PACKAGE_NAME}' as its package, "
            f"matching the test file."
        )

    def _get_go_bullets(self) -> list[str]:
        if self._playbook_manager is None:
            return list(_DEFAULT_GO_BULLETS)
        try:
            bullets = self._playbook_manager.get_bullets(_GO_BULLETS_SECTION)
            return bullets if bullets else list(_DEFAULT_GO_BULLETS)
        except Exception:
            return list(_DEFAULT_GO_BULLETS)

    def _record_usage(self, cycle_number: int) -> None:
        self._token_log.append(TokenUsage(
            cycle_number=cycle_number,
            input_tokens=self._cycle_tokens,
            output_tokens=0,
        ))
        self._cycle_tokens = 0

    def _intercept_tokens(self) -> None:
        original = self._llm_client.generate

        def _tracking_generate(*args, **kwargs):
            result = original(*args, **kwargs)
            self._cycle_tokens += result.get("tokens_used", 0)
            return result

        self._llm_client.generate = _tracking_generate


def _is_security_failure(result: PhaseResult) -> bool:
    return result.error is not None and result.error.startswith("Security gate:")


def _extract_code(content: str) -> str:
    match = re.search(r"```(?:go)?\n(.*?)```", content, re.DOTALL)
    return match.group(1).strip() if match else content.strip()
