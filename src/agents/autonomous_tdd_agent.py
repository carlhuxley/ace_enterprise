#!/usr/bin/env python3
"""
Autonomous TDD Agent

Builds features completely autonomously using Test-Driven Development:
- Plans incremental tests (ensemble-based)
- Writes failing tests (RED)
- Writes minimal code (GREEN)
- Refactors for quality (REFACTOR)
- Learns patterns (LEARN)

Key principle: Methodical over vibe coding.
"""
import ast
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.agents.test_review_agent import TestReviewAgent
from src.ensemble.learner import EnsembleLearner
from src.ensemble.models import ConsensusBullet, Vote
from src.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class TestIncrement:
    """Represents one increment in TDD cycle."""

    test_name: str
    description: str
    test_file: Path
    implementation_file: Path
    dependencies: list[str] = field(default_factory=list)
    scenario_context: Optional[str] = None


@dataclass
class TestResult:
    """Result of running tests."""

    passed: bool
    failed: bool
    output: str
    error: Optional[str] = None
    test_count: int = 0
    failed_count: int = 0

    @property
    def all_passed(self) -> bool:
        """Check if all tests passed."""
        return self.passed and self.failed_count == 0


@dataclass
class CycleResult:
    """Result of one TDD cycle (RED → GREEN → REFACTOR → LEARN)."""

    increment: TestIncrement
    test_code: str
    implementation_code: str
    red_result: TestResult
    green_result: TestResult
    refactored: bool
    learned_bullets: list[ConsensusBullet]
    cycle_number: int


@dataclass
class TDDResult:
    """Final result of autonomous TDD session."""

    requirement: str
    test_files: list[Path]
    implementation_files: list[Path]
    cycles_executed: int
    all_tests_passed: bool
    playbook_bullets_added: int
    total_time_seconds: float


