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


MODULE_ARCHITECT_PROMPT = '''You are a software architect designing a self-contained Python module.

Given a requirement, design a COMPLETE MODULE with:
1. Shared state (module-level variables), or "" if the module is stateless
2. All functions that operate on that state
3. Integration tests that exercise the functions together

RULES:
- The module is standalone. It has NO database, NO framework, NO ambient helpers.
  Use only the Python standard library (json, pathlib, collections, ...).
- integration_tests `setup` and `steps` may ONLY call functions that appear in
  this module's `functions` list, plus the stdlib.
- NEVER invent helpers like init_db(), clear_db(), execute_sql(), create_*().
- Reset shared state in `setup` by clearing the module-level variable directly
  (e.g. "_store.clear()"), not via a helper.
- If the module persists to disk, tests take a directory argument and use
  pathlib / a pytest tmp_path-style path passed in by the caller.

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


# Context-aware prompt: the module builds on other modules already produced in
# this same run (their signatures are in the context section). It is still a
# standalone module tree -- no database, no framework, no ambient helpers.
MODULE_ARCHITECT_CONTEXT_PROMPT = '''You are a software architect designing a Python module.

## ALREADY-BUILT MODULES IN THIS PROJECT (import and call these, don't reimplement)

{context_section}

## YOUR TASK

Design the requested module. You must:
1. REUSE the already-built functions above where appropriate (import them)
2. Follow the SAME conventions (return types, naming)
3. Use ONLY the Python standard library otherwise -- there is NO database and
   NO framework

## HARD RULES FOR integration_tests

- `setup` and `steps` may ONLY call: functions in this module's `functions`
  list, the already-built functions listed above, and the stdlib.
- NEVER invent helpers like init_db(), clear_db(), execute_sql(), create_*().
- Reset shared state by clearing the module-level variable directly.

## REQUIREMENT

{requirement}

## OUTPUT FORMAT

Respond with valid JSON only:
```json
{{
  "module": {{
    "id": "feature-001",
    "name": "feature_name",
    "description": "What this module does",
    "complexity": 3,
    "shared_state": "_index: dict[str, list[str]] = {{}}",
    "dependencies": {{
      "depends_on": ["tokenize"],
      "provides": ["add_document", "search"]
    }},
    "functions": [
      {{
        "name": "add_document",
        "signature": "(doc_id: str, text: str) -> None",
        "docstring": "Index a document's tokens under its id"
      }},
      {{
        "name": "search",
        "signature": "(query: str) -> list[str]",
        "docstring": "Return doc ids whose tokens include every query token"
      }}
    ],
    "integration_tests": [
      {{
        "name": "test_search_finds_indexed_document",
        "setup": "_index.clear()",
        "steps": [
          "add_document('d1', 'the quick brown fox')",
          "results = search('quick fox')"
        ],
        "assertion": "results == ['d1']"
      }}
    ],
    "hints": [
      "tokenize() comes from an already-built module -- import it",
      "Lowercase and split on whitespace if tokenize is unavailable"
    ]
  }}
}}
```

Generate a self-contained module contract with integration tests.
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


# Common English words that are NOT table names
_SQL_NOISE_WORDS = {
    'select', 'from', 'where', 'and', 'or', 'not', 'in', 'is', 'null',
    'true', 'false', 'as', 'on', 'by', 'order', 'group', 'having',
    'limit', 'offset', 'join', 'left', 'right', 'inner', 'outer',
    'values', 'set', 'into', 'insert', 'update', 'delete', 'create',
    'table', 'if', 'exists', 'primary', 'key', 'integer', 'text',
    'real', 'blob', 'default', 'autoincrement', 'unique', 'index',
    'the', 'a', 'an', 'to', 'of', 'for', 'with', 'should', 'be',
    'this', 'that', 'it', 'when', 'then', 'else', 'end', 'case',
    'count', 'sum', 'avg', 'min', 'max', 'like', 'between',
    'asc', 'desc', 'distinct', 'all', 'any', 'some', 'each',
    'now', 'current_timestamp', 'datetime', 'date', 'time',
    'status', 'id', 'name', 'value', 'type', 'data', 'contract',
    'implementation', 'function', 'module', 'test', 'result',
    # SQLite internal tables
    'sqlite_sequence', 'sqlite_master', 'sqlite_temp_master',
    # Generic words
    'database', 'schema', 'column', 'row', 'record', 'field',
}


