"""Tests for GherkinExtractionAgent (src/agents/gherkin_extraction_agent.py).

No prior coverage existed for this file. Covers both the pre-existing
deterministic AST-based extraction (unaffected by these changes) and the
new LLM refinement pass wired into extract_from_codebase().
"""
from pathlib import Path
from unittest.mock import MagicMock

from src.agents.gherkin_extraction_agent import GherkinExtractionAgent


def _write_code_and_test(tmp_path: Path) -> tuple[Path, Path]:
    code = tmp_path / "calculator.py"
    code.write_text(
        "class Calculator:\n"
        "    \"\"\"Performs arithmetic.\"\"\"\n\n"
        "    def add(self, a, b):\n"
        "        return a + b\n"
    )
    test = tmp_path / "test_calculator.py"
    test.write_text(
        "def test_add_returns_sum():\n"
        "    calc = Calculator()\n"
        "    result = calc.add(2, 3)\n"
        "    assert result == 5\n"
    )
    return code, test


class TestDeterministicExtraction:
    """Unaffected by the refinement wiring -- no llm_client configured."""

    def test_extract_without_llm_client_produces_no_refined_gherkin(self, tmp_path):
        code, test = _write_code_and_test(tmp_path)
        agent = GherkinExtractionAgent()  # llm_client=None
        result = agent.extract_from_codebase(code, test)

        assert result.refined_gherkin is None
        assert result.feature.name  # deterministic extraction still works
        assert len(result.feature.scenarios) == 1

    def test_write_gherkin_file_renders_deterministic_feature(self, tmp_path):
        code, test = _write_code_and_test(tmp_path)
        agent = GherkinExtractionAgent()
        result = agent.extract_from_codebase(code, test)

        out = tmp_path / "calculator.feature"
        agent.write_gherkin_file(result.feature, out)

        content = out.read_text()
        assert content.startswith(f"Feature: {result.feature.name}")
        assert "Scenario:" in content


class TestLLMRefinement:
    def _fake_llm(self, content: str) -> MagicMock:
        client = MagicMock()
        client.generate.return_value = {"content": content}
        return client

    def test_refinement_called_when_llm_client_configured(self, tmp_path):
        code, test = _write_code_and_test(tmp_path)
        llm = self._fake_llm("Feature: Calculator\n\n  Scenario: adds two numbers\n    Given ...\n")
        agent = GherkinExtractionAgent(llm_client=llm)

        result = agent.extract_from_codebase(code, test)

        assert llm.generate.call_count == 1
        assert result.refined_gherkin is not None
        assert result.refined_gherkin.startswith("Feature:")

    def test_refinement_prompt_contains_deterministic_draft(self, tmp_path):
        """The prompt must be built from the AST-derived draft, not raw code
        -- confirms the refinement pass never sees source text directly."""
        code, test = _write_code_and_test(tmp_path)
        llm = self._fake_llm("Feature: Calculator\n\n  Scenario: x\n    Given y\n")
        agent = GherkinExtractionAgent(llm_client=llm)

        agent.extract_from_codebase(code, test)

        prompt = llm.generate.call_args.args[0]
        assert "class Calculator" not in prompt  # raw source never appears
        assert "def add" not in prompt
        assert "Feature:" in prompt  # the deterministic draft is embedded

    def test_step_definitions_use_deterministic_steps_not_refined_text(self, tmp_path):
        """Step defs must stay keyed to the exact deterministic step text
        even when refinement rewrites the .feature file's prose -- otherwise
        @given/@when/@then patterns silently stop matching the spec."""
        code, test = _write_code_and_test(tmp_path)
        llm = self._fake_llm(
            "Feature: Calculator (refined)\n\n"
            "  Scenario: A completely reworded scenario\n"
            "    Given something else entirely\n"
        )
        agent = GherkinExtractionAgent(llm_client=llm)

        result = agent.extract_from_codebase(code, test)

        step_patterns = {sd.pattern for sd in result.step_definitions}
        deterministic_steps = set(
            result.feature.scenarios[0].given_steps
            + result.feature.scenarios[0].when_steps
            + result.feature.scenarios[0].then_steps
        )
        assert step_patterns == deterministic_steps
        assert "something else entirely" not in step_patterns

    def test_refinement_falls_back_to_draft_on_llm_error(self, tmp_path):
        code, test = _write_code_and_test(tmp_path)
        llm = MagicMock()
        llm.generate.side_effect = RuntimeError("LLM unavailable")
        agent = GherkinExtractionAgent(llm_client=llm)

        result = agent.extract_from_codebase(code, test)

        # Refinement failed -- falls back silently, no exception propagates,
        # and refined_gherkin is None so callers use the deterministic feature.
        assert result.refined_gherkin is None
        assert result.feature.name

    def test_refinement_falls_back_when_response_has_no_feature_header(self, tmp_path):
        code, test = _write_code_and_test(tmp_path)
        llm = self._fake_llm("I'm not sure how to refine this.")
        agent = GherkinExtractionAgent(llm_client=llm)

        result = agent.extract_from_codebase(code, test)

        assert result.refined_gherkin is None

    def test_write_gherkin_file_can_write_refined_text(self, tmp_path):
        code, test = _write_code_and_test(tmp_path)
        llm = self._fake_llm("Feature: Calculator, refined\n\n  Scenario: polished\n    Given a thing\n")
        agent = GherkinExtractionAgent(llm_client=llm)
        result = agent.extract_from_codebase(code, test)

        out = tmp_path / "calculator.feature"
        agent.write_gherkin_file(result.feature, out, result.refined_gherkin)

        assert out.read_text() == result.refined_gherkin + "\n"

    def test_refinement_never_invoked_when_llm_client_is_none(self, tmp_path):
        code, test = _write_code_and_test(tmp_path)
        agent = GherkinExtractionAgent()
        # No llm_client at all -- _refine_with_llm must never be reached.
        result = agent.extract_from_codebase(code, test)
        assert result.refined_gherkin is None
