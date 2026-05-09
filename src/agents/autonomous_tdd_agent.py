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
import sys
from dataclasses import dataclass, field
from pathlib import Path

from src.utils.code_extraction import extract_code
from src.agents.redundancy_checker import (
    ExistingTest,
    ProposedTest,
    RedundancyPreChecker,
)
from src.agents.project_aware_tdd import (
    ProjectStructure,
    extract_explicit_constraints,
)
from src.agents.tdd_failure_recorder import (
    TDDFailureRecorder,
    FailureContext,
    InterventionRecord,
)
from src.agents.tdd_lesson_injector import TDDLessonInjector
from src.agents.test_review_agent import TestReviewAgent
from src.audit.local_client import LocalAuditClient
from src.audit.schemas import AuditEventType
from src.core.curator.module import Curator
from src.core.generator.module import Generator
from src.ensemble.learner import EnsembleLearner
from src.ensemble.models import ConsensusBullet
from src.storage.experiment_logger import ExperimentLogger
from src.storage.schemas import CuratorOutput, DeltaBullet, TaskInput
from src.utils.llm_client import LLMClient
from src.utils.import_validator import ImportValidator

logger = logging.getLogger(__name__)


@dataclass
class TestIncrement:
    """Represents one increment in TDD cycle."""

    test_name: str
    description: str
    test_file: Path
    implementation_file: Path
    dependencies: list[str] = field(default_factory=list)
    scenario_context: str | None = None


