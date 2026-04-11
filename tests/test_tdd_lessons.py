"""Tests for TDD lessons and anti-patterns module."""
import json
import tempfile
from pathlib import Path

import pytest

from src.agents.tdd_lessons import (
    KNOWN_TDD_LESSONS,
    LessonExtractor,
    TDDFailureCategory,
    TDDLesson,
    categorize_failure,
    get_all_lessons_for_prompt,
    get_lessons_for_prompt,
)


class TestTDDFailureCategory:
    """Tests for failure categorization."""

    def test_categories_are_strings(self):
        """Categories should be usable as strings."""
        assert TDDFailureCategory.MOCKING_ERROR == "mocking_error"
        assert TDDFailureCategory.TEST_DESIGN == "test_design"

    def test_all_categories_have_values(self):
        """All category enum members should have string values."""
        for category in TDDFailureCategory:
            assert isinstance(category.value, str)
            assert len(category.value) > 0


class TestTDDLesson:
    """Tests for TDDLesson dataclass."""

    def test_lesson_creation(self):
        """Can create a lesson with required fields."""
        lesson = TDDLesson(
            category=TDDFailureCategory.MOCKING_ERROR,
            anti_pattern="Test anti-pattern",
            correct_pattern="Correct approach",
        )
        assert lesson.category == TDDFailureCategory.MOCKING_ERROR
        assert lesson.anti_pattern == "Test anti-pattern"
        assert lesson.example_bad is None

    def test_lesson_with_examples(self):
        """Can create lesson with code examples."""
        lesson = TDDLesson(
            category=TDDFailureCategory.TEST_DESIGN,
            anti_pattern="Bad approach",
            correct_pattern="Good approach",
            example_bad="# bad code",
            example_good="# good code",
        )
        assert lesson.example_bad == "# bad code"
        assert lesson.example_good == "# good code"


class TestKnownLessons:
    """Tests for the seed lessons."""

    def test_known_lessons_exist(self):
        """Should have at least one known lesson."""
        assert len(KNOWN_TDD_LESSONS) >= 1

    def test_mocking_lesson_exists(self):
        """Should have the mocking lesson we learned."""
        mocking_lessons = [
            lesson for lesson in KNOWN_TDD_LESSONS
            if lesson.category == TDDFailureCategory.MOCKING_ERROR
        ]
        assert len(mocking_lessons) >= 1

        # Check it contains the specific lesson about caching
        lesson = mocking_lessons[0]
        assert "cach" in lesson.correct_pattern.lower() or "fetch" in lesson.correct_pattern.lower()


class TestGetLessonsForPrompt:
    """Tests for prompt formatting."""

    def test_returns_string(self):
        """Should return a formatted string."""
        result = get_lessons_for_prompt()
        assert isinstance(result, str)

    def test_includes_header(self):
        """Should include anti-patterns header."""
        result = get_lessons_for_prompt()
        assert "Anti-Patterns" in result

    def test_includes_categories(self):
        """Should include failure categories."""
        result = get_lessons_for_prompt()
        assert "mocking_error" in result or "test_design" in result

    def test_includes_examples(self):
        """Should include code examples."""
        result = get_lessons_for_prompt()
        assert "```python" in result


class TestCategorizeFailure:
    """Tests for automatic failure categorization."""

    def test_import_error_detection(self):
        """Should detect import errors."""
        error = "ImportError: No module named 'nonexistent'"
        category = categorize_failure(error, "import nonexistent")
        assert category == TDDFailureCategory.IMPORT_ERROR

    def test_syntax_error_detection(self):
        """Should detect syntax errors."""
        error = "SyntaxError: invalid syntax"
        category = categorize_failure(error, "def foo(")
        assert category == TDDFailureCategory.SYNTAX_ERROR

    def test_type_error_detection(self):
        """Should detect type errors."""
        error = "TypeError: expected str but got int"
        category = categorize_failure(error, "x = 'hello' + 5")
        assert category == TDDFailureCategory.TYPE_ERROR

    def test_mocking_issue_detection(self):
        """Should detect mocking issues from test code patterns."""
        error = "AssertionError: Expected call not found"
        test_code = """
        with patch.object(obj, 'method') as mock:
            obj.method()
            mock.assert_called_once()
        """
        category = categorize_failure(error, test_code)
        assert category == TDDFailureCategory.MOCKING_ERROR

    def test_assertion_error_detection(self):
        """Should detect assertion failures."""
        error = "AssertionError: 5 != 10"
        test_code = "assert result == expected"
        category = categorize_failure(error, test_code)
        assert category == TDDFailureCategory.ASSERTION_WRONG

    def test_defaults_to_implementation_bug(self):
        """Unknown errors should default to implementation bug."""
        error = "Some random error we don't recognize"
        test_code = "some_function()"
        category = categorize_failure(error, test_code)
        assert category == TDDFailureCategory.IMPLEMENTATION_BUG


