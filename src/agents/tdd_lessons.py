"""
TDD Lessons and Anti-Patterns.

This module captures lessons learned from TDD cycle failures to prevent
repeating the same mistakes. These lessons are injected into TDD prompts.
"""
import json
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class TDDFailureCategory(str, Enum):
    """Categories of TDD failures for analysis."""

    TEST_DESIGN = "test_design"
    """Test is fundamentally flawed in its approach."""

    MOCKING_ERROR = "mocking_error"
    """Mock is applied at wrong layer or configured incorrectly."""

    IMPLEMENTATION_BUG = "implementation_bug"
    """Implementation code has a bug."""

    REQUIREMENT_MISMATCH = "requirement_mismatch"
    """Test doesn't match the actual requirement."""

    IMPORT_ERROR = "import_error"
    """Missing or incorrect imports."""

    SYNTAX_ERROR = "syntax_error"
    """Code has syntax errors."""

    TYPE_ERROR = "type_error"
    """Type mismatch or incorrect types."""

    MISSING_DEPENDENCY = "missing_dependency"
    """Required dependency not available."""

    ASSERTION_WRONG = "assertion_wrong"
    """Assertion is incorrect or tests wrong thing."""

    TIMING_ISSUE = "timing_issue"
    """Test has race conditions or timing issues."""


@dataclass
class TDDLesson:
    """A lesson learned from a TDD failure."""

    category: TDDFailureCategory
    anti_pattern: str
    correct_pattern: str
    example_bad: str | None = None
    example_good: str | None = None


# Seed lessons from actual failures
KNOWN_TDD_LESSONS: list[TDDLesson] = [
    TDDLesson(
        category=TDDFailureCategory.MOCKING_ERROR,
        anti_pattern="Mocking the public method you're trying to test caching on",
        correct_pattern="Mock the internal fetch method, not the cached wrapper",
        example_bad="""
# WRONG: Mocking get_architecture() defeats caching test
with patch.object(obj, 'get_architecture') as mock:
    obj.get_architecture()
    obj.get_architecture()
    mock.assert_called_once()  # Will fail - mock called twice!
""",
        example_good="""
# RIGHT: Mock the internal fetch, test the cache wrapper
with patch.object(obj, '_fetch_architecture', return_value={}) as mock:
    obj.get_architecture()  # Triggers fetch
    obj.get_architecture()  # Uses cache
    mock.assert_called_once()  # Passes - fetch only called once
""",
    ),
    TDDLesson(
        category=TDDFailureCategory.TEST_DESIGN,
        anti_pattern="Testing implementation details instead of behavior",
        correct_pattern="Test observable behavior and outcomes, not internal calls",
        example_bad="""
# WRONG: Testing that internal method is called
def test_saves_correctly():
    obj.save()
    mock_internal._write_to_disk.assert_called()
""",
        example_good="""
# RIGHT: Test the observable outcome
def test_saves_correctly():
    obj.save()
    assert Path(obj.filepath).exists()
    assert obj.load() == expected_data
""",
    ),
    TDDLesson(
        category=TDDFailureCategory.ASSERTION_WRONG,
        anti_pattern="Using assertEqual when order doesn't matter",
        correct_pattern="Use assertCountEqual or set comparison for unordered collections",
        example_bad="""
# WRONG: Order-dependent assertion
assert result == ['a', 'b', 'c']  # Fails if order is ['b', 'a', 'c']
""",
        example_good="""
# RIGHT: Order-independent assertion
assert set(result) == {'a', 'b', 'c'}
# OR
assert sorted(result) == ['a', 'b', 'c']
""",
    ),
]


def get_lessons_for_prompt() -> str:
    """
    Format known TDD lessons for injection into LLM prompts.

    Returns:
        Formatted string of anti-patterns to avoid
    """
    lines = ["## TDD Anti-Patterns to Avoid\n"]

    for lesson in KNOWN_TDD_LESSONS:
        lines.append(f"### {lesson.category.value}: {lesson.anti_pattern}")
        lines.append(f"**Instead:** {lesson.correct_pattern}\n")

        if lesson.example_bad:
            lines.append("Bad example:")
            lines.append(f"```python{lesson.example_bad}```\n")

        if lesson.example_good:
            lines.append("Good example:")
            lines.append(f"```python{lesson.example_good}```\n")

    return "\n".join(lines)


def categorize_failure(error_output: str, test_code: str) -> TDDFailureCategory:
    """
    Attempt to categorize a TDD failure from error output.

    Args:
        error_output: The pytest/test runner output
        test_code: The test code that failed

    Returns:
        Best-guess failure category
    """
    error_lower = error_output.lower()
    test_lower = test_code.lower()

    # Check for common patterns
    if "importerror" in error_lower or "modulenotfounderror" in error_lower:
        return TDDFailureCategory.IMPORT_ERROR

    if "syntaxerror" in error_lower:
        return TDDFailureCategory.SYNTAX_ERROR

    if "typeerror" in error_lower:
        return TDDFailureCategory.TYPE_ERROR

    if "assert_called_once" in test_lower and "patch" in test_lower:
        # Likely a mocking issue
        return TDDFailureCategory.MOCKING_ERROR

    if "assertionerror" in error_lower:
        return TDDFailureCategory.ASSERTION_WRONG

    # Default to implementation bug
    return TDDFailureCategory.IMPLEMENTATION_BUG


