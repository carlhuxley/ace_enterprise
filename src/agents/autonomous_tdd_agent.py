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

        # Playbook retrieval for injecting learned patterns
        from src.playbook.retrieval import BulletRetriever
        self.bullet_retriever = BulletRetriever()
        # Use ensemble's playbook manager to see newly learned bullets
        self.playbook_manager = ensemble_learner.playbook_manager
        self.playbook_id = ensemble_learner.playbook_id

        # Ensure directories exist
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.src_dir.mkdir(parents=True, exist_ok=True)

        # Track test functions per file for cycle isolation
        self.test_functions = {}  # {test_file_path: [{'cycle': int, 'name': str, 'code': str}]}

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
5. Aim for 3-5 increments total

**CRITICAL**: You MUST output in this EXACT format (pipe-separated, one per line):
test_name | description | test_file_path | impl_file_path

**Example for "Calculator that adds two numbers"**:
test_calculator_can_be_created | Test that Calculator instance can be created | tests/test_calculator.py | src/calculator.py
test_add_returns_sum_of_two_numbers | Test that add() returns sum of two positive numbers | tests/test_calculator.py | src/calculator.py
test_add_handles_zero | Test that add() handles zero correctly | tests/test_calculator.py | src/calculator.py

**YOUR TASK**: Generate test increments for: "{requirement}"

Output ONLY the pipe-separated lines (no explanations, no markdown, no extra text):
"""

        # Get proposal from primary model
        response_dict = self.llm_client.generate(prompt)
        response = response_dict["content"]

        # Parse response
        increments = []
        for line in response.strip().split("\n"):
            if "|" not in line or line.strip().startswith("#"):
                continue

            parts = [p.strip() for p in line.split("|") if p.strip()]
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

        if not increments:
            logger.warning("No increments parsed from LLM response")
            logger.warning(f"Response was:\n{response}")
            raise ValueError(
                "Failed to parse test increments from LLM response. "
                "Expected pipe-separated format: test_name | description | test_file | impl_file"
            )

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
        test_code = self._write_test(increment, cycle_number)
        logger.info(f"      Created: {increment.test_file.relative_to(self.project_root)}")

        red_result = self._run_tests()
        if not red_result.failed:
            raise RuntimeError(
                f"Test must fail initially (RED phase). "
                f"Test passed unexpectedly: {increment.test_name}"
            )
        logger.info(f"  ⚙️  Running tests... FAILED (expected)")

        # GREEN: Write minimal code (with retry logic)
        logger.info("  🟢 GREEN: Writing minimal code...")
        MAX_GREEN_RETRIES = 3
        green_result = None

        for attempt in range(1, MAX_GREEN_RETRIES + 1):
            if attempt > 1:
                logger.info(f"  🔄 GREEN retry {attempt}/{MAX_GREEN_RETRIES} (previous implementation failed)...")

            impl_code = self._write_minimal_code(increment, red_result, previous_failure=green_result)
            logger.info(f"      Created: {increment.implementation_file.relative_to(self.project_root)}")

            green_result = self._run_tests()
            if green_result.all_passed:
                logger.info(f"  ⚙️  Running tests... PASSED ✓")
                break
            else:
                logger.warning(f"  ⚠️  Tests still failing after attempt {attempt}: {green_result.error[:100]}...")

        if not green_result.all_passed:
            raise RuntimeError(
                f"Tests must pass after implementation (GREEN phase). "
                f"Still failing after {MAX_GREEN_RETRIES} attempts: {green_result.error}"
            )

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

    def _write_test(self, increment: TestIncrement, cycle_number: int) -> str:
        """
        Write failing test for increment.

        Uses array-based storage for cycle isolation.

        Args:
            increment: Test specification
            cycle_number: Current cycle number

        Returns:
            Generated test code
        """
        test_file_key = str(increment.test_file)

        # Get existing test functions for context (but don't modify file directly)
        existing_functions = self.test_functions.get(test_file_key, [])
        existing_code = "\n\n".join([f['code'] for f in existing_functions]) if existing_functions else ""

        # Get learned patterns from playbook
        playbook_guidance = self._get_playbook_guidance(
            query=f"TDD test writing {increment.test_name} {increment.description}",
            top_k=3
        )

        prompt = f"""You are writing a test following TDD (Test-Driven Development).

