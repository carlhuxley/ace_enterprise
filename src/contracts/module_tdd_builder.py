"""Module TDD Builder - Builds module implementations using TDD.

This combines:
1. ModuleArchitect's contract (what to build)
2. Per-function generate → static-validate iteration
3. A whole-module integration-repair loop

Flow:
1. Take ModuleContract from architect
2. Build each function in isolation (generate → _validate_function)
3. Assemble the complete module
4. Run the rendered integration tests as final validation, repairing the
   whole module against failures up to `max_repair_attempts` times
5. If a Reflector + Curator are wired (issue #33), run one LEARN pass over the
   finished ModuleBuildResult and write delta bullets to the playbook so a
   later module / a re-run starts from those lessons
"""

import ast
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from src.audit.local_client import LocalAuditClient
from src.audit.schemas import AuditEventType
from src.contracts.module_architect import (
    FunctionSpec,
    ModuleContract,
    validate_module,
)
from src.utils.code_extraction import extract_code
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
    # Track actual model used (important for auto-routing learning)
    actual_model: str | None = None
    provider: str | None = None


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
    learned_bullets: list = field(default_factory=list)  # delta bullets from the LEARN pass


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
        max_repair_attempts: int = 2,
        *,
        reflector: Any = None,
        curator: Any = None,
        playbook_manager: Any = None,
        playbook_id: str | None = None,
    ):
        """Initialize the module TDD builder.

        Args:
            llm_client: LLM for code generation
            audit_client: Optional audit client for tracking
            model_id: Model identifier for audit
            max_attempts_per_function: Max TDD cycles per function
            max_repair_attempts: Max whole-module repair passes after the
                integration tests first run (functions are built in isolation,
                so integration failures need a fix-it loop that sees them)
            reflector, curator, playbook_manager, playbook_id: wire all four to
                enable the LEARN pass (issue #33) — prior bullets are fed into
                the build prompts and a delta is written back after each module.
        """
        self._llm = llm_client
        self._audit = audit_client
        self._model_id = model_id
        self._max_attempts = max_attempts_per_function
        self._max_repair_attempts = max_repair_attempts
        self._reflector = reflector
        self._curator = curator
        self._playbook_manager = playbook_manager
        self._playbook_id = playbook_id

    _MAX_PRIOR_BULLETS = 12

    def _prior_lessons(self) -> list[str]:
        """Bullet strings from *this project's* playbook to seed the build
        prompts (#33). Scoped to `self._playbook_id` — `get_bullets()` without
        an id aggregates across every playbook on disk."""
        if self._playbook_manager is None or not self._playbook_id:
            return []
        try:
            bullets = self._playbook_manager.get_section_bullets(
                self._playbook_id, "strategies_and_hard_rules"
            )
        except Exception:  # noqa: BLE001 -- retrieval is best-effort
            return []
        return [b.content for b in bullets][-self._MAX_PRIOR_BULLETS :]

    def build_module(
        self,
        contract: ModuleContract,
        session_id: str | None = None,
        dep_modules: dict[str, str] | None = None,
    ) -> ModuleBuildResult:
        """Build a complete module from contract using TDD.

        Args:
            contract: Module contract from architect
            session_id: Optional session ID for audit
            dep_modules: already-built upstream module sources
                ({module_name: code}). Their public symbols are offered to the
                implementer as concrete imports, made available in the
                validation sandbox, and guarded against local re-declaration
                (issue #28).

        Returns:
            ModuleBuildResult with implementation and metrics
        """
        start_time = time.time()
        function_results: list[FunctionBuildResult] = []
        total_cycles = 0
        dep_import_lines = _dep_import_lines(dep_modules)
        prior_lessons = self._prior_lessons()

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
                dep_import_lines=dep_import_lines,
                prior_lessons=prior_lessons,
            )

            function_results.append(result)
            total_cycles += result.tdd_cycles

            # Emit per-function audit event (captures actual model for learning)
            if self._audit:
                self._audit.emit_simple(
                    event_type=AuditEventType.CYCLE_COMPLETED,
                    actor_id=result.actual_model or self._model_id,  # Use actual model!
                    payload={
                        "contract_id": contract.id,
                        "function_name": func.name,
                        "complexity": contract.complexity,
                        "success": result.success,
                        "cycles": result.tdd_cycles,
                        "requested_model": self._model_id,
                        "actual_model": result.actual_model,
                        "provider": result.provider,
                    },
                    session_id=session_id,
                )

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

        # All functions built - run integration tests, then repair the whole
        # module against any failures (each function was built without seeing
        # the integration tests).
        logger.info("Running integration tests...")
        integration_results, integration_failures = self._run_integration_tests(
            contract=contract, module_code=module_code, dep_modules=dep_modules,
        )
        all_integration_passed = all(integration_results.values()) if integration_results else False

        repair = 0
        while not all_integration_passed and repair < self._max_repair_attempts:
            repair += 1
            logger.info(
                "Integration repair pass %d/%d (%d failing)",
                repair, self._max_repair_attempts, len(integration_failures),
            )
            repaired = self._repair_module(
                contract, module_code, integration_failures,
                dep_import_lines=dep_import_lines,
                prior_lessons=prior_lessons,
            )
            if repaired is None or repaired.strip() == module_code.strip():
                break
            module_code = repaired
            total_cycles += 1
            integration_results, integration_failures = self._run_integration_tests(
                contract=contract, module_code=module_code, dep_modules=dep_modules,
            )
            all_integration_passed = (
                all(integration_results.values()) if integration_results else False
            )

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

        # LEARN pass — one reflection over the finished module (#33). Both a
        # clean pass and a repaired/failed module carry reusable signal.
        learned = self._learn(
            contract, module_code, integration_failures,
            passed=all_integration_passed, repairs=repair,
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
            learned_bullets=learned,
        )

    # ------------------------------------------------------------------
    # Learning loop (Reflector → Curator → playbook write) — mirrors
    # tdd_cycle_runner._learn, one pass per module (#33).
    # ------------------------------------------------------------------

    def _learn(
        self, contract: ModuleContract, module_code: str, failures: list[str],
        *, passed: bool, repairs: int,
    ) -> list:
        if self._reflector is None or self._curator is None or not self._playbook_id:
            return []
        from src.storage.schemas import EnvironmentFeedback, GeneratorOutput, TaskInput

        task = TaskInput(
            id=f"module_{contract.name}_{contract.id}",
            query=f"Build the '{contract.name}' module: {contract.description}",
            type="module_tdd",
        )
        gen_output = GeneratorOutput(
            trajectory=(
                f"# module built via {repairs} integration-repair pass(es)\n"
                + render_integration_tests(contract, contract.name)
            ),
            solution=module_code,
            bullets_used=[],
            bullet_feedback={},
            latency_ms=0,
            tokens_used=0,
        )
        env_feedback = EnvironmentFeedback(
            result="SUCCESS" if passed else "FAILED",
            actual="all integration tests passed" if passed else "\n".join(failures[:5]),
            feedback=None if passed else "; ".join(failures[:3]),
        )
        try:
            reflector_output = self._reflector.reflect(task, gen_output, env_feedback)
            curator_output = self._curator.curate(
                reflector_output, self._playbook_id,
                task_context={"module": contract.name, "repairs": repairs, "passed": passed},
            )
            self._curator.apply_updates(self._playbook_id, curator_output)
            logger.info(
                "ModuleTDDBuilder: wrote %d bullet(s) to playbook '%s' after building '%s'",
                len(curator_output.delta_bullets), self._playbook_id, contract.name,
            )
            if self._audit is not None:
                for bullet in curator_output.delta_bullets:
                    try:
                        self._audit.emit_simple(
                            event_type=AuditEventType.PATTERN_LEARNED,
                            actor_id=self._model_id,
                            payload={"section": bullet.section, "module": contract.name},
                            playbook_id=self._playbook_id,
                        )
                    except Exception:  # noqa: BLE001 -- audit is best-effort
                        pass
            return list(curator_output.delta_bullets)
        except Exception as exc:  # noqa: BLE001 -- learning must never fail a build
            logger.warning("ModuleTDDBuilder: LEARN pass failed: %s", exc)
            return []

    def _build_function(
        self,
        func: FunctionSpec,
        shared_state: str,
        hints: list[str],
        existing_code: str,
        session_id: str | None = None,
        dep_import_lines: list[str] | None = None,
        prior_lessons: list[str] | None = None,
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
        dep_block = ""
        if dep_import_lines:
            dep_block = (
                "\n\n**Already-built sibling modules — import what you need, do NOT "
                "reimplement their functions:**\n```python\n"
                + "\n".join(dep_import_lines)
                + "\n```"
            )
        lessons_block = ""
        if prior_lessons:
            lessons_block = (
                "\n\n**Lessons from earlier builds — apply these:**\n"
                + "\n".join(f"- {b}" for b in prior_lessons)
            )

        prompt = f"""You are implementing ONE piece of a Python module.

**Existing module code:**
```python
{existing_code}
```

**To implement — `{func.name}`:**
```python
def {func.name}{func.signature}:
    \"\"\"{func.docstring}\"\"\"
    # Your implementation
```

**Implementation hints:**
{chr(10).join(f"- {h}" for h in hints) if hints else "None"}{dep_block}{lessons_block}

**Rules:**
1. Output ONLY this one definition. It is usually a `def`; if `{func.name}`
   is a class or exception (e.g. ends in Error/Exception, or is CamelCase),
   output a `class` instead.
2. It operates on the shared state shown above.
3. Keep it minimal and correct.
4. Standard-library imports are fine (json, pathlib, collections, ...) —
   put them at the top of your output. No third-party packages.
5. If you need behaviour from an already-built sibling module listed above,
   import it with the exact line shown — never redefine that function here.

Output ONLY the Python code for `{func.name}`:
"""

        actual_model = None
        provider = None

        for attempt in range(1, self._max_attempts + 1):
            logger.info(f"  Attempt {attempt}/{self._max_attempts}...")

            try:
                response = self._llm.generate(prompt)
                code = self._extract_function_code(response["content"], func.name)

                # Capture actual model used (for auto-routing learning)
                actual_model = response.get("actual_model", self._llm.model)
                provider = response.get("provider")

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
                    actual_model=actual_model,
                    provider=provider,
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
            actual_model=actual_model,
            provider=provider,
        )

    def _extract_function_code(self, response: str, function_name: str) -> str:
        """Extract function code from LLM response."""
        stripped = extract_code(response)
        # extract_code returns the full response unchanged when no fences are
        # present; in that case fall back to walking lines for the named def.
        if stripped != response.strip():
            return stripped

        lines = response.strip().split("\n")
        func_lines = []
        in_func = False

        for line in lines:
            if line.strip().startswith((f"def {function_name}", f"class {function_name}")):
                in_func = True
            if in_func:
                func_lines.append(line)
                if func_lines and line.strip() and not line.startswith((" ", "\t")):
                    if not line.startswith(("def", "class")):
                        break

        return "\n".join(func_lines).strip()

    def _validate_function(self, code: str, func: FunctionSpec) -> str | None:
        """Validate function code compiles and has correct structure.

        Returns:
            None if valid, error message if invalid
        """
        try:
            # Check it parses (raises SyntaxError if not)
            compile(code, "<string>", "exec")

            # The spec entry may be a function OR a class (e.g. an exception
            # like CircularDependencyError, or a dataclass).
            if f"def {func.name}" not in code and f"class {func.name}" not in code:
                return f"Definition of {func.name} (def or class) not found in code"

            return None

        except SyntaxError as e:
            return f"Syntax error: {e}"

    def _repair_module(
        self, contract: ModuleContract, module_code: str, failures: list[str],
        *, dep_import_lines: list[str] | None = None,
        prior_lessons: list[str] | None = None,
    ) -> str | None:
        """Ask the LLM to fix the whole module so the integration tests pass.

        Returns the repaired module source, or None on failure.
        """
        test_file = render_integration_tests(contract, contract.name)
        lessons_block = ""
        if prior_lessons:
            lessons_block = (
                "\n# lessons from earlier builds — apply these:\n"
                + "\n".join(f"# - {b}" for b in prior_lessons)
                + "\n"
            )
        dep_block = ""
        if dep_import_lines:
            dep_block = (
                "\n# these symbols are provided by already-built sibling modules — "
                "IMPORT them, never define them in this module:\n"
                + "\n".join(dep_import_lines)
                + "\n(a local def/class shadowing one of these names is a bug to fix)\n"
            )
        prompt = (
            "The module below fails some of its integration tests. Rewrite the "
            "COMPLETE module so every test passes. Keep the public function "
            "signatures. Standard library only, plus the sibling-module imports "
            "noted below.\n\n"
            f"# {contract.name}.py\n```python\n{module_code}\n```\n\n"
            f"# integration tests\n```python\n{test_file}\n```\n\n"
            f"# failures\n" + "\n".join(f"- {f}" for f in failures) + "\n"
            + dep_block + lessons_block + "\n"
            "Output ONLY the corrected Python module."
        )
        try:
            response = self._llm.generate(prompt)
            code = extract_code(response["content"])
            return code or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("module repair pass failed: %s", exc)
            return None

    def _run_integration_tests(
        self,
        contract: ModuleContract,
        module_code: str,
        dep_modules: dict[str, str] | None = None,
    ) -> tuple[dict[str, bool], list[str]]:
        """Run integration tests against the built module.

        Args:
            contract: Module contract with integration tests
            module_code: Complete module implementation
            dep_modules: already-built upstream module sources, made available
                in the sandbox and checked for local re-declaration (issue #28)

        Returns:
            Tuple of (dict mapping test name to pass/fail, list of failure messages)
        """
        # Use the existing validate_module function which runs integration tests
        passed, failures = validate_module(contract, module_code, extra_files=dep_modules)

        # A downstream module that re-defines an upstream symbol still passes a
        # flat-workspace test run — flag it as a failure so the repair loop
        # replaces the duplicate with an import (issue #28).
        dup = _redeclared_upstream(module_code, _upstream_symbols(dep_modules))
        if dup:
            failures = [*dup, *failures]

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
    enable_audit: bool = True,
) -> ModuleTDDBuilder:
    """Factory function to create a TDD builder with common config.

    Args:
        provider: LLM provider (e.g., "togetherai")
        model: Model name
        base_url: Optional base URL for API
        audit_db_url: Optional audit database URL (defaults to AUDIT_DATABASE_URL
            env var or .local/audit.db)
        enable_audit: Enable audit logging (default True, respects AUDIT_DISABLED env)

    Returns:
        Configured ModuleTDDBuilder
    """
    llm_client = LLMClient(provider=provider, model=model, base_url=base_url)

    audit_client = None
    audit_disabled = os.getenv("AUDIT_DISABLED", "").lower() == "true"
    if enable_audit and not audit_disabled:
        db_url = audit_db_url or os.getenv("AUDIT_DATABASE_URL")
        audit_client = LocalAuditClient(db_url)  # Uses .local/audit.db if None

    model_id = f"{provider}-{model}"

    return ModuleTDDBuilder(
        llm_client=llm_client,
        audit_client=audit_client,
        model_id=model_id,
    )


