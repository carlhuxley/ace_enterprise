"""Tests for BlindEvaluator - scores outputs without knowing source."""
import pytest


class TestSubmission:
    """Tests for Submission dataclass."""

    def test_submission_has_no_agent_identity(self):
        """Submission should only have opaque submission_id, no agent info."""
        from src.benchmark.blind_evaluation import Submission

        sub = Submission(
            task_id="task-001",
            submission_id="sub-abc123",
            output_type="code",
            output_content="def add(a, b): return a + b"
        )

        # Should NOT have agent_id or any identity field
        assert not hasattr(sub, "agent_id")
        assert not hasattr(sub, "agent_ref")
        assert hasattr(sub, "submission_id")


class TestEvaluationResult:
    """Tests for EvaluationResult dataclass."""

    def test_evaluation_result_has_quality_score(self):
        """Result should have quality_score 0-100."""
        from src.benchmark.blind_evaluation import EvaluationResult

        result = EvaluationResult(
            submission_id="sub-001",
            quality_score=85,
            tests_passed=True,
            details={"lint_errors": 0}
        )

        assert result.quality_score == 85
        assert 0 <= result.quality_score <= 100

    def test_evaluation_result_has_no_agent_identity(self):
        """Result should not reveal agent identity."""
        from src.benchmark.blind_evaluation import EvaluationResult

        result = EvaluationResult(
            submission_id="sub-001",
            quality_score=85,
            tests_passed=True,
            details={}
        )

        assert not hasattr(result, "agent_id")
        assert not hasattr(result, "agent_ref")


class TestBlindEvaluator:
    """Tests for BlindEvaluator."""

    def test_evaluate_returns_result(self):
        """Should return EvaluationResult for submission."""
        from src.benchmark.blind_evaluation import BlindEvaluator, Submission

        evaluator = BlindEvaluator()
        submission = Submission(
            task_id="task-001",
            submission_id="sub-001",
            output_type="code",
            output_content="def add(a, b): return a + b"
        )

        result = evaluator.evaluate(submission)

        assert result.submission_id == "sub-001"
        assert isinstance(result.quality_score, int)
        assert 0 <= result.quality_score <= 100

    def test_evaluate_with_test_file(self):
        """Should run tests and report pass/fail."""
        from src.benchmark.blind_evaluation import BlindEvaluator, Submission

        evaluator = BlindEvaluator()
        submission = Submission(
            task_id="task-001",
            submission_id="sub-001",
            output_type="code",
            output_content="def add(a, b): return a + b",
            test_content="def test_add(): assert add(1, 2) == 3"
        )

        result = evaluator.evaluate(submission)

        assert isinstance(result.tests_passed, bool)

    def test_evaluate_captures_details(self):
        """Should capture evaluation details."""
        from src.benchmark.blind_evaluation import BlindEvaluator, Submission

        evaluator = BlindEvaluator()
        submission = Submission(
            task_id="task-001",
            submission_id="sub-001",
            output_type="code",
            output_content="def add(a, b): return a + b"
        )

        result = evaluator.evaluate(submission)

        assert isinstance(result.details, dict)


class TestCodeQualityEvaluation:
    """Tests for code quality scoring."""

    def test_scores_syntax_errors_low(self):
        """Code with syntax errors should score low."""
        from src.benchmark.blind_evaluation import BlindEvaluator, Submission

        evaluator = BlindEvaluator()
        submission = Submission(
            task_id="task-001",
            submission_id="sub-001",
            output_type="code",
            output_content="def broken(: return"  # syntax error
        )

        result = evaluator.evaluate(submission)

        assert result.quality_score < 50
        assert result.details.get("syntax_valid") is False

    def test_scores_valid_code_higher(self):
        """Valid code should score higher than broken code."""
        from src.benchmark.blind_evaluation import BlindEvaluator, Submission

        evaluator = BlindEvaluator()

        broken = Submission(
            task_id="task-001",
            submission_id="sub-001",
            output_type="code",
            output_content="def broken(: return"
        )

        valid = Submission(
            task_id="task-001",
            submission_id="sub-002",
            output_type="code",
            output_content="def valid(a, b): return a + b"
        )

        broken_result = evaluator.evaluate(broken)
        valid_result = evaluator.evaluate(valid)

        assert valid_result.quality_score > broken_result.quality_score


class TestTestExecution:
    """Tests for test execution."""

    def test_passing_tests_sets_tests_passed_true(self):
        """Passing tests should set tests_passed=True."""
        from src.benchmark.blind_evaluation import BlindEvaluator, Submission

        evaluator = BlindEvaluator()
        submission = Submission(
            task_id="task-001",
            submission_id="sub-001",
            output_type="code",
            output_content="def add(a, b): return a + b",
            test_content="def test_add(): assert add(1, 2) == 3"
        )

        result = evaluator.evaluate(submission)

        assert result.tests_passed is True

    def test_failing_tests_sets_tests_passed_false(self):
        """Failing tests should set tests_passed=False."""
        from src.benchmark.blind_evaluation import BlindEvaluator, Submission

        evaluator = BlindEvaluator()
        submission = Submission(
            task_id="task-001",
            submission_id="sub-001",
            output_type="code",
            output_content="def add(a, b): return a - b",  # wrong implementation
            test_content="def test_add(): assert add(1, 2) == 3"
        )

        result = evaluator.evaluate(submission)

        assert result.tests_passed is False

    def test_no_tests_sets_tests_passed_none(self):
        """No tests provided should set tests_passed=None."""
        from src.benchmark.blind_evaluation import BlindEvaluator, Submission

        evaluator = BlindEvaluator()
        submission = Submission(
            task_id="task-001",
            submission_id="sub-001",
            output_type="code",
            output_content="def add(a, b): return a + b"
            # no test_content
        )

        result = evaluator.evaluate(submission)

        assert result.tests_passed is None
