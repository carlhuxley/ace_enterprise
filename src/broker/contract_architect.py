"""Contract Architect - Generates contracts from requirements.

This module implements the "architect" role in contract-driven TDD:
1. Takes natural language requirements
2. Decomposes into function contracts with test cases
3. Estimates complexity for routing
4. Emits audit events for tracking

The architect is typically a larger model (e.g., Llama 3.3 70B)
that excels at reasoning and decomposition, while smaller models
handle the implementation.
"""

import json
import logging
import os
import re
from dataclasses import dataclass

from src.audit.local_client import LocalAuditClient
from src.audit.schemas import AuditEventType
from src.broker.contract_schema import ContractSpec, TestCaseSpec, FixtureSpec
from src.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class ArchitectResult:
    """Result of contract generation."""

    contracts: list[ContractSpec]
    requirement_hash: str
    architect_model: str
    elapsed_seconds: float
    success: bool
    error: str | None = None


ARCHITECT_PROMPT = '''You are a software architect. Given a requirement, decompose it into function contracts.

For each function, provide:
1. A unique id (e.g., "feat-001")
2. Function name (snake_case)
3. Signature with type hints
4. Docstring explaining what it does
5. Complexity level (1-6):
   - 1: Single operation (e.g., return a + b)
   - 2: Simple logic (e.g., if/else, basic loop)
   - 3: Multiple conditions or transformations
   - 4: Complex logic with multiple steps
   - 5: Algorithm implementation
   - 6: System integration or complex state
6. Test cases with input/expected pairs
7. Implementation hints
8. Fixtures (setup/teardown) for stateful functions

IMPORTANT: For functions that operate on shared state (e.g., a function with no input that returns different values based on prior calls), you MUST include fixtures with setup code that establishes the required state before each test.

Respond with valid JSON only:
```json
{{
  "contracts": [
    {{
      "id": "feat-001",
      "function_name": "calculate_total",
      "signature": "(items: list[float], tax_rate: float) -> float",
      "docstring": "Calculate total price including tax",
      "complexity": 2,
      "test_cases": [
        {{"name": "basic", "input": "([10.0, 20.0], 0.1)", "expected": "33.0"}},
        {{"name": "empty", "input": "([], 0.1)", "expected": "0.0"}}
      ],
      "hints": ["Sum items first, then apply tax rate"]
    }},
    {{
      "id": "feat-002",
      "function_name": "get_total_value",
      "signature": "() -> float",
      "docstring": "Get total value of inventory",
      "complexity": 3,
      "test_cases": [
        {{"name": "empty", "input": "()", "expected": "0.0"}},
        {{"name": "with_items", "input": "()", "expected": "150.0"}}
      ],
      "fixtures": {{
        "setup": "global inventory; inventory = {{}}\n# For with_items test: add_item('apple', 10, 15.0)",
        "teardown": "inventory.clear()"
      }},
      "hints": ["Sum quantity * price for all items in inventory"]
    }}
  ]
}}
```

Requirement:
{requirement}

Generate contracts for ALL functions needed to implement this requirement.
For stateful functions, always include fixtures with setup code.
'''