@dataclass
class TestResult:
    """Result of running tests."""

    passed: bool
    failed: bool
    output: str
    error: str | None = None
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
    skipped: bool = False  # True if cycle was skipped due to fundamental redundancy
    skip_reason: str = ""  # Explanation of why cycle was skipped


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
        self.skip_learn = False
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

        # Redundancy pre-checker to avoid writing duplicate tests
        self.redundancy_checker = RedundancyPreChecker()

        # Initialize experiment logger for automatic TDD cycle tracking
        self.experiment_logger = ExperimentLogger(playbook_version="1.0.0")

        # Initialize audit client for event tracking
        self.audit_client = LocalAuditClient()
        self._agent_id = f"tdd-agent-{id(self)}"

        # Feature-level constraints for project-aware TDD
        self._feature_requirement: str | None = None
        self._explicit_class_name: str | None = None
        self._explicit_file_path: str | None = None
        self._project_structure = ProjectStructure()

        # Initialize failure recorder for self-healing
        self.failure_recorder = TDDFailureRecorder(
            experiment_logger=self.experiment_logger,
            playbook_manager=self.playbook_manager,
            playbook_id=self.playbook_id,
        )

        # Initialize TDD lesson injector
        self._tdd_lesson_injector = TDDLessonInjector()

        # Initialize import validator for fixing LLM-generated import paths
        self._import_validator = ImportValidator(project_root)

        # ACE pipeline for GREEN phase: Generator retrieves playbook bullets during
        # generation; Curator enforces deduplication and token budgets on learned bullets.
        self.generator = Generator(self.playbook_manager, self.llm_client)
        self.curator = Curator(self.playbook_manager, self.llm_client)

        logger.info("AutonomousTDDAgent initialized")
        logger.info(f"  Project root: {project_root}")
        logger.info(f"  Test dir: {test_dir}")
        logger.info(f"  Src dir: {src_dir}")
        logger.info(f"  Max iterations: {max_iterations}")
        logger.info(f"  Primary LLM: {provider}/{model}")

    def _emit_audit_event(
        self,
        event_type: AuditEventType,
        payload: dict,
        session_id: str | None = None,
    ) -> bool:
        """Emit an audit event.

        Args:
            event_type: Type of audit event
            payload: Event-specific data
            session_id: Optional session identifier

        Returns:
            True if event was emitted successfully
        """
        return self.audit_client.emit_simple(
            event_type=event_type,
            actor_id=self._agent_id,
            payload=payload,
            actor_type="agent",
            session_id=session_id,
            playbook_id=self.playbook_id,
            project_id=str(self.project_root),
        )

    def _determine_impl_path(self, impl_file: str, description: str) -> Path:
        """
        Determine correct implementation file path based on feature-level requirement.

        Uses project-aware TDD to place files in appropriate subdirectories.
        Prioritizes explicit constraints from Gherkin Background.

        Args:
            impl_file: Suggested filename from LLM (ignored if explicit constraint exists)
            description: Test description (for fallback only)

        Returns:
            Path to implementation file in correct subdirectory
        """
        # Check for explicit constraints first - use constraint's filename, not LLM's
        if self._explicit_file_path:
            explicit_path = Path(self._explicit_file_path)
            # Use the filename from the explicit constraint
            filename = explicit_path.name
            logger.info(f"📍 Using explicit file path constraint: {self._explicit_file_path}")

            # Ensure the path includes a src/ component
            if str(explicit_path).startswith("src/"):
                # Remove src/ prefix to get relative path within src
                relative_path = (
                    explicit_path.relative_to("src")
                    if "src" in explicit_path.parts
                    else explicit_path
                )
                target_folder = self.src_dir / relative_path.parent
            else:
                # If explicit path doesn't have src/, treat it as relative to src
                target_folder = self.src_dir / explicit_path.parent
            target_folder.mkdir(parents=True, exist_ok=True)
            result_path = target_folder / filename
            return result_path

        # No explicit constraint - use LLM's suggested filename
        filename = Path(impl_file).name

        # Use feature requirement for placement via project structure
        if self._feature_requirement:
            placement_requirement = self._feature_requirement
        else:
            placement_requirement = description

        target_folder_name = self._project_structure.determine_file_placement(placement_requirement)

        # Build the full path
        if target_folder_name.startswith("src/"):
            # Target is a subdirectory like src/broker - use it directly
            impl_dir = self.project_root / target_folder_name
        else:
            # Target is just "src" - use the configured src_dir
            impl_dir = self.src_dir

        impl_dir.mkdir(parents=True, exist_ok=True)
        return impl_dir / filename

    def build_feature(
        self,
        requirement: str,
        gherkin_dir: Path | None = None,
        project_root: Path | None = None,
        source_dir: Path | None = None,
        test_dir: Path | None = None,
    ) -> TDDResult:
        """
        Build complete feature autonomously using TDD.

        Process:
        1. Plan increments (ensemble votes on test sequence)
        2. For each increment:
           - Execute RED → GREEN → REFACTOR → LEARN cycle
        3. Return complete implementation

        Args:
            requirement: Natural language feature description
            gherkin_dir: Optional directory containing .feature file and steps/ for acceptance testing
            project_root: Optional project root directory (overrides instance default)
            source_dir: Optional source directory (overrides instance default)
            test_dir: Optional test directory (overrides instance default)

        Returns:
            TDDResult with all generated files and metrics
        """
        import time

        start_time = time.time()

        # Use provided directories or fall back to instance defaults
        if project_root:
            self.project_root = project_root
        if source_dir:
            self.src_dir = source_dir
        if test_dir:
            self.test_dir = test_dir

        logger.info("=" * 80)
        logger.info(f"AUTONOMOUS TDD: {requirement}")
        logger.info("=" * 80)

        # Read Gherkin scenarios if provided
        gherkin_content = None
        gherkin_scenarios = None
        if gherkin_dir:
            feature_file = (
                list(gherkin_dir.glob("*.feature"))[0]
                if list(gherkin_dir.glob("*.feature"))
                else None
            )
            if feature_file:
                gherkin_content = self._read_gherkin_scenarios(feature_file)
                gherkin_scenarios = self._parse_gherkin_scenarios(gherkin_content)
                logger.info(
                    f"\n💡 Using GHERKIN-DRIVEN planning ({len(gherkin_scenarios)} scenarios)"
                )
                logger.info(f"📋 Acceptance tests from: {feature_file.name}")

                # Extract explicit class/file constraints from Gherkin Background
                constraints = extract_explicit_constraints(gherkin_content)
                if constraints:
                    self._explicit_class_name = constraints.get("class_name")
                    self._explicit_file_path = constraints.get("file_path")
                    logger.info(
                        f"🎯 Extracted explicit constraints: class={self._explicit_class_name}, path={self._explicit_file_path}"
                    )
            else:
                logger.info("\n💡 Using EMERGENT test planning (each cycle informs the next)")
        else:
            logger.info("\n💡 Using EMERGENT test planning (each cycle informs the next)")

        # Store feature requirement for placement decisions
        self._feature_requirement = requirement

        # Seed test_functions from any files already on disk so the agent is
        # aware of work done in previous runs (context continuity).
        self._load_existing_context()

        # Execute TDD cycles with emergent planning
        results = []
        cycle_number = 1

        while cycle_number <= self.max_iterations:
            # Determine next test based on current state
            logger.info(f"\n{'─' * 80}")
            logger.info(f"[Cycle {cycle_number}] Determining next test...")
            logger.info("─" * 80)

            increment = self._determine_next_increment(
                requirement,
                cycle_number,
                gherkin_context=gherkin_content,
                gherkin_scenarios=gherkin_scenarios,
            )

            # Check if requirement is satisfied
            if increment is None:
                logger.info(f"\n✅ Requirement satisfied after {cycle_number - 1} cycles")
                break

            logger.info(f"  → Next test: {increment.test_name}")
            logger.info(f"  → {increment.description}")

            # Execute TDD cycle
            try:
                cycle_result = self._tdd_cycle(increment, cycle_number=cycle_number)
                results.append(cycle_result)

                if cycle_result.skipped:
                    logger.info("  ⏭️  Cycle skipped (redundant test)")
                else:
                    logger.info("  ✅ Cycle complete")
            except Exception as e:
                logger.error(f"  ❌ Cycle failed: {e}")
                raise

            # Note: Acceptance tests (step definitions) can be added later for end-to-end verification
            # For now, we rely on comprehensive unit tests generated from Gherkin scenarios

            cycle_number += 1

        if cycle_number > self.max_iterations:
            logger.warning(f"\n⚠️  Reached max_iterations ({self.max_iterations}), stopping")

        # Step 3: Final validation
        logger.info(f"\n{'─' * 80}")
        logger.info("[Final Validation] Running all tests...")
        logger.info("─" * 80)

        final_result = self._run_tests()
        if not final_result.all_passed:
            # Record feature-level failure for self-healing
            failure_context = FailureContext(
                feature_requirement=self._feature_requirement or feature_requirement,
                cycle_number=len(results),
                error_message=f"Final validation failed: {final_result.failed_count} tests failing",
                error_type="FeatureIncomplete",
                model=self.llm_client.model,
                provider=self.llm_client.provider,
            )
            self.failure_recorder.record_failure(
                failure_context,
                suggested_fix="Review all cycle implementations for regressions",
            )
            raise RuntimeError(f"Feature incomplete: {final_result.failed_count} tests failing")

        logger.info(f"  ✅ All tests passing ({final_result.test_count} tests)")

        # Collect results
        total_bullets = sum(len(r.learned_bullets) for r in results)
        skipped_count = sum(1 for r in results if r.skipped)
        completed_count = len(results) - skipped_count
        elapsed = time.time() - start_time

        logger.info("\n" + "=" * 80)
        logger.info("✅ FEATURE COMPLETE!")
        logger.info("=" * 80)
        logger.info(
            f"  • Cycles executed: {len(results)} ({completed_count} completed, {skipped_count} skipped)"
        )
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
            total_time_seconds=elapsed,
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

        # Build constraint section for prompt
        constraint_section = ""
        if self._explicit_class_name or self._explicit_file_path:
            constraint_section = "\n**🎯 CRITICAL CONSTRAINTS FROM FEATURE REQUIREMENT:**\n"
            if self._explicit_file_path:
                constraint_section += (
                    f"- Implementation file MUST be placed at: {self._explicit_file_path}\n"
                )
            if self._explicit_class_name:
                constraint_section += (
                    f"- You MUST create a class named: {self._explicit_class_name}\n"
                )
            constraint_section += (
                "**These constraints are non-negotiable - follow them exactly.**\n"
            )

        prompt = f"""You are planning incremental tests for TDD (Test-Driven Development).

**Requirement**: {requirement}
{constraint_section}
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

            # Ensure paths are under test_dir and use smart placement for impl
            test_path = self.test_dir / Path(test_file).name
            impl_path = self._determine_impl_path(impl_file, description)

            increments.append(
                TestIncrement(
                    test_name=test_name,
                    description=description,
                    test_file=test_path,
                    implementation_file=impl_path,
                )
            )

        if not increments:
            logger.warning("No increments parsed from LLM response")
            logger.warning(f"Response was:\n{response}")
            raise ValueError(
                "Failed to parse test increments from LLM response. "
                "Expected pipe-separated format: test_name | description | test_file | impl_file"
            )

        return increments

    def _load_existing_context(self) -> None:
        """Populate self.test_functions from test files already on disk.

        Called once at the start of build_feature so re-runs are aware of
        code written in previous sessions. Only loads files not already tracked.
        """
        import ast

        for test_file in self.test_dir.glob("test_*.py"):
            file_key = str(test_file)
            if file_key in self.test_functions:
                continue  # already tracked from this session

            source = test_file.read_text()
            try:
                tree = ast.parse(source)
            except SyntaxError:
                logger.warning(f"_load_existing_context: skipping unparseable file {test_file.name}")
                continue

            functions: list[dict] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    # Extract the raw source lines for this function
                    lines = source.splitlines()
                    start = node.lineno - 1
                    end = node.end_lineno
                    code = "\n".join(lines[start:end])
                    functions.append({"cycle": 0, "name": node.name, "code": code})

            if functions:
                self.test_functions[file_key] = functions
                logger.info(
                    f"  📂 Loaded {len(functions)} existing test(s) from {test_file.name}"
                )

    def _get_existing_test_summaries(self) -> str:
        """Generate summary of existing tests and implementation to help avoid redundancy.

        Returns:
            String listing what each existing test checks and what implementation exists
        """
        summaries = []

        # Part 1: Existing tests and their assertions
        if self.test_functions:
            summaries.append("**Tests already written:**")
            for test_file_key, functions in self.test_functions.items():
                test_file_name = Path(test_file_key).name
                summaries.append(f"\n{test_file_name}:")
                for func in functions:
                    # Extract what the test checks from the code
                    code = func["code"]
                    # Look for assert statements to understand what's being tested
                    assert_lines = [line.strip() for line in code.split("\n") if "assert" in line]
                    if assert_lines:
                        checks = " | ".join(assert_lines[:2])  # First 2 assertions
                        summaries.append(f"  - {func['name']}: {checks}")
                    else:
                        summaries.append(f"  - {func['name']}")
        else:
            summaries.append("**Tests already written:** None yet")

        # Part 2: Existing implementation details
        impl_files = self._collect_implementation_files()
        if impl_files:
            summaries.append("\n**Implementation already contains:**")
            for impl_file in impl_files:
                if impl_file.name != "__init__.py" and impl_file.name != "__pycache__":
                    content = impl_file.read_text()
                    # Extract class definitions and attributes
                    import re

                    # Find class definitions
                    classes = re.findall(r"class\s+(\w+)", content)

                    # Find instance attributes (self.xxx =)
                    attributes = re.findall(r"self\.(\w+)\s*=", content)

                    # Find method definitions
                    methods = re.findall(r"def\s+(\w+)\s*\(", content)

                    summaries.append(f"\n{impl_file.name}:")
                    if classes:
                        summaries.append(f"  - Classes: {', '.join(set(classes))}")
                    if attributes:
                        summaries.append(
                            f"  - Attributes: {', '.join(f'self.{a}' for a in set(attributes))}"
                        )
                    if methods:
                        # Filter out __init__ and private methods for brevity
                        public_methods = [m for m in set(methods) if not m.startswith("_")]
                        if public_methods:
                            summaries.append(f"  - Methods: {', '.join(public_methods)}")
        else:
            summaries.append("\n**Implementation already contains:** Nothing yet")

        return "\n".join(summaries)

    def _build_existing_tests_list(self) -> list[ExistingTest]:
        """Build list of ExistingTest objects for redundancy pre-check."""
        existing_tests = []
        for test_file_key, functions in self.test_functions.items():
            for func in functions:
                code = func["code"]
                assertions = [line.strip() for line in code.split("\n") if "assert" in line.lower()]
                existing_tests.append(
                    ExistingTest(name=func["name"], assertions=assertions, file_path=test_file_key)
                )
        return existing_tests

    def _get_tdd_lessons(self, phase: str) -> str:
        """Return formatted TDD lessons for the given phase.

        Args:
            phase: One of 'red', 'green', or 'planning'

        Returns:
            Formatted markdown string containing relevant TDD lessons
        """
        return self._tdd_lesson_injector.get_lessons_for_phase(phase)

    def _determine_next_increment(
        self,
        requirement: str,
        cycle_number: int,
        gherkin_context: str | None = None,
        gherkin_scenarios: list[dict] | None = None,
    ) -> TestIncrement | None:
        """
        Determine the next test increment based on current implementation state.

        This implements:
        - GHERKIN-DRIVEN: When scenarios provided, derive tests from Given/When/Then steps
        - EMERGENT: When no Gherkin, each cycle informs what the next test should be

        Args:
            requirement: Original feature requirement
            cycle_number: Current cycle number
            gherkin_context: Optional raw Gherkin content for context
            gherkin_scenarios: Optional parsed Gherkin scenarios for driving test generation

        Returns:
            Next TestIncrement to implement, or None if requirement is satisfied
        """
        # Analyze current state
        existing_tests = self._collect_test_files()
        existing_impl = self._collect_implementation_files()

        # Get test summaries for redundancy checking
        test_summaries = self._get_existing_test_summaries()

        # Retrieve learned redundancy patterns from playbook
        redundancy_patterns = self._get_playbook_guidance(
            query="test redundancy anti-patterns avoid", top_k=3
        )

        # Build context about what exists
        test_context = ""
        if existing_tests:
            test_context = "\n**Existing tests:**\n"
            for test_file in existing_tests:
                if test_file.name != "__pycache__":
                    content = test_file.read_text()
                    test_context += f"\n{test_file.name}:\n```python\n{content}\n```\n"

        impl_context = ""
        if existing_impl:
            impl_context = "\n**Existing implementation:**\n"
            for impl_file in existing_impl:
                if impl_file.name != "__init__.py" and impl_file.name != "__pycache__":
                    content = impl_file.read_text()
                    impl_context += f"\n{impl_file.name}:\n```python\n{content}\n```\n"

        # Add Gherkin context if provided
        gherkin_section = ""
        if gherkin_scenarios and gherkin_context:
            # Build a structured view of scenarios
            scenarios_summary = []
            for idx, scenario in enumerate(gherkin_scenarios, 1):
                scenario_text = f"{idx}. **{scenario['name']}**\n"
                for step in scenario["steps"]:
                    scenario_text += f"   {step['type']}: {step['text']}\n"
                scenarios_summary.append(scenario_text)

            gherkin_section = f"""
**🎯 GHERKIN-DRIVEN ATDD - Business Requirements:**
```gherkin
{gherkin_context}
```

**Parsed Scenarios ({len(gherkin_scenarios)} total):**
{"".join(scenarios_summary)}

**CRITICAL - Generate Unit Tests from Gherkin:**
Each Gherkin scenario defines a business capability. Your task is to derive unit tests that:
1. Verify the behaviors described in the Given/When/Then steps
2. Test the implementation needed to satisfy each scenario
3. Focus on the CONTRACT (what the API should do) not implementation details