def _safe_test_name(name: str) -> str:
    slug = re.sub(r"\W+", "_", name.strip().lower()).strip("_") or "case"
    return slug if slug.startswith("test_") else f"test_{slug}"


def _shared_state_names(shared_state: str) -> list[str]:
    """Top-level names bound in `shared_state` (`_count = 0`, `inventory: dict = {}`)."""
    names: list[str] = []
    for line in (shared_state or "").splitlines():
        m = re.match(r"\s*([A-Za-z_]\w*)\s*[:=]", line)
        if m and m.group(1) not in names:
            names.append(m.group(1))
    return names


def _upstream_symbols(dep_modules: dict[str, str] | None) -> dict[str, str]:
    """Map each public top-level `def`/`class` name in the already-built
    dependency sources to its owning module name."""
    out: dict[str, str] = {}
    for mod_name, src in (dep_modules or {}).items():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    out.setdefault(node.name, mod_name)
    return out


def _dep_import_lines(dep_modules: dict[str, str] | None) -> list[str]:
    """Concrete `from <module> import <symbols>` lines for every upstream
    dependency, so prompts and rendered tests can hand the model exactly the
    imports it should use instead of reimplementing (issue #28)."""
    by_mod: dict[str, list[str]] = {}
    for sym, mod in _upstream_symbols(dep_modules).items():
        by_mod.setdefault(mod, []).append(sym)
    return [
        f"from {mod} import {', '.join(sorted(syms))}"
        for mod, syms in sorted(by_mod.items())
    ]


