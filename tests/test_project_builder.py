"""Tests for src/cli/project_builder.py.

ModuleArchitect, ModuleTDDBuilder and the Podman assembly run are all injected
as fakes -- no LLM / container.
"""
from types import SimpleNamespace

import pytest

from src.cli.project_builder import ModuleStatus, ProjectBuilder
from src.contracts.module_architect import FunctionSpec, IntegrationTest, ModuleContract
from src.contracts.project_architect import ModuleSpec, ProjectPlan


def _contract(name: str) -> ModuleContract:
    return ModuleContract(
        id=f"{name}-1",
        name=name,
        description=f"the {name} module",
        shared_state="",
        functions=[FunctionSpec(f"{name}_fn", "() -> int", "does a thing")],
        integration_tests=[IntegrationTest(f"{name}_works", "", [f"{name}_fn()"], "True")],
        complexity=1,
    )


class FakeArchitect:
    def __init__(self, fail: set[str] | None = None):
        self.fail = fail or set()
        self.seen: list[tuple[str, object]] = []

    def generate_module_contract(self, *, requirement, context=None):
        self.seen.append((requirement, context))
        name = requirement.split()[1]  # "the <name> module"
        if name in self.fail:
            return SimpleNamespace(success=False, contract=None, error="architect boom")
        return SimpleNamespace(success=True, contract=_contract(name), error=None)


class FakeBuilder:
    def __init__(self, fail: set[str] | None = None):
        self.fail = fail or set()
        self.seen_deps: list[dict[str, str]] = []

    def build_module(self, contract, dep_modules=None):
        self.seen_deps.append(dep_modules or {})
        ok = contract.name not in self.fail
        return SimpleNamespace(
            success=ok,
            module_code=f"def {contract.name}_fn():\n    return 1\n",
            total_cycles=2,
            error=None if ok else "green failed",
        )


def _plan(*modules: ModuleSpec) -> ProjectPlan:
    return ProjectPlan(spec="x", modules=list(modules))


@pytest.fixture
def dirs(tmp_path):
    src = tmp_path / "src"
    tests = tmp_path / "tests"
    return tmp_path, src, tests


def _builder(dirs, *, architect, builder, assembler=lambda t, s: (True, [])):
    return ProjectBuilder(
        llm_client=object(),
        architect_factory=lambda: architect,
        builder_factory=lambda: builder,
        assembler=assembler,
    )


def test_builds_modules_in_topological_order(dirs):
    root, src, tests = dirs
    plan = _plan(
        ModuleSpec("api", "the api module", depends_on=("db",)),
        ModuleSpec("db", "the db module"),
    )
    arch = FakeArchitect()
    pb = _builder(dirs, architect=arch, builder=FakeBuilder())
    result = pb.build(plan, root, src, tests)

    assert [o.name for o in result.outcomes] == ["db", "api"]
    assert all(o.status is ModuleStatus.BUILT for o in result.outcomes)
    assert (src / "db.py").exists() and (src / "api.py").exists()
    assert (tests / "test_db.py").exists() and (tests / "test_api.py").exists()
    assert result.assembly_passed is True
    assert result.success


def test_downstream_module_is_blocked_when_a_dependency_fails(dirs):
    root, src, tests = dirs
    plan = _plan(
        ModuleSpec("api", "the api module", depends_on=("db",)),
        ModuleSpec("db", "the db module"),
    )
    pb = _builder(dirs, architect=FakeArchitect(), builder=FakeBuilder(fail={"db"}))
    result = pb.build(plan, root, src, tests, stop_on_failure=True)

    by_name = {o.name: o for o in result.outcomes}
    assert by_name["db"].status is ModuleStatus.FAILED
    assert by_name["api"].status is ModuleStatus.BLOCKED
    assert result.assembly_passed is None  # not run when a module failed
    assert result.success is False


def test_keep_going_still_attempts_independent_modules(dirs):
    root, src, tests = dirs
    plan = _plan(
        ModuleSpec("a", "the a module"),
        ModuleSpec("b", "the b module"),
        ModuleSpec("c", "the c module", depends_on=("a",)),
    )
    pb = _builder(dirs, architect=FakeArchitect(), builder=FakeBuilder(fail={"a"}))
    result = pb.build(plan, root, src, tests, stop_on_failure=False)

    by_name = {o.name: o for o in result.outcomes}
    assert by_name["a"].status is ModuleStatus.FAILED
    assert by_name["b"].status is ModuleStatus.BUILT       # independent, still built
    assert by_name["c"].status is ModuleStatus.BLOCKED     # depends on failed a