{playbook_guidance}

**Project Structure**:
- Tests in: {self.test_dir.name}/
- Implementation in: {self.src_dir.name}/
- Imports use: `from src.{increment.implementation_file.stem} import *`

**Test to write**: {increment.test_name}
**Description**: {increment.description}

**CRITICAL - Existing test patterns to follow**:
{existing_code if existing_code else "# File will be created - this is the first test"}

**IMPORTANT**:
- If existing tests create object instances (e.g., `calc = Calculator()`), your test MUST use the same pattern
- If existing tests use class methods (e.g., `calc.add()`), your test MUST use methods, NOT standalone functions
- Match the coding style and patterns from existing tests
- Do NOT mix patterns (don't use standalone `add()` if existing tests use `calc.add()`)

**Task**: Write ONLY the test function `{increment.test_name}`.

**CRITICAL CONSTRAINT**:
- Output EXACTLY ONE function: {increment.test_name}
- If you output multiple functions, the system will FAIL
- Do NOT write future tests, ONLY this one test

**Guidelines**:
1. Write ONLY the test function (imports are added automatically)
2. Do NOT add import statements inside the function
3. FOLLOW the existing pattern from tests above (instance-based vs function-based)
4. Test should be focused on ONE concept
5. Use clear assertions (assert with meaningful checks)
6. Test should FAIL initially (implementation doesn't exist yet or is incomplete)
7. Use pytest style (simple assert statements)

**Example showing pattern consistency**:
```python
# If first test does this:
def test_calculator_can_be_created():
    calc = Calculator()
    assert calc is not None

# Then subsequent tests MUST follow the same pattern:
def test_add_returns_sum():
    calc = Calculator()
    result = calc.add(2, 3)  # Use calc.add(), NOT add()
    assert result == 5
```

**Output**: ONLY the test function code (no imports, no explanations, no markdown).
"""

        response_dict = self.llm_client.generate(prompt)
        response = response_dict["content"]

        # Extract code from response
        test_function = self._extract_code(response)

        # Validate: ensure only ONE function was generated
        function_count = self._count_functions(test_function)
        if function_count == 0:
            raise ValueError(f"LLM generated no test functions for {increment.test_name}")
        elif function_count > 1:
            logger.warning(
                f"⚠️  LLM generated {function_count} functions instead of 1, "
                f"extracting only '{increment.test_name}'"
            )
            # Extract only the requested function
            test_function = self._extract_single_function(test_function, increment.test_name)

        # Store in array for cycle isolation
        if test_file_key not in self.test_functions:
            self.test_functions[test_file_key] = []

        self.test_functions[test_file_key].append({
            'cycle': cycle_number,
            'name': increment.test_name,
            'code': test_function
        })

        # Assemble complete file from all stored functions
        self._assemble_test_file(increment.test_file, increment.implementation_file)

        return test_function

    def _write_minimal_code(self, increment: TestIncrement, test_result: TestResult, previous_failure: TestResult = None) -> str:
        """
        Write minimal code to make test pass (GREEN phase).

        Args:
            increment: Test specification
            test_result: Result of failed test (RED phase)
            previous_failure: Previous GREEN phase failure (for retry feedback)

        Returns:
            Generated implementation code
        """
        # Check if implementation exists
        existing_code = ""
        if increment.implementation_file.exists():
            existing_code = increment.implementation_file.read_text()

        # Read test code
        test_code = increment.test_file.read_text()

        # Get learned patterns from playbook
        playbook_guidance = self._get_playbook_guidance(
            query=f"TDD implementation minimal code {increment.test_name}",
            top_k=3
        )

        prompt = f"""You are following TDD discipline: write MINIMAL code to pass the test.

{playbook_guidance}

**CRITICAL**: You are writing an IMPLEMENTATION file, NOT a test file.
- This is: {self.src_dir.name}/{increment.implementation_file.name}
- Output ONLY production code (classes, functions, logic)
- Do NOT include test code, test imports, or pytest code
- Do NOT include comments like "# Test file for..."

**Current failing test**:
```python
{test_code}
```

**Test error**:
```
{test_result.error or test_result.output}
```

**Existing implementation** in {increment.implementation_file.name}:
```python
{existing_code if existing_code else "# Empty file - create what's needed"}
```
{"" if not previous_failure else f'''
**⚠️ RETRY FEEDBACK**: Your previous implementation didn't pass the test.
**Previous implementation error**:
```
{previous_failure.error or previous_failure.output}
```
**What went wrong**: The implementation you provided didn't satisfy the test assertion.
**Action needed**: Fix the implementation to make the test pass. Return a value that satisfies the test.
'''}
**Task**: Write the MINIMAL implementation code to make THIS test pass.

**TDD Constraints**:
1. ✅ Write simplest thing that works
2. ✅ Only implement what current test requires
3. ✅ If test expects a class, create/extend that class
4. ✅ If test expects a function, create/add that function
5. ✅ Keep ALL existing implementation code (add to it, don't replace)
6. ❌ Don't add features for future tests
7. ❌ Don't add "nice to have" features
8. ❌ Don't over-engineer
9. ❌ NEVER include test code in implementation file

**Example - Test expects**:
```python
calc = Calculator()
result = calc.add(2, 3)
assert result == 5
```

**Minimal implementation**:
```python
class Calculator:
    def add(self, a, b):
        return a + b
```

**Output**: Complete implementation file content (production code only, no test code).
"""

        response_dict = self.llm_client.generate(prompt)
        response = response_dict["content"]

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

        # Use standard ACE learning flow
        from src.storage.schemas import TaskInput, EnvironmentFeedback
        import uuid

        task = TaskInput(
            id=str(uuid.uuid4()),
            query=f"""Analyze this successful TDD cycle and extract reusable patterns.

**Test increment**: {increment.test_name}
**Description**: {increment.description}

**Test code**:
```python
{test_code}
```

**Implementation code**:
```python
{impl_code}
```

**Task**: Extract 1-3 specific, actionable patterns that worked well.

**Good patterns** (specific and actionable):
- "When testing class instantiation, create instance and assert it's not None"
- "For methods on a class, instantiate the class first, then call the method"
- "Start with simplest test (object creation) before testing behavior"

**Bad patterns** (too vague):
- "Write good tests"
- "Follow TDD"

Output 1-3 bullet points, one per line.""",
            context={
                "test_name": increment.test_name,
                "test_file": str(increment.test_file),
                "impl_file": str(increment.implementation_file),
            }
        )

        feedback = EnvironmentFeedback(
            result="SUCCESS",
            actual="Tests passed",
            test_report={"test_quality": test_review.overall_score}
        )

        # Run ensemble learning (single model auto-approves)
        result = self.ensemble.learn_from_task(task, feedback, parallel=False)

        # Save approved bullets to playbook
        self.ensemble.add_approved_bullets_to_playbook(result)

        # Return approved bullets only
        return result.approved_bullets

    def _get_playbook_guidance(self, query: str, top_k: int = 5) -> str:
        """
        Retrieve relevant playbook bullets using T-shaped retrieval:
        - Primary: Agent's own playbook (deep domain expertise)
        - Secondary: All other playbooks (broad cross-domain knowledge)

        Args:
            query: Query to find relevant patterns
            top_k: Number of bullets to retrieve

        Returns:
            Formatted string to inject into prompts
        """
        # Get primary playbook (agent's own domain expertise)
        primary_playbook = self.playbook_manager.get_playbook(self.playbook_id)
        if not primary_playbook:
            return ""

        primary_bullets = []
        for section_name, section_bullets in primary_playbook.sections.items():
            primary_bullets.extend(section_bullets)

        logger.info(f"🔍 DEBUG: Primary playbook {self.playbook_id} has {len(primary_bullets)} bullets in memory")

        # Get all other playbooks for cross-domain knowledge
        secondary_bullets_by_playbook = {}

        for playbook_id, pb in self.playbook_manager._playbooks.items():
            # Skip agent's own playbook (already in primary)
            if pb.playbook_id == self.playbook_id:
                continue

            # Get bullets from this playbook
            playbook_bullets = []
            for section_bullets in pb.sections.values():
                playbook_bullets.extend(section_bullets)

            if playbook_bullets:
                secondary_bullets_by_playbook[pb.playbook_id] = playbook_bullets

        # Cross-playbook retrieval (T-shaped: deep + broad)
        relevant_scored = self.bullet_retriever.retrieve_cross_model(
            query=query,
            primary_bullets=primary_bullets,
            secondary_bullets_by_playbook=secondary_bullets_by_playbook,
            primary_playbook_id=self.playbook_id,
            secondary_weight=0.5,  # Secondary bullets get 50% weight
        )

        if not relevant_scored:
            return ""

        # Count sources for logging
        primary_count = sum(1 for _, _, src in relevant_scored if src == self.playbook_id)
        secondary_count = len(relevant_scored) - primary_count

        logger.info(
            f"Retrieved {len(relevant_scored)} bullets for query "
            f"({primary_count} from own playbook, {secondary_count} from others)"
        )

        # Format for prompt (take top_k)
        bullets_text = "\n".join([
            f"- {bullet.content}"
            for bullet, score, source in relevant_scored[:top_k]
        ])

        return f"""**Learned Patterns** (from previous experience):
{bullets_text}
"""

    def _run_tests(self) -> TestResult:
        """
        Run all tests in test directory.

        Returns:
            TestResult with pass/fail status
        """
        try:
            # Set PYTHONPATH to include project root so imports work
            import os
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)

            result = subprocess.run(
                ["python", "-m", "pytest", str(self.test_dir), "-v", "--tb=short"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                env=env,
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

    def _count_functions(self, code: str) -> int:
        """
        Count function definitions in code using AST parsing.

        Args:
            code: Python code to analyze

        Returns:
            Number of function definitions found
        """
        try:
            tree = ast.parse(code)
            return sum(1 for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
        except SyntaxError:
            logger.warning("Failed to parse code for function counting")
            return 0

    def _extract_single_function(self, code: str, function_name: str) -> str:
        """
        Extract only the named function from code using AST.

        Args:
            code: Python code containing multiple functions
            function_name: Name of function to extract

        Returns:
            Code for just the requested function, or original code if extraction fails
        """
        try:
            tree = ast.parse(code)
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name == function_name:
                    return ast.unparse(node)
            logger.warning(f"Function '{function_name}' not found in generated code")
            return code
        except Exception as e:
            logger.warning(f"Failed to extract function '{function_name}': {e}")
            return code

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

    def _assemble_test_file(self, test_file: Path, implementation_file: Path):
        """
        Assemble complete test file from stored test functions.

        Provides cycle isolation by building file from individual tracked functions.

        Args:
            test_file: Path to test file to assemble
            implementation_file: Path to implementation (for import statement)
        """
        test_file_key = str(test_file)

        # Get functions for this test file
        functions = self.test_functions.get(test_file_key, [])

        if not functions:
            # No functions yet, file will be created on first test write
            return

        # Build file header
        module_name = implementation_file.stem
        header = f"""# Test file for {module_name}
import pytest
from src.{module_name} import *

"""

        # Combine all test functions in cycle order
        test_bodies = "\n\n".join([f['code'] for f in functions])

        # Write complete file
        full_content = header + test_bodies
        test_file.write_text(full_content)

        logger.debug(f"Assembled {len(functions)} test function(s) into {test_file.name}")

    def _collect_test_files(self) -> list[Path]:
        """Collect all test files created."""
        return list(self.test_dir.glob("test_*.py"))

    def _collect_implementation_files(self) -> list[Path]:
        """Collect all implementation files created."""
        return list(self.src_dir.glob("*.py"))