**Example Mapping:**
```
Scenario: User grants application access
  When: I redirect them to the OAuth provider with required parameters
  Then: they should see a valid authorization URL

→ Unit Test: test_generate_authorization_url_returns_valid_url()
→ Unit Test: test_authorization_url_includes_required_parameters()
```

**Your TDD tests should enable the Gherkin scenarios to pass.**
"""
        elif gherkin_context:
            # Fallback if parsing failed
            gherkin_section = f"""
**Acceptance Tests (Gherkin):**
```gherkin
{gherkin_context}
```
"""

        prompt = f"""You are following TDD (Test-Driven Development) to build: "{requirement}"

**Current state (Cycle {cycle_number}):**
{test_context if test_context else "No tests written yet."}
{impl_context if impl_context else "No implementation yet."}
{gherkin_section}

{test_summaries}

{self._get_tdd_lessons("planning")}

**🧠 LEARNED REDUNDANCY PATTERNS (from past failures):**
{redundancy_patterns if redundancy_patterns.strip() else "No redundancy patterns learned yet."}

⚡ **IMPORTANT - FILE AND CLASS PLACEMENT CONSTRAINTS**:"""

        # Add explicit constraints if they exist
        if self._explicit_class_name or self._explicit_file_path:
            prompt += "\n"
            if self._explicit_file_path:
                prompt += f"- Implementation file MUST be placed at: `{self._explicit_file_path}`\n"
            if self._explicit_class_name:
                prompt += f"- You MUST create a class named: `{self._explicit_class_name}`\n"
            prompt += "**These constraints are non-negotiable - follow them exactly.**\n\n"
        else:
            prompt += "\nNo explicit placement constraints specified.\n\n"

        prompt += f"""⚠️  **CRITICAL - AVOID REDUNDANT TESTS**: The next test you choose MUST:
1. Test NEW behavior not already covered by tests OR implementation above
2. FAIL with the current implementation (for RED phase)
3. NOT test attributes/methods that already exist in the implementation
4. NOT duplicate or overlap with existing test assertions

**Examples of REDUNDANT tests to AVOID:**
- If implementation has `self.client_id` → DON'T test: `assert oauth.client_id == value`
- If implementation has `def get_token()` → DON'T test creation of `get_token()` method
- If test already checks `is not None` → DON'T add another `is not None` test

**Examples of GOOD next tests:**
- If implementation has basic constructor → Test a NEW method that doesn't exist yet
- If implementation has method A → Test a NEW method B
- If implementation returns hardcoded value → Test that it derives value correctly

**Task**: Determine the NEXT SINGLE test to write.

