"""ProjectBuilder — build every module of a ProjectPlan in dependency order.

For each module (topological order from the plan):
  1. `ModuleArchitect` generates a `ModuleContract`, seeded with the
     `CodebaseContext` of everything built so far.
  2. `ModuleTDDBuilder` builds the implementation.
  3. The implementation + a rendered pytest file are written into the project.
Then the whole project test suite is run once as a cross-module assembly check.

Sandboxed: `ModuleTDDBuilder`'s integration-test validation and the assembly
run both go through the Podman sandbox (`--network none`, `--cap-drop=all`).
No generated code executes on the host.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path

from src.audit.local_client import LocalAuditClient
from src.audit.schemas import AuditEventType
from src.contracts.project_architect import ModuleSpec, ProjectPlan
from src.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


class ModuleStatus(StrEnum):
    BUILT = "built"
    FAILED = "failed"
    BLOCKED = "blocked"     # a dependency failed / an earlier module failed
    SKIPPED = "skipped"     # --resume: already present and passing


@dataclass
class ModuleOutcome:
    name: str
    status: ModuleStatus
    contract_id: str | None = None
    cycles: int = 0
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "contract_id": self.contract_id,
            "cycles": self.cycles,
            "error": self.error,
        }


@dataclass
class ProjectBuildResult:
    outcomes: list[ModuleOutcome]
    assembly_passed: bool | None = None            # None = not run
    assembly_failures: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        modules_ok = all(
            o.status in (ModuleStatus.BUILT, ModuleStatus.SKIPPED) for o in self.outcomes
        )
        return modules_ok and self.assembly_passed is not False

    def to_payload(self) -> dict:
        return {
            "modules": [o.to_dict() for o in self.outcomes],
            "assembly_passed": self.assembly_passed,
            "assembly_failures": self.assembly_failures,
            "success": self.success,
        }


class ProjectBuilder:
    """Drives ModuleArchitect + ModuleTDDBuilder over a ProjectPlan."""

    def __init__(
        self,
        llm_client: LLMClient,
        *,
        audit_client: LocalAuditClient | None = None,
        model_id: str = "unknown",
        architect_factory=None,
        builder_factory=None,
        assembler=None,
    ) -> None:
        self._llm = llm_client
        self._audit = audit_client
        self._model_id = model_id
        # Test seams — default to the real sandboxed components.
        self._make_architect = architect_factory or self._default_architect
        self._make_builder = builder_factory or self._default_builder
        self._assemble = assembler or _run_assembly

    def _default_architect(self):
        from src.contracts.module_architect import ModuleArchitect

        return ModuleArchitect(self._llm, self._audit, self._model_id)

    def _default_builder(self):
        from src.contracts.module_tdd_builder import ModuleTDDBuilder

        return ModuleTDDBuilder(self._llm, self._audit, self._model_id)

    # ------------------------------------------------------------------

    def build(
        self,
        plan: ProjectPlan,
        project_root: Path,
        src_dir: Path,
        test_dir: Path,
        *,
        resume: bool = False,
        stop_on_failure: bool = True,
        session_id: str | None = None,
    ) -> ProjectBuildResult:
        src_dir, test_dir = Path(src_dir), Path(test_dir)
        src_dir.mkdir(parents=True, exist_ok=True)
        test_dir.mkdir(parents=True, exist_ok=True)

        by_name = {m.name: m for m in plan.modules}
        outcomes: list[ModuleOutcome] = []
        failed: set[str] = set()
        relinked: set[str] = set()
        stopped_at: int | None = None
        # Only modules produced by THIS run become context for later modules —
        # never pre-existing files in src_dir.
        built_paths: list[Path] = []

        for idx, name in enumerate(plan.build_order):
            module = by_name[name]
            blockers = [d for d in module.depends_on if d in failed]
            if blockers:
                outcomes.append(ModuleOutcome(
                    name, ModuleStatus.BLOCKED,
                    error=f"blocked by failed dependency: {', '.join(blockers)}",
                ))
                failed.add(name)
                continue

            impl_path = src_dir / f"{name}.py"
            test_path = test_dir / f"test_{name}.py"

            if resume and impl_path.exists() and test_path.exists():
                outcomes.append(ModuleOutcome(name, ModuleStatus.SKIPPED))
                built_paths.append(impl_path)
                continue

            outcome = self._build_module(module, built_paths, impl_path, test_path)

            # The plan may have under-specified the DAG: if the generated module
            # reaches for an already-built sibling it never declared, add that
            # edge and rebuild once so the dependency-import machinery engages
            # instead of the model inlining a copy (issue #30).
            missing = _undeclared_sibling_deps(impl_path, module, by_name, built_paths)
            if missing and name not in relinked:
                relinked.add(name)
                logger.warning(
                    "%s uses undeclared sibling module(s) %s — adding the "
                    "dependency edge(s) and rebuilding",
                    name, ", ".join(sorted(missing)),
                )
                module = replace(
                    module,
                    depends_on=tuple(dict.fromkeys((*module.depends_on, *sorted(missing)))),
                )
                by_name[name] = module
                outcome = self._build_module(module, built_paths, impl_path, test_path)

            outcomes.append(outcome)
            if outcome.status is ModuleStatus.BUILT:
                built_paths.append(impl_path)
            if outcome.status is ModuleStatus.FAILED:
                failed.add(name)
                if stop_on_failure:
                    stopped_at = idx
                    break

        if stopped_at is not None:
            for name in plan.build_order[stopped_at + 1:]:
                outcomes.append(ModuleOutcome(
                    name, ModuleStatus.BLOCKED, error="not attempted — an earlier module failed",
                ))

        result = ProjectBuildResult(outcomes=outcomes)

        any_code = any(o.status in (ModuleStatus.BUILT, ModuleStatus.SKIPPED) for o in outcomes)
        any_failed = any(o.status is ModuleStatus.FAILED for o in outcomes)
        if any_code and not any_failed:
            passed, failures = self._assemble(test_dir, src_dir)
            result.assembly_passed = passed
            result.assembly_failures = failures

        self._emit(plan, result, session_id)
        return result

    # ------------------------------------------------------------------

    def _build_module(
        self, module: ModuleSpec, built_paths: list[Path], impl_path: Path, test_path: Path
    ) -> ModuleOutcome:
        from src.contracts.module_tdd_builder import render_integration_tests

        context = _context_from_built(built_paths)
        # Sources of this module's *declared* upstream dependencies — handed to
        # the builder so it imports them instead of inlining copies (issue #28).
        dep_names = set(module.depends_on)
        dep_modules = {p.stem: _safe_read(p) for p in built_paths if p.stem in dep_names}

        architect = self._make_architect()
        arch = architect.generate_module_contract(
            requirement=module.description, context=context,
        )
        if not arch.success or arch.contract is None:
            return ModuleOutcome(module.name, ModuleStatus.FAILED,
                                 error=f"architect: {arch.error}")

        contract = arch.contract
        build = self._make_builder().build_module(contract, dep_modules=dep_modules)

        # Persist what was generated even on failure, so it can be inspected.
        impl_path.write_text(build.module_code or "")
        test_path.write_text(
            render_integration_tests(contract, module.name, dep_modules=dep_modules)
        )

        if not build.success:
            return ModuleOutcome(
                module.name, ModuleStatus.FAILED,
                contract_id=contract.id, cycles=build.total_cycles, error=build.error,
            )
        return ModuleOutcome(
            module.name, ModuleStatus.BUILT, contract_id=contract.id, cycles=build.total_cycles,
        )

    def _emit(self, plan: ProjectPlan, result: ProjectBuildResult, session_id: str | None) -> None:
        if self._audit is None:
            return
        try:
            self._audit.emit_simple(
                event_type=AuditEventType.PROJECT_BUILD_COMPLETED,
                actor_id=self._model_id,
                payload={
                    "build_order": list(plan.build_order),
                    **result.to_payload(),
                },
                session_id=session_id,
            )
        except Exception:  # noqa: BLE001 -- audit is best-effort
            logger.debug("project-build audit emit failed", exc_info=True)


def _undeclared_sibling_deps(
    impl_path: Path,
    module: ModuleSpec,
    by_name: dict[str, ModuleSpec],
    built_paths: list[Path],
) -> set[str]:
    """Already-built sibling modules this one calls into or imports from but
    never listed in `depends_on` — a plan that under-specified the DAG (#30).

    Only already-built siblings count, so adding the edge and rebuilding can
    never introduce a cycle.
    """
    try:
        tree = ast.parse(impl_path.read_text())
    except (OSError, SyntaxError):
        return set()

    from src.contracts.module_architect import extract_context_from_file

    built_stems = {p.stem: p for p in built_paths if p.stem != module.name}
    provider: dict[str, str] = {}
    for stem, path in built_stems.items():
        try:
            ctx = extract_context_from_file(str(path))
        except Exception:  # noqa: BLE001 -- context extraction is best-effort
            continue
        for fn in ctx.existing_functions:
            provider.setdefault(fn.name, stem)

    referenced = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    imported: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            imported.add(n.module.split(".")[0])

    declared = set(module.depends_on)
    missing = {
        owner for sym, owner in provider.items()
        if owner not in declared and sym in referenced
    }
    missing |= (imported & set(built_stems) & set(by_name)) - declared
    missing.discard(module.name)
    return missing


def _context_from_built(built_paths: list[Path]):
    """A CodebaseContext from the modules built earlier in this run (their
    function signatures), so a later module can import and call them. None
    when nothing has been built yet."""
    if not built_paths:
        return None
    from src.contracts.module_architect import CodebaseContext, extract_context_from_file

    ctx = CodebaseContext()
    for path in built_paths:
        try:
            got = extract_context_from_file(str(path))
        except Exception:  # noqa: BLE001 -- context is best-effort
            continue
        ctx.existing_functions.extend(got.existing_functions)
        ctx.patterns.extend(p for p in got.patterns if p not in ctx.patterns)
    return ctx if ctx.existing_functions else None


def _run_assembly(test_dir: Path, src_dir: Path) -> tuple[bool, list[str]]:
    """Run the whole project's test suite in one sandboxed container.

    Every `src/*.py` and `tests/test_*.py` goes into a flat workspace (so
    `from <module> import *` resolves between siblings) and pytest runs over
    it. Returns (passed, failure messages).
    """
    files: dict[str, str] = {}
    for p in sorted(src_dir.glob("*.py")):
        files[p.name] = _safe_read(p)
    test_files = sorted(test_dir.glob("test_*.py"))
    for p in test_files:
        files[p.name] = _safe_read(p)
    if not test_files:
        return True, []

    from src.agents.podman_orchestrator import PodmanOrchestrator, SecurityBreachError
    from src.agents.podman_runner import PodmanRunner

    orch = PodmanOrchestrator(PodmanRunner(test_timeout=60, writable_workdir=True))
    try:
        phase = orch.pulse(files)
    except SecurityBreachError as exc:
        return False, [f"SecurityBreach: {exc}"]
    except Exception as exc:  # noqa: BLE001
        return False, [f"assembly run error: {exc}"]
    finally:
        orch.stop()

    if phase.passed:
        return True, []
    return False, [(phase.error or phase.output or "assembly tests failed").strip()[:2000]]


def _safe_read(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""
