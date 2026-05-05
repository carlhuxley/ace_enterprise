"""Tests for ContractDecomposer - breaks user specs into contracts.

Bead: ace_enterprise-lfu

The decomposer takes user requirements and breaks them into
discrete function contracts (ContractSpec) for TDD execution.

Tests:
1. Decomposes simple requirement into single contract
2. Decomposes complex requirement into multiple contracts
3. Extracts function signatures from descriptions
4. Generates test cases from requirements
5. Estimates complexity level
6. Handles hints extraction
7. Validates decomposed contracts
"""

import pytest
from unittest.mock import MagicMock, patch


class TestDecomposerBasics:
    """Tests for basic decomposition functionality."""

    def test_decomposes_simple_requirement(self):
        """Should decompose simple requirement into single contract."""
        from src.contracts.contract_decomposer import ContractDecomposer

        decomposer = ContractDecomposer()

        requirement = "Create a function that adds two numbers"

        # Mock the LLM response
        with patch.object(decomposer, '_generate_contracts') as mock_gen:
            mock_gen.return_value = [{
                "id": "add-001",
                "function_name": "add",
                "signature": "(a: int, b: int) -> int",
                "docstring": "Add two numbers",
                "complexity": 1,
                "test_cases": [
                    {"name": "basic", "input": "(1, 2)", "expected": "3"}
                ],
                "hints": ["Simple addition"]
            }]

            contracts = decomposer.decompose(requirement)

        assert len(contracts) == 1
        assert contracts[0].function_name == "add"

    def test_decomposes_complex_requirement_into_multiple(self):
        """Should decompose complex requirement into multiple contracts."""
        from src.contracts.contract_decomposer import ContractDecomposer

        decomposer = ContractDecomposer()

        requirement = """
        Build a shopping cart system with:
        - Add item to cart
        - Remove item from cart
        - Calculate total price
        """

        with patch.object(decomposer, '_generate_contracts') as mock_gen:
            mock_gen.return_value = [
                {
                    "id": "cart-001",
                    "function_name": "add_item",
                    "signature": "(cart: list, item: dict) -> list",
                    "docstring": "Add item to cart",
                    "complexity": 1,
                    "test_cases": [
                        {"name": "add_single", "input": "([], {'id': 1})", "expected": "[{'id': 1}]"}
                    ],
                    "hints": []
                },
                {
                    "id": "cart-002",
                    "function_name": "remove_item",
                    "signature": "(cart: list, item_id: int) -> list",
                    "docstring": "Remove item from cart",
                    "complexity": 1,
                    "test_cases": [
                        {"name": "remove_existing", "input": "([{'id': 1}], 1)", "expected": "[]"}
                    ],
                    "hints": []
                },
                {
                    "id": "cart-003",
                    "function_name": "calculate_total",
                    "signature": "(cart: list) -> float",
                    "docstring": "Calculate total price",
                    "complexity": 2,
                    "test_cases": [
                        {"name": "empty_cart", "input": "([])", "expected": "0.0"}
                    ],
                    "hints": ["Sum item prices"]
                },
            ]

            contracts = decomposer.decompose(requirement)

        assert len(contracts) == 3
        assert contracts[0].function_name == "add_item"
        assert contracts[1].function_name == "remove_item"
        assert contracts[2].function_name == "calculate_total"


class TestContractGeneration:
    """Tests for contract field generation."""

    def test_generates_valid_signature(self):
        """Should generate valid Python function signature."""
        from src.contracts.contract_decomposer import ContractDecomposer

        decomposer = ContractDecomposer()

        with patch.object(decomposer, '_generate_contracts') as mock_gen:
            mock_gen.return_value = [{
                "id": "sig-001",
                "function_name": "multiply",
                "signature": "(x: float, y: float) -> float",
                "docstring": "Multiply two numbers",
                "complexity": 1,
                "test_cases": [
                    {"name": "basic", "input": "(2.0, 3.0)", "expected": "6.0"}
                ],
                "hints": []
            }]

            contracts = decomposer.decompose("Multiply two numbers")

        # Signature should be valid Python
        sig = contracts[0].signature
        assert sig.startswith("(")
        assert "->" in sig
        assert sig.endswith("float")

    def test_generates_test_cases(self):
        """Should generate at least one test case per contract."""
        from src.contracts.contract_decomposer import ContractDecomposer

        decomposer = ContractDecomposer()

        with patch.object(decomposer, '_generate_contracts') as mock_gen:
            mock_gen.return_value = [{
                "id": "tc-001",
                "function_name": "is_even",
                "signature": "(n: int) -> bool",
                "docstring": "Check if number is even",
                "complexity": 1,
                "test_cases": [
                    {"name": "even", "input": "(4)", "expected": "True"},
                    {"name": "odd", "input": "(3)", "expected": "False"},
                    {"name": "zero", "input": "(0)", "expected": "True"},
                ],
                "hints": []
            }]

            contracts = decomposer.decompose("Check if a number is even")

        assert len(contracts[0].test_cases) >= 1
        # Should have meaningful test names
        assert contracts[0].test_cases[0].name != ""

    def test_estimates_complexity(self):
        """Should estimate complexity level (1-6)."""
        from src.contracts.contract_decomposer import ContractDecomposer

        decomposer = ContractDecomposer()

        with patch.object(decomposer, '_generate_contracts') as mock_gen:
            mock_gen.return_value = [{
                "id": "cx-001",
                "function_name": "fibonacci",
                "signature": "(n: int) -> int",
                "docstring": "Calculate nth Fibonacci number",
                "complexity": 3,  # Medium complexity
                "test_cases": [
                    {"name": "base", "input": "(0)", "expected": "0"},
                    {"name": "fib_10", "input": "(10)", "expected": "55"},
                ],
                "hints": ["Use memoization for efficiency"]
            }]

            contracts = decomposer.decompose("Calculate Fibonacci number")

        assert 1 <= contracts[0].complexity <= 6


