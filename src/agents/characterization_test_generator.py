"""
CharacterizationTestGenerator — writes empirically-verified pytest tests
describing what existing, untested legacy code actually does at runtime,
not what it should do.

Why this exists: GherkinExtractionAgent.extract_from_codebase() requires a
real test file — its TestAnalyzer derives every Gherkin scenario exclusively
from test functions (see gherkin_extraction_agent.py's _generate_feature();
there is no code path that derives scenarios from method signatures or
docstrings alone). Legacy code that needs migrating disproportionately has
no tests, so `ace migrate` can't get off the ground without first
manufacturing a baseline.

This is a characterization pass, not a specification pass (Michael Feathers'
sense of the term): every assertion is written from what the code actually
evaluates to right now, bugs and silent quirks included, never from what it
"should" do. That is the correct tradeoff for migration (preserve behavior
exactly while porting it) and a dangerous one if the result is later mistaken
for a correctness spec — so every artifact this agent produces is banner- and
tag-marked as auto-characterized (see _AUTO_HEADER / _AUTO_MARKER) rather than
presented as equivalent to a human-written test.

Verification, not trust: a drafted test is never accepted on the LLM's say-so.
Every draft and every retry is executed for real against the real source
inside the same Podman sandbox every other pod uses (ContainerRunner.send_pulse
— no new sandbox plumbing), so what ships is empirically true of the code,
not merely plausible.

Per-test retry, not per-file retry: the draft is many small, independently
retryable test functions rather than one monolithic test, so one stubborn
assertion doesn't sink everything else the draft got right. A test that
still fails after _MAX_RETRIES_PER_TEST rewrites is pruned individually —
but only when doing so still leaves at least `min_core_passed` other tests
genuinely green; otherwise the whole suite hard-aborts (CharacterizationError)
rather than silently handing GherkinExtractionAgent a baseline too thin to
mean anything.
"""
from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

_MAX_RETRIES_PER_TEST = 3
_DEFAULT_MIN_CORE_PASSED = 1

_AUTO_HEADER = (
    "# AUTO-CHARACTERIZED: Empirical runtime baseline\n"
    "#\n"
    "# Every assertion below was verified against the real code's actual\n"
    "# runtime output, not against what the code is supposed to do. Bugs,\n"
    "# silent type coercions, and other quirks are captured as-is. Treat\n"
    "# this as a behavioral freeze for safe migration, not a correctness\n"
    "# spec -- do not \"fix\" an assertion here without confirming the\n"
    "# change is intentional, since Gherkin scenarios extracted from this\n"
    "# file will carry the @auto-characterized tag through to the target\n"
    "# language build.\n"
)
_TEST_NAME_RE = re.compile(r"^\s*def\s+(test_\w+)\s*\(", re.MULTILINE)
_PYTEST_STATUS_RE = re.compile(r"::(test_\w+)\s+(PASSED|FAILED|ERROR)\b")

_DRAFT_SYSTEM_PROMPT = (
    "You write pytest characterization tests. A characterization test "
    "records what code currently does, not what it should do. You are "
    "not a code reviewer and not fixing anything."
)

_DRAFT_PROMPT = """\
Below is a Python module with no test coverage. Write a pytest test file \
that characterizes its CURRENT runtime behavior.

STRICT RULES:
- Do not fix bugs or invent intended behavior.
- Assert strictly what the given code evaluates to at runtime. If the code \
accepts True as 1.0, or silently drops bad types, or has an off-by-one, \
assert that exact outcome -- do not assert what you think the "correct" \
outcome should be.
- If you are unsure what a call actually returns, write a minimal \
assertion you are certain is true from reading the code, rather than a \
detailed one you are guessing at.
- Write 4-10 small, independent test functions, each named `test_<behavior>` \
and each testing exactly one behavior in isolation. Independent means: no \
test may depend on another test's side effects.
- Import the module under test as `import {module_stem}` (it will be in the \
same directory) and call its real public functions/classes/methods.
- Output ONLY a single python code fence with the complete test file \
(imports included). No prose before or after.

MODULE ({filename}):
```python
{source}
```
"""

