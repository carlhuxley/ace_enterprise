"""Module Architect - Generates module-level contracts for stateful systems.

Unlike ContractArchitect which generates per-function contracts,
ModuleArchitect generates a single contract for an entire module
with all functions and integration tests.

This is better for stateful systems where functions are interdependent.

Enhanced with codebase context awareness:
- Understands existing functions and their signatures
- Knows database schema (tables, columns)
- Follows existing patterns and conventions
- Tracks module dependencies
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.audit.local_client import LocalAuditClient
from src.audit.schemas import AuditEventType
from src.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


# ============================================================================
# Context Models - Understanding the existing codebase
# ============================================================================

@dataclass
class ExistingFunction:
    """An existing function in the codebase."""
    name: str
    signature: str
    docstring: str
    module: str  # Which module it's in


@dataclass
class SchemaTable:
    """Database table schema."""
    name: str
    columns: list[str]
    primary_key: str = "id"


@dataclass
class CodebaseContext:
    """Context about the existing codebase for the architect.

    This helps the architect understand:
    - What functions already exist (to call them, not duplicate)
    - Database schema (to write correct queries)
    - Patterns to follow (conventions, return types)
    """
    existing_functions: list[ExistingFunction] = field(default_factory=list)
    schema: list[SchemaTable] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)  # e.g., "Use get_db() for connections"
    imports: list[str] = field(default_factory=list)  # Required imports


@dataclass
class ModuleDependencies:
    """Dependencies between modules."""
    depends_on: list[str] = field(default_factory=list)  # Functions this module calls
    provides: list[str] = field(default_factory=list)    # Functions this module exports
    tables_read: list[str] = field(default_factory=list)  # Tables read from
    tables_write: list[str] = field(default_factory=list) # Tables written to


# ============================================================================
# Contract Models
# ============================================================================

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
    # NEW: Module connections
    dependencies: ModuleDependencies = field(default_factory=ModuleDependencies)


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


# Context-aware prompt that understands existing codebase
MODULE_ARCHITECT_CONTEXT_PROMPT = '''You are a software architect designing a Python module extension.

## EXISTING CODEBASE CONTEXT

{context_section}

## YOUR TASK

Design NEW functions that extend this codebase. You must:
1. REUSE existing functions where appropriate (call them, don't reimplement)
2. Follow the SAME patterns and conventions
3. Use the CORRECT database schema
4. Return data in the SAME format as existing functions

## REQUIREMENT

{requirement}

## OUTPUT FORMAT

Respond with valid JSON only:
```json
{{
  "module": {{
    "id": "feature-001",
    "name": "feature_name",
    "description": "What this feature does",
    "complexity": 3,
    "shared_state": "",
    "dependencies": {{
      "depends_on": ["get_db", "get_application"],
      "provides": ["search_applications"],
      "tables_read": ["applications"],
      "tables_write": []
    }},
    "functions": [
      {{
        "name": "search_applications",
        "signature": "(query: str) -> list[dict]",
        "docstring": "Search applications by text query"
      }}
    ],
    "integration_tests": [
      {{
        "name": "test_search_finds_match",
        "setup": "init_db(); clear_db(); create_application('Acme Corp', 'Engineer')",
        "steps": [
          "results = search_applications('Acme')"
        ],
        "assertion": "len(results) == 1 and results[0]['name'] == 'Acme Corp'"
      }}
    ],
    "hints": [
      "Use LIKE query for text search",
      "Return list of dicts matching get_application format"
    ]
  }}
}}
```

Generate a module contract that INTEGRATES with the existing codebase.
'''


class ModuleArchitect:
    """Generates module-level contracts for stateful systems.

    Enhanced with codebase context awareness for understanding
    existing functions, schema, and patterns.
    """

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
        context: CodebaseContext | None = None,
    ) -> ModuleArchitectResult:
        """Generate a module contract from a requirement.

        Args:
            requirement: Natural language description of what to build
            session_id: Optional session ID for audit tracking
            context: Optional codebase context (existing functions, schema, patterns)

        Returns:
            ModuleArchitectResult with the generated contract
        """
        import time

        start_time = time.time()

        try:
            # Use context-aware prompt if context is provided
            if context:
                context_section = self._format_context(context)
                prompt = MODULE_ARCHITECT_CONTEXT_PROMPT.format(
                    context_section=context_section,
                    requirement=requirement,
                )
            else:
                prompt = MODULE_ARCHITECT_PROMPT.format(requirement=requirement)

            result = self._llm.generate(prompt)
            response = result["content"]

            contract = self._parse_module(response)
            elapsed = time.time() - start_time

            # Emit audit event with dependency info
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
                        # NEW: Track module connections
                        "depends_on": contract.dependencies.depends_on,
                        "provides": contract.dependencies.provides,
                        "tables_read": contract.dependencies.tables_read,
                        "tables_write": contract.dependencies.tables_write,
                        "has_context": context is not None,
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

    def _format_context(self, context: CodebaseContext) -> str:
        """Format codebase context for the prompt."""
        sections = []

        # Existing functions
        if context.existing_functions:
            funcs = []
            for f in context.existing_functions:
                funcs.append(f"  - {f.name}{f.signature}: {f.docstring}")
            sections.append("### Existing Functions (you can call these)\n" + "\n".join(funcs))

        # Database schema
        if context.schema:
            tables = []
            for t in context.schema:
                cols = ", ".join(t.columns)
                tables.append(f"  - {t.name}: {cols} (PK: {t.primary_key})")
            sections.append("### Database Schema\n" + "\n".join(tables))

        # Patterns
        if context.patterns:
            patterns = "\n".join(f"  - {p}" for p in context.patterns)
            sections.append("### Patterns to Follow\n" + patterns)

        # Imports
        if context.imports:
            imports = "\n".join(f"  - {i}" for i in context.imports)
            sections.append("### Required Imports\n" + imports)

        return "\n\n".join(sections) if sections else "No existing context provided."

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

        # Parse dependencies (new)
        deps_data = module.get("dependencies", {})
        dependencies = ModuleDependencies(
            depends_on=deps_data.get("depends_on", []),
            provides=deps_data.get("provides", [f.name for f in functions]),  # Default to function names
            tables_read=deps_data.get("tables_read", []),
            tables_write=deps_data.get("tables_write", []),
        )

        return ModuleContract(
            id=module.get("id", "module-001"),
            name=module.get("name", "module"),
            description=module.get("description", ""),
            shared_state=module.get("shared_state", ""),
            functions=functions,
            integration_tests=tests,
            complexity=module.get("complexity", 3),
            hints=module.get("hints", []),
            dependencies=dependencies,
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


def extract_context_from_file(file_path: str) -> CodebaseContext:
    """Extract codebase context from an existing Python file.

    Parses the file to find:
    - Function definitions with signatures and docstrings
    - SQL table references (for schema inference)
    - Common patterns

    Args:
        file_path: Path to Python file to analyze

    Returns:
        CodebaseContext with extracted information
    """
    import ast

    with open(file_path, 'r') as f:
        source = f.read()

    tree = ast.parse(source)
    module_name = Path(file_path).stem

    functions = []
    tables = set()
    patterns = []

    for node in ast.walk(tree):
        # Extract function definitions
        if isinstance(node, ast.FunctionDef):
            # Build signature from arguments
            args = []
            for arg in node.args.args:
                arg_str = arg.arg
                if arg.annotation:
                    arg_str += f": {ast.unparse(arg.annotation)}"
                args.append(arg_str)

            # Get return type
            returns = ""
            if node.returns:
                returns = f" -> {ast.unparse(node.returns)}"

            signature = f"({', '.join(args)}){returns}"

            # Get docstring
            docstring = ast.get_docstring(node) or ""

            functions.append(ExistingFunction(
                name=node.name,
                signature=signature,
                docstring=docstring.split('\n')[0] if docstring else "",
                module=module_name,
            ))

        # Extract SQL table references
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            sql = node.value.upper()
            # Look for table references in SQL
            for keyword in ['FROM ', 'INTO ', 'UPDATE ', 'JOIN ']:
                if keyword in sql:
                    # Simple extraction - find word after keyword
                    idx = sql.find(keyword) + len(keyword)
                    rest = sql[idx:].strip()
                    table = rest.split()[0].strip('(').lower() if rest else None
                    if table and table.isalnum():
                        tables.add(table)

    # Infer patterns from code
    if 'get_db()' in source or 'get_db(' in source:
        patterns.append("Use get_db() for database connections")
    if 'cursor.fetchone()' in source:
        patterns.append("Use fetchone() for single row queries")
    if 'cursor.fetchall()' in source:
        patterns.append("Use fetchall() for multiple row queries")
    if '-> dict' in source or '-> dict |' in source:
        patterns.append("Return dict for single records")
    if '-> list[dict]' in source:
        patterns.append("Return list[dict] for multiple records")

    # Build schema from discovered tables (columns need manual specification)
    schema = [SchemaTable(name=t, columns=["*"]) for t in tables]

    return CodebaseContext(
        existing_functions=functions,
        schema=schema,
        patterns=patterns,
    )


def extract_context_from_directory(dir_path: str, pattern: str = "*.py") -> CodebaseContext:
    """Extract codebase context from all Python files in a directory.

    Args:
        dir_path: Directory path to scan
        pattern: Glob pattern for files (default: *.py)

    Returns:
        Combined CodebaseContext from all files
    """
    from pathlib import Path

    all_functions = []
    all_tables = {}
    all_patterns = set()

    for py_file in Path(dir_path).glob(pattern):
        if py_file.name.startswith('__'):
            continue
        try:
            ctx = extract_context_from_file(str(py_file))
            all_functions.extend(ctx.existing_functions)
            for t in ctx.schema:
                all_tables[t.name] = t
            all_patterns.update(ctx.patterns)
        except Exception as e:
            logger.warning(f"Failed to parse {py_file}: {e}")

    return CodebaseContext(
        existing_functions=all_functions,
        schema=list(all_tables.values()),
        patterns=list(all_patterns),
    )


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
