"""
GoLanguagePod — LanguagePod implementation for Go TDD cycles.

Runs go test, gofmt, and go vet via subprocess. Uses LLM to generate
test stubs (RED) and implementation code (GREEN) with optional Go-idiom
playbook bullets. No behavioural changes to the underlying toolchain.
"""
import logging
import re
import subprocess
from pathlib import Path

from src.agents.language_pod import LanguagePod, PhaseResult, PodSpec, TokenUsage

logger = logging.getLogger(__name__)

_GO_BULLETS_SECTION = "global-go-bullets"

_DEFAULT_GO_BULLETS = [
    "use errors.New or fmt.Errorf for sentinel errors, not panic",
    "satisfy interfaces implicitly — define the interface at the call site, not the implementation site",
    "prefer channels and goroutines over shared memory for concurrency",
]


class GoLanguagePod:
    """
    LanguagePod implementation for Go TDD cycles.

    LLM generates Go test stubs (run_red) and implementation code (run_green).
    run_refactor runs gofmt + go vet without LLM involvement.
    Injects global-go-bullets from PlaybookManager into the GREEN prompt when available.
    """

    def __init__(self, llm_client, playbook_manager=None) -> None:
        self._llm_client = llm_client
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
            spec.test_file.parent.mkdir(parents=True, exist_ok=True)
            spec.test_file.write_text(test_code)
        except Exception as exc:
            self._record_usage(spec.cycle_number)
            return PhaseResult(passed=False, output="", error=str(exc))

        result = _run_go_test(spec.test_file.parent)
        self._record_usage(spec.cycle_number)
        return PhaseResult(
            passed=result.returncode == 0,
            output=result.stdout,
            error=result.stderr if result.returncode != 0 else None,
        )

    def run_green(self, spec: PodSpec) -> PhaseResult:
        self._cycle_tokens = 0
        bullets = self._get_go_bullets()
        prompt = self._green_prompt(spec, bullets)
        response = self._llm_client.generate(prompt)
        impl_code = _extract_code(response.get("content", ""))
        spec.implementation_file.parent.mkdir(parents=True, exist_ok=True)
        spec.implementation_file.write_text(impl_code)

        result = _run_go_test(spec.implementation_file.parent)
        self._record_usage(spec.cycle_number)
        return PhaseResult(
            passed=result.returncode == 0,
            output=result.stdout,
            error=result.stderr if result.returncode != 0 else None,
        )

    def run_refactor(self, spec: PodSpec) -> PhaseResult:
        self._cycle_tokens = 0
        if spec.implementation_file.exists():
            subprocess.run(
                ["gofmt", "-w", str(spec.implementation_file)],
                capture_output=True, text=True,
            )
            subprocess.run(
                ["go", "vet", "./..."],
                capture_output=True, text=True,
                cwd=spec.implementation_file.parent,
            )

        result = _run_go_test(spec.implementation_file.parent)
        self._record_usage(spec.cycle_number)
        return PhaseResult(
            passed=result.returncode == 0,
            output=result.stdout,
            error=result.stderr if result.returncode != 0 else None,
        )

    def token_usage(self) -> list[TokenUsage]:
        return list(self._token_log)

    # --- internal helpers ---

    def _red_prompt(self, spec: PodSpec) -> str:
        return (
            f"Write a failing Go test for this feature: {spec.feature_requirement}\n"
            f"Output only valid Go code for {spec.test_file.name}. "
            f"Use the standard 'testing' package. The test must fail in the RED phase. "
            f"Do not include an implementation."
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
            f"Output only valid Go code."
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


def _run_go_test(working_dir: Path):
    return subprocess.run(
        ["go", "test", "./..."],
        capture_output=True, text=True,
        cwd=working_dir,
    )


def _extract_code(content: str) -> str:
    match = re.search(r"```(?:go)?\n(.*?)```", content, re.DOTALL)
    return match.group(1).strip() if match else content.strip()
