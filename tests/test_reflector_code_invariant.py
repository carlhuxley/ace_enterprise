"""Tests for the Reflector's "### Code Invariant" section: an exact Python
expression/pattern (e.g. `math.copysign(1.0, x) < 0`) rather than prose
("check the sign bit"), threaded through ReflectorOutput.code_invariant and
on into Curator's synthesis prompt so the resulting bullet embeds it
verbatim instead of paraphrasing it away.

Motivated by real forensic findings: num_neg_zero's curated bullet promised
"a corrected implementation" without ever containing one, and
conc_first_to_finish's bullets described *that* a fix was needed
("asyncio.wait expects Tasks") without ever stating the second, more
specific fix actually required (`next(iter(done)).result()`, not
`next(done)`).
"""
from datetime import datetime
from unittest.mock import MagicMock

from src.core.curator.module import Curator
from src.core.reflector.module import Reflector
from src.storage.schemas import (
    EnvironmentFeedback,
    GeneratorOutput,
    Playbook,
    PlaybookMetadata,
    ReflectorOutput,
    TaskInput,
)

_ANALYSIS_WITH_INVARIANT = """### Error Identification
is_negative_zero(0.0) incorrectly returned True.

### Root Cause
The implementation compared sign bits without excluding the zero-magnitude case.

### Correct Approach
Check that the value is zero AND has a negative sign, not just the sign bit alone.

### Key Insight
Sign-only checks misfire on -0.0 vs 0.0 without an equality guard.

### Code Invariant
`x == 0.0 and math.copysign(1.0, x) < 0`
"""

_ANALYSIS_WITHOUT_INVARIANT = """### Error Identification
is_negative_zero(0.0) incorrectly returned True.

### Root Cause
The implementation compared sign bits without excluding the zero-magnitude case.

### Correct Approach
Check that the value is zero AND has a negative sign, not just the sign bit alone.

### Key Insight
Sign-only checks misfire on -0.0 vs 0.0 without an equality guard.
"""


def _reflector():
    return Reflector(llm_client=MagicMock(), enable_iterative=False)


class TestParseAnalysisCodeInvariant:
    def test_extracts_code_invariant_when_present(self):
        analysis = _reflector()._parse_analysis(_ANALYSIS_WITH_INVARIANT)
        # Stripped of the wrapping backticks the prompt asked for -- stored
        # as the bare expression, not markdown-decorated text (see
        # test_stored_value_has_no_wrapping_backticks for why this matters).
        assert analysis["code_invariant"] == "x == 0.0 and math.copysign(1.0, x) < 0"

    def test_stored_value_has_no_wrapping_backticks(self):
        """If the parsed value kept its backticks, Curator._build_synthesis_prompt
        wrapping it in backticks again would double them up
        ("``x < 0``" instead of "`x < 0`")."""
        analysis = _reflector()._parse_analysis(_ANALYSIS_WITH_INVARIANT)
        assert not analysis["code_invariant"].startswith("`")
        assert not analysis["code_invariant"].endswith("`")

    def test_code_invariant_is_none_when_absent(self):
        analysis = _reflector()._parse_analysis(_ANALYSIS_WITHOUT_INVARIANT)
        assert analysis["code_invariant"] is None

    def test_strips_double_backtick_fence_with_language_tag(self):
        """Confirmed live against a real SWE-bench traceback (DataDog
        postgres.py): the model didn't use a single backtick pair, it used
        a double-backtick fence with a "python" language tag."""
        response = (
            "### Error Identification\nX\n### Root Cause\nY\n"
            "### Correct Approach\nZ\n### Key Insight\nW\n"
            "### Code Invariant\n``python\nlen(m['metrics'][ref]) >= 2\n``\n"
        )
        analysis = _reflector()._parse_analysis(response)
        assert analysis["code_invariant"] == "len(m['metrics'][ref]) >= 2"

    def test_strips_triple_backtick_fence_with_language_tag(self):
        response = (
            "### Error Identification\nX\n### Root Cause\nY\n"
            "### Correct Approach\nZ\n### Key Insight\nW\n"
            "### Code Invariant\n```python\nx < 0\n```\n"
        )
        analysis = _reflector()._parse_analysis(response)
        assert analysis["code_invariant"] == "x < 0"

    def test_other_fields_still_parse_alongside_invariant(self):
        analysis = _reflector()._parse_analysis(_ANALYSIS_WITH_INVARIANT)
        assert "sign bits" in analysis["root_cause"]
        assert "equality guard" in analysis["key_insight"]


