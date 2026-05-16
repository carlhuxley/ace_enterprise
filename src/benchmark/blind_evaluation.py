"""BlindEvaluator - scores outputs without knowing which agent produced them.

Key constraint: No agent identity in evaluation path.
submission_id is opaque - evaluator cannot link to agent.
"""

import ast
import statistics
import tempfile
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Submission:
    """A submission to be evaluated.

    Contains only opaque identifiers - no agent identity.
    """

    task_id: str
    submission_id: str  # opaque - cannot be linked to agent by evaluator
    output_type: str  # "code", "tests", "docs", etc.
    output_content: str
    test_content: str | None = None
    submitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class EvaluationResult:
    """Result of blind evaluation.

    Contains only submission_id - no agent identity revealed.
    """

    submission_id: str
    quality_score: int  # 0-100
    tests_passed: bool | None  # None if no tests provided
    details: dict = field(default_factory=dict)
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    rubric_name: str | None = None  # set when a domain rubric was applied


@dataclass
class MultiRunResult:
    """Aggregated result across N evaluations of the same task.

    Captures score variance and pass/fail consistency to flag unreliable models.
    """

    task_id: str
    results: list[EvaluationResult]
    mean_score: float
    std_dev: float
    variance_coefficient: float  # std_dev / mean_score; 0 when mean is 0
    consistency_rate: float      # fraction of runs matching majority pass/fail