class TestContractValidation:
    """Tests for decomposed contract validation."""

    def test_validates_generated_contracts(self):
        """Should validate all generated contracts."""
        from src.contracts.contract_decomposer import ContractDecomposer

        decomposer = ContractDecomposer()

        with patch.object(decomposer, '_generate_contracts') as mock_gen:
            mock_gen.return_value = [{
                "id": "val-001",
                "function_name": "square",
                "signature": "(n: int) -> int",
                "docstring": "Square a number",
                "complexity": 1,
                "test_cases": [
                    {"name": "basic", "input": "(3)", "expected": "9"}
                ],
                "hints": []
            }]

            contracts = decomposer.decompose("Square a number")

        # All contracts should be valid
        for contract in contracts:
            assert contract.id is not None
            assert contract.function_name is not None
            assert contract.signature is not None
            assert len(contract.test_cases) > 0

    def test_rejects_invalid_llm_output(self):
        """Should raise error if LLM output is invalid."""
        from src.contracts.contract_decomposer import ContractDecomposer, DecompositionError

        decomposer = ContractDecomposer()

        with patch.object(decomposer, '_generate_contracts') as mock_gen:
            # Missing required fields
            mock_gen.return_value = [{
                "id": "bad-001",
                # Missing function_name
                "signature": "(x: int) -> int",
            }]

            with pytest.raises(DecompositionError):
                decomposer.decompose("Some requirement")


class TestDecomposerWithLLM:
    """Tests for actual LLM integration (mocked)."""

    def test_builds_correct_prompt(self):
        """Should build correct prompt for LLM."""
        from src.contracts.contract_decomposer import ContractDecomposer

        decomposer = ContractDecomposer()

        requirement = "Calculate tax on income"

        with patch.object(decomposer, '_call_llm') as mock_llm:
            mock_llm.return_value = """```json
[{
    "id": "tax-001",
    "function_name": "calculate_tax",
    "signature": "(income: float, rate: float) -> float",
    "docstring": "Calculate tax amount",
    "complexity": 1,
    "test_cases": [{"name": "basic", "input": "(1000, 0.2)", "expected": "200.0"}],
    "hints": []
}]
```"""

            decomposer.decompose(requirement)

        # Should have called LLM with requirement in prompt
        call_args = mock_llm.call_args[0][0]
        assert "Calculate tax on income" in call_args

    def test_parses_json_from_llm_response(self):
        """Should parse JSON contracts from LLM response."""
        from src.contracts.contract_decomposer import ContractDecomposer

        decomposer = ContractDecomposer()

        with patch.object(decomposer, '_call_llm') as mock_llm:
            mock_llm.return_value = """
Here's the decomposition:

```json
[{
    "id": "parse-001",
    "function_name": "parse_date",
    "signature": "(date_str: str) -> tuple",
    "docstring": "Parse date string to tuple",
    "complexity": 2,
    "test_cases": [{"name": "iso", "input": "('2024-01-15')", "expected": "(2024, 1, 15)"}],
    "hints": ["Handle ISO format"]
}]
```

This contract covers the requirement.
"""

            contracts = decomposer.decompose("Parse a date string")

        assert len(contracts) == 1
        assert contracts[0].function_name == "parse_date"


class TestDecomposerToYAML:
    """Tests for converting decomposed contracts to YAML."""

    def test_converts_to_yaml_format(self):
        """Should convert contracts to YAML-compatible format."""
        from src.contracts.contract_decomposer import ContractDecomposer
        from src.contracts.contract_schema import save_contracts
        import tempfile
        from pathlib import Path

        decomposer = ContractDecomposer()

        with patch.object(decomposer, '_generate_contracts') as mock_gen:
            mock_gen.return_value = [{
                "id": "yaml-001",
                "function_name": "greet",
                "signature": "(name: str) -> str",
                "docstring": "Generate greeting",
                "complexity": 1,
                "test_cases": [
                    {"name": "basic", "input": "('Alice')", "expected": "'Hello, Alice!'"}
                ],
                "hints": ["Use f-string"]
            }]

            contracts = decomposer.decompose("Create a greeting function")

        # Should be saveable to YAML
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "contracts.yml"
            save_contracts(contracts, path)

            # Verify file exists and is valid YAML
            assert path.exists()
            content = path.read_text()
            assert "greet" in content
            assert "yaml-001" in content
