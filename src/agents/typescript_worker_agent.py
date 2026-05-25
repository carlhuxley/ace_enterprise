"""
TypeScriptWorkerAgent — code generation for TypeScript TDD cycles.

Mirrors WorkerAgent's interface but uses TypeScript-specific prompts:
- Tests use vitest globals (describe/it/expect) — no import needed for the runner
- Implementations use named exports so test files can import selectively
- Type annotations are required; strict mode is assumed
"""
from __future__ import annotations

import re

from src.agents.language_pod import PodSpec

_DEFAULT_TEST_RULES = [
    (
        "Assert PROPERTIES not exact value when multiple correct outputs exist "
        "(e.g. shortest paths, orderings, set members): use .length, structural checks, "
        "membership checks like result[0]===start and result[result.length-1]===end"
    ),
    (
        "Use toEqual or toBe only when there is provably ONE correct answer "
        "(arithmetic, deterministic transformations, unique key lookup)"
    ),
    (
        "Never assert a specific ordering when the algorithm may produce "
        "any valid result of equal quality"
    ),
]


class TypeScriptWorkerAgent:
    """Generates TypeScript code for each TDD phase given a PodSpec."""

    def __init__(self, llm_client, playbook_manager=None, temperature: float = 0.0) -> None:
        self.llm_client = llm_client
        self._playbook_manager = playbook_manager
        self._temperature = temperature

    def generate_test(self, spec: PodSpec, existing_code: str = "") -> str:
        prompt = self._test_prompt(spec, existing_code)
        response = self.llm_client.generate(prompt, temperature=self._temperature)
        return _extract_code(response.get("content", ""))

    def generate_implementation(
        self,
        spec: PodSpec,
        error_output: str = "",
        test_code: str = "",
    ) -> str:
        prompt = self._impl_prompt(spec, error_output, test_code)
        response = self.llm_client.generate(prompt, temperature=self._temperature)
        return _extract_code(response.get("content", ""))

    def generate_refactor(self, spec: PodSpec, current_code: str = "") -> str:
        prompt = self._refactor_prompt(spec, current_code)
        response = self.llm_client.generate(prompt, temperature=self._temperature)
        return _extract_code(response.get("content", ""))

    # --- prompt builders ---

    def _test_prompt(self, spec: PodSpec, existing_code: str) -> str:
        stem = spec.test_file.stem.replace(".test", "").replace("test_", "")
        parts = [
            f"Add ONE new failing vitest test for: {spec.feature_requirement}",
            f"Test file: {spec.test_file.name}",
            f"Implementation file: {spec.implementation_file.name}",
            "The new test must FAIL before any implementation exists (RED phase).",
            "Do NOT duplicate or overlap with any existing test.",
            "vitest globals (describe, it, test, expect, beforeEach) are available without imports.",
            f"Import the implementation with: import {{ ... }} from './{stem}';",
        ]
        if spec.gherkin_context:
            parts.append(
                f"\nAcceptance criteria (Gherkin — use exact values from relevant scenarios):\n"
                f"```gherkin\n{spec.gherkin_context}\n```"
            )
        rules = self._get_test_rules()
        if rules:
            parts.append("\nAssertion rules:\n" + "\n".join(f"- {r}" for r in rules))
        if existing_code:
            parts.append(
                f"\nExisting tests (KEEP ALL of these unchanged):\n{existing_code}"
                "\n\nOutput the COMPLETE test file: all existing tests preserved, "
                "plus exactly ONE new failing test appended at the end."
            )
        else:
            parts.append("Output only valid TypeScript code.")
        return "\n".join(parts)

    def _impl_prompt(self, spec: PodSpec, error_output: str, test_code: str) -> str:
        parts = [
            "Write minimal TypeScript implementation to make the failing tests pass.",
            f"Implementation file: {spec.implementation_file.name}",
            "Use named exports. Strict TypeScript — all parameters and return types annotated.",
        ]
        if test_code:
            parts.append(f"\nTest file to satisfy:\n```typescript\n{test_code}\n```")
        if error_output:
            parts.append(f"\nTest failure output:\n{error_output}")
        parts.append("Output only valid TypeScript code.")
        return "\n".join(parts)

    def _refactor_prompt(self, spec: PodSpec, current_code: str) -> str:
        parts = [
            "Refactor the TypeScript implementation while keeping tests green.",
            f"Feature: {spec.feature_requirement}",
            f"Implementation file: {spec.implementation_file.name}",
        ]
        if current_code:
            parts.append(f"\nCurrent code:\n{current_code}")
        parts.append("Output only the refactored TypeScript code.")
        return "\n".join(parts)

    def _get_test_rules(self) -> list[str]:
        if not self._playbook_manager:
            return _DEFAULT_TEST_RULES
        try:
            bullets = self._playbook_manager.get_bullets("test_assertion_rules") or []
            return bullets if bullets else _DEFAULT_TEST_RULES
        except Exception:
            return _DEFAULT_TEST_RULES


def _extract_code(content: str) -> str:
    for lang in ("typescript", "ts", ""):
        pattern = rf"```{lang}\n(.*?)```" if lang else r"```\w*\n(.*?)```"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
    # Unclosed fence
    match = re.search(r"```(?:\w+)?\n(.*?)$", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return content.strip()