def _extract_tables_from_sql(sql: str) -> set[str]:
    """Extract table names from SQL string with improved accuracy.

    Uses regex patterns to find tables after SQL keywords,
    filters out noise words, and validates table name format.

    Args:
        sql: SQL string to parse

    Returns:
        Set of table names found
    """
    tables = set()
    sql_upper = sql.upper()

    # Pattern 1: CREATE TABLE [IF NOT EXISTS] table_name
    create_match = re.search(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["\']?(\w+)["\']?',
        sql_upper
    )
    if create_match:
        table = create_match.group(1).lower()
        if _is_valid_table_name(table):
            tables.add(table)

    # Pattern 2: FROM table_name or JOIN table_name
    from_matches = re.findall(
        r'(?:FROM|JOIN)\s+["\']?(\w+)["\']?',
        sql_upper
    )
    for table in from_matches:
        table = table.lower()
        if _is_valid_table_name(table):
            tables.add(table)

    # Pattern 3: INSERT INTO table_name
    insert_match = re.search(
        r'INSERT\s+INTO\s+["\']?(\w+)["\']?',
        sql_upper
    )
    if insert_match:
        table = insert_match.group(1).lower()
        if _is_valid_table_name(table):
            tables.add(table)

    # Pattern 4: UPDATE table_name
    update_match = re.search(
        r'UPDATE\s+["\']?(\w+)["\']?',
        sql_upper
    )
    if update_match:
        table = update_match.group(1).lower()
        if _is_valid_table_name(table):
            tables.add(table)

    # Pattern 5: DELETE FROM table_name
    delete_match = re.search(
        r'DELETE\s+FROM\s+["\']?(\w+)["\']?',
        sql_upper
    )
    if delete_match:
        table = delete_match.group(1).lower()
        if _is_valid_table_name(table):
            tables.add(table)

    return tables


def _normalize_tables(tables: set[str]) -> set[str]:
    """Normalize table names - prefer plural form, dedupe singular/plural.

    Args:
        tables: Set of table names

    Returns:
        Normalized set of table names
    """
    normalized = set()
    table_list = sorted(tables)

    for table in table_list:
        # If we have both singular and plural, keep only plural
        plural = table + 's'
        singular = table.rstrip('s') if table.endswith('s') else None

        if plural in tables:
            # This is singular, plural exists - skip
            continue
        elif singular and singular in tables:
            # This is plural, singular also exists - keep this one
            normalized.add(table)
        else:
            # No singular/plural conflict
            normalized.add(table)

    return normalized


def _is_valid_table_name(name: str) -> bool:
    """Check if a string looks like a valid table name.

    Valid table names:
    - Are not SQL keywords or common noise words
    - Are snake_case or simple identifiers
    - Are at least 2 characters
    - Don't start with numbers

    Args:
        name: Potential table name

    Returns:
        True if it looks like a valid table name
    """
    if not name or len(name) < 2:
        return False

    # Filter out noise words
    if name.lower() in _SQL_NOISE_WORDS:
        return False

    # Must start with letter or underscore
    if not (name[0].isalpha() or name[0] == '_'):
        return False

    # Must be alphanumeric with underscores (snake_case)
    if not re.match(r'^[a-z_][a-z0-9_]*$', name.lower()):
        return False

    # Likely table names end with 's' (plural) or common suffixes
    # But don't enforce this - just a heuristic
    return True


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

    with open(file_path) as f:
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
            sql = node.value
            # Only process strings that look like SQL
            sql_upper = sql.upper()
            if any(kw in sql_upper for kw in ['SELECT ', 'INSERT ', 'UPDATE ', 'DELETE ', 'CREATE TABLE']):
                extracted = _extract_tables_from_sql(sql)
                tables.update(extracted)

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
    # Normalize to dedupe singular/plural (e.g., application vs applications)
    normalized_tables = _normalize_tables(tables)
    schema = [SchemaTable(name=t, columns=["*"]) for t in sorted(normalized_tables)]

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
    all_table_names = set()
    all_tables = {}
    all_patterns = set()

    for py_file in Path(dir_path).glob(pattern):
        if py_file.name.startswith('__'):
            continue
        try:
            ctx = extract_context_from_file(str(py_file))
            all_functions.extend(ctx.existing_functions)
            for t in ctx.schema:
                all_table_names.add(t.name)
                all_tables[t.name] = t
            all_patterns.update(ctx.patterns)
        except Exception as e:
            logger.warning(f"Failed to parse {py_file}: {e}")

    # Normalize tables across all files (dedupe singular/plural)
    normalized_names = _normalize_tables(all_table_names)
    normalized_schema = [all_tables[name] for name in sorted(normalized_names) if name in all_tables]

    return CodebaseContext(
        existing_functions=all_functions,
        schema=normalized_schema,
        patterns=list(all_patterns),
    )


_MODULE_RESULT_MARKER = "===MODULE_VALIDATION_RESULT==="


def validate_module(
    contract: ModuleContract, code: str, orchestrator=None
) -> tuple[bool, list[str]]:
    """Validate module implementation against integration tests.

    code is LLM-generated implementer output -- untrusted by this
    pipeline's own design (see module docstring: Architect -> Broker ->
    Implementer -> Validator). Runs inside the same rootless Podman sandbox
    the TDD engine's language pods use (--network none, --cap-drop=all),
    never in-process.

    Args:
        orchestrator: Injected PodmanOrchestrator (e.g. shared across many
            validations in tests). When None, a fresh sandboxed container
            is created and torn down per call.

    Returns: (all_passed, list of failure messages)
    """
    import ast

    try:
        ast.parse(code)
    except SyntaxError as e:
        return False, [f"Syntax error: {e}"]

    from src.agents.podman_orchestrator import PodmanOrchestrator, SecurityBreachError
    from src.agents.podman_runner import PodmanRunner

    script = _build_module_validation_script(contract, code)

    owns_orchestrator = orchestrator is None
    if owns_orchestrator:
        orchestrator = PodmanOrchestrator(PodmanRunner(test_timeout=30))

    try:
        result = orchestrator.pulse(script)
    except SecurityBreachError as exc:
        return False, [f"SecurityBreach: {exc}"]
    except Exception as e:
        return False, [f"Execution error: {e}"]
    finally:
        if owns_orchestrator:
            orchestrator.stop()

    if result.error and result.error.startswith("Security gate:"):
        return False, [result.error]

    payload = _parse_module_marker(result.output)
    if payload is None:
        return False, [
            f"Execution error: no result from sandbox.\n"
            f"{(result.output or '')[:500]}\n{(result.error or '')[:500]}"
        ]

    failures = payload.get("failures", [])
    return len(failures) == 0, failures


def _parse_module_marker(output: str | None) -> dict | None:
    """Extract the JSON payload the sandbox reported.

    The driver always fails its one test (raises AssertionError) so pytest
    reports the message regardless of output-capture settings -- print()
    output is silently swallowed by pytest for a passing test. That means
    the marker text appears multiple times in pytest's own rendered output
    (echoed source line, the traceback's "E ..." line, a possibly-truncated
    short-summary line) and never at the very start of a line. Scan every
    line for the marker anywhere in it and return the first one whose tail
    parses as JSON -- the malformed/truncated occurrences fail to parse and
    are skipped.
    """
    for line in (output or "").splitlines():
        idx = line.find(_MODULE_RESULT_MARKER)
        if idx == -1:
            continue
        try:
            return json.loads(line[idx + len(_MODULE_RESULT_MARKER):])
        except json.JSONDecodeError:
            continue
    return None


def _build_module_validation_script(contract: ModuleContract, code: str) -> str:
    """Build a pytest file that runs exec/eval validation *inside the
    sandbox* and reports structured results via a marked stdout line -- the
    only channel available back to the host (the workspace mount is
    read-only from the container's side).

    code is embedded as a repr()'d string literal, executed into its own
    isolated dict rather than the test module's namespace. Trade-off:
    bandit's static scan (podman_runner.py's send_pulse) sees a string
    constant here, not executable source. Acceptable because bandit is
    defense-in-depth, not the containment boundary -- that's
    --network none / --cap-drop=all, unaffected by how the code is
    embedded in the file. Same pattern as contract_driven.py's
    _build_validation_script.
    """
    function_names = [f.name for f in contract.functions]
    tests = [
        {"name": t.name, "setup": t.setup, "steps": t.steps, "assertion": t.assertion}
        for t in contract.integration_tests
    ]

    return f'''
import json

_MARKER = {_MODULE_RESULT_MARKER!r}
_FUNCTION_NAMES = {function_names!r}
_TESTS = {tests!r}
_MODULE_CODE = {code!r}


def test_module_validation():
    failures = []
    exec_globals = {{}}
    try:
        exec(_MODULE_CODE, exec_globals)
    except Exception as e:
        failures.append(f"Execution error: {{e}}")
        raise AssertionError(_MARKER + json.dumps({{"failures": failures}}))

    for name in _FUNCTION_NAMES:
        if name not in exec_globals:
            failures.append(f"Function '{{name}}' not found")
            raise AssertionError(_MARKER + json.dumps({{"failures": failures}}))

    for test in _TESTS:
        try:
            # Fresh exec context per test: re-exec the module into its own
            # new dict rather than exec_globals.copy(). A shallow copy is
            # NOT isolation here -- functions keep __globals__ bound to the
            # dict they were originally exec'd into, so a `global`-mutating
            # function called via the copy still writes to (and is read
            # back from) the ORIGINAL exec_globals, not the copy the
            # assertion below actually inspects. That silently broke every
            # assertion over global-mutated state (the primary pattern for
            # the "stateful systems" this class exists for) before this fix.
            test_globals = {{}}
            exec(_MODULE_CODE, test_globals)
            if test["setup"]:
                exec(test["setup"], test_globals)
            for step in test["steps"]:
                exec(step, test_globals)
            result = eval(test["assertion"], test_globals)
            if not result:
                failures.append(f"{{test['name']}}: assertion failed - {{test['assertion']}}")
        except Exception as e:
            failures.append(f"{{test['name']}}: {{e}}")

    # Always raise -- pytest only reliably surfaces the message (vs. print()
    # output, which is captured/swallowed for a passing test) via a failure.
    # The real pass/fail verdict is _parse_module_marker()'s job on the host.
    raise AssertionError(_MARKER + json.dumps({{"failures": failures}}))
'''
