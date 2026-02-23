"""Module Architect - Generates module-level contracts for stateful systems.

Unlike ContractArchitect which generates per-function contracts,
ModuleArchitect generates a single contract for an entire module
with all functions and integration tests.

This is better for stateful systems where functions are interdependent.
"""

import json
import logging
import re
from dataclasses import dataclass, field

from src.audit.local_client import LocalAuditClient
from src.audit.schemas import AuditEventType
from src.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class FunctionSpec:
    """Specification for a function within a module."""
    name: str
    signature: str
    docstring: str


@dataclass
class IntegrationTest:
    """Integration test that exercises multiple functions."""
    name: str
    setup: str  # Code to set up state
    steps: list[str]  # Sequence of function calls
    assertion: str  # Final assertion


@dataclass
class ModuleContract:
    """Contract for an entire module with shared state."""
    id: str
    name: str
    description: str
    shared_state: str  # Code defining shared state (e.g., "inventory = {}")
    functions: list[FunctionSpec]
    integration_tests: list[IntegrationTest]
    complexity: int  # Overall module complexity
    hints: list[str] = field(default_factory=list)


@dataclass
class ModuleArchitectResult:
    """Result of module contract generation."""
    contract: ModuleContract | None
    architect_model: str
    elapsed_seconds: float
    success: bool
    error: str | None = None


MODULE_ARCHITECT_PROMPT = '''You are a software architect designing a Python module.

Given a requirement, design a COMPLETE MODULE with:
1. Shared state (module-level variables)
2. All functions that operate on that state
3. Integration tests that exercise the functions together

IMPORTANT: This is for a STATEFUL system. Functions share state and must be tested together.

Respond with valid JSON only:
```json
{{
  "module": {{
    "id": "inventory-001",
    "name": "inventory",
    "description": "Simple inventory management system",
    "complexity": 4,
    "shared_state": "inventory: dict[str, dict] = {{}}",
    "functions": [
      {{
        "name": "add_item",
        "signature": "(name: str, quantity: int, price: float) -> None",
        "docstring": "Add or update an item in inventory"
      }},
      {{
        "name": "get_total_value",
        "signature": "() -> float",
        "docstring": "Calculate total value of all inventory items"
      }}
    ],
    "integration_tests": [
      {{
        "name": "test_add_and_get_value",
        "setup": "inventory.clear()",
        "steps": [
          "add_item('apple', 10, 1.50)",
          "add_item('banana', 5, 0.75)",
          "result = get_total_value()"
        ],
        "assertion": "result == 18.75"
      }},
      {{
        "name": "test_empty_inventory",
        "setup": "inventory.clear()",
        "steps": [
          "result = get_total_value()"
        ],
        "assertion": "result == 0.0"
      }}
    ],
    "hints": [
      "Use a dict to store items by name",
      "Each item should have quantity and price"
    ]
  }}
}}
```

Requirement:
{requirement}

Generate a complete module contract with integration tests.
'''


class ModuleArchitect:
    """Generates module-level contracts for stateful systems."""

    def __init__(
        self,
        llm_client: LLMClient,
        audit_client: LocalAuditClient | None = None,
        model_id: str = "unknown",
    ):
        self._llm = llm_client
        self._audit = audit_client
        self._model_id = model_id

    def generate_module_contract(
        self,
        requirement: str,
        session_id: str | None = None,
    ) -> ModuleArchitectResult:
        """Generate a module contract from a requirement."""
        import hashlib
        import time

        start_time = time.time()

        try:
            prompt = MODULE_ARCHITECT_PROMPT.format(requirement=requirement)
            result = self._llm.generate(prompt)
            response = result["content"]

            contract = self._parse_module(response)
            elapsed = time.time() - start_time

            # Emit audit event
            if self._audit:
                self._audit.emit_simple(
                    event_type=AuditEventType.CONTRACT_GENERATED,
                    actor_id=self._model_id,
                    payload={
                        "contract_id": contract.id,
                        "contract_type": "module",
                        "module_name": contract.name,
                        "function_count": len(contract.functions),
                        "test_count": len(contract.integration_tests),
                        "complexity": contract.complexity,
                    },
                    session_id=session_id,
                )

            return ModuleArchitectResult(
                contract=contract,
                architect_model=self._model_id,
                elapsed_seconds=elapsed,
                success=True,
            )

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Module contract generation failed: {e}")

            return ModuleArchitectResult(
                contract=None,
                architect_model=self._model_id,
                elapsed_seconds=elapsed,
                success=False,
                error=str(e),
            )

    def _parse_module(self, response: str) -> ModuleContract:
        """Parse module contract from LLM response."""
        # Extract JSON
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                raise ValueError("No JSON found in response")

        data = json.loads(json_str)
        module = data.get("module", data)

        functions = [
            FunctionSpec(
                name=f["name"],
                signature=f["signature"],
                docstring=f.get("docstring", ""),
            )
            for f in module.get("functions", [])
        ]

        tests = [
            IntegrationTest(
                name=t["name"],
                setup=t.get("setup", ""),
                steps=t.get("steps", []),
                assertion=t.get("assertion", "True"),
            )
            for t in module.get("integration_tests", [])
        ]

        return ModuleContract(
            id=module.get("id", "module-001"),
            name=module.get("name", "module"),
            description=module.get("description", ""),
            shared_state=module.get("shared_state", ""),
            functions=functions,
            integration_tests=tests,
            complexity=module.get("complexity", 3),
            hints=module.get("hints", []),
        )


def generate_module_prompt(contract: ModuleContract) -> str:
    """Generate implementation prompt for a module contract."""
    func_specs = "\n\n".join([
        f"def {f.name}{f.signature}:\n    \"\"\"{f.docstring}\"\"\"\n    pass"
        for f in contract.functions
    ])

    test_specs = "\n\n".join([
        f"# {t.name}\n# Setup: {t.setup}\n# Steps:\n" +
        "\n".join(f"#   {step}" for step in t.steps) +
        f"\n# Assert: {t.assertion}"
        for t in contract.integration_tests
    ])

    return f'''Write a complete Python module with the following:

Shared state:
{contract.shared_state}

Functions to implement:
{func_specs}

Integration tests that must pass:
{test_specs}

Hints:
{chr(10).join(f"- {h}" for h in contract.hints)}

Respond with ONLY the Python code. Include the shared state and all functions.
Do NOT include test code - just the implementation.
'''


def validate_module(contract: ModuleContract, code: str) -> tuple[bool, list[str]]:
    """Validate module implementation against integration tests.

    Returns: (all_passed, list of failure messages)
    """
    failures = []

    try:
        # Execute the module code
        exec_globals = {}
        exec(code, exec_globals)

        # Check all functions exist
        for func in contract.functions:
            if func.name not in exec_globals:
                failures.append(f"Function '{func.name}' not found")
                return False, failures

        # Run integration tests
        for test in contract.integration_tests:
            try:
                # Fresh exec context with module functions
                test_globals = exec_globals.copy()

                # Run setup
                if test.setup:
                    exec(test.setup, test_globals)

                # Run steps
                for step in test.steps:
                    exec(step, test_globals)

                # Check assertion
                result = eval(test.assertion, test_globals)
                if not result:
                    failures.append(f"{test.name}: assertion failed - {test.assertion}")

            except Exception as e:
                failures.append(f"{test.name}: {e}")

    except SyntaxError as e:
        failures.append(f"Syntax error: {e}")
    except Exception as e:
        failures.append(f"Execution error: {e}")

    return len(failures) == 0, failures
