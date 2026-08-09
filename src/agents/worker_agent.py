"""
WorkerAgent — standalone LLM code-generation component.

Separates the prompt-building + LLM-calling concern from the TDD loop
orchestration. Receives feature context and optional constraints (playbook
bullets, AST context map) explicitly; returns code strings. File I/O and
test execution are the caller's (pod's) responsibility.
"""
from __future__ import annotations

import re

from src.agents.language_pod import PodSpec

_PLAYBOOK_SECTION = "strategies_and_hard_rules"
_TEST_RULES_SECTION = "test_assertion_rules"

_DEFAULT_TEST_RULES = [
    (
        "Assert PROPERTIES not exact value when multiple correct outputs exist "
        "(e.g. shortest paths, orderings, set members): use len(), structural validity loops, "
        "membership checks like result[0]==start and result[-1]==end"
    ),
    (
        "Use == equality on the full result only when there is provably ONE correct answer "
        "(arithmetic, deterministic transformations, unique key lookup)"
    ),
    (
        "Never assert a specific path or ordering when the algorithm may produce "
        "any valid path of equal quality"
    ),
]


class WorkerAgent:
    """
    Generates code for each TDD phase given a PodSpec and optional context.

    Call generate_test for RED, generate_implementation for GREEN,
    and generate_refactor for REFACTOR. All methods return raw code strings.
    """

    def __init__(self, llm_client, playbook_manager=None, context_map=None, temperature: float = 0.0) -> None:
        self.llm_client = llm_client
        self._playbook_manager = playbook_manager
        self._context_map = context_map
        self._temperature = temperature

    def generate_test(self, spec: PodSpec, existing_code: str = "") -> str:
        prompt = self._test_prompt(spec, existing_code)
        response = self.llm_client.generate(prompt, temperature=self._temperature)
        return _extract_code(response.get("content", ""))

    def generate_implementation(
        self,
        spec: PodSpec,
        error_output: str = "",
        module_context: str = "",
        failing_test_ids: list[str] | None = None,
        test_code: str = "",
    ) -> str:
        if not module_context and self._context_map and failing_test_ids:
            module_context = self._context_from_map(failing_test_ids)
        bullets = self._get_bullets()
        prompt = self._impl_prompt(spec, error_output, module_context, bullets, test_code)
        response = self.llm_client.generate(prompt, temperature=self._temperature)
        return _extract_code(response.get("content", ""))

    def generate_refactor(self, spec: PodSpec, current_code: str = "") -> str:
        prompt = self._refactor_prompt(spec, current_code)
        response = self.llm_client.generate(prompt, temperature=self._temperature)
        return _extract_code(response.get("content", ""))

    # --- prompt builders ---

    def _test_prompt(self, spec: PodSpec, existing_code: str) -> str:
        parts = [
            f"Add ONE new failing pytest test for: {spec.feature_requirement}",
            f"Test file: {spec.test_file.name}",
            "The new test must FAIL before any implementation exists (RED phase).",
            "Do NOT duplicate or overlap with any existing test.",
        ]
        if spec.gherkin_context:
            parts.append(
                f"\nAcceptance criteria (Gherkin — use exact values from relevant scenarios):\n"
                f"```gherkin\n{spec.gherkin_context}\n```"
            )
        rules = self._get_test_bullets()
        if rules:
            parts.append("\nAssertion contract rules:\n" + "\n".join(f"- {r}" for r in rules))
        if existing_code:
            parts.append(
                f"\nExisting tests (KEEP ALL of these unchanged):\n{existing_code}"
                "\n\nOutput the COMPLETE test file: all existing tests preserved, "
                "plus exactly ONE new failing test function appended at the end."
            )
        else:
            parts.append("Output only valid Python code.")
        return "\n".join(parts)

    def _impl_prompt(
        self,
        spec: PodSpec,
        error_output: str,
        module_context: str,
        bullets: list[str],
        test_code: str = "",
    ) -> str:
        parts = [
            "Write minimal implementation to make the failing tests pass.",
            f"Feature: {spec.feature_requirement}",
            f"Implementation file: {spec.implementation_file.name}",
        ]
        if test_code:
            parts.append(f"\nTest file to satisfy:\n```python\n{test_code}\n```")
        if error_output:
            parts.append(f"\nTest failure output:\n{error_output}")
        if module_context:
            parts.append(f"\nModule context (AST signatures):\n{module_context}")
        if bullets:
            parts.append("\nPlaybook guidance:\n" + "\n".join(f"- {b}" for b in bullets))
        parts.append("Output only valid Python code.")
        return "\n".join(parts)

    def _refactor_prompt(self, spec: PodSpec, current_code: str) -> str:
        parts = [
            "Refactor the implementation while keeping tests green.",
            f"Feature: {spec.feature_requirement}",
            f"Implementation file: {spec.implementation_file.name}",
        ]
        if current_code:
            parts.append(f"\nCurrent code:\n{current_code}")
        parts.append("Output only the refactored Python code.")
        return "\n".join(parts)

    # --- context helpers ---

    def _get_bullets(self) -> list[str]:
        if not self._playbook_manager:
            return []
        try:
            return self._playbook_manager.get_bullets(_PLAYBOOK_SECTION) or []
        except Exception:
            return []

    def _get_test_bullets(self) -> list[str]:
        if not self._playbook_manager:
            return _DEFAULT_TEST_RULES
        try:
            bullets = self._playbook_manager.get_bullets(_TEST_RULES_SECTION) or []
            return bullets if bullets else _DEFAULT_TEST_RULES
        except Exception:
            return _DEFAULT_TEST_RULES

    def _context_from_map(self, failing_test_ids: list[str]) -> str:
        try:
            nodes = self._context_map.nodes_relevant_to(failing_test_ids)
            return "\n".join(n.format_compact() for n in nodes)
        except Exception:
            return ""


def _extract_code(content: str) -> str:
    match = re.search(r"```python\n(.*?)```", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\w*\n(.*?)```", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Unclosed fence (model truncated before closing ```)
    match = re.search(r"```(?:\w+)?\n(.*?)$", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return content.strip()

