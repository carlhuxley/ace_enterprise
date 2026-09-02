"""Contract-driven agent orchestration.

This module implements the pattern:
1. Architect (human/large model) defines interface contracts
2. Broker routes to capable implementer agents
3. Small models implement to spec
4. Tests validate the implementation

The key insight: well-specified interfaces make small models capable.
"""

import ast
import json
from dataclasses import dataclass, field
from enum import Enum

_RESULT_MARKER = "===CONTRACT_VALIDATION_RESULT==="


class ContractStatus(Enum):
    """Status of a contract implementation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    VALIDATED = "validated"
    FAILED = "failed"


@dataclass
class TestCase:
    """A test case for validating implementation."""
    name: str
    input_expr: str  # Python expression for input
    expected_expr: str  # Python expression for expected output
    description: str = ""


@dataclass
class Fixtures:
    """Test fixtures for setup/teardown."""
    setup: str = ""  # Code to run before tests
    teardown: str = ""  # Code to run after tests


@dataclass
class InterfaceContract:
    """Defines what needs to be implemented.

    This is what the architect produces and the implementer consumes.
    """
    contract_id: str
    function_name: str
    signature: str  # e.g., "(income: float, rate: float) -> float"
    docstring: str
    test_cases: list[TestCase]

    # Optional hints for implementer
    hints: list[str] = field(default_factory=list)

    # Complexity estimate (helps broker route)
    estimated_complexity: int = 1  # 1-6 scale from stress test

    # Implementation constraints
    max_lines: int = 50
    allowed_imports: list[str] = field(default_factory=list)

    # Test fixtures (setup/teardown)
    fixtures: Fixtures | None = None

    def to_prompt(self) -> str:
        """Generate implementation prompt from contract."""
        test_examples = "\n".join(
            f"  - {tc.name}: {tc.input_expr} should return {tc.expected_expr}"
            for tc in self.test_cases[:3]  # Limit examples for small model
        )

        hints_text = ""
        if self.hints:
            hints_text = "\nHints:\n" + "\n".join(f"  - {h}" for h in self.hints)

        return f'''Write a Python function with this exact signature:

def {self.function_name}{self.signature}:
    """{self.docstring}"""
    # Your implementation here

Test cases that must pass:
{test_examples}
{hints_text}
Respond with ONLY the function code. No explanations.'''


@dataclass
class Implementation:
    """Result of implementing a contract."""
    contract_id: str
    code: str
    status: ContractStatus
    test_results: dict[str, bool] = field(default_factory=dict)
    error: str | None = None
    agent_ref: str | None = None
    elapsed_seconds: float = 0.0


class ContractValidator:
    """Validates implementations against contracts.

    `code` is submitted by an implementer agent -- untrusted by this
    pipeline's own design (see module docstring). Validation therefore
    never executes it in-process: it runs inside the same rootless Podman
    sandbox the TDD engine's language pods use (--network none,
    --cap-drop=all), same principle as BlindEvaluator.
    """

    def __init__(self, orchestrator=None) -> None:
        """
        Args:
            orchestrator: Injected PodmanOrchestrator (e.g. shared across
                many validations in tests). When None, a fresh sandboxed
                container is created and torn down per validate() call.
        """
        self._orchestrator = orchestrator

    def validate(self, contract: InterfaceContract, code: str) -> Implementation:
        """Run all test cases against the implementation, inside a sandbox."""
        impl = Implementation(
            contract_id=contract.contract_id,
            code=code,
            status=ContractStatus.IN_PROGRESS
        )

        try:
            ast.parse(code)
        except SyntaxError as e:
            impl.status = ContractStatus.FAILED
            impl.error = f"Syntax error: {e}"
            return impl

        from src.agents.podman_orchestrator import PodmanOrchestrator, SecurityBreachError
        from src.agents.podman_runner import PodmanRunner

        script = _build_validation_script(
            impl_code=code,
            function_name=contract.function_name,
            test_cases=contract.test_cases,
            fixtures=contract.fixtures,
        )

        orchestrator = self._orchestrator
        owns_orchestrator = orchestrator is None
        if owns_orchestrator:
            orchestrator = PodmanOrchestrator(PodmanRunner(test_timeout=30, writable_workdir=True))

        try:
            result = orchestrator.pulse(script)
        except SecurityBreachError as exc:
            impl.status = ContractStatus.FAILED
            impl.error = f"SecurityBreach: {exc}"
            return impl
        except Exception as e:
            impl.status = ContractStatus.FAILED
            impl.error = f"Execution error: {e}"
            return impl
        finally:
            if owns_orchestrator:
                orchestrator.stop()

        if result.error and result.error.startswith("Security gate:"):
            impl.status = ContractStatus.FAILED
            impl.error = result.error
            return impl

        payload = _parse_marker(result.output)
        if payload is None:
            impl.status = ContractStatus.FAILED
            impl.error = f"Execution error: no result from sandbox.\n{(result.output or '')[:500]}\n{(result.error or '')[:500]}"
            return impl

        if payload.get("error"):
            impl.status = ContractStatus.FAILED
            impl.error = payload["error"]
            return impl

        impl.test_results = payload.get("test_results", {})
        all_passed = all(impl.test_results.values()) if impl.test_results else True
        impl.status = ContractStatus.VALIDATED if all_passed else ContractStatus.FAILED

        return impl


def _parse_marker(output: str | None) -> dict | None:
    """Extract the JSON payload the sandbox reported.

    The driver script always fails its one test (raises AssertionError)
    so pytest reports the message regardless of output-capture settings --
    print() output is silently swallowed by pytest for a passing test.
    That means the marker text appears multiple times in pytest's own
    rendered output (the echoed source line, the traceback's "E ..." line,
    and a possibly-truncated short-summary line) and never at the very
    start of a line. Scan every line for the marker anywhere in it and
    return the first one whose tail parses as JSON -- the malformed/
    truncated occurrences fail to parse and are skipped.
    """
    for line in (output or "").splitlines():
        idx = line.find(_RESULT_MARKER)
        if idx == -1:
            continue
        try:
            return json.loads(line[idx + len(_RESULT_MARKER):])
        except json.JSONDecodeError:
            continue
    return None


def _build_validation_script(
    impl_code: str,
    function_name: str,
    test_cases: list["TestCase"],
    fixtures: "Fixtures | None",
) -> str:
    """Build a pytest file that runs exec/eval validation *inside the
    sandbox* and reports structured results via a marked stdout line --
    the only channel available back to the host (the workspace mount is
    read-only from the container's side).

    impl_code is embedded as a repr()'d string literal, executed into its
    own isolated dict rather than the test module's namespace -- avoids any
    risk of the submitted function's top-level names colliding with this
    driver's own (_MARKER, json, test_contract_validation, ...). Trade-off:
    bandit's static scan (podman_runner.py's send_pulse) sees a string
    constant here, not executable source, so it can't flag patterns inside
    impl_code. Acceptable because bandit is defense-in-depth here, not the
    containment boundary -- that's --network none / --cap-drop=all, which
    applies regardless of how the code is embedded in the file."""
    setup_code = fixtures.setup if fixtures else ""
    teardown_code = fixtures.teardown if fixtures else ""
    cases = [
        {"name": tc.name, "input_expr": tc.input_expr, "expected_expr": tc.expected_expr}
        for tc in test_cases
    ]

    return f'''
import json

_MARKER = {_RESULT_MARKER!r}
_FUNCTION_NAME = {function_name!r}
_SETUP_CODE = {setup_code!r}
_TEARDOWN_CODE = {teardown_code!r}
_TEST_CASES = {cases!r}
_IMPL_CODE = {impl_code!r}


def test_contract_validation():
    results = {{"test_results": {{}}, "error": None}}
    exec_globals = {{}}
    try:
        exec(_IMPL_CODE, exec_globals)
    except Exception as e:
        results["error"] = f"Execution error: {{e}}"
        raise AssertionError(_MARKER + json.dumps(results))

    if _FUNCTION_NAME not in exec_globals:
        results["error"] = f"Function '{{_FUNCTION_NAME}}' not found in implementation"
        raise AssertionError(_MARKER + json.dumps(results))

    if _SETUP_CODE:
        try:
            exec(_SETUP_CODE, exec_globals)
        except Exception as e:
            results["error"] = f"Fixture setup error: {{e}}"
            raise AssertionError(_MARKER + json.dumps(results))

    for tc in _TEST_CASES:
        try:
            func = exec_globals[_FUNCTION_NAME]
            exec_globals["_func"] = func
            actual = eval(f"_func{{tc['input_expr']}}", exec_globals)
            expected = eval(tc["expected_expr"], exec_globals)
            results["test_results"][tc["name"]] = (actual == expected)
        except Exception:
            results["test_results"][tc["name"]] = False

    if _TEARDOWN_CODE:
        try:
            exec(_TEARDOWN_CODE, exec_globals)
        except Exception:
            pass  # Teardown errors are not fatal

    # Always raise -- pytest only reliably surfaces the message (vs. print()
    # output, which is captured/swallowed for a passing test) via a failure.
    # The real pass/fail verdict is _parse_marker()'s job on the host side.
    raise AssertionError(_MARKER + json.dumps(results))
'''


class ContractOrchestrator:
    """Orchestrates contract-driven development.

    Coordinates between:
    - Architect: produces contracts
    - Broker: routes to capable agents
    - Implementers: small models that implement
    - Validator: verifies implementations
    """

    def __init__(self, broker_advisor=None, capability_registry=None, orchestrator=None):
        self.broker = broker_advisor
        self.registry = capability_registry
        # orchestrator: injected PodmanOrchestrator forwarded to the
        # validator (e.g. a session-scoped one shared across tests).
        self.validator = ContractValidator(orchestrator=orchestrator)
        self.contracts: dict[str, InterfaceContract] = {}
        self.implementations: dict[str, Implementation] = {}

    def register_contract(self, contract: InterfaceContract) -> None:
        """Register a contract for implementation."""
        self.contracts[contract.contract_id] = contract

    def get_implementation_prompt(self, contract_id: str) -> str:
        """Get the prompt for implementing a contract."""
        contract = self.contracts.get(contract_id)
        if not contract:
            raise ValueError(f"Contract {contract_id} not found")
        return contract.to_prompt()

    def submit_implementation(
        self,
        contract_id: str,
        code: str,
        agent_ref: str | None = None
    ) -> Implementation:
        """Submit and validate an implementation."""
        contract = self.contracts.get(contract_id)
        if not contract:
            raise ValueError(f"Contract {contract_id} not found")

        impl = self.validator.validate(contract, code)
        impl.agent_ref = agent_ref
        self.implementations[contract_id] = impl

        return impl

    def get_contract_status(self, contract_id: str) -> ContractStatus:
        """Get current status of a contract."""
        if contract_id in self.implementations:
            return self.implementations[contract_id].status
        if contract_id in self.contracts:
            return ContractStatus.PENDING
        raise ValueError(f"Contract {contract_id} not found")


# Pre-built contract templates for common patterns
CONTRACT_TEMPLATES = {
    "transform": '''def {name}(data: {input_type}) -> {output_type}:
    """Transform {input_type} to {output_type}."""''',

    "filter": '''def {name}(items: list[{item_type}], predicate: Callable) -> list[{item_type}]:
    """Filter items by predicate."""''',

    "reduce": '''def {name}(items: list[{item_type}], initial: {acc_type}) -> {acc_type}:
    """Reduce items to single value."""''',

    "validate": '''def {name}(value: {value_type}) -> bool:
    """Return True if value is valid."""''',
}
