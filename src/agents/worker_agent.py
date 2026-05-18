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
    ) -> str:
        if not module_context and self._context_map and failing_test_ids:
            module_context = self._context_from_map(failing_test_ids)
        bullets = self._get_bullets()
        prompt = self._impl_prompt(spec, error_output, module_context, bullets)
        response = self.llm_client.generate(prompt, temperature=self._temperature)
        return _extract_code(response.get("content", ""))

    def generate_refactor(self, spec: PodSpec, current_code: str = "") -> str:
        prompt = self._refactor_prompt(spec, current_code)
        response = self.llm_client.generate(prompt, temperature=self._temperature)
        return _extract_code(response.get("content", ""))

    # --- prompt builders ---

    def _test_prompt(self, spec: PodSpec, existing_code: str) -> str:
        parts = [
            f"Write a failing test for this feature: {spec.feature_requirement}",
            f"Test file: {spec.test_file.name}",
            "The test must fail before the implementation exists (RED phase).",
        ]
        if existing_code:
            parts.append(f"\nExisting tests:\n{existing_code}")
        parts.append("Output only valid Python code.")
        return "\n".join(parts)

    def _impl_prompt(
        self,
        spec: PodSpec,
        error_output: str,
        module_context: str,
        bullets: list[str],
    ) -> str:
        parts = [
            "Write minimal implementation to make the tests pass.",
            f"Feature: {spec.feature_requirement}",
            f"Implementation file: {spec.implementation_file.name}",
        ]
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

    def _context_from_map(self, failing_test_ids: list[str]) -> str:
        try:
            nodes = self._context_map.nodes_relevant_to(failing_test_ids)
            return "\n".join(n.format_compact() for n in nodes)
        except Exception:
            return ""


def _extract_code(content: str) -> str:
    match = re.search(r"```(?:python)?\n(.*?)```", content, re.DOTALL)
    return match.group(1).strip() if match else content.strip()