class BlindEvaluator:
    """Evaluates submissions without knowing which agent produced them.

    When a domain rubric matches submission.output_type the rubric drives
    scoring.  Otherwise the built-in heuristic (syntax + structure + tests)
    is used as a fallback.

    Scoring (fallback):
    - Syntax validity: 30 points
    - Code structure: 20 points
    - Tests passing: 50 points (or 30 if no tests)
    """

    def evaluate(self, submission: Submission) -> EvaluationResult:
        """Evaluate a submission and return quality score.

        Selects a domain rubric based on submission.output_type when one is
        registered; otherwise falls back to the built-in heuristic.

        Args:
            submission: The submission to evaluate (no agent identity)

        Returns:
            EvaluationResult with quality_score (0-100), tests_passed, details,
            and rubric_name (set when a domain rubric was used).
        """
        from src.benchmark.rubrics import get_rubric

        rubric = get_rubric(submission.output_type)
        if rubric is not None:
            return self._evaluate_with_rubric(submission, rubric)
        return self._evaluate_fallback(submission)

    def _evaluate_with_rubric(self, submission: Submission, rubric) -> EvaluationResult:
        """Score using a domain-specific rubric."""
        context = {}
        if submission.test_content:
            context["test_content"] = submission.test_content

        result = rubric.score(submission.output_content, context)

        # Determine tests_passed from rubric dimension scores if applicable
        tests_passed: bool | None = None
        for ds in result.dimension_scores:
            if ds.dimension == "tests" and submission.test_content:
                tests_passed = ds.score >= 50.0
                break

        return EvaluationResult(
            submission_id=submission.submission_id,
            quality_score=round(result.total_score),
            tests_passed=tests_passed,
            details={
                "syntax_valid": self._check_syntax(submission.output_content),
                "rubric_dimensions": {
                    ds.dimension: {"score": ds.score, "weight": ds.weight}
                    for ds in result.dimension_scores
                },
            },
            rubric_name=rubric.name,
        )

    def _evaluate_fallback(self, submission: Submission) -> EvaluationResult:
        """Built-in heuristic scoring (no rubric available)."""
        details: dict = {}
        score = 0

        # Check syntax validity (30 points)
        syntax_valid = self._check_syntax(submission.output_content)
        details["syntax_valid"] = syntax_valid
        if syntax_valid:
            score += 30

        # Check code structure (20 points)
        if syntax_valid:
            structure_score = self._evaluate_structure(submission.output_content)
            details["structure_score"] = structure_score
            score += structure_score

        # Run tests if provided (50 points)
        if submission.test_content:
            tests_passed, test_details = self._run_tests(
                submission.output_content,
                submission.test_content,
            )
            details["test_details"] = test_details
            if tests_passed:
                score += 50
        else:
            tests_passed = None
            if syntax_valid:
                score += 20

        return EvaluationResult(
            submission_id=submission.submission_id,
            quality_score=min(score, 100),
            tests_passed=tests_passed,
            details=details,
            rubric_name=None,
        )

    def evaluate_multi_run(
        self,
        submissions: list[Submission],
    ) -> MultiRunResult:
        """Evaluate multiple submissions for the same task and report variance.

        Args:
            submissions: Multiple outputs for the same task (same task_id).

        Returns:
            MultiRunResult with per-run scores, variance coefficient, and
            consistency rate so callers can detect unreliable models.

        Raises:
            ValueError: if submissions is empty or task_ids are mixed.
        """
        if not submissions:
            raise ValueError("submissions must not be empty")

        task_ids = {s.task_id for s in submissions}
        if len(task_ids) > 1:
            raise ValueError(f"All submissions must share the same task_id; got {task_ids}")

        task_id = submissions[0].task_id
        results = [self.evaluate(s) for s in submissions]
        scores = [r.quality_score for r in results]

        mean_score = statistics.mean(scores)
        std_dev = statistics.stdev(scores) if len(scores) > 1 else 0.0
        variance_coefficient = std_dev / mean_score if mean_score > 0 else 0.0

        # Consistency: fraction of runs matching majority pass/fail outcome
        pass_count = sum(1 for r in results if r.tests_passed is True)
        fail_count = len(results) - pass_count
        majority_count = max(pass_count, fail_count)
        consistency_rate = majority_count / len(results)

        return MultiRunResult(
            task_id=task_id,
            results=results,
            mean_score=mean_score,
            std_dev=std_dev,
            variance_coefficient=variance_coefficient,
            consistency_rate=consistency_rate,
        )

    def _check_syntax(self, code: str) -> bool:
        """Check if code has valid Python syntax."""
        try:
            ast.parse(code)
            return True
        except SyntaxError:
            return False

    def _evaluate_structure(self, code: str) -> int:
        """Evaluate code structure quality (0-20 points)."""
        score = 0
        try:
            tree = ast.parse(code)

            # Has function definitions (5 points)
            has_functions = any(
                isinstance(node, ast.FunctionDef)
                for node in ast.walk(tree)
            )
            if has_functions:
                score += 5

            # Has docstrings (5 points)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if (node.body and isinstance(node.body[0], ast.Expr)
                            and isinstance(node.body[0].value, ast.Constant)
                            and isinstance(node.body[0].value.value, str)):
                        score += 5
                        break

            # Has type hints (5 points)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if node.returns or any(arg.annotation for arg in node.args.args):
                        score += 5
                        break

            # Has return statements (5 points)
            has_returns = any(
                isinstance(node, ast.Return)
                for node in ast.walk(tree)
            )
            if has_returns:
                score += 5

        except Exception:
            pass

        return score

    def _run_tests(
        self,
        code: str,
        test_code: str
    ) -> tuple[bool, dict]:
        """Run tests against code in isolated environment.

        Returns:
            (tests_passed, details_dict)
        """
        # Combine code and tests
        full_code = f"{code}\n\n{test_code}"

        # Write to temp file and run with pytest
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False
        ) as f:
            f.write(full_code)
            temp_path = f.name

        try:
            import sys
            result = subprocess.run(
                [sys.executable, "-m", "pytest", temp_path, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=30
            )

            passed = result.returncode == 0
            details = {
                "returncode": result.returncode,
                "stdout": result.stdout[:500] if result.stdout else "",
                "stderr": result.stderr[:500] if result.stderr else ""
            }

            return passed, details

        except subprocess.TimeoutExpired:
            return False, {"error": "timeout"}
        except Exception as e:
            return False, {"error": str(e)}
