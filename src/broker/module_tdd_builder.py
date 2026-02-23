"""Module TDD Builder - Builds module implementations using TDD.

This combines:
1. ModuleArchitect's contract (what to build)
2. AutonomousTDDAgent's methodology (how to build)

Flow:
1. Take ModuleContract from architect
2. For each function, run TDD cycle (RED → GREEN → REFACTOR → LEARN)
3. Assemble complete module
4. Run integration tests as final validation
5. Learn patterns on success/failure
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.audit.local_client import LocalAuditClient
from src.audit.schemas import AuditEventType
from src.broker.module_architect import (
    FunctionSpec,
    IntegrationTest,
    ModuleContract,
    validate_module,
)
from src.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class FunctionBuildResult:
    """Result of building one function via TDD."""

    function_name: str
    code: str
    tdd_cycles: int
    success: bool
    error: str | None = None
    patterns_learned: list[str] = field(default_factory=list)


@dataclass
class ModuleBuildResult:
    """Result of building complete module via TDD."""

    contract_id: str
    module_code: str
    function_results: list[FunctionBuildResult]
    integration_test_results: dict[str, bool]  # test_name -> passed
    success: bool
    total_cycles: int
    elapsed_seconds: float
    error: str | None = None


def function_spec_to_requirement(func: FunctionSpec, shared_state: str, hints: list[str]) -> str:
    """Convert a FunctionSpec to a natural language requirement for TDD agent.

    Args:
        func: Function specification from module contract
        shared_state: Module's shared state definition
        hints: Implementation hints

    Returns:
        Natural language requirement string
    """
    hint_text = ""
    if hints:
        hint_text = "\n\nHints:\n" + "\n".join(f"- {h}" for h in hints)

    return f"""Implement the function `{func.name}` with this signature:

def {func.name}{func.signature}:
    \"\"\"{func.docstring}\"\"\"

This function operates on shared state:
{shared_state}
{hint_text}

The function should be minimal and focused. Do not implement other functions."""


class ModuleTDDBuilder:
    """Builds module implementations using TDD methodology.

    For each function in a ModuleContract:
    1. Converts FunctionSpec to requirement
    2. Uses TDD cycle: RED → GREEN → REFACTOR
    3. Accumulates code into complete module
    4. Runs integration tests at the end
    """

    def __init__(
        self,
        llm_client: LLMClient,
        audit_client: LocalAuditClient | None = None,
        model_id: str = "unknown",
        max_attempts_per_function: int = 3,
    ):
        """Initialize the module TDD builder.

        Args:
            llm_client: LLM for code generation
            audit_client: Optional audit client for tracking
            model_id: Model identifier for audit
            max_attempts_per_function: Max TDD cycles per function
        """
        self._llm = llm_client
        self._audit = audit_client
        self._model_id = model_id
        self._max_attempts = max_attempts_per_function

    def build_module(
        self,
        contract: ModuleContract,
        session_id: str | None = None,
    ) -> ModuleBuildResult:
        """Build a complete module from contract using TDD.

        Args:
            contract: Module contract from architect
            session_id: Optional session ID for audit

        Returns:
            ModuleBuildResult with implementation and metrics
        """
        start_time = time.time()
        function_results: list[FunctionBuildResult] = []
        total_cycles = 0

        # Track accumulated module code
        module_code = f"# {contract.name}\n# {contract.description}\n\n"
        module_code += f"# Shared state\n{contract.shared_state}\n\n"

        # Build each function via TDD
        for func in contract.functions:
            logger.info(f"Building function: {func.name}")

            result = self._build_function(
                func=func,
                shared_state=contract.shared_state,
                hints=contract.hints,
                existing_code=module_code,
                session_id=session_id,
            )

            function_results.append(result)
            total_cycles += result.tdd_cycles

            if result.success:
                # Append function to module
                module_code += f"\n{result.code}\n"
            else:
                # Function failed - module build fails
                elapsed = time.time() - start_time
                return ModuleBuildResult(
                    contract_id=contract.id,
                    module_code=module_code,
                    function_results=function_results,
                    integration_test_results={},
                    success=False,
                    total_cycles=total_cycles,
                    elapsed_seconds=elapsed,
                    error=f"Failed to build function {func.name}: {result.error}",
                )

        # All functions built - run integration tests
        logger.info("Running integration tests...")
        integration_results, integration_failures = self._run_integration_tests(
            contract=contract,
            module_code=module_code,
        )

        all_integration_passed = all(integration_results.values()) if integration_results else False
        elapsed = time.time() - start_time

        # Build error message if integration tests failed
        error_msg = None
        if not all_integration_passed:
            if integration_failures:
                error_msg = f"Integration tests failed: {'; '.join(integration_failures[:3])}"
            else:
                error_msg = "Integration tests failed (unknown reason)"

        # Emit audit event
        if self._audit:
            self._audit.emit_simple(
                event_type=AuditEventType.CYCLE_COMPLETED,
                actor_id=self._model_id,
                payload={
                    "contract_id": contract.id,
                    "contract_type": "module_tdd",
                    "complexity": contract.complexity,
                    "function_count": len(contract.functions),
                    "total_cycles": total_cycles,
                    "integration_tests_passed": sum(integration_results.values()),
                    "integration_tests_total": len(integration_results),
                    "success": all_integration_passed,
                },
                session_id=session_id,
            )

        return ModuleBuildResult(
            contract_id=contract.id,
            module_code=module_code,
            function_results=function_results,
            integration_test_results=integration_results,
            success=all_integration_passed,
            total_cycles=total_cycles,
            elapsed_seconds=elapsed,
            error=error_msg,
        )

    def _build_function(
        self,
        func: FunctionSpec,
        shared_state: str,
        hints: list[str],
        existing_code: str,
        session_id: str | None = None,
    ) -> FunctionBuildResult:
        """Build a single function using TDD-style iteration.

        This is a simplified TDD cycle:
        1. Generate implementation
        2. Test against function signature/docstring
        3. Iterate on failures

        Args:
            func: Function specification
            shared_state: Module's shared state
            hints: Implementation hints
            existing_code: Already built module code
            session_id: Optional session ID

        Returns:
            FunctionBuildResult
        """
        prompt = f"""You are implementing a Python function for a module.