_DEF_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
# Compound statements whose bodies are still module scope — a def guarded by
# one of these rebinds the module name just like a bare top-level def does.
_SCOPE_TRANSPARENT: tuple[type[ast.AST], ...] = (
    ast.Try, ast.If, ast.With, ast.AsyncWith,
    ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
    ast.Match, ast.match_case,
    *((ast.TryStar,) if hasattr(ast, "TryStar") else ()),
)


def _module_scope_defs(tree: ast.Module) -> list[str]:
    """Names bound by a `def`/`class` at module scope, including ones nested in
    `try`/`if`/`with`/`for`/`while` blocks — but not methods or closures inside
    a function or class body (those may legitimately reuse a name)."""
    names: list[str] = []
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, _DEF_NODES):
            names.append(node.name)  # do not descend — its body is a new scope
        elif isinstance(node, _SCOPE_TRANSPARENT):
            stack.extend(ast.iter_child_nodes(node))
    return names


def _redeclared_upstream(module_code: str, upstream: dict[str, str]) -> list[str]:
    """Messages for any module-scope `def`/`class` in `module_code` that shadows
    a symbol an upstream dependency already provides — the module should import
    it, not carry a duplicate (issue #28). Catches definitions guarded by
    `try/except ImportError` and other compound statements (issue #30)."""
    if not upstream:
        return []
    try:
        tree = ast.parse(module_code)
    except SyntaxError:
        return []
    msgs: list[str] = []
    for name in dict.fromkeys(_module_scope_defs(tree)):
        if name in upstream:
            mod = upstream[name]
            msgs.append(
                f"{name}: defined locally but already provided by the "
                f"already-built module '{mod}' — delete this definition and "
                f"`from {mod} import {name}` instead"
            )
    return msgs