class TestReflectThreadsCodeInvariantIntoOutput:
    def test_reflect_output_carries_code_invariant(self):
        llm = MagicMock()
        llm.generate.return_value = {"content": _ANALYSIS_WITH_INVARIANT, "tokens_used": 20}
        reflector = Reflector(llm_client=llm, enable_iterative=False)

        task = TaskInput(id="t1", query="detect negative zero")
        generator_output = GeneratorOutput(
            trajectory="", solution="def is_negative_zero(x): return x < 0",
            bullets_used=[], bullet_feedback={}, latency_ms=0, tokens_used=10,
        )
        env_feedback = EnvironmentFeedback(result="FAILED", feedback="assert True is False")

        output = reflector.reflect(task, generator_output, env_feedback)

        assert isinstance(output, ReflectorOutput)
        assert output.code_invariant == "x == 0.0 and math.copysign(1.0, x) < 0"

    def test_reflect_output_code_invariant_none_when_model_omits_it(self):
        """Graceful degradation: an older/smaller model that doesn't produce
        the new section must not break anything downstream."""
        llm = MagicMock()
        llm.generate.return_value = {"content": _ANALYSIS_WITHOUT_INVARIANT, "tokens_used": 20}
        reflector = Reflector(llm_client=llm, enable_iterative=False)

        task = TaskInput(id="t1", query="detect negative zero")
        generator_output = GeneratorOutput(
            trajectory="", solution="def is_negative_zero(x): return x < 0",
            bullets_used=[], bullet_feedback={}, latency_ms=0, tokens_used=10,
        )
        env_feedback = EnvironmentFeedback(result="FAILED", feedback="assert True is False")

        output = reflector.reflect(task, generator_output, env_feedback)

        assert output.code_invariant is None


def _playbook():
    now = datetime.utcnow()
    return Playbook(
        playbook_id="pb1", version="0.1.0",
        metadata=PlaybookMetadata(domain="test", base_model="", total_tokens=0, total_bullets=0),
        sections={"strategies_and_hard_rules": [], "code_snippets": [], "troubleshooting": [], "domain_knowledge": []},
        created_at=now, updated_at=now,
    )


class TestCuratorSynthesisPromptSurfacesInvariant:
    def _curator(self):
        return Curator(playbook_manager=MagicMock(), llm_client=MagicMock())

    def test_prompt_includes_invariant_verbatim_in_backticks(self):
        reflector_output = ReflectorOutput(
            error_identification="X", root_cause="Y", correct_approach="Z",
            key_insight="W", code_invariant="x == 0.0 and math.copysign(1.0, x) < 0",
        )
        prompt = self._curator()._build_synthesis_prompt(
            reflector_output=reflector_output, playbook=_playbook(),
            playbook_stats={"sections": {}}, task_context=None,
        )
        assert "`x == 0.0 and math.copysign(1.0, x) < 0`" in prompt
        assert "do not paraphrase it into prose" in prompt

    def test_prompt_omits_invariant_section_when_absent(self):
        # The general instruction to embed a code invariant *when one is
        # provided* is always present -- only the conditional block quoting
        # this specific reflector_output's invariant should be missing.
        reflector_output = ReflectorOutput(
            error_identification="X", root_cause="Y", correct_approach="Z", key_insight="W",
        )
        prompt = self._curator()._build_synthesis_prompt(
            reflector_output=reflector_output, playbook=_playbook(),
            playbook_stats={"sections": {}}, task_context=None,
        )
        assert "embed this exact expression verbatim" not in prompt
