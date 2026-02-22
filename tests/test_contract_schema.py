"""Tests for contract.yml schema - interface data specification.

Bead: ace_enterprise-lfu

The contract schema defines:
- Function signatures
- Test cases (input → expected)
- Complexity level
- Hints for implementation
"""

import pytest
import yaml
from pathlib import Path


class TestContractSchemaLoading:
    """Tests for loading contracts from YAML."""

    def test_loads_contract_from_yaml_string(self):
        """Should parse contract from YAML."""
        from src.broker.contract_schema import ContractSpec, load_contracts

        yaml_content = """
contracts:
  - id: test-001
    function_name: add
    signature: "(a: int, b: int) -> int"
    docstring: "Add two numbers"
    complexity: 1
    test_cases:
      - name: basic
        input: "(1, 2)"
        expected: "3"
"""
        contracts = load_contracts(yaml_content)

        assert len(contracts) == 1
        assert contracts[0].id == "test-001"
        assert contracts[0].function_name == "add"

    def test_loads_multiple_contracts(self):
        """Should load multiple contracts from one file."""
        from src.broker.contract_schema import load_contracts

        yaml_content = """
contracts:
  - id: math-001
    function_name: add
    signature: "(a: int, b: int) -> int"
    docstring: "Add"
    complexity: 1
    test_cases:
      - name: basic
        input: "(1, 2)"
        expected: "3"

  - id: math-002
    function_name: subtract
    signature: "(a: int, b: int) -> int"
    docstring: "Subtract"
    complexity: 1
    test_cases:
      - name: basic
        input: "(5, 3)"
        expected: "2"
"""
        contracts = load_contracts(yaml_content)
        assert len(contracts) == 2
        assert contracts[0].function_name == "add"
        assert contracts[1].function_name == "subtract"


class TestContractSpecFields:
    """Tests for ContractSpec fields."""

    def test_has_required_fields(self):
        """ContractSpec should have all required fields."""
        from src.broker.contract_schema import ContractSpec, TestCaseSpec

        spec = ContractSpec(
            id="test-001",
            function_name="calculate",
            signature="(x: float) -> float",
            docstring="Calculate something",
            complexity=2,
            test_cases=[
                TestCaseSpec(name="basic", input="(1.0)", expected="2.0")
            ],
        )

        assert spec.id == "test-001"
        assert spec.function_name == "calculate"
        assert spec.signature == "(x: float) -> float"
        assert spec.docstring == "Calculate something"
        assert spec.complexity == 2
        assert len(spec.test_cases) == 1

    def test_optional_hints(self):
        """Should support optional hints field."""
        from src.broker.contract_schema import ContractSpec, TestCaseSpec

        spec = ContractSpec(
            id="test-001",
            function_name="calc",
            signature="(x: int) -> int",
            docstring="Calc",
            complexity=1,
            test_cases=[TestCaseSpec(name="t", input="(1)", expected="1")],
            hints=["Use multiplication", "Handle edge cases"],
        )

        assert spec.hints == ["Use multiplication", "Handle edge cases"]

    def test_default_hints_empty(self):
        """Hints should default to empty list."""
        from src.broker.contract_schema import ContractSpec, TestCaseSpec

        spec = ContractSpec(
            id="test-001",
            function_name="calc",
            signature="(x: int) -> int",
            docstring="Calc",
            complexity=1,
            test_cases=[TestCaseSpec(name="t", input="(1)", expected="1")],
        )

        assert spec.hints == []


class TestContractToInterfaceContract:
    """Tests for converting ContractSpec to InterfaceContract."""

    def test_converts_to_interface_contract(self):
        """Should convert to InterfaceContract for TDD execution."""
        from src.broker.contract_schema import ContractSpec, TestCaseSpec
        from src.broker.contract_driven import InterfaceContract

        spec = ContractSpec(
            id="conv-001",
            function_name="double",
            signature="(x: int) -> int",
            docstring="Double a number",
            complexity=1,
            test_cases=[
                TestCaseSpec(name="basic", input="(5)", expected="10"),
                TestCaseSpec(name="zero", input="(0)", expected="0"),
            ],
            hints=["Multiply by 2"],
        )

        interface = spec.to_interface_contract()

        assert isinstance(interface, InterfaceContract)
        assert interface.contract_id == "conv-001"
        assert interface.function_name == "double"
        assert interface.estimated_complexity == 1
        assert len(interface.test_cases) == 2


class TestContractValidation:
    """Tests for contract validation."""

    def test_rejects_missing_function_name(self):
        """Should reject contract without function_name."""
        from src.broker.contract_schema import load_contracts

        yaml_content = """
contracts:
  - id: bad-001
    signature: "(x: int) -> int"
    docstring: "Missing function name"
    complexity: 1
    test_cases: []
"""
        with pytest.raises(ValueError):
            load_contracts(yaml_content)

    def test_rejects_empty_test_cases(self):
        """Should reject contract with no test cases."""
        from src.broker.contract_schema import load_contracts

        yaml_content = """
contracts:
  - id: bad-002
    function_name: empty_tests
    signature: "(x: int) -> int"
    docstring: "No tests"
    complexity: 1
    test_cases: []
"""
        with pytest.raises(ValueError):
            load_contracts(yaml_content)

    def test_rejects_invalid_complexity(self):
        """Should reject complexity outside 1-6 range."""
        from src.broker.contract_schema import load_contracts

        yaml_content = """
contracts:
  - id: bad-003
    function_name: bad_complexity
    signature: "(x: int) -> int"
    docstring: "Bad complexity"
    complexity: 10
    test_cases:
      - name: t
        input: "(1)"
        expected: "1"
"""
        with pytest.raises(ValueError):
            load_contracts(yaml_content)


class TestLoadFromFile:
    """Tests for loading contracts from file."""

    def test_load_from_file(self, tmp_path):
        """Should load contracts from file path."""
        from src.broker.contract_schema import load_contracts_from_file

        contract_file = tmp_path / "contracts.yml"
        contract_file.write_text("""
contracts:
  - id: file-001
    function_name: from_file
    signature: "(x: int) -> int"
    docstring: "Loaded from file"
    complexity: 1
    test_cases:
      - name: basic
        input: "(1)"
        expected: "1"
""")

        contracts = load_contracts_from_file(contract_file)

        assert len(contracts) == 1
        assert contracts[0].id == "file-001"
