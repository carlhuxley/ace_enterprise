"""
Test Review Agent - Validates test quality before implementation

This agent reviews human-written tests and provides feedback on:
- Test structure (Arrange-Act-Assert)
- Edge case coverage
- Test naming clarity
- Isolation and independence
- Assertion quality

Helps ensure tests are high-quality before ACE learns from them.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.utils.llm_client import LLMClient


@dataclass
class TestQualityIssue:
    """An issue found in test quality."""

    severity: str  # "critical", "warning", "suggestion"
    category: str  # "structure", "coverage", "naming", "isolation", "assertions"
    message: str
    test_name: str | None = None
    line_number: int | None = None
    suggestion: str | None = None


@dataclass
class TestReviewResult:
    """Result of reviewing a test file."""

    test_file: str
    overall_score: float  # 0.0-1.0
    issues: list[TestQualityIssue] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    test_count: int = 0
    edge_cases_covered: list[str] = field(default_factory=list)
    edge_cases_missing: list[str] = field(default_factory=list)

    def is_good_quality(self, threshold: float = 0.7) -> bool:
        """Check if test quality meets threshold."""
        return self.overall_score >= threshold

    def has_critical_issues(self) -> bool:
        """Check if there are any critical issues."""
        return any(issue.severity == "critical" for issue in self.issues)

    def format_report(self) -> str:
        """Format review as human-readable report."""
        lines = []
        lines.append("=" * 80)
        lines.append(f"TEST REVIEW: {self.test_file}")
        lines.append("=" * 80)
        lines.append(f"\n📊 Overall Score: {self.overall_score:.1%}")
        lines.append(f"📝 Tests Found: {self.test_count}")

        if self.strengths:
            lines.append("\n✅ Strengths:")
            for strength in self.strengths:
                lines.append(f"   - {strength}")

        if self.issues:
            lines.append(f"\n⚠️  Issues Found ({len(self.issues)}):")

            # Group by severity
            critical = [i for i in self.issues if i.severity == "critical"]
            warnings = [i for i in self.issues if i.severity == "warning"]
            suggestions = [i for i in self.issues if i.severity == "suggestion"]

            if critical:
                lines.append("\n   🔴 CRITICAL:")
                for issue in critical:
                    lines.append(f"      - {issue.message}")
                    if issue.suggestion:
                        lines.append(f"        Suggestion: {issue.suggestion}")

            if warnings:
                lines.append("\n   🟡 WARNINGS:")
                for issue in warnings:
                    lines.append(f"      - {issue.message}")
                    if issue.suggestion:
                        lines.append(f"        Suggestion: {issue.suggestion}")

            if suggestions:
                lines.append("\n   🔵 SUGGESTIONS:")
                for issue in suggestions:
                    lines.append(f"      - {issue.message}")
                    if issue.suggestion:
                        lines.append(f"        Suggestion: {issue.suggestion}")

        if self.edge_cases_covered:
            lines.append(f"\n✅ Edge Cases Covered ({len(self.edge_cases_covered)}):")
            for case in self.edge_cases_covered:
                lines.append(f"   - {case}")

        if self.edge_cases_missing:
            lines.append(f"\n❌ Edge Cases Missing ({len(self.edge_cases_missing)}):")
            for case in self.edge_cases_missing:
                lines.append(f"   - {case}")

        lines.append("\n" + "=" * 80)

        if self.is_good_quality():
            lines.append("✅ Test quality is GOOD - safe to proceed with TDD")
        else:
            lines.append("⚠️  Test quality needs improvement - consider addressing issues first")

        lines.append("=" * 80)

        return "\n".join(lines)


class TestReviewAgent:
    """
    Agent that reviews test quality before TDD implementation.

    Provides automated checks and LLM-powered analysis to ensure
    tests are well-structured, comprehensive, and maintainable.
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        use_llm_analysis: bool = True,
    ):
        """
        Initialize Test Review Agent.

        Args:
            llm_client: LLM client for deep analysis (creates one if None)
            use_llm_analysis: Whether to use LLM for deep review (slower but better)
        """
        self.llm_client = llm_client or LLMClient(provider="ollama", model="qwen2.5-coder:1.5b")
        self.use_llm_analysis = use_llm_analysis

    def review_test_file(self, test_path: Path) -> TestReviewResult:
        """
        Review a test file and return quality assessment.

        Args:
            test_path: Path to test file

        Returns:
            TestReviewResult with issues and suggestions
        """
        test_content = test_path.read_text()

        result = TestReviewResult(
            test_file=str(test_path),
            overall_score=0.0,
        )

        # Run automated checks
        self._check_test_structure(test_content, result)
        self._check_test_naming(test_content, result)
        self._check_assertions(test_content, result)
        self._check_edge_cases(test_content, result)

        # Optional: Deep LLM analysis
        if self.use_llm_analysis:
            self._llm_deep_review(test_content, result)

        # Calculate overall score
        result.overall_score = self._calculate_score(result)

        return result

    def _check_test_structure(self, content: str, result: TestReviewResult) -> None:
        """Check if tests have proper structure (assertions, clear phases)."""
        test_functions = self._extract_test_functions(content)
        result.test_count = len(test_functions)

        if result.test_count == 0:
            result.issues.append(TestQualityIssue(
                severity="critical",
                category="structure",
                message="No test functions found (should start with 'test_')",
            ))
            return

        for test_name, test_body in test_functions:
            # CRITICAL: Must have assertions
            has_assert = "assert " in test_body.lower()

            if not has_assert:
                result.issues.append(TestQualityIssue(
                    severity="critical",
                    category="structure",
                    message=f"Test '{test_name}' has no assertions",
                    test_name=test_name,
                    suggestion="Add assert statements to verify expected behavior",
                ))
                continue

            # Check for visual structure (blank lines or length)
            line_count = len([l for l in test_body.split('\n') if l.strip()])
            has_blank_lines = "\n\n" in test_body

            # For complex tests (>10 lines), suggest structure (but not critical)
            if line_count > 10 and not has_blank_lines:
                result.issues.append(TestQualityIssue(
                    severity="suggestion",
                    category="structure",
                    message=f"Test '{test_name}' is complex (>{line_count} lines) but lacks clear phases",
                    test_name=test_name,
                    suggestion="Use blank lines to separate setup, action, and verification phases",
                ))

        if result.test_count > 0 and not result.has_critical_issues():
            result.strengths.append(f"Found {result.test_count} test functions with assertions")

    def _check_test_naming(self, content: str, result: TestReviewResult) -> None:
        """Check if test names clearly describe what they test."""
        test_functions = self._extract_test_functions(content)

        for test_name, _ in test_functions:
            # Check for vague names
            if test_name in ["test_basic", "test_simple", "test_1", "test_main"]:
                result.issues.append(TestQualityIssue(
                    severity="warning",
                    category="naming",
                    message=f"Test name '{test_name}' is too vague",
                    test_name=test_name,
                    suggestion="Use descriptive name like 'test_function_does_expected_behavior'",
                ))

            # Check for good naming patterns
            if any(keyword in test_name for keyword in ["_when_", "_should_", "_with_", "_returns_"]):
                result.strengths.append(f"Test '{test_name}' has descriptive name")

    def _check_assertions(self, content: str, result: TestReviewResult) -> None:
        """Check quality of assertions (focus on substance not style)."""
        test_functions = self._extract_test_functions(content)

        for test_name, test_body in test_functions:
            # Count assertions
            assertion_count = test_body.lower().count("assert ")

            if assertion_count == 0:
                continue  # Already flagged in structure check

            # SUBSTANTIVE ISSUE: Warn if too many assertions (testing multiple concepts)
            if assertion_count > 5:
                result.issues.append(TestQualityIssue(
                    severity="warning",
                    category="assertions",
                    message=f"Test '{test_name}' has {assertion_count} assertions (may test multiple concepts)",
                    test_name=test_name,
                    suggestion="Consider splitting into separate tests, one per concept",
                ))

            # Note: We don't enforce assertion messages - that's style not substance
            # Tests can be clear without explicit messages if well-named

    def _check_edge_cases(self, content: str, result: TestReviewResult) -> None:
        """Check if common edge cases are tested."""
        content_lower = content.lower()

        # Common edge cases to look for
        edge_case_patterns = {
            "empty input": ["\"\"", "''", "[]", "{}", "empty", "none"],
            "null/None": ["none", "null"],
            "negative numbers": ["-1", "negative"],
            "zero": ["== 0", "!= 0", "zero"],
            "boundary values": ["max", "min", "boundary"],
            "invalid input": ["invalid", "malformed", "bad"],
        }

        for case_name, patterns in edge_case_patterns.items():
            if any(pattern in content_lower for pattern in patterns):
                result.edge_cases_covered.append(case_name)

        # Suggest common missing edge cases based on content analysis
        if "validate" in content_lower or "parse" in content_lower:
            if "empty input" not in result.edge_cases_covered:
                result.edge_cases_missing.append("empty input")
            if "null/None" not in result.edge_cases_covered:
                result.edge_cases_missing.append("null/None")
            if "invalid input" not in result.edge_cases_covered:
                result.edge_cases_missing.append("invalid input")

        if any(word in content_lower for word in ["int", "number", "count", "age"]):
            if "negative numbers" not in result.edge_cases_covered:
                result.edge_cases_missing.append("negative numbers")
            if "zero" not in result.edge_cases_covered:
                result.edge_cases_missing.append("zero")

        if result.edge_cases_covered:
            result.strengths.append(f"Tests cover {len(result.edge_cases_covered)} edge cases")

        if result.edge_cases_missing:
            result.issues.append(TestQualityIssue(
                severity="suggestion",
                category="coverage",
                message=f"Consider testing these edge cases: {', '.join(result.edge_cases_missing)}",
                suggestion="Add tests for boundary conditions and error cases",
            ))

    def _llm_deep_review(self, content: str, result: TestReviewResult) -> None:
        """Use LLM to perform deep analysis of test quality (substance over style)."""
        prompt = f"""Review this test code for SUBSTANTIVE quality issues (not style preferences).

Test Code:
```python
{content}
```

Focus on:
1. Are tests independent (no shared state between tests)?
2. Do tests cover both happy path AND error cases?
3. What critical edge cases are missing (null, empty, boundary, invalid)?
4. Does any test verify multiple unrelated behaviors (should be split)?
5. Are there fragile patterns (brittle assertions, timing dependencies)?

IGNORE style issues like:
- Whether to use AAA comments (structure is more important than comments)
- Assertion message formatting (optional, not required)
- Naming conventions (as long as intent is clear)

Provide 3-5 specific, actionable feedback points that affect test EFFECTIVENESS."""

        try:
            response = self.llm_client.generate(
                prompt=prompt,
                system_prompt="You are a test quality expert. Provide constructive, specific feedback on test code.",
                max_tokens=500,
                temperature=0.3,
            )

            # Parse LLM response into issues
            feedback = response["content"]

            # Add as suggestions (LLM feedback is advisory, not critical)
            for line in feedback.split("\n"):
                line = line.strip()
                if line and (line.startswith("-") or line.startswith("•")):
                    result.issues.append(TestQualityIssue(
                        severity="suggestion",
                        category="deep_analysis",
                        message=line.lstrip("-•").strip(),
                    ))

        except Exception as e:
            # LLM analysis is optional, don't fail if it errors
            result.issues.append(TestQualityIssue(
                severity="suggestion",
                category="deep_analysis",
                message=f"LLM analysis failed: {e}",
            ))

    def _calculate_score(self, result: TestReviewResult) -> float:
        """Calculate overall test quality score."""
        if result.test_count == 0:
            return 0.0

        score = 1.0

        # Deduct for issues
        for issue in result.issues:
            if issue.severity == "critical":
                score -= 0.3
            elif issue.severity == "warning":
                score -= 0.1
            elif issue.severity == "suggestion":
                score -= 0.05

        # Boost for strengths
        score += len(result.strengths) * 0.05

        # Boost for edge case coverage
        score += len(result.edge_cases_covered) * 0.05

        return max(0.0, min(1.0, score))  # Clamp to 0.0-1.0

    def _extract_test_functions(self, content: str) -> list[tuple[str, str]]:
        """Extract test function names and bodies."""
        test_functions = []
        lines = content.split('\n')

        i = 0
        while i < len(lines):
            line = lines[i]

            # Find test function definition
            if line.strip().startswith('def test_'):
                # Extract function name
                match = re.match(r'\s*def (test_\w+)', line)
                if match:
                    test_name = match.group(1)

                    # Extract function body
                    body_lines = []
                    i += 1

                    # Get indentation of first line in body
                    while i < len(lines) and not lines[i].strip():
                        i += 1

                    if i < len(lines):
                        base_indent = len(lines[i]) - len(lines[i].lstrip())

                        # Collect body lines until next function or dedent
                        while i < len(lines):
                            if lines[i].strip() and not lines[i].startswith(' ' * base_indent):
                                break
                            body_lines.append(lines[i])
                            i += 1

                    test_body = '\n'.join(body_lines)
                    test_functions.append((test_name, test_body))
                    continue

            i += 1

        return test_functions

    def _has_setup_pattern(self, body: str) -> bool:
        """Check if test body has typical setup/arrange patterns."""
        setup_keywords = ["=", "create", "mock", "setup", "initialize"]
        first_lines = body.split('\n')[:3]  # Check first few lines
        return any(keyword in line.lower() for line in first_lines for keyword in setup_keywords)

    def _has_action_pattern(self, body: str) -> bool:
        """Check if test body has typical action patterns."""
        action_keywords = ["result =", "output =", "response =", "call", "execute"]
        return any(keyword in body.lower() for keyword in action_keywords)