def test_resume_skips_modules_whose_files_exist(dirs):
    root, src, tests = dirs
    src.mkdir()
    tests.mkdir()
    (src / "db.py").write_text("x = 1\n")
    (tests / "test_db.py").write_text("def test_x(): pass\n")
    plan = _plan(ModuleSpec("db", "the db module"), ModuleSpec("api", "the api module", depends_on=("db",)))
    arch = FakeArchitect()
    pb = _builder(dirs, architect=arch, builder=FakeBuilder())
    result = pb.build(plan, root, src, tests, resume=True)

    by_name = {o.name: o for o in result.outcomes}
    assert by_name["db"].status is ModuleStatus.SKIPPED
    assert by_name["api"].status is ModuleStatus.BUILT
    assert [r for r, _ in arch.seen] == ["the api module"]  # db never sent to architect


def test_later_modules_get_prior_modules_as_context(dirs):
    root, src, tests = dirs
    plan = _plan(
        ModuleSpec("db", "the db module"),
        ModuleSpec("api", "the api module", depends_on=("db",)),
    )
    arch = FakeArchitect()
    pb = _builder(dirs, architect=arch, builder=FakeBuilder())
    pb.build(plan, root, src, tests)

    contexts = dict(arch.seen)
    assert contexts["the db module"] is None                 # nothing built yet
    assert contexts["the api module"] is not None            # db.py scanned into context


def test_declared_dependency_sources_are_handed_to_the_builder(dirs):
    """The builder gets the source of each *declared* upstream module so it
    can import from it instead of reimplementing (issue #28)."""
    root, src, tests = dirs
    plan = _plan(
        ModuleSpec("api", "the api module", depends_on=("db",)),
        ModuleSpec("db", "the db module"),
    )
    fb = FakeBuilder()
    _builder(dirs, architect=FakeArchitect(), builder=fb).build(plan, root, src, tests)

    assert fb.seen_deps[0] == {}                       # db: nothing built yet
    assert set(fb.seen_deps[1]) == {"db"}              # api: db's source only
    assert "db_fn" in fb.seen_deps[1]["db"]


def test_preexisting_src_files_are_not_used_as_context(dirs):
    """A greenfield first module must not pick up unrelated files already in src/."""
    root, src, tests = dirs
    src.mkdir()
    (src / "unrelated.py").write_text("def legacy_helper():\n    return 1\n")
    plan = _plan(ModuleSpec("thing", "the thing module"))
    arch = FakeArchitect()
    _builder(dirs, architect=arch, builder=FakeBuilder()).build(plan, root, src, tests)
    assert dict(arch.seen)["the thing module"] is None


def test_assembly_failure_makes_the_result_unsuccessful(dirs):
    root, src, tests = dirs
    plan = _plan(ModuleSpec("db", "the db module"))
    pb = _builder(
        dirs, architect=FakeArchitect(), builder=FakeBuilder(),
        assembler=lambda t, s: (False, ["2 failed"]),
    )
    result = pb.build(plan, root, src, tests)
    assert all(o.status is ModuleStatus.BUILT for o in result.outcomes)
    assert result.assembly_passed is False
    assert result.success is False


def test_emits_project_build_completed_audit_event(dirs, tmp_path):
    from src.audit.local_client import LocalAuditClient
    from src.audit.schemas import AuditEventType
    from src.audit.store import AuditQuery

    root, src, tests = dirs
    audit = LocalAuditClient(database_url=f"sqlite:///{tmp_path / 'a.db'}")
    pb = ProjectBuilder(
        llm_client=object(), audit_client=audit, model_id="m",
        architect_factory=lambda: FakeArchitect(),
        builder_factory=lambda: FakeBuilder(),
        assembler=lambda t, s: (True, []),
    )
    pb.build(_plan(ModuleSpec("db", "the db module")), root, src, tests)
    events = audit._store.query(
        AuditQuery(event_types=[AuditEventType.PROJECT_BUILD_COMPLETED], limit=10)
    ).events
    assert len(events) == 1
    assert events[0].payload["build_order"] == ["db"]
    assert events[0].payload["success"] is True