class TestLessonExtractor:
    """Tests for LessonExtractor class."""

    def test_extractor_initialization_default_path(self):
        """Extractor should use default beads path."""
        extractor = LessonExtractor()
        assert extractor.beads_path == Path(".beads/issues.jsonl")

    def test_extractor_initialization_custom_path(self):
        """Extractor should accept custom beads path."""
        custom_path = Path("/custom/path/issues.jsonl")
        extractor = LessonExtractor(beads_path=custom_path)
        assert extractor.beads_path == custom_path

    def test_category_from_labels_import(self):
        """Should map import label to IMPORT_ERROR."""
        extractor = LessonExtractor()
        category = extractor._category_from_labels(["tdd", "import_error"])
        assert category == TDDFailureCategory.IMPORT_ERROR

    def test_category_from_labels_mocking(self):
        """Should map mocking label to MOCKING_ERROR."""
        extractor = LessonExtractor()
        category = extractor._category_from_labels(["tdd", "mocking_error"])
        assert category == TDDFailureCategory.MOCKING_ERROR

    def test_category_from_labels_default(self):
        """Should default to IMPLEMENTATION_BUG for unknown labels."""
        extractor = LessonExtractor()
        category = extractor._category_from_labels(["tdd", "unknown"])
        assert category == TDDFailureCategory.IMPLEMENTATION_BUG

    def test_extract_from_issue_returns_none_for_open_status(self):
        """Should return None for non-resolved issues."""
        extractor = LessonExtractor()
        issue = {
            "status": "open",
            "title": "TDD build failed: ImportError",
            "labels": ["tdd", "import"],
        }
        result = extractor.extract_from_issue(issue)
        assert result is None

    def test_extract_from_issue_returns_none_without_intervention_steps(self):
        """Should return None for resolved issues without intervention_steps."""
        extractor = LessonExtractor()
        issue = {
            "status": "resolved",
            "title": "TDD build failed: ImportError",
            "labels": ["tdd", "import"],
        }
        result = extractor.extract_from_issue(issue)
        assert result is None

    def test_extract_from_issue_returns_lesson_for_resolved_with_steps(self):
        """Should return TDDLesson for resolved issues with intervention_steps."""
        extractor = LessonExtractor()
        issue = {
            "status": "resolved",
            "title": "TDD build failed: ImportError in cycle 1",
            "labels": ["tdd", "import"],
            "intervention_steps": ["Added missing import", "Fixed path"],
            "description": "Error details here",
        }
        result = extractor.extract_from_issue(issue)
        assert result is not None
        assert isinstance(result, TDDLesson)
        assert result.category == TDDFailureCategory.IMPORT_ERROR
        assert "ImportError" in result.anti_pattern
        assert "Added missing import" in result.correct_pattern

    def test_extract_from_issue_handles_closed_status(self):
        """Should also work with 'closed' status."""
        extractor = LessonExtractor()
        issue = {
            "status": "closed",
            "title": "TDD build failed: TypeError",
            "labels": ["tdd", "type"],
            "intervention_steps": ["Fixed type mismatch"],
        }
        result = extractor.extract_from_issue(issue)
        assert result is not None
        assert result.category == TDDFailureCategory.TYPE_ERROR

    def test_extract_all_from_beads_with_missing_file(self):
        """Should return empty list when beads file doesn't exist."""
        extractor = LessonExtractor(beads_path=Path("/nonexistent/path.jsonl"))
        lessons = extractor.extract_all_from_beads()
        assert lessons == []

    def test_extract_all_from_beads_with_empty_file(self):
        """Should return empty list for empty beads file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("")
            temp_path = Path(f.name)

        try:
            extractor = LessonExtractor(beads_path=temp_path)
            lessons = extractor.extract_all_from_beads()
            assert lessons == []
        finally:
            temp_path.unlink()

    def test_extract_all_from_beads_filters_non_tdd_issues(self):
        """Should only extract TDD-related issues."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            # TDD issue
            f.write(json.dumps({
                "status": "resolved",
                "title": "TDD build failed: ImportError",
                "labels": ["tdd", "import"],
                "intervention_steps": ["Fixed import"],
            }) + "\n")
            # Non-TDD issue
            f.write(json.dumps({
                "status": "resolved",
                "title": "Bug: something else",
                "labels": ["bug"],
                "intervention_steps": ["Fixed bug"],
            }) + "\n")
            temp_path = Path(f.name)

        try:
            extractor = LessonExtractor(beads_path=temp_path)
            lessons = extractor.extract_all_from_beads()
            assert len(lessons) == 1
            assert lessons[0].category == TDDFailureCategory.IMPORT_ERROR
        finally:
            temp_path.unlink()

    def test_extract_all_from_beads_handles_malformed_json(self):
        """Should skip malformed JSON lines gracefully."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("not valid json\n")
            f.write(json.dumps({
                "status": "resolved",
                "title": "TDD build failed: SyntaxError",
                "labels": ["tdd", "syntax"],
                "intervention_steps": ["Fixed syntax"],
            }) + "\n")
            temp_path = Path(f.name)

        try:
            extractor = LessonExtractor(beads_path=temp_path)
            lessons = extractor.extract_all_from_beads()
            assert len(lessons) == 1
        finally:
            temp_path.unlink()


class TestGetAllLessonsForPrompt:
    """Tests for combined lessons function."""

    def test_returns_string(self):
        """Should return a formatted string."""
        result = get_all_lessons_for_prompt()
        assert isinstance(result, str)

    def test_includes_static_lessons(self):
        """Should include hardcoded lessons."""
        result = get_all_lessons_for_prompt()
        assert "Anti-Patterns" in result
        # Check for content from known lessons
        assert "mocking" in result.lower() or "test_design" in result.lower()

    def test_includes_dynamic_lessons_when_beads_exist(self):
        """Should include lessons from beads when file exists."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write(json.dumps({
                "status": "resolved",
                "title": "TDD build failed: CustomError",
                "labels": ["tdd", "implementation"],
                "intervention_steps": ["Fixed the custom issue"],
            }) + "\n")
            temp_path = Path(f.name)

        try:
            result = get_all_lessons_for_prompt(beads_path=temp_path)
            assert "CustomError" in result
            assert "3 core lessons + 1 learned from past failures" in result
        finally:
            temp_path.unlink()

    def test_handles_missing_beads_gracefully(self):
        """Should work even when beads file doesn't exist."""
        result = get_all_lessons_for_prompt(beads_path=Path("/nonexistent/path.jsonl"))
        assert isinstance(result, str)
        assert "Anti-Patterns" in result