class ContractArchitect:
    """Generates contracts from natural language requirements.

    Uses a capable LLM to decompose requirements into well-specified
    contracts that smaller models can implement.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        audit_client: LocalAuditClient | None = None,
        model_id: str = "unknown",
    ):
        """Initialize the architect.

        Args:
            llm_client: LLM client for generating contracts
            audit_client: Optional audit client for tracking
            model_id: Identifier for the architect model (for audit)
        """
        self._llm = llm_client
        self._audit = audit_client
        self._model_id = model_id

    def generate_contracts(
        self,
        requirement: str,
        session_id: str | None = None,
    ) -> ArchitectResult:
        """Generate contracts from a requirement.

        Args:
            requirement: Natural language requirement
            session_id: Optional session ID for audit tracking

        Returns:
            ArchitectResult with generated contracts
        """
        import hashlib
        import time

        start_time = time.time()
        requirement_hash = hashlib.sha256(requirement.encode()).hexdigest()[:16]

        try:
            # Generate contracts using LLM
            prompt = ARCHITECT_PROMPT.format(requirement=requirement)
            result = self._llm.generate(prompt)
            response = result["content"]

            # Parse JSON from response
            contracts = self._parse_contracts(response)

            elapsed = time.time() - start_time

            # Emit audit events for each contract
            if self._audit:
                for contract in contracts:
                    self._emit_contract_generated(
                        contract=contract,
                        requirement_hash=requirement_hash,
                        session_id=session_id,
                    )

                # Emit decomposition summary
                self._emit_decomposition(
                    requirement_hash=requirement_hash,
                    contract_count=len(contracts),
                    complexities=[c.complexity for c in contracts],
                    session_id=session_id,
                )

            return ArchitectResult(
                contracts=contracts,
                requirement_hash=requirement_hash,
                architect_model=self._model_id,
                elapsed_seconds=elapsed,
                success=True,
            )

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Contract generation failed: {e}")

            return ArchitectResult(
                contracts=[],
                requirement_hash=requirement_hash,
                architect_model=self._model_id,
                elapsed_seconds=elapsed,
                success=False,
                error=str(e),
            )

    def _parse_contracts(self, response: str) -> list[ContractSpec]:
        """Parse contracts from LLM response."""
        # Extract JSON from response (may be wrapped in markdown)
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON object
            json_match = re.search(r'\{\s*"contracts"\s*:\s*\[.*\]\s*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                # Last resort: find any JSON-like structure
                json_match = re.search(r'\{[^{}]*"contracts"[^{}]*\[.*?\][^{}]*\}', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    # Debug: show what we got
                    logger.error(f"Could not parse JSON from response: {response[:500]}...")
                    raise ValueError(f"No JSON found in response. First 200 chars: {response[:200]}")

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}. JSON string: {json_str[:500]}...")
            raise ValueError(f"Invalid JSON: {e}")

        if "contracts" not in data:
            raise ValueError("Response missing 'contracts' key")

        contracts = []
        for entry in data["contracts"]:
            test_cases = [
                TestCaseSpec(
                    name=tc["name"],
                    input=tc["input"],
                    expected=tc["expected"],
                    description=tc.get("description", ""),
                )
                for tc in entry.get("test_cases", [])
            ]

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
                complexity=entry.get("complexity", 3),
                test_cases=test_cases,
                hints=entry.get("hints", []),
                fixtures=fixtures,
            )

            contracts.append(contract)

        return contracts

    def _emit_contract_generated(
        self,
        contract: ContractSpec,
        requirement_hash: str,
        session_id: str | None,
    ) -> None:
        """Emit CONTRACT_GENERATED audit event."""
        if not self._audit:
            return

        self._audit.emit_simple(
            event_type=AuditEventType.CONTRACT_GENERATED,
            actor_id=self._model_id,
            payload={
                "contract_id": contract.id,
                "function_name": contract.function_name,
                "complexity": contract.complexity,
                "test_case_count": len(contract.test_cases),
                "requirement_hash": requirement_hash,
                "has_fixtures": contract.fixtures is not None,
                "hint_count": len(contract.hints),
            },
            session_id=session_id,
        )

    def _emit_decomposition(
        self,
        requirement_hash: str,
        contract_count: int,
        complexities: list[int],
        session_id: str | None,
    ) -> None:
        """Emit CONTRACT_DECOMPOSED audit event."""
        if not self._audit:
            return

        self._audit.emit_simple(
            event_type=AuditEventType.CONTRACT_DECOMPOSED,
            actor_id=self._model_id,
            payload={
                "requirement_hash": requirement_hash,
                "contract_count": contract_count,
                "complexity_distribution": {
                    str(c): complexities.count(c) for c in set(complexities)
                },
                "avg_complexity": sum(complexities) / len(complexities) if complexities else 0,
                "max_complexity": max(complexities) if complexities else 0,
            },
            session_id=session_id,
        )


def create_architect_from_config(
    provider: str,
    model: str,
    base_url: str | None = None,
    audit_db_url: str | None = None,
    enable_audit: bool = True,
) -> ContractArchitect:
    """Factory function to create an architect with common config.

    Args:
        provider: LLM provider (e.g., "openai", "anthropic", "together")
        model: Model name
        base_url: Optional base URL for API
        audit_db_url: Optional audit database URL (defaults to AUDIT_DATABASE_URL
            env var or .local/audit.db)
        enable_audit: Enable audit logging (default True, respects AUDIT_DISABLED env)

    Returns:
        Configured ContractArchitect
    """
    llm_client = LLMClient(provider=provider, model=model, base_url=base_url)

    audit_client = None
    audit_disabled = os.getenv("AUDIT_DISABLED", "").lower() == "true"
    if enable_audit and not audit_disabled:
        db_url = audit_db_url or os.getenv("AUDIT_DATABASE_URL")
        audit_client = LocalAuditClient(db_url)  # Uses .local/audit.db if None

    model_id = f"{provider}-{model}"

    return ContractArchitect(
        llm_client=llm_client,
        audit_client=audit_client,
        model_id=model_id,
    )