**Existing module code:**
```python
{existing_code}
```

**Function to implement:**
```python
def {func.name}{func.signature}:
    \"\"\"{func.docstring}\"\"\"
    # Your implementation
```

**Implementation hints:**
{chr(10).join(f"- {h}" for h in hints) if hints else "None"}

**Rules:**
1. ONLY output the function definition (not the whole module)
2. The function operates on the shared state defined above
3. Keep implementation minimal and correct
4. No imports - use what's already in the module

Output ONLY the Python function code:
"""

        for attempt in range(1, self._max_attempts + 1):
            logger.info(f"  Attempt {attempt}/{self._max_attempts}...")

            try:
                response = self._llm.generate(prompt)
                code = self._extract_function_code(response["content"], func.name)

                # Validate the function compiles and has correct signature
                validation_error = self._validate_function(code, func)
                if validation_error:
                    logger.warning(f"  Validation failed: {validation_error}")
                    # Update prompt with error feedback
                    prompt = f"""Previous attempt failed with: {validation_error}

Fix the implementation:

{prompt}"""
                    continue

                # Function looks valid
                return FunctionBuildResult(
                    function_name=func.name,
                    code=code,
                    tdd_cycles=attempt,
                    success=True,
                )

            except Exception as e:
                logger.error(f"  Error generating function: {e}")

        # All attempts failed
        return FunctionBuildResult(
            function_name=func.name,
            code="",
            tdd_cycles=self._max_attempts,
            success=False,
            error=f"Failed after {self._max_attempts} attempts",
        )

    def _extract_function_code(self, response: str, function_name: str) -> str:
        """Extract function code from LLM response."""
        # Try to extract from code blocks
        if "```python" in response:
            code = response.split("```python")[1]
            if "```" in code:
                code = code.split("```")[0]
            return code.strip()
        elif "```" in response:
            code = response.split("```")[1]
            if "```" in code:
                code = code.split("```")[0]
            return code.strip()

        # Look for function definition
        lines = response.strip().split("\n")
        func_lines = []
        in_func = False

        for line in lines:
            if line.strip().startswith(f"def {function_name}"):
                in_func = True
            if in_func:
                func_lines.append(line)
                # Detect end of function (blank line or new def)
                if func_lines and line.strip() and not line.startswith(" ") and not line.startswith("\t"):
                    if not line.startswith("def"):
                        break

        return "\n".join(func_lines).strip()

    def _validate_function(self, code: str, func: FunctionSpec) -> str | None:
        """Validate function code compiles and has correct structure.

        Returns:
            None if valid, error message if invalid
        """
        try:
            # Check it parses
            tree = compile(code, "<string>", "exec")

            # Check function name exists
            if f"def {func.name}" not in code:
                return f"Function {func.name} not found in code"

            return None

        except SyntaxError as e:
            return f"Syntax error: {e}"

    def _run_integration_tests(
        self,
        contract: ModuleContract,
        module_code: str,
    ) -> tuple[dict[str, bool], list[str]]:
        """Run integration tests against the built module.

        Args:
            contract: Module contract with integration tests
            module_code: Complete module implementation

        Returns:
            Tuple of (dict mapping test name to pass/fail, list of failure messages)
        """
        # Use the existing validate_module function which runs integration tests
        passed, failures = validate_module(contract, module_code)

        # Log failures for debugging
        if failures:
            logger.warning(f"Integration test failures: {failures}")

        results = {}
        for test in contract.integration_tests:
            # Check if this test failed
            test_failed = any(test.name in f for f in failures)
            results[test.name] = not test_failed

        # If there are failures that don't match any test name, mark all as failed
        if failures and all(results.values()):
            # Generic failure (syntax error, execution error, etc.)
            for test in contract.integration_tests:
                results[test.name] = False

        return results, failures


def create_tdd_builder_from_config(
    provider: str,
    model: str,
    base_url: str | None = None,
    audit_db_url: str | None = None,
) -> ModuleTDDBuilder:
    """Factory function to create a TDD builder with common config.

    Args:
        provider: LLM provider (e.g., "togetherai")
        model: Model name
        base_url: Optional base URL for API
        audit_db_url: Optional audit database URL

    Returns:
        Configured ModuleTDDBuilder
    """
    llm_client = LLMClient(provider=provider, model=model, base_url=base_url)

    audit_client = None
    if audit_db_url:
        audit_client = LocalAuditClient(audit_db_url)

    model_id = f"{provider}-{model}"

    return ModuleTDDBuilder(
        llm_client=llm_client,
        audit_client=audit_client,
        model_id=model_id,
    )