class AutonomousTDDAgent:
    """
    Autonomous TDD Agent that builds features incrementally.

    Workflow:
    1. PLAN: Break requirement into incremental tests (ensemble)
    2. For each increment:
       - RED: Write failing test
       - GREEN: Write minimal code to pass
       - REFACTOR: Improve quality while keeping tests green
       - LEARN: Ensemble votes on patterns
    3. Complete when all tests pass

    Key constraints:
    - Tests MUST run after every code change
    - Tests MUST fail in RED phase (for right reason)
    - Tests MUST pass in GREEN phase
    - Code MUST stay minimal (YAGNI principle)
    - Refactoring MUST keep tests green
    """

    def __init__(
        self,
        ensemble_learner: EnsembleLearner,
        test_reviewer: TestReviewAgent,
        project_root: Path,
        test_dir: Path,
        src_dir: Path,
        max_iterations: int = 20,
        review_threshold: float = 0.7,
    ):
        """
        Initialize Autonomous TDD Agent.

        Args:
            ensemble_learner: Ensemble for planning and learning
            test_reviewer: Agent to validate test quality
            project_root: Root of project
            test_dir: Where to write tests (e.g., tests/)
            src_dir: Where to write implementation (e.g., src/)
            max_iterations: Maximum TDD cycles before stopping
            review_threshold: Minimum test quality score to learn from
        """
        self.ensemble = ensemble_learner
        self.test_reviewer = test_reviewer
        self.project_root = project_root
        self.test_dir = test_dir
        self.src_dir = src_dir
        self.max_iterations = max_iterations
        self.review_threshold = review_threshold

        # Create LLM client for primary model
        provider, model = ensemble_learner.models[0][:2]
        base_url = ensemble_learner.models[0][2] if len(ensemble_learner.models[0]) > 2 else None
        self.llm_client = LLMClient(provider=provider, model=model, base_url=base_url)

        # Ensure directories exist
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.src_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"AutonomousTDDAgent initialized")
        logger.info(f"  Project root: {project_root}")
        logger.info(f"  Test dir: {test_dir}")
        logger.info(f"  Src dir: {src_dir}")
        logger.info(f"  Max iterations: {max_iterations}")
        logger.info(f"  Primary LLM: {provider}/{model}")

    def build_feature(self, requirement: str) -> TDDResult:
        """
        Build complete feature autonomously using TDD.

        Process:
        1. Plan increments (ensemble votes on test sequence)
        2. For each increment:
           - Execute RED → GREEN → REFACTOR → LEARN cycle
        3. Return complete implementation

        Args:
            requirement: Natural language feature description

        Returns:
            TDDResult with all generated files and metrics
        """
        import time
        start_time = time.time()

        logger.info("=" * 80)
        logger.info(f"AUTONOMOUS TDD: {requirement}")
        logger.info("=" * 80)

        # Step 1: Plan increments (ensemble-based)
        logger.info("\n[Planning] Breaking requirement into incremental tests...")
        test_plan = self._plan_increments(requirement)
        logger.info(f"  ✓ {len(test_plan)} increments planned")
        for i, inc in enumerate(test_plan, 1):
            logger.info(f"  {i}. {inc.test_name}")

        # Step 2: Execute TDD cycles
        results = []
        for i, increment in enumerate(test_plan):
            if i >= self.max_iterations:
                logger.warning(f"\n⚠️  Reached max_iterations ({self.max_iterations}), stopping")
                break

            logger.info(f"\n{'─' * 80}")
            logger.info(f"[Cycle {i+1}/{len(test_plan)}] {increment.test_name}")
            logger.info('─' * 80)

            try:
                cycle_result = self._tdd_cycle(increment, cycle_number=i+1)
                results.append(cycle_result)
                logger.info(f"  ✅ Cycle complete")
            except Exception as e:
                logger.error(f"  ❌ Cycle failed: {e}")
                raise

        # Step 3: Final validation
        logger.info(f"\n{'─' * 80}")
        logger.info("[Final Validation] Running all tests...")
        logger.info('─' * 80)

        final_result = self._run_tests()
        if not final_result.all_passed:
            raise RuntimeError(f"Feature incomplete: {final_result.failed_count} tests failing")

        logger.info(f"  ✅ All tests passing ({final_result.test_count} tests)")

        # Collect results
        total_bullets = sum(len(r.learned_bullets) for r in results)
        elapsed = time.time() - start_time

        logger.info("\n" + "=" * 80)
        logger.info("✅ FEATURE COMPLETE!")
        logger.info("=" * 80)
        logger.info(f"  • Cycles executed: {len(results)}")
        logger.info(f"  • Tests created: {final_result.test_count}")
        logger.info(f"  • Playbook bullets learned: {total_bullets}")
        logger.info(f"  • Time: {elapsed:.1f}s")
        logger.info("=" * 80)

        return TDDResult(
            requirement=requirement,
            test_files=self._collect_test_files(),
            implementation_files=self._collect_implementation_files(),
            cycles_executed=len(results),
            all_tests_passed=True,
            playbook_bullets_added=total_bullets,
            total_time_seconds=elapsed
        )

    def _plan_increments(self, requirement: str) -> list[TestIncrement]:
        """
        Plan test increments using ensemble voting.

        Each model proposes a test sequence, then ensemble votes on best order.

        Args:
            requirement: Feature description

        Returns:
            Ordered list of test increments
        """
        # For MVP, use simple planning (single model)
        # TODO: Implement ensemble-based planning in Phase 2

        prompt = f"""You are planning incremental tests for TDD (Test-Driven Development).

**Requirement**: {requirement}

**Task**: Break this requirement into a sequence of small, incremental tests.

**Guidelines**:
1. Start simple (domain models, basic functionality)
2. Build complexity gradually (validation, edge cases, integration)
3. Each test should be SMALL and focused (one concept)
4. Order by dependency (can't test API before model exists)
5. Aim for 5-10 increments total

**Example**:
Requirement: "Calculator that adds two numbers"
Increments:
1. test_calculator_can_be_created
2. test_add_returns_sum_of_two_positive_numbers
3. test_add_handles_zero
4. test_add_handles_negative_numbers
5. test_add_handles_floats

**Output Format** (one per line):
test_name | description | test_file_path | impl_file_path

Example:
test_calculator_can_be_created | Test that Calculator instance can be created | tests/test_calculator.py | src/calculator.py
test_add_returns_sum | Test that add() returns sum of two numbers | tests/test_calculator.py | src/calculator.py
"""

        # Get proposal from primary model
        response = self.llm_client.chat(prompt)

        # Parse response
        increments = []
        for line in response.strip().split("\n"):
            if "|" not in line or line.strip().startswith("#"):
                continue

            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 4:
                continue

            test_name, description, test_file, impl_file = parts

            # Ensure paths are under test_dir and src_dir
            test_path = self.test_dir / Path(test_file).name
            impl_path = self.src_dir / Path(impl_file).name

            increments.append(TestIncrement(
                test_name=test_name,
                description=description,
                test_file=test_path,
                implementation_file=impl_path
            ))

        return increments

    def _tdd_cycle(self, increment: TestIncrement, cycle_number: int) -> CycleResult:
        """
        Execute one TDD cycle: RED → GREEN → REFACTOR → LEARN.

        Args:
            increment: Test increment to implement
            cycle_number: Current cycle number

        Returns:
            CycleResult with all artifacts
        """
        # RED: Write failing test
        logger.info("  🔴 RED: Writing failing test...")
        test_code = self._write_test(increment)
        logger.info(f"      Created: {increment.test_file.relative_to(self.project_root)}")

        red_result = self._run_tests()
        if not red_result.failed:
            raise RuntimeError(
                f"Test must fail initially (RED phase). "
                f"Test passed unexpectedly: {increment.test_name}"
            )
        logger.info(f"  ⚙️  Running tests... FAILED (expected)")

        # GREEN: Write minimal code
        logger.info("  🟢 GREEN: Writing minimal code...")
        impl_code = self._write_minimal_code(increment, red_result)
        logger.info(f"      Created: {increment.implementation_file.relative_to(self.project_root)}")

        green_result = self._run_tests()
        if not green_result.all_passed:
            raise RuntimeError(
                f"Tests must pass after implementation (GREEN phase). "
                f"Still failing: {green_result.error}"
            )
        logger.info(f"  ⚙️  Running tests... PASSED ✓")

        # REFACTOR: Improve quality (optional)
        refactored = False
        if self._needs_refactoring(impl_code):
            logger.info("  ✨ REFACTOR: Improving code quality...")
            refactored_code = self._refactor_code(increment.implementation_file)

            # Tests must stay green
            refactor_result = self._run_tests()
            if not refactor_result.all_passed:
                logger.warning("  ⚠️  Refactoring broke tests, reverting...")
                increment.implementation_file.write_text(impl_code)
            else:
                logger.info("  ✓ Refactoring complete, tests still green")
                impl_code = refactored_code
                refactored = True
        else:
            logger.info("  ✨ REFACTOR: Code quality acceptable, skipping")

        # LEARN: Ensemble votes on patterns
        logger.info("  🧠 LEARN: Ensemble reviewing cycle...")
        learned_bullets = self._ensemble_learn(test_code, impl_code, increment)
        logger.info(f"      {len(learned_bullets)} patterns approved")

        return CycleResult(
            increment=increment,
            test_code=test_code,
            implementation_code=impl_code,
            red_result=red_result,
            green_result=green_result,
            refactored=refactored,
            learned_bullets=learned_bullets,
            cycle_number=cycle_number
        )

    def _write_test(self, increment: TestIncrement) -> str:
        """
        Write failing test for increment.

        Args:
            increment: Test specification

        Returns:
            Generated test code
        """
        # Check if test file exists
        existing_code = ""
        if increment.test_file.exists():
            existing_code = increment.test_file.read_text()

        prompt = f"""You are writing a test following TDD (Test-Driven Development).

**Test to write**: {increment.test_name}
**Description**: {increment.description}
**Test file**: {increment.test_file.name}
**Implementation file**: {increment.implementation_file.name}

**Existing test code**:
```python
{existing_code if existing_code else "# Empty file"}
```

**Task**: Write the test function `{increment.test_name}`.

**Guidelines**:
1. Write ONLY the test function (don't duplicate existing code)
2. Test should be focused on ONE concept
3. Use clear assertions (assert with meaningful checks)
4. Test should FAIL initially (implementation doesn't exist yet)
5. Use pytest style (simple assert statements)
6. Import what you need from implementation module

**Example**:
```python
def test_calculator_can_be_created():
    \"\"\"Test that Calculator instance can be created.\"\"\"
    calc = Calculator()
    assert calc is not None
```

**Output**: ONLY the new test function code (no explanations).
"""

        response = self.llm_client.chat(prompt)

        # Extract code from response
        test_function = self._extract_code(response)

        # Append to existing file or create new
        if existing_code:
            full_code = existing_code + "\n\n" + test_function
        else:
            # New file, add imports and function
            module_name = increment.implementation_file.stem
            full_code = f"""import pytest\nfrom src.{module_name} import *\n\n{test_function}"""

        increment.test_file.write_text(full_code)

        return test_function

    def _write_minimal_code(self, increment: TestIncrement, test_result: TestResult) -> str:
        """
        Write minimal code to make test pass (GREEN phase).

        Args:
            increment: Test specification
            test_result: Result of failed test (RED phase)

        Returns:
            Generated implementation code
        """
        # Check if implementation exists
        existing_code = ""
        if increment.implementation_file.exists():
            existing_code = increment.implementation_file.read_text()

        # Read test code
        test_code = increment.test_file.read_text()

        prompt = f"""You are following TDD discipline: write MINIMAL code to pass the test.

**Current failing test**:
```python
{test_code}
```

**Test error**:
```
{test_result.error or test_result.output}
```

**Existing implementation**:
```python
{existing_code if existing_code else "# Empty file"}
```

**Task**: Write the MINIMAL code needed to make THIS test pass.

**TDD Constraints**:
1. ✅ Write simplest thing that works
2. ✅ Only implement what current test requires
3. ❌ Don't add features for future tests
4. ❌ Don't add "nice to have" features
5. ❌ Don't over-engineer

**Example of minimal thinking**:
- Test: `assert add(2, 3) == 5`
- ❌ Bad (over-engineered): Support lists, floats, validation, logging
- ✅ Good (minimal): `def add(a, b): return a + b`

**Output**: Complete implementation file content (update existing code if present).
"""

        response = self.llm_client.chat(prompt)

        # Extract code
        impl_code = self._extract_code(response)

        # Write to file
        increment.implementation_file.write_text(impl_code)

        return impl_code

    def _needs_refactoring(self, code: str) -> bool:
        """
        Check if code needs refactoring.

        Simple heuristics:
        - Long functions (>20 lines)
        - Duplicated code patterns
        - Complex expressions

        Args:
            code: Implementation code

        Returns:
            True if refactoring recommended
        """
        # For MVP, skip refactoring (Phase 3 feature)
        return False

    def _refactor_code(self, implementation_file: Path) -> str:
        """
        Refactor code while keeping tests green.

        Args:
            implementation_file: File to refactor

        Returns:
            Refactored code
        """
        # TODO: Implement in Phase 3
        return implementation_file.read_text()

    def _ensemble_learn(
        self,
        test_code: str,
        impl_code: str,
        increment: TestIncrement
    ) -> list[ConsensusBullet]:
        """
        Ensemble extracts and votes on patterns from TDD cycle.

        Args:
            test_code: Test that was written
            impl_code: Implementation that was written
            increment: Context about increment

        Returns:
            List of approved bullets
        """
        # Review test quality first
        test_review = self.test_reviewer.review_test_file(increment.test_file)

        if test_review.overall_score < self.review_threshold:
            logger.warning(f"  ⚠️  Test quality low ({test_review.overall_score:.0%}), skipping learning")
            return []

        # TODO: Implement ensemble pattern extraction and voting
        # For MVP, return empty (Phase 1 focuses on TDD loop)
        return []

    def _run_tests(self) -> TestResult:
        """
        Run all tests in test directory.

        Returns:
            TestResult with pass/fail status
        """
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", str(self.test_dir), "-v", "--tb=short"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=30
            )

            output = result.stdout + result.stderr

            # Parse pytest output
            passed = result.returncode == 0
            failed = result.returncode != 0

            # Count tests
            test_count = output.count(" PASSED") + output.count(" FAILED")
            failed_count = output.count(" FAILED")

            # Extract error if failed
            error = None
            if failed:
                # Get last error from output
                lines = output.split("\n")
                for i, line in enumerate(lines):
                    if "FAILED" in line or "ERROR" in line:
                        error = "\n".join(lines[i:i+10])
                        break

            return TestResult(
                passed=passed,
                failed=failed,
                output=output,
                error=error,
                test_count=test_count,
                failed_count=failed_count
            )

        except subprocess.TimeoutExpired:
            return TestResult(
                passed=False,
                failed=True,
                output="",
                error="Test execution timed out (30s)"
            )
        except Exception as e:
            return TestResult(
                passed=False,
                failed=True,
                output="",
                error=f"Test execution failed: {e}"
            )

    def _extract_code(self, llm_response: str) -> str:
        """
        Extract Python code from LLM response.

        Handles various formats:
        - Markdown code blocks (```python)
        - Plain code

        Args:
            llm_response: LLM output

        Returns:
            Extracted code
        """
        # Try to extract from markdown code block
        if "```python" in llm_response:
            start = llm_response.find("```python") + len("```python")
            end = llm_response.find("```", start)
            if end != -1:
                return llm_response[start:end].strip()

        if "```" in llm_response:
            start = llm_response.find("```") + 3
            end = llm_response.find("```", start)
            if end != -1:
                return llm_response[start:end].strip()

        # Assume entire response is code
        return llm_response.strip()

    def _collect_test_files(self) -> list[Path]:
        """Collect all test files created."""
        return list(self.test_dir.glob("test_*.py"))

    def _collect_implementation_files(self) -> list[Path]:
        """Collect all implementation files created."""
        return list(self.src_dir.glob("*.py"))
