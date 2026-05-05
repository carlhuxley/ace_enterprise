"""Contract-driven agent orchestration.

This module implements the pattern:
1. Architect (human/large model) defines interface contracts
2. Broker routes to capable implementer agents
3. Small models implement to spec
4. Tests validate the implementation

The key insight: well-specified interfaces make small models capable.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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
    """Validates implementations against contracts."""

    def validate(self, contract: InterfaceContract, code: str) -> Implementation:
        """Run all test cases against the implementation."""
        impl = Implementation(
            contract_id=contract.contract_id,
            code=code,
            status=ContractStatus.IN_PROGRESS
        )

        try:
            # Execute the implementation code
            exec_globals = {}
            exec(code, exec_globals)

            # Check function exists
            if contract.function_name not in exec_globals:
                impl.status = ContractStatus.FAILED
                impl.error = f"Function '{contract.function_name}' not found in implementation"
                return impl

            # Run fixture setup once if present (for shared state)
            if contract.fixtures and contract.fixtures.setup:
                try:
                    exec(contract.fixtures.setup, exec_globals)
                except Exception as e:
                    impl.status = ContractStatus.FAILED
                    impl.error = f"Fixture setup error: {e}"
                    return impl

            # Run each test case
            all_passed = True
            for tc in contract.test_cases:
                try:
                    # Build test expression
                    func = exec_globals[contract.function_name]
                    exec_globals['_func'] = func

                    # Evaluate input and expected
                    actual = eval(f"_func{tc.input_expr}", exec_globals)
                    expected = eval(tc.expected_expr, exec_globals)

                    passed = actual == expected
                    impl.test_results[tc.name] = passed

                    if not passed:
                        all_passed = False

                except Exception as e:
                    impl.test_results[tc.name] = False
                    all_passed = False

            # Run fixture teardown if present
            if contract.fixtures and contract.fixtures.teardown:
                try:
                    exec(contract.fixtures.teardown, exec_globals)
                except Exception:
                    pass  # Teardown errors are not fatal

            impl.status = ContractStatus.VALIDATED if all_passed else ContractStatus.FAILED

        except SyntaxError as e:
            impl.status = ContractStatus.FAILED
            impl.error = f"Syntax error: {e}"
        except Exception as e:
            impl.status = ContractStatus.FAILED
            impl.error = f"Execution error: {e}"

        return impl


class ContractOrchestrator:
    """Orchestrates contract-driven development.

    Coordinates between:
    - Architect: produces contracts
    - Broker: routes to capable agents
    - Implementers: small models that implement
    - Validator: verifies implementations
    """

    def __init__(self, broker_advisor=None, capability_registry=None):
        self.broker = broker_advisor
        self.registry = capability_registry
        self.validator = ContractValidator()
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
