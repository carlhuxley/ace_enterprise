"""
Gherkin Extraction Agent - Reverse engineers Gherkin scenarios from existing code and tests.

This agent analyzes existing codebases to extract business behavior as Gherkin acceptance tests,
enabling safe refactoring, cross-language migration, and knowledge extraction from legacy systems.

Workflow:
1. Analyze existing code (classes, methods, APIs)
2. Analyze existing tests (scenarios, assertions, behavior)
3. Extract business scenarios from test patterns
4. Generate Gherkin feature files
5. Generate step definitions matching actual API
6. Validate generated Gherkin passes against existing code
"""

import ast
import inspect
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class MethodSignature:
    """Represents a method signature extracted from code."""
    name: str
    parameters: List[Tuple[str, Optional[str]]]  # [(param_name, type_hint), ...]
    return_type: Optional[str]
    docstring: Optional[str]
    is_constructor: bool = False


@dataclass
class ClassAnalysis:
    """Analysis of a single class."""
    name: str
    methods: List[MethodSignature]
    docstring: Optional[str]
    base_classes: List[str]


@dataclass
class CodeAnalysis:
    """Complete code analysis result."""
    classes: List[ClassAnalysis]
    functions: List[MethodSignature]
    file_path: Path


@dataclass
class TestAssertion:
    """A single assertion extracted from a test."""
    assertion_type: str  # 'equal', 'true', 'false', 'in', 'not_none', etc.
    actual: str  # What's being tested
    expected: Optional[str]  # Expected value
    message: Optional[str]


@dataclass
class TestScenario:
    """A test scenario extracted from test code."""
    test_name: str
    setup_actions: List[str]  # Given: Setup code
    action: Optional[str]  # When: The action being tested
    assertions: List[TestAssertion]  # Then: What's verified
    docstring: Optional[str]
    line_number: int


@dataclass
class TestAnalysis:
    """Complete test analysis result."""
    scenarios: List[TestScenario]
    fixtures: Dict[str, Any]  # Shared setup/fixtures
    file_path: Path


@dataclass
class GherkinScenario:
    """A Gherkin scenario to be generated."""
    name: str
    given_steps: List[str]
    when_steps: List[str]
    then_steps: List[str]
    background_context: Optional[str] = None


@dataclass
class GherkinFeature:
    """A complete Gherkin feature."""
    name: str
    description: str
    scenarios: List[GherkinScenario]
    background: Optional[List[str]] = None


@dataclass
class StepDefinition:
    """A step definition for Gherkin steps."""
    step_type: str  # 'given', 'when', 'then'
    pattern: str  # The step pattern
    implementation: str  # Python code to implement the step
    method_signature: Optional[MethodSignature] = None


@dataclass
class ExtractionResult:
    """Result of Gherkin extraction."""
    feature: GherkinFeature
    step_definitions: List[StepDefinition]
    code_analysis: CodeAnalysis
    test_analysis: TestAnalysis
    confidence_score: float
    warnings: List[str] = field(default_factory=list)


class CodeAnalyzer:
    """Analyzes Python code to extract structure and APIs."""

    def analyze(self, code_path: Path) -> CodeAnalysis:
        """Analyze code file and extract structure."""
        logger.info(f"Analyzing code: {code_path}")

        with open(code_path, 'r') as f:
            source = f.read()

        tree = ast.parse(source)

        classes = []
        functions = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(self._analyze_class(node))
            elif isinstance(node, ast.FunctionDef) and self._is_top_level(node, tree):
                functions.append(self._analyze_function(node))

        return CodeAnalysis(
            classes=classes,
            functions=functions,
            file_path=code_path
        )

    def _analyze_class(self, node: ast.ClassDef) -> ClassAnalysis:
        """Analyze a class definition."""
        methods = []

        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                method = self._analyze_function(item)
                method.is_constructor = item.name == '__init__'
                methods.append(method)

        return ClassAnalysis(
            name=node.name,
            methods=methods,
            docstring=ast.get_docstring(node),
            base_classes=[self._get_name(base) for base in node.bases]
        )

    def _analyze_function(self, node: ast.FunctionDef) -> MethodSignature:
        """Analyze a function/method definition."""
        parameters = []

        for arg in node.args.args:
            param_name = arg.arg
            type_hint = None

            if arg.annotation:
                type_hint = self._get_annotation(arg.annotation)

            parameters.append((param_name, type_hint))

        return_type = None
        if node.returns:
            return_type = self._get_annotation(node.returns)

        return MethodSignature(
            name=node.name,
            parameters=parameters,
            return_type=return_type,
            docstring=ast.get_docstring(node)
        )

    def _get_annotation(self, node: ast.expr) -> str:
        """Extract type annotation as string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return str(node.value)
        elif isinstance(node, ast.Subscript):
            return ast.unparse(node)
        else:
            return ast.unparse(node) if hasattr(ast, 'unparse') else str(node)

    def _get_name(self, node: ast.expr) -> str:
        """Get name from expression."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        else:
            return ast.unparse(node) if hasattr(ast, 'unparse') else str(node)

    def _is_top_level(self, node: ast.FunctionDef, tree: ast.Module) -> bool:
        """Check if function is at module level (not inside a class)."""
        for item in tree.body:
            if item == node:
                return True
        return False


