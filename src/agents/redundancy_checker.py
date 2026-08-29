"""
RedundancyPreChecker - Detect redundant tests BEFORE writing them.

This module provides pre-check functionality to avoid generating
duplicate or semantically redundant tests during TDD cycles.

Key insight: It's cheaper to detect redundancy before generating
test code than to discover it when RED phase unexpectedly passes.
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExistingTest:
    """Represents an existing test in the codebase."""
    name: str
    assertions: list[str]
    file_path: str


@dataclass
class ProposedTest:
    """Represents a test being proposed for the next TDD cycle."""
    name: str
    description: str


@dataclass
class RedundancyResult:
    """Result of redundancy pre-check."""
    is_redundant: bool
    reason: str
    confidence: float  # 0.0 to 1.0


class RedundancyPreChecker:
    """
    Pre-checks proposed tests for redundancy before RED phase.

    Detection strategies:
    1. Exact name match - definite redundancy
    2. Semantic similarity - compare description to existing assertions
    3. Implicit coverage - check if behavior is covered by broader test
    """

    def __init__(self):
        # Synonyms for operation keywords (normalized to canonical form)
        self._operation_synonyms = {
            'addition': 'add', 'sum': 'add', 'plus': 'add',
            'subtraction': 'subtract', 'minus': 'subtract', 'difference': 'subtract',
            'multiplication': 'multiply', 'product': 'multiply', 'times': 'multiply',
            'division': 'divide', 'quotient': 'divide',
            'creation': 'create', 'instantiate': 'create', 'construct': 'create',
        }

        # Core operation keywords (canonical forms)
        self._operation_keywords = {
            'add', 'subtract', 'multiply', 'divide', 'create',
        }

        # Edge case indicators - presence means test is NOT redundant
        self._edge_case_indicators = {
            'negative', 'zero', 'edge', 'error', 'invalid', 'empty',
            'null', 'none', 'boundary', 'overflow', 'underflow',
            'exception', 'fail', 'maximum', 'minimum',
        }

    def check(
        self,
        existing_tests: list[ExistingTest],
        proposed: ProposedTest
    ) -> RedundancyResult:
        """
        Check if proposed test is redundant given existing tests.

        Args:
            existing_tests: List of tests already in the codebase
            proposed: The test being proposed for next TDD cycle

        Returns:
            RedundancyResult with is_redundant, reason, and confidence
        """
        # No existing tests = definitely not redundant
        if not existing_tests:
            return RedundancyResult(
                is_redundant=False,
                reason="No existing tests to conflict with",
                confidence=1.0
            )

        # Check 1: Exact name match
        for existing in existing_tests:
            if existing.name == proposed.name:
                return RedundancyResult(
                    is_redundant=True,
                    reason=f"Duplicate test name: '{proposed.name}' already exists",
                    confidence=1.0
                )

        # Check 2: Semantic similarity based on description
        proposed_keywords = self._extract_keywords(proposed.name, proposed.description)
        proposed_normalized = self._normalize_keywords(proposed_keywords)

        # Check if proposed test has edge case indicators - if so, it's likely NOT redundant
        proposed_edge_cases = proposed_normalized & self._edge_case_indicators
        if proposed_edge_cases:
            # Edge case tests are valuable even if base operation is tested
            return RedundancyResult(
                is_redundant=False,
                reason=f"Tests edge case: {', '.join(proposed_edge_cases)}",
                confidence=0.9
            )

        for existing in existing_tests:
            existing_keywords = self._extract_keywords(existing.name, *existing.assertions)
            existing_normalized = self._normalize_keywords(existing_keywords)

            # Check for operation keyword match (strong signal)
            proposed_operations = proposed_normalized & self._operation_keywords
            existing_operations = existing_normalized & self._operation_keywords
            operation_overlap = proposed_operations & existing_operations

            if operation_overlap:
                # Same operation — but only redundant if the subject/entity also overlaps.
                # "add plant" vs "add structural_asset" are different behaviors despite
                # sharing the "add" verb.
                proposed_subject = proposed_normalized - self._operation_keywords
                existing_subject = existing_normalized - self._operation_keywords
                subject_overlap = proposed_subject & existing_subject
                if not subject_overlap:
                    # Different entities: same verb, distinct behavior
                    continue
                operation = next(iter(operation_overlap))
                return RedundancyResult(
                    is_redundant=True,
                    reason=f"Tests same behavior: {operation} already tested in {existing.name}",
                    confidence=0.8
                )

        # Check 3: Implicit coverage - is proposed test a subset of existing?
        for existing in existing_tests:
            if self._is_implicitly_covered(proposed, existing):
                return RedundancyResult(
                    is_redundant=True,
                    reason=f"Already covered by broader test: {existing.name}",
                    confidence=0.75
                )

        # No redundancy detected
        return RedundancyResult(
            is_redundant=False,
            reason="Proposed test covers new behavior",
            confidence=0.85
        )

    def _extract_keywords(self, *texts: str) -> set[str]:
        """Extract meaningful keywords from text strings."""
        keywords = set()
        for text in texts:
            # Normalize and split
            words = text.lower().replace('_', ' ').replace('.', ' ').split()
            for word in words:
                # Remove common prefixes/suffixes
                word = word.strip('()[]{}"\',')
                if len(word) > 2 and word not in {
                'test', 'assert', 'that', 'the', 'and', 'for', 'with',
                'can', 'should', 'will', 'when', 'given', 'then', 'have',
                'has', 'been', 'into', 'from', 'its', 'are', 'not',
            }:
                    keywords.add(word)
        return keywords

    def _normalize_keywords(self, keywords: set[str]) -> set[str]:
        """Normalize keywords using synonym mapping."""
        normalized = set()
        for keyword in keywords:
            # Map synonyms to canonical form
            if keyword in self._operation_synonyms:
                normalized.add(self._operation_synonyms[keyword])
            else:
                normalized.add(keyword)
        return normalized

    def _is_implicitly_covered(self, proposed: ProposedTest, existing: ExistingTest) -> bool:
        """Check if proposed test is implicitly covered by existing test."""
        # Extract the operation from proposed test name
        proposed_words = set(proposed.name.lower().replace('_', ' ').split())
        proposed_words.discard('test')

        # Check if any assertion in existing test covers this operation
        for assertion in existing.assertions:
            assertion_lower = assertion.lower()
            # Look for method calls in assertion
            for word in proposed_words:
                if word in self._operation_keywords and word in assertion_lower:
                    return True

        return False


def existing_tests_from_file(test_file: Path) -> list[ExistingTest]:
    """AST-scan a test file for existing test_* functions, for RedundancyPreChecker.

    Static analysis only (same discipline as ImportFilter) -- never executes
    the file's content, so this is safe to run on unverified generated code
    before it's ever pulsed into the sandbox.
    """
    import ast

    if not test_file.exists():
        return []
    source = test_file.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    existing: list[ExistingTest] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            code = "\n".join(lines[node.lineno - 1:node.end_lineno])
            assertions = [line.strip() for line in code.split("\n") if "assert" in line.lower()]
            existing.append(ExistingTest(name=node.name, assertions=assertions, file_path=str(test_file)))
    return existing