_RETRY_PROMPT = """\
The test function `{test_name}` below does not match the real code's \
actual runtime behavior -- it failed when actually executed. Rewrite ONLY \
this one function so it asserts exactly what the real code actually does, \
based on the failure output. Do not change what it tests, only correct the \
expected value/exception to match reality. Do not touch the module under \
test.

STRICT RULES (same as before):
- Assert strictly what the code evaluates to at runtime, not what it should do.
- Output ONLY a single python code fence containing the corrected function \
definition (just that one `def {test_name}(...):` block). No prose.

MODULE ({filename}):
```python
{source}
```

CURRENT (FAILING) TEST FUNCTION:
```python
{failing_function_source}
```

PYTEST OUTPUT (full run, look for `{test_name}` specifically):
```
{pytest_output}
```
"""


class LLMClient(Protocol):
    def generate(self, prompt: str, system_prompt: str | None = None, temperature: float = 0.0) -> dict: ...


class ContainerRunner(Protocol):
    def start(self) -> None: ...
    def send_pulse(self, files: dict[str, str]) -> object: ...
    def stop(self) -> None: ...


class CharacterizationError(Exception):
    """Raised when the suite can't reach a usable baseline.

    Either every drafted test failed to characterize the real code (never
    went green), or so many individually-stubborn tests had to be pruned
    that fewer than `min_core_passed` remained -- in both cases there isn't
    enough of a verified behavioral baseline to hand to GherkinExtractionAgent,
    so this aborts loudly instead of emitting a thin or empty test file.
    """


@dataclass
class CharacterizationResult:
    test_code: str
    passed_tests: list[str]
    pruned_tests: list[str] = field(default_factory=list)
    retry_counts: dict[str, int] = field(default_factory=dict)


def _strip_fence(text: str) -> str:
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    return (match.group(1) if match else text).strip()


def _function_names(test_code: str) -> list[str]:
    return _TEST_NAME_RE.findall(test_code)


def _function_source(test_code: str, name: str) -> str | None:
    """Extract one top-level `def <name>(...): ...` block's exact source via AST line ranges."""
    try:
        tree = ast.parse(test_code)
    except SyntaxError:
        return None
    lines = test_code.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            end = node.end_lineno or node.lineno
            return "".join(lines[node.lineno - 1:end])
    return None


def _replace_function(test_code: str, name: str, new_source: str) -> str:
    """Splice a rewritten function body back in at the same line range."""
    try:
        tree = ast.parse(test_code)
    except SyntaxError:
        return test_code
    lines = test_code.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            end = node.end_lineno or node.lineno
            new_lines = new_source.rstrip("\n") + "\n"
            return "".join(lines[:node.lineno - 1]) + new_lines + "".join(lines[end:])
    return test_code


def _remove_function(test_code: str, name: str) -> str:
    """Drop one top-level test function entirely (pruning)."""
    try:
        tree = ast.parse(test_code)
    except SyntaxError:
        return test_code
    lines = test_code.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            end = node.end_lineno or node.lineno
            return "".join(lines[:node.lineno - 1]) + "".join(lines[end:])
    return test_code


def _parse_pytest_statuses(stdout: str) -> dict[str, str]:
    """{test_name: 'PASSED'|'FAILED'|'ERROR'} from pytest -v output lines."""
    return dict(_PYTEST_STATUS_RE.findall(stdout))