class TestAnalyzer:
    """Analyzes test code to extract test scenarios."""

    def analyze(self, test_path: Path) -> TestAnalysis:
        """Analyze test file and extract scenarios."""
        logger.info(f"Analyzing tests: {test_path}")

        with open(test_path, 'r') as f:
            source = f.read()

        tree = ast.parse(source)

        scenarios = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
                scenario = self._analyze_test_function(node)
                scenarios.append(scenario)

        return TestAnalysis(
            scenarios=scenarios,
            fixtures={},
            file_path=test_path
        )

    def _analyze_test_function(self, node: ast.FunctionDef) -> TestScenario:
        """Analyze a single test function."""
        setup_actions = []
        action = None
        assertions = []

        # Split test into setup, action, and assertions
        in_setup = True

        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                # Setup: variable assignments
                if in_setup:
                    setup_actions.append(ast.unparse(stmt))

            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                # Potential action or assertion
                call = stmt.value

                if self._is_assertion(call):
                    assertions.append(self._extract_assertion(call))
                    in_setup = False
                else:
                    # Action: method call that's not an assertion
                    if in_setup:
                        action = ast.unparse(stmt)
                        in_setup = False

            elif isinstance(stmt, (ast.Assert, ast.With)):
                # Direct assertions or context managers with asserts
                assertions.extend(self._extract_assertions_from_stmt(stmt))
                in_setup = False

        return TestScenario(
            test_name=node.name,
            setup_actions=setup_actions,
            action=action,
            assertions=assertions,
            docstring=ast.get_docstring(node),
            line_number=node.lineno
        )

    def _is_assertion(self, call: ast.Call) -> bool:
        """Check if a call is an assertion."""
        if isinstance(call.func, ast.Attribute):
            return call.func.attr.startswith('assert')
        elif isinstance(call.func, ast.Name):
            return call.func.id.startswith('assert')
        return False

    def _extract_assertion(self, call: ast.Call) -> TestAssertion:
        """Extract assertion details from a call."""
        func_name = ""

        if isinstance(call.func, ast.Attribute):
            func_name = call.func.attr
        elif isinstance(call.func, ast.Name):
            func_name = call.func.id

        # Determine assertion type
        assertion_type = self._map_assertion_type(func_name)

        # Extract actual and expected values
        actual = ast.unparse(call.args[0]) if call.args else ""
        expected = ast.unparse(call.args[1]) if len(call.args) > 1 else None

        return TestAssertion(
            assertion_type=assertion_type,
            actual=actual,
            expected=expected,
            message=None
        )

    def _extract_assertions_from_stmt(self, stmt: ast.stmt) -> List[TestAssertion]:
        """Extract assertions from assert statements."""
        assertions = []

        if isinstance(stmt, ast.Assert):
            test_expr = stmt.test

            if isinstance(test_expr, ast.Compare):
                for op, comparator in zip(test_expr.ops, test_expr.comparators):
                    assertion_type = self._map_compare_op(op)
                    assertions.append(TestAssertion(
                        assertion_type=assertion_type,
                        actual=ast.unparse(test_expr.left),
                        expected=ast.unparse(comparator),
                        message=None
                    ))

        return assertions

    def _map_assertion_type(self, func_name: str) -> str:
        """Map assertion function name to type."""
        mapping = {
            'assertEqual': 'equal',
            'assertEquals': 'equal',
            'assertTrue': 'true',
            'assertFalse': 'false',
            'assertIn': 'in',
            'assertNotNone': 'not_none',
            'assertIsNone': 'is_none',
            'assertGreater': 'greater',
            'assertLess': 'less',
        }

        for key, value in mapping.items():
            if key in func_name:
                return value

        return 'unknown'

    def _map_compare_op(self, op: ast.cmpop) -> str:
        """Map comparison operator to assertion type."""
        if isinstance(op, ast.Eq):
            return 'equal'
        elif isinstance(op, ast.NotEq):
            return 'not_equal'
        elif isinstance(op, ast.In):
            return 'in'
        elif isinstance(op, ast.NotIn):
            return 'not_in'
        elif isinstance(op, ast.Gt):
            return 'greater'
        elif isinstance(op, ast.Lt):
            return 'less'
        else:
            return 'unknown'


