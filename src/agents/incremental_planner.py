"""
IncrementalPlanner — determines the next test increment given the current
state of the test suite and implementation.

Extracted from AutonomousTDDAgent so it can be used with TDDCycleRunner
without pulling in the full autonomous agent infrastructure.
"""
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Returned by next_increment() when the LLM judges the requirement satisfied.
# None means a parse error — caller should skip the cycle and try again.
COMPLETE = object()


def _strip_markdown(text: str) -> str:
    return text.strip().strip("*`_").strip()


@dataclass
class TestIncrement:
    """One planned test step in the TDD loop."""

    test_name: str
    description: str
    test_file: Path
    implementation_file: Path
    dependencies: list[str] = field(default_factory=list)
    scenario_context: str | None = None


class IncrementalPlanner:
    """
    Determines the next test increment to write by asking the LLM what
    behaviour is still uncovered, given the current test file and implementation.

    Call next_increment() each cycle to get the next TestIncrement.
    Call record_test_written() after a successful RED phase so the planner
    can track what has already been covered.
    """

    def __init__(
        self,
        llm_client,
        test_dir: Path,
        src_dir: Path,
        *,
        playbook_manager=None,
        playbook_id: str = "default",
        temperature: float = 0.0,
        target_language: str = "python",
    ) -> None:
        self._llm = llm_client
        self._test_dir = test_dir
        self._src_dir = src_dir
        self._playbook_manager = playbook_manager
        self._playbook_id = playbook_id
        self._target_language = target_language
        self._temperature = temperature
        # {test_file_str: [{"name": str, "code": str, "cycle": int}]}
        self._test_functions: dict[str, list[dict]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def next_increment(
        self,
        requirement: str,
        cycle_number: int,
        gherkin_context: str | None = None,
        gherkin_scenarios: list[dict] | None = None,
    ) -> "TestIncrement | object":
        """
        Ask the LLM for the next single test to write.

        Returns COMPLETE when the requirement is satisfied, None on a parse
        error (caller should skip and retry), or a TestIncrement otherwise.
        """
        test_ctx = self._format_test_context()
        impl_ctx = self._format_impl_context()
        summaries = self._get_existing_test_summaries()
        redundancy = self._get_playbook_guidance("test redundancy anti-patterns avoid", top_k=3)
        gherkin_section = self._build_gherkin_section(gherkin_context, gherkin_scenarios)

        prompt = f"""You are following TDD to build: "{requirement}"

**Current state (Cycle {cycle_number}):**
{test_ctx or "No tests written yet."}
{impl_ctx or "No implementation yet."}
{gherkin_section}

{summaries}

**🧠 LEARNED REDUNDANCY PATTERNS:**
{redundancy or "No redundancy patterns learned yet."}

⚠️  **CRITICAL - AVOID REDUNDANT TESTS**: The next test MUST:
1. Test NEW behaviour not already covered by tests or implementation above
2. FAIL with the current implementation (RED phase)
3. NOT duplicate or overlap with existing test assertions

**TDD Principles:**
1. Nothing exists yet → start with simplest possible test
2. Basic creation exists → test the FIRST behaviour it should have
3. Look at what's implemented → what is the NEXT SMALLEST step?
4. Each test discovers ONE new piece of the API
5. Build incrementally — don't jump to complex features

**CRITICAL Decision:**
- If the requirement is SATISFIED (all core functionality working) → output: COMPLETE
- Otherwise → output ONE line:

test_name | description | test_file_path | impl_file_path

**Description field rules (CRITICAL — this is the ONLY context the code writer sees):**
- MUST include the exact function/method signature being tested
- MUST include concrete input values AND the exact expected output
- If from a Gherkin scenario, embed the precise numbers: e.g. "calculate_bill(consumption=40, standing_charge=5.0, baseline_rate=0.15, baseline_limit=100) returns 11.0"
- Do NOT use vague phrases like "basic test" or "check feature" — be a specification

**Example progression (note specific values in description):**
Cycle 1: test_can_be_created | Widget() creates instance without error | tests/test_widget.py | src/widget.py
Cycle 2: test_add_returns_sum | Widget.add(2, 3) returns 5 | tests/test_widget.py | src/widget.py
Cycle 3: test_add_with_negatives | Widget.add(-1, 1) returns 0 | tests/test_widget.py | src/widget.py

What is the next test for cycle {cycle_number}?
Output EITHER "COMPLETE" or ONE pipe-delimited line.
"""

        response = self._llm.generate(prompt, temperature=self._temperature)["content"].strip()

        if "COMPLETE" in response.upper() and "|" not in response:
            logger.info("IncrementalPlanner: requirement satisfied")
            return COMPLETE

        lines = [l.strip() for l in response.split("\n") if "|" in l and not l.startswith("#")]
        if not lines:
            logger.warning("IncrementalPlanner: could not parse increment from: %s", response)
            return None

        parts = [_strip_markdown(p) for p in lines[0].split("|")]
        if len(parts) < 4:
            logger.warning("IncrementalPlanner: invalid format: %s", lines[0])
            return None

        test_name = parts[0]
        description = "|".join(parts[1:-2])
        test_file_str = parts[-2]
        impl_file_str = parts[-1]
        return TestIncrement(
            test_name=test_name,
            description=description,
            test_file=self._test_dir / Path(test_file_str).name,
            implementation_file=self._src_dir / Path(impl_file_str).name,
        )

    def next_increment_for_scenario(
        self,
        requirement: str,
        cycle_number: int,
        scenario,
        gherkin_context: str,
        *,
        test_file: "Path | None" = None,
        impl_file: "Path | None" = None,
    ) -> "TestIncrement | None":
        """
        Plan ONE test for a specific Gherkin scenario.

        Unlike next_increment(), the LLM does not choose which behaviour to
        test next — the caller supplies the scenario. Returns None on a parse
        error (caller should skip this scenario).
        """
        name = scenario.name if hasattr(scenario, "name") else scenario["name"]
        steps = scenario.steps if hasattr(scenario, "steps") else scenario["steps"]
        if steps and isinstance(steps[0], str):
            step_lines = "\n".join(f"  {s}" for s in steps)
        else:
            step_lines = "\n".join(f"  {s['type']}: {s['text']}" for s in steps)

        test_ctx = self._format_test_context()
        impl_ctx = self._format_impl_context()

        path_instructions = (
            f"\nUse these file paths:\n"
            f"  test file: {test_file}\n"
            f"  impl file: {impl_file}\n"
            if test_file and impl_file
            else ""
        )

        framework = "vitest" if self._target_language == "typescript" else "pytest"
        prompt = f"""You are planning TDD tests for: "{requirement}"

Plan ONE failing {framework} test for this SPECIFIC Gherkin scenario:

  Scenario: {name}
{step_lines}

Full feature file for reference:
```gherkin
{gherkin_context}
```

{test_ctx or "No tests written yet."}
{impl_ctx or "No implementation yet."}
{path_instructions}
The test MUST:
1. Use the EXACT input values and expected outputs stated in the scenario above
2. FAIL against the current implementation (RED phase)
3. NOT duplicate any existing test
4. Be API-compatible with existing tests — if existing tests assert a scalar return value,
   this test must also assert a scalar; do NOT introduce a dict/tuple/dataclass return
   type unless an existing test already uses one
5. Assert the FINAL output value (e.g. total bill amount); do NOT assert intermediate
   computation steps unless the scenario explicitly names them as separate return values

⚠️  DO NOT write any test code. Output ONLY one pipe-delimited line — nothing else:
test_name | description with exact values | test_file_path | impl_file_path
"""

        response = self._llm.generate(prompt, temperature=self._temperature)["content"].strip()

        lines = [l.strip() for l in response.split("\n") if "|" in l and not l.startswith("#")]
        if not lines:
            logger.warning("IncrementalPlanner: could not parse scenario increment from: %s", response)
            return None

        parts = [_strip_markdown(p) for p in lines[0].split("|")]
        if len(parts) < 4:
            logger.warning("IncrementalPlanner: invalid scenario increment format: %s", lines[0])
            return None

        test_name = parts[0]
        description = "|".join(parts[1:-2])
        test_file_str = parts[-2]
        impl_file_str = parts[-1]
        return TestIncrement(
            test_name=test_name,
            description=description,
            test_file=test_file or (self._test_dir / Path(test_file_str).name),
            implementation_file=impl_file or (self._src_dir / Path(impl_file_str).name),
        )

    def record_test_written(
        self, test_file: Path, test_name: str, test_code: str, cycle_number: int
    ) -> None:
        """Record a test that was successfully written in the RED phase."""
        key = str(test_file)
        self._test_functions.setdefault(key, []).append(
            {"name": test_name, "code": test_code, "cycle": cycle_number}
        )

    # ------------------------------------------------------------------
    # Context builders
    # ------------------------------------------------------------------

    def _format_test_context(self) -> str:
        files = self._collect_test_files()
        if not files:
            return ""
        parts = ["\n**Existing tests:**"]
        for f in files:
            parts.append(f"\n{f.name}:\n```python\n{f.read_text()}\n```")
        return "\n".join(parts)

    def _format_impl_context(self) -> str:
        files = self._collect_impl_files()
        if not files:
            return ""
        parts = ["\n**Existing implementation:**"]
        for f in files:
            if f.name not in ("__init__.py",):
                parts.append(f"\n{f.name}:\n```python\n{f.read_text()}\n```")
        return "\n".join(parts)

    def _get_existing_test_summaries(self) -> str:
        summaries = []
        if self._test_functions:
            summaries.append("**Tests already written:**")
            for file_key, funcs in self._test_functions.items():
                summaries.append(f"\n{Path(file_key).name}:")
                for fn in funcs:
                    asserts = [l.strip() for l in fn["code"].split("\n") if "assert" in l]
                    if asserts:
                        summaries.append(f"  - {fn['name']}: {' | '.join(asserts[:2])}")
                    else:
                        summaries.append(f"  - {fn['name']}")
        else:
            summaries.append("**Tests already written:** None yet")

        impl_files = self._collect_impl_files()
        if impl_files:
            summaries.append("\n**Implementation already contains:**")
            for f in impl_files:
                if f.name in ("__init__.py",):
                    continue
                content = f.read_text()
                classes = re.findall(r"class\s+(\w+)", content)
                attributes = re.findall(r"self\.(\w+)\s*=", content)
                methods = [m for m in re.findall(r"def\s+(\w+)\s*\(", content) if not m.startswith("_")]
                summaries.append(f"\n{f.name}:")
                if classes:
                    summaries.append(f"  - Classes: {', '.join(set(classes))}")
                if attributes:
                    summaries.append(f"  - Attributes: {', '.join(f'self.{a}' for a in set(attributes))}")
                if methods:
                    summaries.append(f"  - Methods: {', '.join(set(methods))}")
        else:
            summaries.append("\n**Implementation already contains:** Nothing yet")

        return "\n".join(summaries)

    def _get_playbook_guidance(self, query: str, top_k: int = 5) -> str:
        if self._playbook_manager is None:
            return ""
        playbook = self._playbook_manager.get_playbook(self._playbook_id)
        if not playbook:
            return ""
        bullets = []
        for section_bullets in playbook.sections.values():
            bullets.extend(section_bullets)
        if not bullets:
            return ""
        # Simple keyword match — good enough for redundancy hints
        query_words = set(query.lower().split())
        scored = []
        for b in bullets:
            overlap = len(query_words & set(b.content.lower().split()))
            if overlap:
                scored.append((overlap, b.content))
        scored.sort(reverse=True)
        return "\n".join(f"- {c}" for _, c in scored[:top_k])

    def _build_gherkin_section(
        self,
        gherkin_context: str | None,
        gherkin_scenarios,
    ) -> str:
        if not gherkin_context:
            return ""
        if not gherkin_scenarios:
            return f"\n**Acceptance Tests (Gherkin):**\n```gherkin\n{gherkin_context}\n```\n"

        scenario_lines = []
        for i, s in enumerate(gherkin_scenarios, 1):
            # Handle both ScenarioSpec objects and plain dicts
            name = s["name"] if isinstance(s, dict) else s.name
            steps = s["steps"] if isinstance(s, dict) else s.steps
            scenario_lines.append(f"{i}. **{name}**")
            for step in steps:
                # Steps may be plain strings or dicts with type/text keys
                line = f"{step['type']}: {step['text']}" if isinstance(step, dict) else step
                scenario_lines.append(f"   {line}")

        return (
            f"\n**🎯 GHERKIN-DRIVEN ATDD:**\n"
            f"```gherkin\n{gherkin_context}\n```\n\n"
            f"**Parsed Scenarios ({len(gherkin_scenarios)} total):**\n"
            + "\n".join(scenario_lines)
            + "\n\nYour TDD tests should enable these Gherkin scenarios to pass.\n"
        )

    def _collect_test_files(self) -> list[Path]:
        return sorted(self._test_dir.glob("test_*.py"))

    def _collect_impl_files(self) -> list[Path]:
        return sorted(self._src_dir.glob("*.py"))