class CharacterizationTestGenerator:
    """Drafts, verifies, and repairs a pytest characterization suite for
    untested legacy code, using per-test-function retry with pruning.

    `runner` is any ContainerRunner (PodmanRunner and friends) -- the same
    zero-trust sandbox every LanguagePod runs generated code through. This
    class never executes LLM-generated code on the host.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        runner: ContainerRunner,
        audit_client=None,
    ) -> None:
        self.llm_client = llm_client
        self.runner = runner
        self.audit_client = audit_client

    def generate(
        self,
        source_path: Path,
        *,
        min_core_passed: int = _DEFAULT_MIN_CORE_PASSED,
        max_retries_per_test: int = _MAX_RETRIES_PER_TEST,
    ) -> CharacterizationResult:
        module_stem = source_path.stem
        source_code = source_path.read_text(encoding="utf-8")
        module_filename = source_path.name
        test_filename = f"test_{module_stem}_characterized.py"

        draft = self.llm_client.generate(
            _DRAFT_PROMPT.format(module_stem=module_stem, filename=module_filename, source=source_code),
            system_prompt=_DRAFT_SYSTEM_PROMPT,
            temperature=0.0,
        )
        test_code = _strip_fence(draft.get("content", ""))
        test_names = _function_names(test_code)
        if not test_names:
            raise CharacterizationError(
                f"LLM draft for {module_filename} produced no recognizable test_* functions"
            )

        retry_counts = dict.fromkeys(test_names, 0)
        pruned: list[str] = []
        remaining = list(test_names)

        self.runner.start()
        try:
            while remaining:
                result = self.runner.send_pulse({module_filename: source_code, test_filename: test_code})
                statuses = _parse_pytest_statuses(result.stdout)

                failing = [n for n in remaining if statuses.get(n) != "PASSED"]
                if not failing:
                    break

                progressed = False
                for name in failing:
                    if retry_counts[name] >= max_retries_per_test:
                        currently_passing = len(remaining) - len(failing)
                        if currently_passing < min_core_passed:
                            raise CharacterizationError(
                                f"{module_filename}: '{name}' never characterized correctly after "
                                f"{max_retries_per_test} attempts, and only {currently_passing} other "
                                f"test(s) are passing (need >= {min_core_passed}) -- aborting rather than "
                                f"handing GherkinExtractionAgent a baseline too thin to mean anything."
                            )
                        logger.warning(
                            f"{module_filename}: pruning '{name}' after {max_retries_per_test} failed "
                            f"attempts ({currently_passing} other test(s) still passing)"
                        )
                        test_code = _remove_function(test_code, name)
                        remaining.remove(name)
                        pruned.append(name)
                        progressed = True
                        continue

                    failing_src = _function_source(test_code, name) or ""
                    rewrite = self.llm_client.generate(
                        _RETRY_PROMPT.format(
                            test_name=name,
                            filename=module_filename,
                            source=source_code,
                            failing_function_source=failing_src,
                            pytest_output=result.stdout,
                        ),
                        system_prompt=_DRAFT_SYSTEM_PROMPT,
                        temperature=0.0,
                    )
                    new_src = _strip_fence(rewrite.get("content", ""))
                    test_code = _replace_function(test_code, name, new_src)
                    retry_counts[name] += 1
                    progressed = True

                if not progressed:
                    # Safety valve -- should be unreachable given the branches above.
                    raise CharacterizationError(
                        f"{module_filename}: characterization loop made no progress; aborting"
                    )

            if len(remaining) < min_core_passed:
                raise CharacterizationError(
                    f"{module_filename}: only {len(remaining)} characterization test(s) survived "
                    f"(need >= {min_core_passed})"
                )
        finally:
            self.runner.stop()

        tagged_code = _tag_scenarios(test_code, remaining)
        final_code = _AUTO_HEADER + "\n" + tagged_code

        if self.audit_client is not None:
            from src.audit.schemas import AuditEventType
            self.audit_client.emit_simple(
                AuditEventType.CHARACTERIZATION_TEST_GENERATED,
                actor_id="characterization_test_generator",
                payload={
                    "source_file": str(source_path),
                    "passed_tests": remaining,
                    "pruned_tests": pruned,
                    "retry_counts": retry_counts,
                },
            )

        return CharacterizationResult(
            test_code=final_code,
            passed_tests=remaining,
            pruned_tests=pruned,
            retry_counts=retry_counts,
        )


_AUTO_MARKER = "auto_characterized"  # -> "@auto-characterized" via GherkinExtractionAgent._decorator_to_tag


def _tag_scenarios(test_code: str, surviving_tests: list[str]) -> str:
    """Decorate each surviving test function with @pytest.mark.auto_characterized.

    A real decorator, not a comment: GherkinExtractionAgent's TestAnalyzer
    reads a test function's `node.decorator_list` via AST and turns a
    `@pytest.mark.<name>` decorator into a "@<name>" Gherkin tag on the
    scenario it derives from that test (gherkin_extraction_agent.py's
    _decorator_to_tag/TestScenario.tags/GherkinScenario.tags) -- a plain
    comment above the function would never reach that path, since nothing
    in TestAnalyzer inspects comments.
    """
    try:
        tree = ast.parse(test_code)
    except SyntaxError:
        return test_code
    lines = test_code.splitlines(keepends=True)
    insertions: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in surviving_tests:
            indent = " " * node.col_offset
            insertions.append((node.lineno - 1, f"{indent}@pytest.mark.{_AUTO_MARKER}\n"))
    for lineno, decorator_line in sorted(insertions, key=lambda x: x[0], reverse=True):
        lines.insert(lineno, decorator_line)
    tagged = "".join(lines)
    if not re.search(r"^\s*import pytest\s*$", tagged, re.MULTILINE):
        tagged = "import pytest\n" + tagged
    return tagged
