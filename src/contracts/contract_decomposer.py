"""Contract Decomposer - Breaks user specs into interface contracts.

Bead: ace_enterprise-lfu

The decomposer takes natural language requirements and decomposes them
into discrete function contracts (ContractSpec) that can be executed
via TDD.

Flow:
1. User provides requirement text
2. LLM decomposes into JSON contract specifications
3. Contracts are validated and converted to ContractSpec
4. Contracts saved to contract.yml for TDD execution
"""

import json
import logging
import re
from dataclasses import dataclass

from src.contracts.contract_schema import ContractSpec, TestCaseSpec

logger = logging.getLogger(__name__)


class DecompositionError(Exception):
    """Raised when contract decomposition fails."""
    pass


@dataclass
class DecomposerConfig:
    """Configuration for contract decomposition."""

    # LLM settings
    max_tokens: int = 2000
    temperature: float = 0.3

    # Validation
    require_test_cases: bool = True
    min_test_cases: int = 1


class ContractDecomposer:
    """Decomposes user requirements into interface contracts.

    Takes natural language specifications and produces ContractSpec
    objects ready for TDD execution.
    """

    SYSTEM_PROMPT = """You are a software architect who decomposes requirements into
precise function contracts. For each function, you specify:
- id: Unique identifier (e.g., "task-001")
- function_name: Python function name (snake_case)
- signature: Type-annotated Python signature
- docstring: Brief description
- complexity: Estimated difficulty (1-6 scale)
- test_cases: List of input/expected pairs
- hints: Implementation hints (optional)

Output ONLY valid JSON array of contracts. No explanations."""

    DECOMPOSE_PROMPT = """Decompose this requirement into function contracts:

{requirement}

Rules:
1. Each function should do ONE thing well
2. Include at least one test case per function
3. Use proper Python type annotations
4. Estimate complexity 1-6 (1=trivial, 6=complex algorithm)

Output as JSON array:
```json
[
  {{
    "id": "unique-id",
    "function_name": "snake_case_name",
    "signature": "(param: type, ...) -> return_type",
    "docstring": "Brief description",
    "complexity": 1,
    "test_cases": [
      {{"name": "test_name", "input": "(args)", "expected": "result"}}
    ],
    "hints": ["optional hints"]
  }}
]
```"""

    def __init__(self, config: DecomposerConfig | None = None):
        """Initialize decomposer with optional config."""
        self.config = config or DecomposerConfig()
        self._llm_client = None

    def decompose(self, requirement: str) -> list[ContractSpec]:
        """Decompose requirement into contracts.

        Args:
            requirement: Natural language requirement text

        Returns:
            List of ContractSpec objects

        Raises:
            DecompositionError: If decomposition fails
        """
        # Generate contracts via LLM
        raw_contracts = self._generate_contracts(requirement)

        # Validate and convert
        contracts = []
        for raw in raw_contracts:
            try:
                contract = self._validate_and_convert(raw)
                contracts.append(contract)
            except (KeyError, ValueError) as e:
                raise DecompositionError(f"Invalid contract format: {e}") from e

        if not contracts:
            raise DecompositionError("No contracts generated")

        logger.info(f"Decomposed requirement into {len(contracts)} contracts")
        return contracts

    def _generate_contracts(self, requirement: str) -> list[dict]:
        """Generate raw contract dicts from requirement.

        This method calls the LLM and parses the response.
        Can be mocked for testing.
        """
        prompt = self.DECOMPOSE_PROMPT.format(requirement=requirement)
        response = self._call_llm(prompt)
        return self._parse_json_response(response)

    def _call_llm(self, prompt: str) -> str:
        """Call LLM with prompt.

        Override or mock for testing.
        """
        # Default implementation uses effGen if available
        if self._llm_client is None:
            try:
                from src.utils.effgen_client import EffGenClient
                self._llm_client = EffGenClient()
            except ImportError:
                raise DecompositionError("No LLM client available")

        result = self._llm_client.generate(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )

        return result.get("content", "")

    def _parse_json_response(self, response: str) -> list[dict]:
        """Parse JSON contracts from LLM response.

        Handles markdown code blocks and extracts JSON array.
        """
        # Try to extract JSON from code block
        json_match = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', response)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON array
            array_match = re.search(r'\[[\s\S]*\]', response)
            if array_match:
                json_str = array_match.group(0)
            else:
                raise DecompositionError(f"No JSON array found in response: {response[:200]}")

        try:
            contracts = json.loads(json_str)
            if not isinstance(contracts, list):
                raise DecompositionError("Response is not a JSON array")
            return contracts
        except json.JSONDecodeError as e:
            raise DecompositionError(f"Invalid JSON: {e}") from e

    def _validate_and_convert(self, raw: dict) -> ContractSpec:
        """Validate raw contract dict and convert to ContractSpec.

        Args:
            raw: Raw contract dictionary from LLM

        Returns:
            Validated ContractSpec

        Raises:
            KeyError: If required field is missing
            ValueError: If field value is invalid
        """
        # Required fields
        if "function_name" not in raw:
            raise KeyError("Missing required field: function_name")

        if "test_cases" not in raw or not raw["test_cases"]:
            if self.config.require_test_cases:
                raise KeyError("Missing required field: test_cases")
            raw["test_cases"] = []

        # Validate complexity
        complexity = raw.get("complexity", 1)
        if not (1 <= complexity <= 6):
            raise ValueError(f"Complexity must be 1-6, got {complexity}")

        # Convert test cases
        test_cases = []
        for tc in raw["test_cases"]:
            test_cases.append(TestCaseSpec(
                name=tc["name"],
                input=tc["input"],
                expected=tc["expected"],
                description=tc.get("description", ""),
            ))

        # Build ContractSpec
        return ContractSpec(
            id=raw.get("id", f"{raw['function_name']}-001"),
            function_name=raw["function_name"],
            signature=raw.get("signature", "()"),
            docstring=raw.get("docstring", ""),
            complexity=complexity,
            test_cases=test_cases,
            hints=raw.get("hints", []),
        )

    def set_llm_client(self, client) -> None:
        """Set custom LLM client for decomposition."""
        self._llm_client = client
