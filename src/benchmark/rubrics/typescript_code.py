"""TypeScriptGenerationRubric — evaluates TypeScript code output.

Dimensions (weights sum to 1.0, matching CodeGenerationRubric's Python
weights so scores stay comparable across an ensemble's candidates):
  syntax       0.30  heuristic (balanced brackets/braces/strings, at least
                      one recognizable TS/JS construct) -- NOT a real
                      compiler check: no `tsc`/`typescript` npm package is
                      available on the host running this rubric (only
                      inside the sandbox image, which the "tests"
                      dimension already uses). A genuine syntax error in
                      code that also has test_content still surfaces as a
                      real compile failure there.
  structure    0.20  function/arrow-function, type annotations, a doc
                      comment, a return statement
  tests        0.30  REAL: pulses {candidate.ts, candidate.test.ts} into
                      the sandboxed TypeScriptRunner/vitest harness (if
                      test_content is provided)
  security     0.20  no dangerous built-ins / dynamic code execution

#7 follow-up to CodeGenerationRubric (issue's own reference: "TS/Go blind
evaluation needs language-appropriate rubrics").
"""
from __future__ import annotations

from src.benchmark.rubrics.base import EvaluationRubric, ScoringDimension

_BRACKET_PAIRS = {"(": ")", "{": "}", "[": "]"}
_CLOSERS = set(_BRACKET_PAIRS.values())

_TS_CONSTRUCTS = ("function", "=>", "const ", "let ", "class ", "interface ", "type ", "export ")
_TYPE_ANNOTATION_HINTS = (": string", ": number", ": boolean", ": void", "interface ", "type ")

_DANGEROUS_PATTERNS = (
    "eval(", "new Function(", "child_process", "process.exit(",
    "require(\"child_process\")", "require('child_process')",
)

# Fixed, throwaway working names -- must match
# src.agents.ensemble_build._CANDIDATE_FILE_NAMES["typescript"] exactly, so
# a candidate's own test_content (whose import statement was written
# against that same stem by TypeScriptWorkerAgent during generation) still
# resolves when re-pulsed here independently.
_IMPL_FILE = "candidate.ts"
_TEST_FILE = "candidate.test.ts"


class TypeScriptGenerationRubric(EvaluationRubric):
    def __init__(self, orchestrator=None) -> None:
        """
        Args:
            orchestrator: Injected PodmanOrchestrator (e.g. wrapping a
                TypeScriptRunner) to run the tests dimension in. When None,
                a fresh sandboxed container is created and torn down per
                score() call -- `output` is unidentified submission
                content and must never execute on the host.
        """
        self._orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "typescript_code_generation"

    @property
    def dimensions(self) -> list[ScoringDimension]:
        return [
            ScoringDimension("syntax",    0.30, "Balanced brackets/strings; a recognizable TS/JS construct"),
            ScoringDimension("structure", 0.20, "Functions, type annotations, doc comments, returns"),
            ScoringDimension("tests",     0.30, "Test suite passes in the sandbox (if provided)"),
            ScoringDimension("security",  0.20, "No dangerous built-ins or dynamic code execution"),
        ]

    def _score_dimension(self, dimension: str, output: str, context: dict) -> float:
        if dimension == "syntax":
            return self._score_syntax(output)
        if dimension == "structure":
            return self._score_structure(output)
        if dimension == "tests":
            return self._score_tests(output, context.get("test_content"))
        if dimension == "security":
            return self._score_security(output)
        return 0.0

    # ------------------------------------------------------------------

    def _score_syntax(self, code: str) -> float:
        if not _brackets_balanced(code):
            return 0.0
        if not any(construct in code for construct in _TS_CONSTRUCTS):
            return 0.0
        return 100.0

    def _score_structure(self, code: str) -> float:
        if not _brackets_balanced(code):
            return 0.0
        score = 0.0
        if "function" in code or "=>" in code:
            score += 25.0
        if "/**" in code or "//" in code:
            score += 25.0
        if any(hint in code for hint in _TYPE_ANNOTATION_HINTS):
            score += 25.0
        if "return" in code:
            score += 25.0
        return score

    def _score_tests(self, code: str, test_content: str | None) -> float:
        if not test_content:
            return 50.0 if self._score_syntax(code) == 100.0 else 0.0

        from src.agents.podman_orchestrator import PodmanOrchestrator, SecurityBreachError

        files = {_IMPL_FILE: code, _TEST_FILE: test_content}

        orchestrator = self._orchestrator
        owns_orchestrator = orchestrator is None
        if owns_orchestrator:
            from src.agents.typescript_runner import TypeScriptRunner

            orchestrator = PodmanOrchestrator(TypeScriptRunner(test_timeout=30))

        try:
            result = orchestrator.pulse(files)
            return 100.0 if result.passed else 0.0
        except SecurityBreachError:
            return 0.0
        except Exception:
            return 0.0
        finally:
            if owns_orchestrator:
                orchestrator.stop()

    def _score_security(self, code: str) -> float:
        # A scoring signal only, not a containment mechanism -- same
        # principle as CodeGenerationRubric._score_security. Real
        # containment is the Podman sandbox in _score_tests
        # (--network none, --cap-drop=all).
        for pattern in _DANGEROUS_PATTERNS:
            if pattern in code:
                return 0.0
        return 100.0


def _brackets_balanced(code: str) -> bool:
    """Cheap structural syntax proxy: every (){}[] closes in the right
    order, and every quote/backtick/template-literal is closed. Not a real
    parser -- see module docstring."""
    stack: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(code):
        ch = code[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"', "`"):
            quote = ch
        elif ch in _BRACKET_PAIRS:
            stack.append(_BRACKET_PAIRS[ch])
        elif ch in _CLOSERS:
            if not stack or stack.pop() != ch:
                return False
        i += 1
    return not stack and quote is None
