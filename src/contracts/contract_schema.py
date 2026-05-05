"""Contract Schema - YAML specification for interface contracts.

Bead: ace_enterprise-lfu

The contract.yml format defines interface data:
- Function signatures
- Test cases (input → expected)
- Complexity level for routing
- Hints for implementation

Example:
    contracts:
      - id: tax-001
        function_name: calculate_tax
        signature: "(income: float, rate: float) -> float"
        docstring: "Calculate tax amount"
        complexity: 1
        test_cases:
          - name: basic
            input: "(1000, 0.2)"
            expected: "200.0"
        hints:
          - "Simple multiplication"
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.contracts.contract_driven import InterfaceContract, TestCase, Fixtures

logger = logging.getLogger(__name__)


@dataclass
class TestCaseSpec:
    """Test case specification from YAML."""

    name: str
    input: str  # Python expression for input args
    expected: str  # Python expression for expected result
    description: str = ""


@dataclass
class FixtureSpec:
    """Fixture specification for test setup/teardown."""

    setup: str = ""  # Code to run before tests
    teardown: str = ""  # Code to run after tests


@dataclass
class ContractSpec:
    """Contract specification loaded from YAML.

    This is the data class representing a contract.yml entry.
    """

    id: str
    function_name: str
    signature: str
    docstring: str
    complexity: int
    test_cases: list[TestCaseSpec]
    hints: list[str] = field(default_factory=list)
    fixtures: FixtureSpec | None = None

    def to_interface_contract(self) -> InterfaceContract:
        """Convert to InterfaceContract for TDD execution."""
        # Convert fixtures if present
        fixtures = None
        if self.fixtures:
            fixtures = Fixtures(
                setup=self.fixtures.setup,
                teardown=self.fixtures.teardown,
            )

        return InterfaceContract(
            contract_id=self.id,
            function_name=self.function_name,
            signature=self.signature,
            docstring=self.docstring,
            test_cases=[
                TestCase(
                    name=tc.name,
                    input_expr=tc.input,
                    expected_expr=tc.expected,
                    description=tc.description,
                )
                for tc in self.test_cases
            ],
            estimated_complexity=self.complexity,
            hints=self.hints,
            fixtures=fixtures,
        )


def load_contracts(yaml_content: str) -> list[ContractSpec]:
    """Load contracts from YAML string.

    Args:
        yaml_content: YAML string with contracts

    Returns:
        List of ContractSpec objects

    Raises:
        ValueError: If contracts are invalid
    """
    data = yaml.safe_load(yaml_content)

    if not data or "contracts" not in data:
        raise ValueError("YAML must contain 'contracts' key")

    contracts = []

    for entry in data["contracts"]:
        # Validate required fields
        if "function_name" not in entry:
            raise ValueError(f"Contract {entry.get('id', '?')} missing function_name")

        if "test_cases" not in entry or not entry["test_cases"]:
            raise ValueError(
                f"Contract {entry.get('id', '?')} must have at least one test case"
            )

        complexity = entry.get("complexity", 1)
        if complexity < 1 or complexity > 6:
            raise ValueError(
                f"Contract {entry.get('id', '?')} complexity must be 1-6, got {complexity}"
            )

        # Parse test cases
        test_cases = [
            TestCaseSpec(
                name=tc["name"],
                input=tc["input"],
                expected=tc["expected"],
                description=tc.get("description", ""),
            )
            for tc in entry["test_cases"]
        ]

        # Parse fixtures if present
        fixtures = None
        if "fixtures" in entry:
            fixtures = FixtureSpec(
                setup=entry["fixtures"].get("setup", ""),
                teardown=entry["fixtures"].get("teardown", ""),
            )

        contract = ContractSpec(
            id=entry["id"],
            function_name=entry["function_name"],
            signature=entry.get("signature", "()"),
            docstring=entry.get("docstring", ""),
            complexity=complexity,
            test_cases=test_cases,
            hints=entry.get("hints", []),
            fixtures=fixtures,
        )

        contracts.append(contract)

    logger.info(f"Loaded {len(contracts)} contracts from YAML")

    return contracts


def load_contracts_from_file(file_path: Path) -> list[ContractSpec]:
    """Load contracts from YAML file.

    Args:
        file_path: Path to contract.yml file

    Returns:
        List of ContractSpec objects
    """
    content = file_path.read_text()
    return load_contracts(content)


def save_contracts(contracts: list[ContractSpec], file_path: Path) -> None:
    """Save contracts to YAML file.

    Args:
        contracts: List of ContractSpec objects
        file_path: Output path
    """
    contracts_data = []
    for c in contracts:
        contract_dict = {
            "id": c.id,
            "function_name": c.function_name,
            "signature": c.signature,
            "docstring": c.docstring,
            "complexity": c.complexity,
            "test_cases": [
                {
                    "name": tc.name,
                    "input": tc.input,
                    "expected": tc.expected,
                    "description": tc.description,
                }
                for tc in c.test_cases
            ],
            "hints": c.hints,
        }
        if c.fixtures:
            contract_dict["fixtures"] = {
                "setup": c.fixtures.setup,
                "teardown": c.fixtures.teardown,
            }
        contracts_data.append(contract_dict)

    data = {"contracts": contracts_data}

    file_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    logger.info(f"Saved {len(contracts)} contracts to {file_path}")