def _local_names(block: str) -> set[str]:
    """Names bound (assigned / looped over) within a block of statements."""
    try:
        tree = ast.parse(block)
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store,)):
            out.add(node.id)
        elif isinstance(node, (ast.For, ast.comprehension)):
            out |= {n.id for n in ast.walk(node.target) if isinstance(n, ast.Name)}
    return out


def _qualify(src: str, module_names: set[str], skip: set[str]) -> str:
    """Rewrite bare references to `module_names` -> `_module.<name>` (leaving
    `skip` — names bound locally in the test — alone) so the generated pytest
    reads and writes the module's live state instead of a stale `import *`
    copy. Returns `src` unchanged if it doesn't parse."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    targets = module_names - skip

    class _Q(ast.NodeTransformer):
        def visit_Name(self, node: ast.Name):
            if node.id in targets:
                return ast.copy_location(
                    ast.Attribute(
                        value=ast.Name(id="_module", ctx=ast.Load()),
                        attr=node.id,
                        ctx=node.ctx,
                    ),
                    node,
                )
            return node

    ast.fix_missing_locations(_Q().visit(tree))
    return ast.unparse(tree)


_RESET_FIXTURE = '''\
import copy as _copy
import types as _types

import pytest as _pytest

_STATE_NAMES = {state_names}


def _snapshot():
    snap = {{}}
    for name in dir(_module):
        if name.startswith("__"):
            continue
        value = getattr(_module, name)
        if callable(value) or isinstance(value, (_types.ModuleType, type)):
            if name not in _STATE_NAMES:
                continue
        try:
            snap[name] = _copy.deepcopy(value)
        except Exception:
            pass
    return snap


_INITIAL_STATE = _snapshot()


@_pytest.fixture(autouse=True)
def _reset_module_state():
    """Restore {module}'s module-level state before each test — the contract's
    tests assume a fresh module and pytest shares one process."""
    for name, value in _INITIAL_STATE.items():
        setattr(_module, name, _copy.deepcopy(value))
    yield
'''


def render_integration_tests(
    contract: ModuleContract, module_name: str,
    dep_modules: dict[str, str] | None = None,
) -> str:
    """Serialize a `ModuleContract`'s integration tests into a runnable pytest
    file: `import <module_name> as _module`, an autouse fixture that resets the
    module's state before each test, and one `def test_*()` per integration
    test whose setup/steps/assertion have bare module names rewritten to
    `_module.<name>` so they act on the live module (#25).

    `dep_modules` ({module_name: source}) are the already-built upstream
    dependencies: their public symbols are imported at the top of the file so a
    test step that calls one resolves (issue #28).
    """
    module_names = {f.name for f in contract.functions}
    module_names |= set(_shared_state_names(contract.shared_state))

    state_names = _shared_state_names(contract.shared_state)
    dep_imports = "".join(
        f"{line}  # noqa: F401\n" for line in _dep_import_lines(dep_modules)
    )
    header = (
        f'"""Integration tests for `{module_name}`, generated from its '
        f'ModuleContract."""\n'
        f"import {module_name} as _module  # noqa: F401\n"
        + dep_imports
        + "\n"
        + _RESET_FIXTURE.format(module=module_name, state_names=set(state_names) or set())
        + "\n"
    )

    if not contract.integration_tests:
        return header + "\ndef test_module_importable():\n    assert _module is not None\n"

    blocks: list[str] = []
    for t in contract.integration_tests:
        raw = "\n".join(
            [s.strip() for s in (t.setup or "").splitlines() if s.strip()]
            + [s.strip() for s in t.steps if s.strip()]
        )
        fn = _safe_test_name(t.name)
        try:
            ast.parse(f"{raw}\n_ = ({t.assertion or 'True'})")
        except SyntaxError as exc:
            blocks.append(
                f"def {fn}():\n    import pytest\n"
                f"    pytest.fail({f'contract test {t.name!r} does not parse: {exc}'!r})"
            )
            continue
        # A test-local var stays bare; a *module* name stays qualified even when
        # assigned (e.g. `_count = 0` in setup means "reset module state").
        skip = _local_names(raw) - module_names
        body_lines = [
            f"    {line}" for line in _qualify(raw, module_names, skip).splitlines() if line.strip()
        ]
        assertion = _qualify(t.assertion.strip() or "True", module_names, skip).strip()
        block = [f"def {fn}():"]
        block += body_lines or ["    pass"]
        block.append(f"    assert {assertion}")
        blocks.append("\n".join(block))
    return header + "\n" + "\n\n\n".join(blocks) + "\n"