**TDD Principles:**
1. If nothing exists yet → Start with simplest test (can we create the main object?)
2. If we have basic creation → What's the FIRST behavior it should have?
3. Look at what's implemented → What's the NEXT SMALLEST step?
4. Each test discovers ONE new piece of the API
5. Build incrementally (don't jump ahead to complex features)
6. **If Gherkin scenarios provided → Create TDD tests that match Gherkin step granularity**
   - Each Gherkin "Then" step = roughly one TDD test
   - Map acceptance criteria directly to unit tests
   - Follow the incremental progression shown in Gherkin
7. **AVOID tests that check behavior already verified by existing tests**
8. **ONE BEHAVIOR PER TEST** - If a test would verify 5+ things, split it into 5 tests

**CRITICAL Decision:**
- If the requirement is SATISFIED (all core functionality working), output: COMPLETE
- Otherwise, output the next test in this format:

test_name | description | test_file_path | impl_file_path

**Examples of good progression:**
Cycle 1: test_calculator_can_be_created | Create Calculator instance | tests/test_calculator.py | src/calculator.py
Cycle 2: test_calculator_has_add_method | Calculator should have add method | tests/test_calculator.py | src/calculator.py
Cycle 3: test_add_returns_sum | add(2, 3) should return 5 | tests/test_calculator.py | src/calculator.py

**YOUR TASK**: What is the next test for cycle {cycle_number}?

Output EITHER:
- "COMPLETE" if requirement is satisfied
- ONE line in format: test_name | description | test_file_path | impl_file_path
"""

        # Get next increment from LLM
        response_dict = self.llm_client.generate(prompt)
        response = response_dict["content"].strip()

        # Check if complete
        if "COMPLETE" in response.upper() and "|" not in response:
            logger.info("  ✓ LLM determined requirement is satisfied")
            return None

        # Parse response
        lines = [
            line.strip()
            for line in response.split("\n")
            if "|" in line and not line.startswith("#")
        ]
        if not lines:
            logger.warning(f"Could not parse next increment from: {response}")
            return None

        line = lines[0]  # Take first valid line
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 4:
            logger.warning(f"Invalid increment format: {line}")
            return None

        test_name, description, test_file, impl_file = parts

        # Ensure paths are under test_dir and use smart placement for impl
        test_path = self.test_dir / Path(test_file).name
        impl_path = self._determine_impl_path(impl_file, description)

        return TestIncrement(
            test_name=test_name,
            description=description,
            test_file=test_path,
            implementation_file=impl_path,
        )

    def _tdd_cycle(self, increment: TestIncrement, cycle_number: int) -> CycleResult:
        """
        Execute one TDD cycle: RED → GREEN → REFACTOR → LEARN.

        Args:
            increment: Test increment to implement
            cycle_number: Current cycle number

        Returns:
            CycleResult with all artifacts
        """
        # PRE-CHECK: Detect redundancy BEFORE writing test code
        existing_tests = self._build_existing_tests_list()
        proposed = ProposedTest(name=increment.test_name, description=increment.description)
        redundancy_result = self.redundancy_checker.check(existing_tests, proposed)

        if redundancy_result.is_redundant:
            logger.info(
                f"  ⏭️  PRE-CHECK: Skipping redundant test (confidence: {redundancy_result.confidence:.0%})"
            )
            logger.info(f"      Reason: {redundancy_result.reason}")

            # Return skipped cycle without writing any code
            return CycleResult(
                increment=increment,
                test_code="",
                implementation_code="",
                red_result=TestResult(passed=True, failed=False, output="Pre-check: redundant"),
                green_result=TestResult(passed=True, failed=False, output="Pre-check: redundant"),
                refactored=False,
                learned_bullets=[],
                cycle_number=cycle_number,
                skipped=True,
                skip_reason=f"Pre-check redundancy: {redundancy_result.reason}",
            )

        # RED: Write failing test
        logger.info("  🔴 RED: Writing failing test...")
        try:
            test_code = self._write_test(increment, cycle_number)
        except ValueError as exc:
            logger.warning(f"  ⏭️  Skipping cycle — LLM could not generate a valid test: {exc}")
            return CycleResult(
                increment=increment,
                test_code="",
                implementation_code="",
                red_result=TestResult(passed=True, failed=False, output=str(exc)),
                green_result=TestResult(passed=True, failed=False, output=str(exc)),
                refactored=False,
                learned_bullets=[],
                cycle_number=cycle_number,
                skipped=True,
                skip_reason=f"LLM test generation failed: {exc}",
            )
        logger.info(f"      Created: {increment.test_file.relative_to(self.project_root)}")

        red_result = self._run_tests()

        # RED PHASE REFINEMENT: If test passes, refine it to make it fail (proper TDD)
        MAX_RED_REFINEMENTS = 3
        refinement_attempt = 0

        while not red_result.failed and refinement_attempt < MAX_RED_REFINEMENTS:
            refinement_attempt += 1

            logger.info(
                f"  ⚠️  Test passed unexpectedly (attempt {refinement_attempt}/{MAX_RED_REFINEMENTS})"
            )
            logger.info("  🧠 LEARN: Analyzing redundancy pattern...")

            # Analyze why test is redundant
            redundancy_bullet = self._analyze_redundancy_pattern(increment, test_code)

            # Store bullet in playbook for future learning (only on first refinement)
            if refinement_attempt == 1:
                from src.storage.schemas import BulletCreate

                bullet_data = BulletCreate(
                    content=redundancy_bullet,
                    section="strategies_and_hard_rules",  # Anti-patterns are strategic rules
                    tags=["test_redundancy", "anti_pattern", "tdd"],
                    created_by_model=self.llm_client.model,
                    model_provider=self.llm_client.provider,
                    license_type=self._get_license_type(
                        self.llm_client.provider, self.llm_client.model
                    ),
                    # Low initial confidence - needs validation via feedback
                    confidence_score=0.3,
                    applicable_domains=["tdd"],
                    project_ids=[str(self.project_root)],
                )
                if self.playbook_manager is not None:
                    self.playbook_manager.add_bullet(self.playbook_id, bullet_data)
                    logger.info("      Stored redundancy pattern")

            # Refine test to make it more specific/strict
            logger.info("  🔧 REFINING: Strengthening test to make it fail...")
            refined_test_code = self._refine_test_to_fail(
                increment=increment,
                test_code=test_code,
                redundancy_analysis=redundancy_bullet,
                attempt=refinement_attempt,
            )

            # Update test code and test_functions array
            test_code = refined_test_code
            test_file_key = str(increment.test_file)

            # Update the stored test function
            if test_file_key in self.test_functions:
                for func_data in self.test_functions[test_file_key]:
                    if func_data["name"] == increment.test_name:
                        func_data["code"] = refined_test_code
                        break

            # Reassemble test file with refined test
            self._assemble_test_file(increment.test_file, increment.implementation_file)
            logger.info("      ✓ Test refined and reloaded")

            # Retry RED phase with refined test
            red_result = self._run_tests()

        # After refinement loop, check if test finally fails
        if not red_result.failed:
            skip_reason = (
                f"Test passed after {MAX_RED_REFINEMENTS} refinement attempts, "
                f"indicating the behavior is already fully implemented."
            )
            logger.info(f"  ⏭️  SKIPPING: {skip_reason}")
            logger.info("  ✓ Moving to next increment...")

            # Return a skipped cycle result
            return CycleResult(
                increment=increment,
                test_code=test_code,
                implementation_code="",  # No new implementation needed
                red_result=red_result,
                green_result=red_result,  # Reuse red_result since we didn't run GREEN
                refactored=False,
                learned_bullets=[],
                cycle_number=cycle_number,
                skipped=True,
                skip_reason=skip_reason,
            )

        logger.info("  ⚙️  Running tests... FAILED (expected)")

        # GREEN: Write minimal code (with retry logic and in-loop learning)
        logger.info("  🟢 GREEN: Writing minimal code...")
        MAX_GREEN_RETRIES = 3
        green_result = None
        previous_impl_code = None
        latest_bullets_used: list[str] = []

        for attempt in range(1, MAX_GREEN_RETRIES + 1):
            if attempt > 1:
                logger.info(
                    f"  🔄 GREEN retry {attempt}/{MAX_GREEN_RETRIES} (previous implementation failed)..."
                )

                # LEARN from previous failure BEFORE next attempt
                logger.info(f"  🧠 LEARN: Analyzing attempt {attempt - 1} failure...")
                failure_analysis = self._analyze_green_failure(
                    increment=increment,
                    test_code=test_code,
                    impl_code=previous_impl_code,
                    error=green_result.error,
                    attempts=attempt - 1,
                )

                if failure_analysis and self.playbook_manager is not None:
                    # Route through Curator so redundancy checking and token
                    # budget enforcement apply, rather than bypassing via add_bullet().
                    curator_output = CuratorOutput(
                        delta_bullets=[DeltaBullet(
                            section="troubleshooting",
                            content=failure_analysis["bullet"],
                            tags=failure_analysis["tags"],
                        )],
                        reasoning=failure_analysis["summary"],
                    )
                    self.curator.apply_updates(self.playbook_id, curator_output)
                    logger.info(f"      ✓ Stored: {failure_analysis['summary']}")

                    # If test correction is suggested, APPLY IT automatically
                    if failure_analysis.get("test_correction"):
                        logger.info("      🔧 Applying test correction...")
                        corrected = self._apply_test_correction(
                            increment.test_file,
                            increment.implementation_file,
                            increment.test_name,
                            test_code,
                            failure_analysis["test_correction"],
                            cycle_number,
                        )
                        if corrected:
                            test_code = increment.test_file.read_text()  # Reload corrected test
                            logger.info("      ✓ Test corrected and reloaded")
                        else:
                            logger.warning(
                                "      ⚠️  Test correction failed, continuing with original test"
                            )

            impl_code, latest_bullets_used = self._write_minimal_code(
                increment, red_result, previous_failure=green_result, attempt=attempt
            )
            previous_impl_code = impl_code  # Save for learning if this attempt fails
            logger.info(
                f"      Created: {increment.implementation_file.relative_to(self.project_root)}"
            )

            # ATDD: No triangulation enforcement - allow comprehensive implementations
            # (Triangulation validation removed - conflicts with contract-based testing)

            green_result = self._run_tests()
            if green_result.all_passed:
                logger.info("  ⚙️  Running tests... PASSED ✓")
                break
            else:
                logger.warning(f"  ⚠️  Tests still failing: {green_result.error[:100]}...")

        if not green_result.all_passed:
            # Record failure for self-healing before raising
            failure_context = FailureContext(
                feature_requirement=self._feature_requirement or increment.description,
                cycle_number=cycle_number,
                error_message=green_result.error,
                error_type="GreenPhaseFailure",
                test_file=str(increment.test_file),
                impl_file=str(increment.implementation_file),
                explicit_class_name=self._explicit_class_name,
                explicit_file_path=self._explicit_file_path,
                model=self.llm_client.model,
                provider=self.llm_client.provider,
            )
            self.failure_recorder.record_failure(
                failure_context,
                suggested_fix=f"Review test expectations and implementation for cycle {cycle_number}",
            )

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
        if self.skip_learn:
            logger.info("  🧠 LEARN: skipped (--no-learn)")
            learned_bullets = []
        else:
            logger.info("  🧠 LEARN: Ensemble reviewing cycle...")
            learned_bullets = self._ensemble_learn(test_code, impl_code, increment)
            logger.info(f"      {len(learned_bullets)} patterns approved")

        # LOG: Record TDD cycle to experiment_logs
        logger.info("  📊 LOG: Recording cycle to experiment_logs...")
        try:
            self.experiment_logger.log_tdd_cycle(
                cycle_number=cycle_number,
                requirement=increment.description,
                test_name=increment.test_name,
                test_code=test_code,
                implementation_code=impl_code,
                red_passed=not red_result.failed,
                green_passed=green_result.all_passed,
                red_output=red_result.output[:500] if red_result.output else "",
                green_output=green_result.output[:500] if green_result.output else "",
                learned_bullets=[
                    {
                        "content": bullet.content,
                        "section": bullet.section,
                        "tags": bullet.tags or [],
                    }
                    for bullet in learned_bullets
                ],
                playbook_id=self.playbook_id,
                retrieved_bullet_ids=latest_bullets_used,
                # Model attribution for production quality analysis
                actual_model=self.llm_client.model,
                requested_model=self.llm_client.model,
                provider=self.llm_client.provider,
            )
            logger.info("      ✓ Cycle logged successfully")
        except Exception as e:
            logger.warning(f"      ⚠️  Failed to log cycle: {e}")

        return CycleResult(
            increment=increment,
            test_code=test_code,
            implementation_code=impl_code,
            red_result=red_result,
            green_result=green_result,
            refactored=refactored,
            learned_bullets=learned_bullets,
            cycle_number=cycle_number,
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
        existing_code = (
            "\n\n".join([f["code"] for f in existing_functions]) if existing_functions else ""
        )

        # Get learned patterns from playbook
        playbook_guidance = self._get_playbook_guidance(
            query=f"TDD test writing {increment.test_name} {increment.description}", top_k=3
        )

        prompt = f"""You are writing a test following TDD (Test-Driven Development).

{playbook_guidance}

{self._get_tdd_lessons("red")}

🎯 **CRITICAL - Single Behavior Test:**
This test should verify EXACTLY ONE observable behavior.
Think: "If this was a Gherkin step, what would it say?"
Example: "Then the URL should contain the client_id parameter" → ONE assertion about client_id

**Project Structure**:
- Tests in: {self.test_dir.name}/
- Implementation in: {self.src_dir.name}/
- Imports automatically included: `pytest`, `Mock`, `patch`, `MagicMock`, and the implementation module
- You can use `patch()`, `Mock()`, `MagicMock()` directly without importing them

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

**TDD Test Quality - ONE BEHAVIOR RULE**:

✅ **GOOD - Single Behavior Tests**:
```python
def test_returns_access_token():
    result = oauth.exchange_code("code")
    assert "access_token" in result  # ← ONE thing

def test_url_contains_client_id():
    url = oauth.generate_url(...)
    assert "client_id=" in url  # ← ONE thing
```

❌ **BAD - Multiple Behaviors**:
```python
def test_everything_at_once():
    result = oauth.exchange_code("code")
    assert result["access_token"]  # ← Testing 5+ things
    assert result["refresh_token"]
    assert result["expires_in"]
    assert mock.called
    assert mock.call_args[0][0] == url
```

**Key Rules**:
1. **ONE assertion** (or 2-3 closely related assertions max)
2. **Happy path first** - No error handling in early tests
3. **Test observable behavior** - Not implementation details
4. **Match Gherkin granularity** - Each test like a Gherkin step
5. Write ONLY the test function (imports added automatically)
6. FOLLOW existing patterns from tests above
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

        # Test quality validation loop - retry up to 3 times if test has too many behaviors
        MAX_QUALITY_RETRIES = 3
        quality_validation_feedback = ""

        for quality_attempt in range(1, MAX_QUALITY_RETRIES + 1):
            # Generate test code
            if quality_attempt == 1:
                # First attempt - use original prompt
                full_prompt = prompt
            else:
                # Retry with quality feedback
                full_prompt = f"{quality_validation_feedback}\n\n{prompt}"

            response_dict = self.llm_client.generate(full_prompt)
            response = response_dict["content"]

            # Extract code from response
            test_function = extract_code(response)

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

            # ATDD: Allow comprehensive tests with multiple assertions
            # (Validation disabled to support contract-based testing)
            is_valid = True  # self._validate_test_quality(test_function, increment.test_name)

            if is_valid:
                # Test accepted
                break

        # Store in array for cycle isolation
        if test_file_key not in self.test_functions:
            self.test_functions[test_file_key] = []

        self.test_functions[test_file_key].append(
            {"cycle": cycle_number, "name": increment.test_name, "code": test_function}
        )

        # Assemble complete file from all stored functions
        self._assemble_test_file(increment.test_file, increment.implementation_file)

        return test_function

    def _write_minimal_code(
        self,
        increment: TestIncrement,
        test_result: TestResult,
        previous_failure: TestResult = None,
        attempt: int = 1,
    ) -> tuple[str, list[str]]:
        """
        Write minimal code to make test pass (GREEN phase).

        Args:
            increment: Test specification
            test_result: Result of failed test (RED phase)
            previous_failure: Previous GREEN phase failure (for retry feedback)
            attempt: Current attempt number (1-3) for retry awareness

        Returns:
            Generated implementation code
        """
        # Check if implementation exists
        existing_code = ""
        if increment.implementation_file.exists():
            existing_code = increment.implementation_file.read_text()

        # Read test code
        test_code = increment.test_file.read_text()

        prompt = f"""You are following ATDD (Acceptance Test-Driven Development): write code to satisfy the test contract.

**🎯 ATDD APPROACH - Contract-Based Implementation:**
Write comprehensive, production-quality code that satisfies the test's contract (behavior specification).
- Focus on making the test PASS with correct, maintainable code
- Implement the full behavior needed by the test
- Use appropriate algorithms, data structures, and libraries
- Write code you'd be proud to deploy to production

**⚠️ ATTEMPT {attempt}/3** {
            "- 🚨 THIS IS YOUR FINAL ATTEMPT! 🚨"
            if attempt == 3
            else f"- You have {4 - attempt} attempt{'s' if 4 - attempt > 1 else ''} remaining if this fails"
        }
{
            "🚨 CRITICAL: The cycle will FAIL if this implementation does not pass the test. There are NO more retries after this."
            if attempt == 3
            else "⚠️ IMPORTANT: Get this right the FIRST time. While you have retries, each failed attempt wastes time and resources."
        }

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
{
            ""
            if not previous_failure
            else f'''
**Previous implementation error** (attempt {attempt - 1} failed):
```
{previous_failure.error or previous_failure.output}
```

**What went wrong**: The implementation you provided didn't satisfy the test assertion.
**Action needed**: {"CAREFULLY review the error above and the test requirements below." if attempt == 3 else "Fix the implementation to make the test pass. Pay close attention to the error message above."}
'''
        }

**PRE-FLIGHT CHECKLIST** (verify before writing code):
1. ✓ Read the test code above - what class/function names does it use?
2. ✓ What parameters does the test pass to __init__ or functions?
3. ✓ What methods does the test call?
4. ✓ What specific assertions must pass?
5. ✓ If existing code exists, what must be preserved?

**Task**: Write the MINIMAL implementation code to make THIS test pass.

**TRUE TDD Discipline - CRITICAL Rules**:

**STATE and INITIALIZATION**:
1. ✅ If test creates object with parameters → Store them in __init__
   - Example: `OAuth('client_123', 'http://callback')` → __init__ must save these
2. ✅ Methods must USE stored instance variables, not hardcoded values
   - ❌ BAD: `return "http://example.com/auth"`
   - ✅ GOOD: `return f"{{self.auth_url}}?client_id={{self.client_id}}"`

**INCREMENTAL Building**:
3. ✅ If method exists → ENHANCE it for new test, don't rewrite
   - Add ONE small thing (parameter, check, field) to make new test pass
4. ✅ If method doesn't exist → Add it with minimal implementation
5. ✅ Keep ALL existing code (add to it, never delete/replace)

**TRIANGULATION - Start Simple, Add Complexity Gradually**:
6. **Test 1 → HARDCODE** (Yes, really!):
   - ✅ `return {{"access_token": "fake_token"}}` ← Literal value is OK!
   - ✅ `return "https://auth.example.com?client_id=123"` ← Hardcoded OK!

7. **Test 2 → Minimal Logic** (Now make it work for both tests):
   - ✅ Use simple if/else: `return "token_a" if code == "a" else "token_b"`
   - ✅ Or basic string building: `return f"token_{{auth_code}}"`

8. **Test 3+ → Generalize** (Now you can abstract):
   - ✅ Now add proper logic, validation, API calls
   - ✅ Extract helpers, handle edge cases

**SCOPE**:
8. ❌ Don't add features for future tests
9. ❌ Don't add "nice to have" features
10. ❌ Don't over-engineer
11. ❌ NEVER include test code in implementation file

**Example - TRUE Triangulation Progression**:

**Cycle 1 - Test**:
```python
def test_get_token_returns_access_token():
    result = oauth.get_token()
    assert result["access_token"] == "token_123"
```
**Cycle 1 - Implementation** (HARDCODED!):
```python
def get_token(self):
    return {{"access_token": "token_123"}}  # ← Hardcoded literal!
```

**Cycle 2 - Test** (Forces different value):
```python
def test_get_token_with_different_code():
    result = oauth.get_token("code_abc")
    assert result["access_token"] == "token_abc"
```
**Cycle 2 - Implementation** (Minimal logic):
```python
def get_token(self, code=""):
    if not code:
        return {{"access_token": "token_123"}}
    return {{"access_token": f"token_{{code}}"}}  # ← Now using input!
```

**Cycle 3 - Test** (Forces real API call):
```python
def test_get_token_makes_api_request():
    with patch("requests.post") as mock:
        result = oauth.get_token("code")
        assert mock.called
```
**Cycle 3 - Implementation** (NOW generalize):
```python
def get_token(self, code=""):
    response = requests.post(self.token_url, data={{"code": code}})
    return response.json()  # ← Real implementation!
```

**Cycle 2 - Test**:
```python
def test_get_auth_url_includes_client_id():
    oauth = OAuth('client_123', 'http://callback.com')
    url = oauth.get_auth_url()
    assert 'client_id=client_123' in url
```
**Cycle 2 - Implementation** (Use stored state!):
```python
class OAuth:
    def __init__(self, client_id, redirect_uri):
        self.client_id = client_id
        self.redirect_uri = redirect_uri

    def get_auth_url(self):
        return f"http://auth.example.com?client_id={{self.client_id}}"
```

**Cycle 3 - Test** (Refine existing method):
```python
def test_get_auth_url_includes_redirect_uri():
    oauth = OAuth('client_123', 'http://callback.com')
    url = oauth.get_auth_url()
    assert 'redirect_uri=http://callback.com' in url
```
**Cycle 3 - Implementation** (Enhance existing method):
```python
class OAuth:
    def __init__(self, client_id, redirect_uri):
        self.client_id = client_id
        self.redirect_uri = redirect_uri

    def get_auth_url(self):
        return f"http://auth.example.com?client_id={{self.client_id}}&redirect_uri={{self.redirect_uri}}"
```

**Output**: Complete implementation file content (production code only, no test code).
"""

        task = TaskInput(
            id=f"green_{increment.test_name}_{attempt:03d}",
            query=prompt,
            type="code_generation",
        )
        gen_output = self.generator.execute(task, self.playbook_id)
        impl_code = extract_code(gen_output.solution)
        bullets_used = gen_output.bullets_used

        # Validate and fix import paths
        try:
            impl_code, corrections = self._import_validator.validate_and_fix(impl_code)
            if corrections:
                logger.info(f"Fixed {len(corrections)} import path(s) in generated code")
                for old_imp, new_imp in corrections:
                    logger.info(f"  {old_imp} -> {new_imp}")
        except Exception as e:
            logger.warning(f"Import validation failed: {e}")

        # Write to file
        increment.implementation_file.write_text(impl_code)

        return impl_code, bullets_used

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
        self, test_code: str, impl_code: str, increment: TestIncrement
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
            logger.warning(
                f"  ⚠️  Test quality low ({test_review.overall_score:.0%}), skipping learning"
            )
            return []

        # Use standard ACE learning flow
        import uuid

        from src.storage.schemas import EnvironmentFeedback

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
            },
        )

        feedback = EnvironmentFeedback(
            result="SUCCESS",
            actual="Tests passed",
            test_report={"test_quality": test_review.overall_score},
        )

        # Run ensemble learning (single model auto-approves)
        result = self.ensemble.learn_from_task(task, feedback, parallel=False)

        # Save approved bullets to playbook
        self.ensemble.add_approved_bullets_to_playbook(result)

        # Return approved bullets only
        return result.approved_bullets

    def _get_playbook_guidance(
        self,
        query: str,
        top_k: int = 5,
        min_confidence: float = 0.5,
        domain: str | None = None,
        project_id: str | None = None,
    ) -> str:
        """
        Retrieve relevant playbook bullets using T-shaped retrieval with confidence gating.

        - Primary: Agent's own playbook (deep domain expertise)
        - Secondary: All other playbooks (broad cross-domain knowledge)
        - Only returns bullets above confidence threshold
        - Filters by domain and project if specified

        Args:
            query: Query to find relevant patterns
            top_k: Number of bullets to retrieve
            min_confidence: Minimum confidence_score threshold (default 0.5)
            domain: Filter to patterns applicable to this domain
            project_id: Filter to patterns applicable to this project

        Returns:
            Formatted string to inject into prompts
        """
        # Skip if no playbook manager (file mode)
        if self.playbook_manager is None:
            return ""

        # Get primary playbook (agent's own domain expertise)
        primary_playbook = self.playbook_manager.get_playbook(self.playbook_id)
        if not primary_playbook:
            return ""

        primary_bullets = []
        for section_name, section_bullets in primary_playbook.sections.items():
            primary_bullets.extend(section_bullets)

        logger.info(
            f"🔍 DEBUG: Primary playbook {self.playbook_id} has {len(primary_bullets)} bullets in memory"
        )

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

        # Cross-playbook retrieval with confidence gating (T-shaped: deep + broad)
        relevant_scored = self.bullet_retriever.retrieve_cross_model(
            query=query,
            primary_bullets=primary_bullets,
            secondary_bullets_by_playbook=secondary_bullets_by_playbook,
            primary_playbook_id=self.playbook_id,
            secondary_weight=0.5,  # Secondary bullets get 50% weight
            min_confidence=min_confidence,
            domain=domain,
            project_id=project_id,
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
        bullets_text = "\n".join(
            [f"- {bullet.content}" for bullet, score, source in relevant_scored[:top_k]]
        )

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
                [sys.executable, "-m", "pytest", str(self.test_dir), "-v", "--tb=short"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                env=env,
                timeout=30,
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
                        error = "\n".join(lines[i : i + 10])
                        break

            return TestResult(
                passed=passed,
                failed=failed,
                output=output,
                error=error,
                test_count=test_count,
                failed_count=failed_count,
            )

        except subprocess.TimeoutExpired:
            return TestResult(
                passed=False, failed=True, output="", error="Test execution timed out (30s)"
            )
        except Exception as e:
            return TestResult(
                passed=False, failed=True, output="", error=f"Test execution failed: {e}"
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

    def _extract_method_from_test_name(self, test_name: str) -> str:
        """
        Extract the method being tested from the test name.

        Args:
            test_name: Test function name (e.g., test_generate_authorization_url_returns_string)

        Returns:
            Method name being tested (e.g., generate_authorization_url) or __init__ for constructor tests
        """
        # Remove 'test_' prefix
        if not test_name.startswith("test_"):
            return test_name  # Fallback

        without_prefix = test_name[5:]  # Remove 'test_'

        # Check for constructor tests
        if any(
            pattern in without_prefix
            for pattern in [
                "can_be_created",
                "can_be_instantiated",
                "constructor",
                "accepts_optional",
            ]
        ):
            return "__init__"

        # Find common action verbs that indicate where the method name ends
        verbs = [
            "returns",
            "contains",
            "accepts",
            "sends",
            "makes",
            "gets",
            "sets",
            "validates",
            "has",
            "is",
            "should",
            "includes",
            "uses",
            "calls",
            "raises",
            "handles",
        ]

        parts = without_prefix.split("_")

        # Find the first verb and everything before it is the method name
        for i, part in enumerate(parts):
            if part in verbs:
                method = "_".join(parts[:i])
                return method if method else parts[0]

        # If no verb found, assume first part is method name
        # This handles cases like test_<method_name>_<specific_case>
        return parts[0] if parts else test_name

    def _validate_test_quality(self, test_code: str, test_name: str) -> tuple[bool, str]:
        """
        Validate that test follows single-behavior principle by counting assertions.

        Args:
            test_code: The test function code to validate
            test_name: Name of the test function

        Returns:
            Tuple of (is_valid, feedback_message)
        """
        try:
            tree = ast.parse(test_code)

            # Find the test function
            test_func = None
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == test_name:
                    test_func = node
                    break

            if not test_func:
                return True, ""  # Can't find function, skip validation

            # Count assertions and mock assertions
            assertion_count = 0
            for node in ast.walk(test_func):
                # Count assert statements
                if isinstance(node, ast.Assert):
                    assertion_count += 1
                # Count mock assertions (assert_called, assert_called_once, etc.)
                elif isinstance(node, ast.Attribute):
                    if node.attr.startswith("assert_"):
                        assertion_count += 1

            # Allow up to 2 assertions (some tests need 2 closely related checks)
            # More than 2 indicates multi-behavior testing
            if assertion_count > 2:
                feedback = f"""
❌ **TEST QUALITY VIOLATION - Multiple Behaviors Detected**

Your test has {assertion_count} assertions, but should verify EXACTLY ONE behavior.

**Current test**: {test_name}
- {assertion_count} assertions found
- This violates the single-behavior principle
- Each assertion should be a SEPARATE test

**Example Fix**:
Instead of:
```python
def test_url_contains_all_params():
    assert "client_id=" in url
    assert "redirect_uri=" in url
    assert "scope=" in url
    assert "state=" in url  # ← 4 behaviors!
```

Write FOUR separate tests:
```python
def test_url_contains_client_id():
    assert "client_id=" in url  # ← ONE behavior

def test_url_contains_redirect_uri():
    assert "redirect_uri=" in url  # ← ONE behavior

def test_url_contains_scope():
    assert "scope=" in url  # ← ONE behavior

def test_url_contains_state():
    assert "state=" in url  # ← ONE behavior
```

**REWRITE the test to verify ONLY ONE behavior.**
"""
                return False, feedback

            return True, ""

        except Exception as e:
            logger.warning(f"Failed to validate test quality: {e}")
            return True, ""  # Skip validation on error

    def _validate_hardcode_implementation(
        self, impl_code: str, method_name: str
    ) -> tuple[bool, str]:
        """
        Validate that implementation uses HARDCODED literals (no logic) for first test.

        Args:
            impl_code: The implementation code to validate
            method_name: Name of the method being implemented

        Returns:
            Tuple of (is_valid, feedback_message)
        """
        try:
            tree = ast.parse(impl_code)

            # Find the method being implemented
            target_func = None
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == method_name:
                    target_func = node
                    break

            if not target_func:
                return True, ""  # Can't find function, skip validation

            # Check for FORBIDDEN patterns
            violations = []

            for node in ast.walk(target_func):
                # F-strings (JoinedStr)
                if isinstance(node, ast.JoinedStr):
                    violations.append('f-string formatting (f"...")')

                # .format() calls
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute) and node.func.attr == "format":
                        violations.append(".format() method")
                    # urlencode, quote, etc.
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ["urlencode", "quote", "quote_plus", "dumps", "loads"]:
                            violations.append(f"{node.func.id}() library call")
                    elif isinstance(node.func, ast.Attribute):
                        if node.func.attr in [
                            "urlencode",
                            "quote",
                            "quote_plus",
                            "dumps",
                            "loads",
                            "encode",
                            "decode",
                        ]:
                            violations.append(f".{node.func.attr}() method")

                # Loops
                elif isinstance(node, (ast.For, ast.While)):
                    violations.append("loop (for/while)")

                # Comprehensions
                elif isinstance(node, (ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp)):
                    violations.append("comprehension")

                # Lambda functions
                elif isinstance(node, ast.Lambda):
                    violations.append("lambda function")

                # If/else (allow simple if for minimal logic, but flag complex ones)
                elif isinstance(node, ast.If):
                    # Count nested ifs - complex logic
                    if any(isinstance(n, ast.If) for n in ast.walk(node)):
                        violations.append("nested if/else (complex logic)")

            if violations:
                feedback = f"""
🚨 **HARDCODE VIOLATION - Logic Detected in First Implementation**

Your implementation uses logic patterns, but this is the FIRST test for this method.
You MUST return a HARDCODED literal value.

**Violations found:**
{chr(10).join("- " + v for v in violations)}

**❌ FORBIDDEN - Remove these:**
- String formatting: f"..." or .format()
- Loops: for/while
- Comprehensions: [x for x in ...]
- Lambda functions
- Library calls: urlencode, quote, dumps, etc.
- Complex logic: nested if/else

**✅ REQUIRED - Do this instead:**
Return a LITERAL hardcoded string or dict that matches EXACTLY what the test expects.

**Example (CORRECT)**:
```python
def {method_name}(self):
    return "https://auth.example.com?client_id=test&redirect_uri=http%3A%2F%2Fcallback"
    # ↑ Literal string, no variables or formatting!
```

**Example (WRONG - what you just did)**:
```python
def {method_name}(self):
    return f"https://...{{self.client_id}}..."  # ← Uses f-string!
```

🎯 **WHY?** This is TDD triangulation: Start with the simplest thing (hardcoded),
then add logic in the NEXT test when you need to handle different values.

**REWRITE to use ONLY hardcoded literals.**
"""
                return False, feedback

            return True, ""

        except Exception as e:
            logger.warning(f"Failed to validate hardcode implementation: {e}")
            return True, ""  # Skip validation on error

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

    def _get_module_path(self, file_path: Path) -> str:
        """
        Convert file path to Python module path.

        e.g., /path/to/src/playbook/markdown_importer.py -> src.playbook.markdown_importer

        Uses _explicit_file_path if set, otherwise derives from file_path.

        Args:
            file_path: Path to the Python file

        Returns:
            Dotted module path string
        """
        # If explicit constraint is set, use it
        if self._explicit_file_path:
            # Convert path like "src/playbook/foo.py" to "src.playbook.foo"
            return self._explicit_file_path.replace("/", ".").replace(".py", "")

        # Otherwise derive from file_path
        # Find 'src' in path parts and build module from there
        parts = file_path.parts
        try:
            src_idx = parts.index("src")
            # Take from 'src' onwards, remove .py extension from last part
            module_parts = list(parts[src_idx:])
            module_parts[-1] = module_parts[-1].replace(".py", "")
            return ".".join(module_parts)
        except ValueError:
            # 'src' not in path, fall back to just the stem
            logger.warning(f"Could not find 'src' in path {file_path}, using stem")
            return f"src.{file_path.stem}"

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

        # Build module path from implementation file
        # e.g., /path/to/src/playbook/markdown_importer.py -> src.playbook.markdown_importer
        module_path = self._get_module_path(implementation_file)
        module_name = implementation_file.stem

        header = f"""# Test file for {module_name}
import pytest
from unittest.mock import Mock, patch, MagicMock
from {module_path} import *

"""

        # Combine all test functions in cycle order
        test_bodies = "\n\n".join([f["code"] for f in functions])

        # Write complete file
        full_content = header + test_bodies
        test_file.write_text(full_content)

        logger.debug(f"Assembled {len(functions)} test function(s) into {test_file.name}")

    def _analyze_redundancy_pattern(self, increment: TestIncrement, test_code: str) -> str:
        """Analyze why a test is redundant and create semantic learning bullet.

        Args:
            increment: The test increment that passed unexpectedly
            test_code: The test code that was written

        Returns:
            Semantic pattern bullet describing the redundancy
        """
        # Get current implementation state
        impl_summary = self._get_existing_test_summaries()

        # Get existing implementation code
        impl_code = ""
        if increment.implementation_file.exists():
            impl_code = increment.implementation_file.read_text()

        # Analyze the redundancy pattern
        prompt = f"""You are analyzing a TDD redundancy failure to extract a semantic learning pattern.

**What Happened:**
A test was written but passed immediately (RED phase violation), indicating the behavior already exists.

**Test that passed unexpectedly:**
```python
{test_code}
```

**Current implementation state:**
{impl_summary}

**Implementation code:**
```python
{impl_code if impl_code else "# No implementation yet"}
```

**Task:** Analyze WHY this test is redundant and create a semantic anti-pattern that can help avoid similar redundancies in the future.

**Output a JSON object with these fields:**
- "pattern_name": Short name for this redundancy pattern (e.g., "Constructor Parameter Storage")
- "context": When does this pattern apply? (e.g., "When __init__ accepts parameters x, y")
- "redundancy_type": What makes it redundant? (e.g., "Testing attribute storage that constructor implicitly handles")
- "underlying_concept": The deeper concept (e.g., "Successful instantiation validates parameter storage")
- "how_to_avoid": Specific guidance (e.g., "Don't test self.x == value after __init__(x). Test BEHAVIOR that uses x instead.")
- "example_bad": Example of redundant test name
- "example_good": Example of better test that tests new behavior

Output ONLY the JSON, no other text."""

        response_dict = self.llm_client.generate(prompt)
        response = response_dict["content"].strip()

        # Parse JSON response
        import json
        import re

        # Extract JSON if wrapped in markdown
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if json_match:
            response = json_match.group(1)

        try:
            pattern = json.loads(response)

            # Create semantic bullet
            bullet = f"""**REDUNDANCY ANTI-PATTERN: {pattern["pattern_name"]}**

**Context:** {pattern["context"]}

**Why Redundant:** {pattern["redundancy_type"]}

**Underlying Concept:** {pattern["underlying_concept"]}

**How to Avoid:** {pattern["how_to_avoid"]}

**Examples:**
- ❌ Bad: {pattern["example_bad"]}
- ✅ Good: {pattern["example_good"]}

**Category:** Test Redundancy Detection
**Learned From:** {increment.test_name} (passed unexpectedly in RED phase)
"""
            return bullet

        except json.JSONDecodeError:
            # Fallback: create simple bullet
            return f"""**REDUNDANCY ANTI-PATTERN: Test Passed Unexpectedly**

**Test:** {increment.test_name}

**Why Redundant:** This test passed immediately, indicating the behavior already exists in the implementation.

**How to Avoid:** Before writing a test, check if the behavior is already implemented. Test NEW behavior, not existing functionality.

**Category:** Test Redundancy Detection
"""

    def _refine_test_to_fail(
        self, increment: TestIncrement, test_code: str, redundancy_analysis: str, attempt: int
    ) -> str:
        """Refine a test that passed unexpectedly to make it actually test new behavior.

        When a test passes in RED phase, it means it's redundant. This method
        refines the test to make it more specific/strict so it properly fails
        and drives out new implementation.

        Args:
            increment: The test increment
            test_code: Current test code that passed
            redundancy_analysis: Analysis of why test is redundant
            attempt: Refinement attempt number

        Returns:
            Refined test code that should fail
        """
        # Get current implementation
        impl_code = ""
        if increment.implementation_file.exists():
            impl_code = increment.implementation_file.read_text()

        # Get existing tests for context
        test_file_key = str(increment.test_file)
        existing_functions = self.test_functions.get(test_file_key, [])
        existing_test_names = [f["name"] for f in existing_functions]

        prompt = f"""You are refining a TDD test that passed unexpectedly in the RED phase.

**The Problem:**
A test was written but PASSED immediately, violating TDD RED phase discipline.
This means the test is redundant - the behavior already exists.

**Current test (PASSED when it should FAIL):**
```python
{test_code}
```

**Why it's redundant:**
{redundancy_analysis}

**Current implementation:**
```python
{impl_code if impl_code else "# No implementation yet"}
```

**Existing tests:**
{", ".join(existing_test_names) if existing_test_names else "None - this is the first test"}

**Your Task ({attempt}/3 refinement attempts):**
Refine the test to make it MORE SPECIFIC and STRICTER so it actually FAILS and drives out new behavior.

**Strategies to make test fail properly:**
1. **Strengthen assertions**: Make expectations more specific
   - Instead of: `assert result is not None`
   - Use: `assert result == {{"access_token": "xyz", "expires_in": 3600}}`

2. **Test deeper behavior**: Go beyond surface-level checks
   - Instead of: `assert hasattr(obj, 'method')`
   - Use: `result = obj.method(input); assert result == expected_output`

3. **Add edge cases**: Test boundaries, error cases
   - Test with empty inputs, special characters, boundary values
   - Test error handling, validation

4. **Test interactions**: Verify method calls, side effects
   - Use mocks to verify HTTP requests were made with correct params
   - Check that methods were called in correct order

5. **Verify state changes**: Check that operations have effects
   - After mutation, verify object state changed correctly
   - Test that operations are idempotent/non-idempotent as expected

**CRITICAL:**
- The refined test MUST fail against current implementation
- The refined test MUST test NEW behavior not yet implemented
- Keep the same test name: `{increment.test_name}`
- Output ONLY the refined test function (NO imports, NO explanations)

**Output the complete refined test function:**"""

        response_dict = self.llm_client.generate(prompt)
        refined_code = extract_code(response_dict["content"])

        return refined_code

    def _analyze_green_failure(
        self, increment: TestIncrement, test_code: str, impl_code: str, error: str, attempts: int
    ) -> dict | None:
        """Analyze GREEN failures to detect test quality issues and extract learning.

        This method determines if repeated GREEN failures might indicate:
        - Malformed test assertions (e.g., incorrect URL encoding expectations)
        - Missing technical knowledge (e.g., RFC standards, best practices)
        - Test correctness issues (test might be wrong, not implementation)

        Args:
            increment: The test increment being implemented
            test_code: The test code
            impl_code: The implementation code that failed
            error: The error message from test failure
            attempts: Number of attempts made

        Returns:
            Dict with 'bullet', 'tags', 'summary', and optional 'test_correction'
            or None if no learning pattern detected
        """
        prompt = f"""You are analyzing a TDD GREEN phase failure to detect test quality issues and extract technical knowledge.

**Context:**
After {attempts} implementation attempts, the test still fails. This suggests:
1. The implementation might be technically correct
2. The test assertion might be malformed or technically incorrect
3. There's technical knowledge worth capturing for future cycles

**Test code:**
```python
{test_code}
```

**Implementation code (attempt {attempts}):**
```python
{impl_code}
```

**Error message:**
```
{error}
```

**Task:** Analyze if there's a test quality issue or technical knowledge worth learning.

**Look for patterns like:**
- URL encoding: Does test expect `%3A//` instead of `%3A%2F%2F`? (RFC 3986 requires encoding ALL special chars)
- String comparison: Case sensitivity, whitespace, escaping issues
- API contracts: Does implementation match but test expects wrong signature?
- Type mismatches: Strings vs numbers, lists vs tuples
- Security: Weak validation, missing sanitization
- Standards violations: HTTP, RFC, ISO standards

**Output a JSON object:**
- "has_learning": true/false (Is there valuable knowledge to capture?)
- "issue_type": "malformed_assertion" | "missing_knowledge" | "implementation_bug" | "unclear"
- "technical_domain": "url_encoding" | "http_apis" | "security" | "testing" | "general" (what domain does this relate to?)
- "knowledge_summary": One-line summary (e.g., "RFC 3986 requires encoding ALL special characters in URLs")
- "explanation": Detailed explanation of what's technically correct and why
- "test_is_wrong": true/false (Should the test be corrected instead of implementation?)
- "test_correction": If test_is_wrong=true, describe what needs fixing
- "tags": Array of relevant tags for semantic retrieval

Output ONLY the JSON, no other text."""

        try:
            response_dict = self.llm_client.generate(prompt)
            response = response_dict["content"].strip()

            # Parse JSON response
            import json
            import re

            # Extract JSON if wrapped in markdown
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
            if json_match:
                response = json_match.group(1)

            analysis = json.loads(response)

            # Only create bullet if there's actual learning
            if not analysis.get("has_learning", False):
                return None

            # Create semantic knowledge bullet
            bullet = f"""**{analysis["technical_domain"].upper().replace("_", " ")} - TEST QUALITY INSIGHT**

**Issue Detected:** {analysis["issue_type"].replace("_", " ").title()}

**Knowledge:** {analysis["knowledge_summary"]}

**Explanation:**
{analysis["explanation"]}

**Test Status:** {"⚠️ Test assertion appears incorrect" if analysis.get("test_is_wrong") else "✓ Test is correct, implementation needs work"}

**Learned From:** {increment.test_name} (failed after {attempts} GREEN attempts)

**When This Applies:** Future tests in {analysis["technical_domain"]} domain
"""

            result = {
                "bullet": bullet,
                "tags": analysis.get(
                    "tags", [analysis["technical_domain"], "test_quality", "learned_from_failure"]
                ),
                "summary": analysis["knowledge_summary"],
            }

            if analysis.get("test_is_wrong") and analysis.get("test_correction"):
                result["test_correction"] = analysis["test_correction"]

            return result

        except (json.JSONDecodeError, KeyError, Exception) as e:
            logger.warning(f"Failed to analyze GREEN failure: {e}")
            return None

    def _apply_test_correction(
        self,
        test_file: Path,
        implementation_file: Path,
        test_name: str,
        current_test_code: str,
        correction_description: str,
        cycle_number: int,
    ) -> bool:
        """Apply suggested test correction to fix malformed test.

        Args:
            test_file: Path to test file
            implementation_file: Path to implementation file (for reassembly)
            test_name: Name of the test function being corrected
            current_test_code: Current test code content
            correction_description: Description of what needs to be fixed
            cycle_number: Current cycle number

        Returns:
            True if correction was successfully applied, False otherwise
        """
        prompt = f"""You are fixing a malformed test based on failure analysis.

**Current test code:**
```python
{current_test_code}
```

**Required correction:**
{correction_description}

**Task:** Apply the correction to the test code.

**IMPORTANT:**
- Make ONLY the changes described in the correction
- Preserve all existing test logic and assertions
- Maintain proper Python syntax and indentation
- Do NOT change test behavior, only fix technical issues (imports, syntax, etc.)
- Output ONLY the test function code (NO imports - they are added automatically)

**Output the COMPLETE corrected test FUNCTION, nothing else.**"""

        try:
            response_dict = self.llm_client.generate(prompt)
            corrected_code = response_dict["content"].strip()

            # Extract code from markdown if present
            import re

            code_match = re.search(r"```(?:python)?\s*\n(.*?)\n```", corrected_code, re.DOTALL)
            if code_match:
                corrected_code = code_match.group(1)

            # Basic validation - check if it's still valid Python-ish
            if "def test_" in corrected_code and len(corrected_code) > len(current_test_code) * 0.5:
                # Update the test_functions array instead of writing directly
                test_file_key = str(test_file)
                if test_file_key in self.test_functions:
                    # Find and update the corrected test function
                    for func_data in self.test_functions[test_file_key]:
                        if func_data["name"] == test_name:
                            func_data["code"] = corrected_code
                            break

                # Reassemble the complete test file with imports
                self._assemble_test_file(test_file, implementation_file)
                return True
            else:
                logger.warning("Corrected code failed validation")
                return False

        except Exception as e:
            logger.warning(f"Failed to apply test correction: {e}")
            return False

    def _get_license_type(self, provider: str, model: str) -> str:
        """
        Map provider/model to license type for auditability.

        Args:
            provider: Model provider (ollama, vllm, deepseek, togetherai)
            model: Model name

        Returns:
            License type string (e.g., 'apache-2.0', 'mit', 'proprietary')

        Raises:
            ValueError: If proprietary provider is used
        """
        # Note proprietary/closed-source providers for audit trail
        if provider in ["openai", "anthropic", "google", "cohere"]:
            logger.warning(f"Proprietary provider '{provider}' — tagging bullets as proprietary")
            return "proprietary"

        # Open-source models with permissive licenses
        if provider in ["ollama", "vllm", "togetherai"]:
            # Map common open-source models to their licenses
            model_lower = model.lower()

            # Apache 2.0 licensed models
            if any(name in model_lower for name in ["qwen", "deepseek-coder", "mistral"]):
                return "apache-2.0"

            # MIT licensed models (DeepSeek base models)
            if "deepseek" in model_lower and "coder" not in model_lower:
                return "mit"

            # Llama models (Llama 3.1 Community License - permissive)
            if "llama" in model_lower:
                return "llama-3.1-community"

            # Default for unknown Ollama/vLLM/TogetherAI models - assume open source but mark as unknown
            return "open-source-unknown"

        # DeepSeek API provider (all MIT licensed)
        if provider == "deepseek":
            return "mit"

        # OpenRouter provider - routes to various models, check model name for license
        if provider == "openrouter":
            model_lower = model.lower()

            # Note proprietary models accessed through openrouter for audit trail
            proprietary_prefixes = ["openai/", "anthropic/", "cohere/"]
            if any(model_lower.startswith(prefix) for prefix in proprietary_prefixes):
                logger.warning(f"Proprietary model '{model}' via OpenRouter — tagging bullets as proprietary")
                return "proprietary"

            # Apache 2.0 licensed models via OpenRouter
            if any(name in model_lower for name in ["qwen", "mistral", "gemma"]):
                return "apache-2.0"

            # MIT licensed models via OpenRouter
            if "deepseek" in model_lower:
                return "mit"

            # Llama models via OpenRouter
            if "llama" in model_lower or "meta-llama" in model_lower:
                return "llama-3.1-community"

            # OpenRouter auto-routing (openrouter/free routes to free open-source models)
            if model_lower.startswith("openrouter/"):
                return "open-source-unknown"

            # Default for other OpenRouter models - assume open source
            return "open-source-unknown"

        # Unknown provider - raise error for safety
        raise ValueError(
            f"Unknown provider '{provider}'. "
            f"Allowed providers: ollama, vllm, deepseek, togetherai, openrouter"
        )

    def _collect_test_files(self) -> list[Path]:
        """Collect all test files created."""
        return list(self.test_dir.glob("test_*.py"))

    def _collect_implementation_files(self) -> list[Path]:
        """Collect all implementation files created."""
        return list(self.src_dir.glob("*.py"))

    def _run_acceptance_tests(self, gherkin_dir: Path) -> dict:
        """Run Gherkin acceptance tests using behave.

        Args:
            gherkin_dir: Directory containing .feature files and steps/

        Returns:
            Dict with test results: passed, failed, total, all_passed
        """
        try:
            result = subprocess.run(
                ["behave", str(gherkin_dir), "--no-capture"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(self.project_root.parent),
            )

            # Parse plain text output
            # Look for summary line like: "3 scenarios passed, 2 failed, 0 skipped"
            import re

            output = result.stdout + result.stderr

            # Find scenarios summary line
            scenario_pattern = (
                r"(\d+)\s+scenarios?\s+passed(?:,\s*(\d+)\s+failed)?(?:,\s*(\d+)\s+skipped)?"
            )
            match = re.search(scenario_pattern, output)

            if match:
                passed_scenarios = int(match.group(1))
                failed_scenarios = int(match.group(2) or 0)
                skipped_scenarios = int(match.group(3) or 0)
                total_scenarios = passed_scenarios + failed_scenarios + skipped_scenarios
            else:
                # Try alternate format: "0 features passed, 1 failed"
                # Also check for "X scenarios passed, Y failed"
                passed_match = re.search(r"(\d+)\s+scenarios?\s+passed", output)
                failed_match = re.search(r"(\d+)\s+scenarios?\s+failed", output)
                skipped_match = re.search(r"(\d+)\s+scenarios?\s+skipped", output)

                if passed_match or failed_match or skipped_match:
                    passed_scenarios = int(passed_match.group(1)) if passed_match else 0
                    failed_scenarios = int(failed_match.group(1)) if failed_match else 0
                    skipped_scenarios = int(skipped_match.group(1)) if skipped_match else 0
                    total_scenarios = passed_scenarios + failed_scenarios + skipped_scenarios
                else:
                    logger.warning("Could not parse behave output")
                    logger.debug(f"Behave output: {output[:500]}")
                    return {
                        "total": 0,
                        "passed": 0,
                        "failed": 0,
                        "all_passed": False,
                        "details": "Could not parse behave output",
                    }

            return {
                "total": total_scenarios,
                "passed": passed_scenarios,
                "failed": failed_scenarios,
                "all_passed": (failed_scenarios == 0 and total_scenarios > 0),
                "details": f"{passed_scenarios}/{total_scenarios} scenarios passing",
            }

        except subprocess.TimeoutExpired:
            logger.error("Acceptance tests timed out")
            return {"total": 0, "passed": 0, "failed": 0, "all_passed": False, "details": "Timeout"}
        except Exception as e:
            logger.error(f"Error running acceptance tests: {e}")
            return {"total": 0, "passed": 0, "failed": 0, "all_passed": False, "details": str(e)}

    def _read_gherkin_scenarios(self, gherkin_file: Path) -> str:
        """Read Gherkin file and extract scenarios for context.

        Args:
            gherkin_file: Path to .feature file

        Returns:
            String containing scenario text for prompt context
        """
        try:
            content = gherkin_file.read_text()
            return content
        except Exception as e:
            logger.error(f"Error reading Gherkin file: {e}")
            return ""

    def _read_step_definitions(self, gherkin_dir: Path) -> str:
        """Read step definition files to understand the expected API contract.

        Step definitions define the exact method signatures, parameter names,
        and return types that the generated code must match. This ensures
        acceptance tests drive the implementation API, not vice versa.

        Args:
            gherkin_dir: Directory containing .feature files and steps/ subdirectory

        Returns:
            String containing all step definition code for prompt context
        """
        steps_dir = gherkin_dir / "steps"
        if not steps_dir.exists():
            logger.warning(f"Step definitions directory not found: {steps_dir}")
            return ""

        step_definitions = []
        for step_file in sorted(steps_dir.glob("*.py")):
            try:
                content = step_file.read_text()
                step_definitions.append(f"# {step_file.name}\n{content}")
            except Exception as e:
                logger.error(f"Error reading step file {step_file}: {e}")

        if step_definitions:
            logger.info(f"Loaded step definitions from {len(step_definitions)} file(s)")

        return "\n\n".join(step_definitions)

    def _parse_gherkin_scenarios(self, gherkin_content: str) -> list[dict]:
        """Parse Gherkin content into structured scenarios.

        This extracts scenarios and their Given/When/Then steps for driving unit test generation.

        Args:
            gherkin_content: Raw Gherkin feature file content

        Returns:
            List of scenario dicts with structure:
            {
                'name': 'Scenario name',
                'steps': [
                    {'type': 'Given', 'text': 'step text'},
                    {'type': 'When', 'text': 'step text'},
                    {'type': 'Then', 'text': 'step text'}
                ]
            }
        """
        scenarios = []
        current_scenario = None
        current_step_type = None

        for line in gherkin_content.split("\n"):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Detect scenario
            if line.startswith("Scenario:"):
                if current_scenario:
                    scenarios.append(current_scenario)
                current_scenario = {"name": line.replace("Scenario:", "").strip(), "steps": []}
                current_step_type = None

            # Detect Given/When/Then/And/But
            elif current_scenario:
                if line.startswith("Given "):
                    current_step_type = "Given"
                    step_text = line.replace("Given ", "").strip()
                    current_scenario["steps"].append({"type": "Given", "text": step_text})
                elif line.startswith("When "):
                    current_step_type = "When"
                    step_text = line.replace("When ", "").strip()
                    current_scenario["steps"].append({"type": "When", "text": step_text})
                elif line.startswith("Then "):
                    current_step_type = "Then"
                    step_text = line.replace("Then ", "").strip()
                    current_scenario["steps"].append({"type": "Then", "text": step_text})
                elif line.startswith("And "):
                    # "And" continues the previous step type
                    if current_step_type:
                        step_text = line.replace("And ", "").strip()
                        current_scenario["steps"].append(
                            {"type": current_step_type, "text": step_text}
                        )
                elif line.startswith("But "):
                    # "But" also continues the previous step type
                    if current_step_type:
                        step_text = line.replace("But ", "").strip()
                        current_scenario["steps"].append(
                            {"type": current_step_type, "text": step_text}
                        )

        # Add the last scenario
        if current_scenario:
            scenarios.append(current_scenario)

        return scenarios