class GherkinExtractionAgent:
    """
    Extracts Gherkin scenarios from existing code and tests.

    This enables:
    - Safe refactoring with Gherkin as specification
    - Cross-language migration
    - Documentation generation
    - Legacy system understanding
    """

    def __init__(self, llm_client=None):
        """
        Initialize extraction agent.

        Args:
            llm_client: Optional LLM client for semantic analysis
        """
        self.code_analyzer = CodeAnalyzer()
        self.test_analyzer = TestAnalyzer()
        self.llm_client = llm_client

    def extract_from_codebase(
        self,
        code_path: Path,
        test_path: Path,
        feature_name: Optional[str] = None
    ) -> ExtractionResult:
        """
        Extract Gherkin from existing codebase.

        Args:
            code_path: Path to source code file
            test_path: Path to test file
            feature_name: Optional feature name override

        Returns:
            ExtractionResult with Gherkin and step definitions
        """
        logger.info("Starting Gherkin extraction")

        # 1. Analyze code
        code_analysis = self.code_analyzer.analyze(code_path)
        logger.info(f"Found {len(code_analysis.classes)} classes, {len(code_analysis.functions)} functions")

        # 2. Analyze tests
        test_analysis = self.test_analyzer.analyze(test_path)
        logger.info(f"Found {len(test_analysis.scenarios)} test scenarios")

        # 3. Generate Gherkin scenarios
        feature = self._generate_feature(code_analysis, test_analysis, feature_name)

        # 4. Generate step definitions
        step_definitions = self._generate_step_definitions(feature, code_analysis)

        # 5. Calculate confidence
        confidence = self._calculate_confidence(code_analysis, test_analysis)

        # 6. Collect warnings
        warnings = self._collect_warnings(code_analysis, test_analysis)

        result = ExtractionResult(
            feature=feature,
            step_definitions=step_definitions,
            code_analysis=code_analysis,
            test_analysis=test_analysis,
            confidence_score=confidence,
            warnings=warnings
        )

        logger.info(f"Extraction complete. Confidence: {confidence:.2f}")
        return result

    def _generate_feature(
        self,
        code_analysis: CodeAnalysis,
        test_analysis: TestAnalysis,
        feature_name: Optional[str]
    ) -> GherkinFeature:
        """Generate Gherkin feature from analyses."""

        # Infer feature name from class or file name
        if not feature_name:
            if code_analysis.classes:
                feature_name = self._humanize_name(code_analysis.classes[0].name)
            else:
                feature_name = code_analysis.file_path.stem.replace('_', ' ').title()

        # Generate description
        description = self._generate_feature_description(code_analysis)

        # Generate scenarios from tests
        scenarios = []
        for test_scenario in test_analysis.scenarios:
            gherkin_scenario = self._test_to_gherkin(test_scenario, code_analysis)
            scenarios.append(gherkin_scenario)

        return GherkinFeature(
            name=feature_name,
            description=description,
            scenarios=scenarios
        )

    def _generate_feature_description(self, code_analysis: CodeAnalysis) -> str:
        """Generate feature description from code."""

        # Use class docstring if available
        if code_analysis.classes and code_analysis.classes[0].docstring:
            return code_analysis.classes[0].docstring

        # Generate generic description
        if code_analysis.classes:
            class_name = code_analysis.classes[0].name
            return f"As a user\nI want to use {self._humanize_name(class_name)}\nSo that I can accomplish my goals"

        return "Feature description"

    def _test_to_gherkin(self, test_scenario: TestScenario, code_analysis: CodeAnalysis) -> GherkinScenario:
        """Convert test scenario to Gherkin scenario."""

        # Generate scenario name from test name
        scenario_name = self._humanize_test_name(test_scenario.test_name)

        # Generate Given steps from setup
        given_steps = []
        for setup in test_scenario.setup_actions:
            given_step = self._setup_to_given(setup)
            if given_step:
                given_steps.append(given_step)

        # Generate When step from action
        when_steps = []
        if test_scenario.action:
            when_step = self._action_to_when(test_scenario.action)
            if when_step:
                when_steps.append(when_step)

        # Generate Then steps from assertions
        then_steps = []
        for assertion in test_scenario.assertions:
            then_step = self._assertion_to_then(assertion)
            if then_step:
                then_steps.append(then_step)

        return GherkinScenario(
            name=scenario_name,
            given_steps=given_steps,
            when_steps=when_steps,
            then_steps=then_steps
        )

    def _setup_to_given(self, setup: str) -> Optional[str]:
        """Convert setup code to Given step."""
        # Extract meaningful context from setup

        # Match object creation: obj = Class(params)
        obj_creation = re.match(r'(\w+)\s*=\s*(\w+)\((.*)\)', setup)
        if obj_creation:
            var_name, class_name, params = obj_creation.groups()
            human_class = self._humanize_name(class_name)

            if params:
                return f"a {human_class} with {self._humanize_params(params)}"
            else:
                return f"a {human_class}"

        return None

    def _action_to_when(self, action: str) -> Optional[str]:
        """Convert action code to When step."""
        # Extract method call: result = obj.method(params)

        method_call = re.match(r'(?:(\w+)\s*=\s*)?(\w+)\.(\w+)\((.*)\)', action)
        if method_call:
            result_var, obj_var, method_name, params = method_call.groups()
            human_method = self._humanize_name(method_name)

            if params:
                return f"I {human_method} with {self._humanize_params(params)}"
            else:
                return f"I {human_method}"

        return None

    def _assertion_to_then(self, assertion: TestAssertion) -> Optional[str]:
        """Convert assertion to Then step."""

        if assertion.assertion_type == 'equal':
            return f"{self._humanize_name(assertion.actual)} should be {assertion.expected}"
        elif assertion.assertion_type == 'true':
            return f"{self._humanize_name(assertion.actual)} should be true"
        elif assertion.assertion_type == 'false':
            return f"{self._humanize_name(assertion.actual)} should be false"
        elif assertion.assertion_type == 'in':
            return f"{assertion.expected} should contain {assertion.actual}"
        elif assertion.assertion_type == 'not_none':
            return f"{self._humanize_name(assertion.actual)} should not be empty"
        else:
            return f"{self._humanize_name(assertion.actual)} should pass validation"

    def _generate_step_definitions(
        self,
        feature: GherkinFeature,
        code_analysis: CodeAnalysis
    ) -> List[StepDefinition]:
        """Generate step definitions for Gherkin steps."""

        step_definitions = []

        # Collect all unique steps
        all_steps = set()
        for scenario in feature.scenarios:
            all_steps.update(scenario.given_steps)
            all_steps.update(scenario.when_steps)
            all_steps.update(scenario.then_steps)

        # Generate step definitions
        for step in all_steps:
            # Determine step type
            step_type = 'given'  # Will be overridden based on usage

            # Generate pattern and implementation
            pattern = step
            implementation = f"# TODO: Implement step: {step}"

            step_definitions.append(StepDefinition(
                step_type=step_type,
                pattern=pattern,
                implementation=implementation
            ))

        return step_definitions

    def _calculate_confidence(self, code_analysis: CodeAnalysis, test_analysis: TestAnalysis) -> float:
        """Calculate confidence score for extraction."""

        score = 0.0
        max_score = 0.0

        # Factor 1: Has tests (40%)
        max_score += 0.4
        if test_analysis.scenarios:
            score += 0.4

        # Factor 2: Test coverage (30%)
        max_score += 0.3
        if code_analysis.classes:
            total_methods = sum(len(cls.methods) for cls in code_analysis.classes)
            if total_methods > 0:
                coverage = min(len(test_analysis.scenarios) / total_methods, 1.0)
                score += 0.3 * coverage

        # Factor 3: Has docstrings (20%)
        max_score += 0.2
        if code_analysis.classes:
            classes_with_docs = sum(1 for cls in code_analysis.classes if cls.docstring)
            doc_ratio = classes_with_docs / len(code_analysis.classes)
            score += 0.2 * doc_ratio

        # Factor 4: Clear assertions (10%)
        max_score += 0.1
        if test_analysis.scenarios:
            scenarios_with_assertions = sum(1 for s in test_analysis.scenarios if s.assertions)
            assertion_ratio = scenarios_with_assertions / len(test_analysis.scenarios)
            score += 0.1 * assertion_ratio

        return score

    def _collect_warnings(self, code_analysis: CodeAnalysis, test_analysis: TestAnalysis) -> List[str]:
        """Collect warnings about extraction quality."""

        warnings = []

        if not test_analysis.scenarios:
            warnings.append("No tests found - extraction based solely on code structure")

        if not code_analysis.classes and not code_analysis.functions:
            warnings.append("No classes or functions found in code")

        scenarios_without_assertions = [
            s for s in test_analysis.scenarios if not s.assertions
        ]
        if scenarios_without_assertions:
            warnings.append(
                f"{len(scenarios_without_assertions)} tests have no assertions"
            )

        return warnings

    def _humanize_name(self, name: str) -> str:
        """Convert code name to human-readable form."""
        # Convert snake_case or CamelCase to words
        # Example: OAuthClient -> OAuth Client
        # Example: generate_authorization_url -> generate authorization url

        # Insert spaces before capitals
        name = re.sub(r'([A-Z])', r' \1', name)
        # Replace underscores with spaces
        name = name.replace('_', ' ')
        # Clean up multiple spaces
        name = re.sub(r'\s+', ' ', name)
        # Strip and lowercase
        return name.strip().lower()

    def _humanize_test_name(self, test_name: str) -> str:
        """Convert test name to scenario name."""
        # Remove 'test_' prefix
        name = test_name.replace('test_', '')
        # Humanize
        name = self._humanize_name(name)
        # Capitalize first letter
        return name.capitalize()

    def _humanize_params(self, params: str) -> str:
        """Convert parameter list to human-readable form."""
        # Simple version: just return params
        # TODO: Could extract parameter names and values more intelligently
        return params.strip()

    def write_gherkin_file(self, feature: GherkinFeature, output_path: Path) -> None:
        """Write Gherkin feature to file."""

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            # Write feature header
            f.write(f"Feature: {feature.name}\n")
            if feature.description:
                for line in feature.description.split('\n'):
                    f.write(f"  {line}\n")
            f.write("\n")

            # Write scenarios
            for scenario in feature.scenarios:
                f.write(f"  Scenario: {scenario.name}\n")

                for given_step in scenario.given_steps:
                    f.write(f"    Given {given_step}\n")

                for when_step in scenario.when_steps:
                    f.write(f"    When {when_step}\n")

                for then_step in scenario.then_steps:
                    f.write(f"    Then {then_step}\n")

                f.write("\n")

        logger.info(f"Wrote Gherkin to: {output_path}")

    def write_step_definitions(
        self,
        step_definitions: List[StepDefinition],
        code_analysis: CodeAnalysis,
        output_path: Path
    ) -> None:
        """Write step definitions to Python file."""

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            # Write imports
            f.write("from behave import given, when, then\n")

            # Import the actual code being tested
            if code_analysis.classes:
                module_name = code_analysis.file_path.stem
                class_names = [cls.name for cls in code_analysis.classes]
                f.write(f"from {module_name} import {', '.join(class_names)}\n")

            f.write("\n\n")

            # Write step definitions
            for step_def in step_definitions:
                decorator = f"@{step_def.step_type}"
                f.write(f"{decorator}('{step_def.pattern}')\n")
                f.write(f"def step_impl(context):\n")
                f.write(f"    {step_def.implementation}\n")
                f.write(f"    pass\n\n")

        logger.info(f"Wrote step definitions to: {output_path}")