class LessonExtractor:
    """Extracts TDD lessons from resolved beads issues."""

    # Map label keywords to failure categories
    LABEL_TO_CATEGORY = {
        "import": TDDFailureCategory.IMPORT_ERROR,
        "syntax": TDDFailureCategory.SYNTAX_ERROR,
        "type": TDDFailureCategory.TYPE_ERROR,
        "mock": TDDFailureCategory.MOCKING_ERROR,
        "assertion": TDDFailureCategory.ASSERTION_WRONG,
        "test_design": TDDFailureCategory.TEST_DESIGN,
        "requirement": TDDFailureCategory.REQUIREMENT_MISMATCH,
        "dependency": TDDFailureCategory.MISSING_DEPENDENCY,
        "timing": TDDFailureCategory.TIMING_ISSUE,
        "implementation": TDDFailureCategory.IMPLEMENTATION_BUG,
    }

    def __init__(self, beads_path: Path | None = None):
        """
        Initialize the LessonExtractor.

        Args:
            beads_path: Path to the beads issues.jsonl file.
                       Defaults to .beads/issues.jsonl in cwd.
        """
        self.beads_path = beads_path or Path(".beads/issues.jsonl")

    def _category_from_labels(self, labels: list[str]) -> TDDFailureCategory:
        """
        Determine failure category from issue labels.

        Args:
            labels: List of labels from the beads issue

        Returns:
            Best-matching TDDFailureCategory
        """
        labels_lower = [label.lower() for label in labels]

        for label in labels_lower:
            for keyword, category in self.LABEL_TO_CATEGORY.items():
                if keyword in label:
                    return category

        # Default to implementation bug
        return TDDFailureCategory.IMPLEMENTATION_BUG

    def extract_from_issue(self, issue: dict) -> TDDLesson | None:
        """
        Extract a TDD lesson from a resolved beads issue.

        Args:
            issue: A beads issue dict with keys like 'title', 'description',
                  'labels', 'status', 'intervention_steps'

        Returns:
            TDDLesson if extractable, None otherwise
        """
        # Only extract from resolved issues with intervention info
        if issue.get("status") not in ("resolved", "closed"):
            return None

        intervention_steps = issue.get("intervention_steps", [])
        if not intervention_steps:
            return None

        # Extract lesson components
        labels = issue.get("labels", [])
        category = self._category_from_labels(labels)

        title = issue.get("title", "Unknown failure")

        # Anti-pattern is the failure description
        anti_pattern = title.replace("TDD build failed: ", "")

        # Correct pattern is derived from intervention steps
        if isinstance(intervention_steps, list) and intervention_steps:
            correct_pattern = "; ".join(intervention_steps[:3])  # First 3 steps
        else:
            correct_pattern = str(intervention_steps)

        # Extract code examples from description if available
        example_bad = None
        description = issue.get("description", "")

        if "```" in description:
            # Try to extract code blocks
            code_blocks = []
            parts = description.split("```")
            for i, part in enumerate(parts):
                if i % 2 == 1:  # Odd indices are inside code blocks
                    # Remove language identifier if present
                    lines = part.strip().split("\n")
                    if lines and lines[0] in ("python", "py", ""):
                        code_blocks.append("\n".join(lines[1:]))
                    else:
                        code_blocks.append(part.strip())

            if code_blocks:
                example_bad = code_blocks[0]

        return TDDLesson(
            category=category,
            anti_pattern=anti_pattern,
            correct_pattern=correct_pattern,
            example_bad=example_bad,
            example_good=None,
        )

    def extract_all_from_beads(self) -> list[TDDLesson]:
        """
        Extract all lessons from resolved beads issues.

        Returns:
            List of TDDLesson objects extracted from resolved issues
        """
        lessons = []

        if not self.beads_path.exists():
            logger.debug(f"Beads file not found: {self.beads_path}")
            return lessons

        try:
            content = self.beads_path.read_text().strip()
            if not content:
                return lessons

            for line in content.split("\n"):
                if not line.strip():
                    continue

                try:
                    issue = json.loads(line)

                    # Only process TDD-related issues
                    labels = issue.get("labels", [])
                    if "tdd" not in [label.lower() for label in labels]:
                        continue

                    lesson = self.extract_from_issue(issue)
                    if lesson:
                        lessons.append(lesson)

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse beads line: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Failed to read beads file: {e}")

        return lessons


def get_all_lessons_for_prompt(beads_path: Path | None = None) -> str:
    """
    Combined static + dynamic lessons for prompt injection.

    This merges the hardcoded KNOWN_TDD_LESSONS with lessons
    extracted from resolved beads issues.

    Args:
        beads_path: Optional path to beads issues.jsonl

    Returns:
        Formatted string of all lessons for LLM prompts
    """
    # Start with static lessons
    all_lessons = list(KNOWN_TDD_LESSONS)

    # Add dynamic lessons from beads
    extractor = LessonExtractor(beads_path)
    dynamic_lessons = extractor.extract_all_from_beads()
    all_lessons.extend(dynamic_lessons)

    # Format for prompt
    lines = ["## TDD Anti-Patterns to Avoid\n"]

    # Add section header for dynamic lessons if any
    static_count = len(KNOWN_TDD_LESSONS)
    dynamic_count = len(dynamic_lessons)

    if dynamic_count > 0:
        lines.append(f"*({static_count} core lessons + {dynamic_count} learned from past failures)*\n")

    for lesson in all_lessons:
        lines.append(f"### {lesson.category.value}: {lesson.anti_pattern}")
        lines.append(f"**Instead:** {lesson.correct_pattern}\n")

        if lesson.example_bad:
            lines.append("Bad example:")
            lines.append(f"```python{lesson.example_bad}```\n")

        if lesson.example_good:
            lines.append("Good example:")
            lines.append(f"```python{lesson.example_good}```\n")

    return "\n".join(lines)
