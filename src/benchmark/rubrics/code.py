"""CodeGenerationRubric — evaluates Python code output.

Dimensions (weights sum to 1.0):
  syntax       0.30  valid Python syntax
  structure    0.20  functions, docstrings, type hints, return statements
  tests        0.30  test suite passes (if provided in context)
  security     0.20  no dangerous built-ins / shell calls

Bead: ace_enterprise-nf7
"""

from __future__ import annotations

import ast

from src.benchmark.rubrics.base import EvaluationRubric, ScoringDimension

_DANGEROUS_PATTERNS = ("eval(", "exec(", "os.system(", "subprocess.call(", "__import__(")


class CodeGenerationRubric(EvaluationRubric):
    def __init__(self, orchestrator=None) -> None:
        """
        Args:
            orchestrator: Injected PodmanOrchestrator to run the tests
                dimension in (e.g. shared across tests). When None, a fresh
                sandboxed container is created and torn down per score()
                call -- `output` is unidentified submission content and
                must never execute on the host.
        """
        self._orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "code_generation"

    @property
    def dimensions(self) -> list[ScoringDimension]:
        return [
            ScoringDimension("syntax",    0.30, "Valid Python syntax"),
            ScoringDimension("structure", 0.20, "Functions, docstrings, type hints, returns"),
            ScoringDimension("tests",     0.30, "Test suite passes (if provided)"),
            ScoringDimension("security",  0.20, "No dangerous built-ins or shell calls"),
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
        try:
            ast.parse(code)
            return 100.0
        except SyntaxError:
            return 0.0

    def _score_structure(self, code: str) -> float:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return 0.0

        score = 0.0
        funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        if funcs:
            score += 25.0
        for fn in funcs:
            if (fn.body and isinstance(fn.body[0], ast.Expr)
                    and isinstance(fn.body[0].value, ast.Constant)
                    and isinstance(fn.body[0].value.value, str)):
                score += 25.0
                break
        for fn in funcs:
            if fn.returns or any(a.annotation for a in fn.args.args):
                score += 25.0
                break
        if any(isinstance(n, ast.Return) for n in ast.walk(tree)):
            score += 25.0
        return score

    def _score_tests(self, code: str, test_content: str | None) -> float:
        if not test_content:
            # No tests provided — award partial credit for valid code
            return 50.0 if self._score_syntax(code) == 100.0 else 0.0

        from src.agents.podman_orchestrator import PodmanOrchestrator, SecurityBreachError
        from src.agents.podman_runner import PodmanRunner

        full_code = f"{code}\n\n{test_content}"

        orchestrator = self._orchestrator
        owns_orchestrator = orchestrator is None
        if owns_orchestrator:
            orchestrator = PodmanOrchestrator(PodmanRunner(test_timeout=30))

        try:
            result = orchestrator.pulse(full_code)
            return 100.0 if result.passed else 0.0
        except SecurityBreachError:
            return 0.0
        except Exception:
            return 0.0
        finally:
            if owns_orchestrator:
                orchestrator.stop()

    def _score_security(self, code: str) -> float:
        # A scoring signal only, not a containment mechanism -- trivially
        # bypassable (e.g. subprocess.Popen, a stray space in "exec (") and
        # scored independently of _score_tests, which already ran the code
        # by this point. Actual containment is the Podman sandbox in
        # _score_tests (--network none, --cap-drop=all), same principle as
        # podman_runner.py's own bandit scan.
        for pattern in _DANGEROUS_PATTERNS:
            if pattern in code:
                return 0.0
        return 100.0
