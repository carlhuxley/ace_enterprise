"""Tests for src/cli/project_builder.py.

ModuleArchitect, ModuleTDDBuilder and the Podman assembly run are all injected
as fakes -- no LLM / container.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.cli.project_builder import (
    MODULE_STATUS_RELPATH,
    ModuleStatus,
    ProjectBuilder,
    _run_assembly,
)
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
        self.seen_contract_yaml: list[str | None] = []

    def generate_module_contract(self, *, requirement, context=None, contract_yaml=None):
        self.seen.append((requirement, context))
        self.seen_contract_yaml.append(contract_yaml)
        name = requirement.split()[1]  # "the <name> module"
        if name in self.fail:
            return SimpleNamespace(success=False, contract=None, error="architect boom")
        return SimpleNamespace(success=True, contract=_contract(name), error=None)


class FakeBuilder:
    def __init__(self, fail: set[str] | None = None):
        self.fail = fail or set()
        self.seen_deps: list[dict[str, str]] = []
        self.seen_known_project_modules: list[set[str]] = []

    def build_module(self, contract, dep_modules=None, known_project_modules=None):
        self.seen_deps.append(dep_modules or {})
        self.seen_known_project_modules.append(known_project_modules or set())
        ok = contract.name not in self.fail
        return SimpleNamespace(
            success=ok,
            module_code=f"def {contract.name}_fn():\n    return 1\n",
            total_cycles=2,
            error=None if ok else "green failed",
            learned_bullets=["b1", "b2"] if ok else [],
        )


class FlakyBuilder:
    """Fails a module's first build, succeeds on the next attempt --
    models the shape of a bug Reflector/Curator's fresh bullets actually fix."""

    def __init__(self, fail_first: set[str] | None = None):
        self.fail_first = fail_first or set()
        self.attempts: dict[str, int] = {}

    def build_module(self, contract, dep_modules=None, known_project_modules=None):
        n = self.attempts.get(contract.name, 0) + 1
        self.attempts[contract.name] = n
        if contract.name in self.fail_first and n == 1:
            return SimpleNamespace(
                success=False, module_code="", total_cycles=1,
                error="green failed", learned_bullets=[],
            )
        return SimpleNamespace(
            success=True, module_code=f"def {contract.name}_fn():\n    return 1\n",
            total_cycles=1, error=None, learned_bullets=["b1"],
        )


class ConstantEmittingBuilder:
    """Every module it builds defines the same top-level constant -- models
    the #56 shape (two independently-built modules each needing "the data
    file path" as a constant)."""

    def build_module(self, contract, dep_modules=None, known_project_modules=None):
        code = f"DATA_FILE: str = 'shared.json'\ndef {contract.name}_fn():\n    return 1\n"
        return SimpleNamespace(success=True, module_code=code, total_cycles=1, error=None)


class SiblingCallingBuilder:
    """Emits `web` code that calls core_fn() regardless of what the plan
    declared — models the #30 'plan under-specified the DAG' shape."""

    def __init__(self):
        self.calls: list[tuple[str, set[str]]] = []

    def build_module(self, contract, dep_modules=None, known_project_modules=None):
        self.calls.append((contract.name, set(dep_modules or {})))
        code = (
            "def web_fn():\n    return core_fn() + 1\n"
            if contract.name == "web"
            else f"def {contract.name}_fn():\n    return 1\n"
        )
        return SimpleNamespace(success=True, module_code=code, total_cycles=1, error=None)


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


def test_a_modules_contract_yaml_reaches_the_architect_call(dirs):
    """Issue #57 follow-up: a --from-spec-dir module's formal contract text
    must reach ModuleArchitect, not just its one-line description."""
    root, src, tests = dirs
    plan = _plan(
        ModuleSpec("db", "the db module", contract_yaml="module: db\ndepends_on: []\n"),
        ModuleSpec("api", "the api module", depends_on=("db",), contract_yaml=None),
    )
    arch = FakeArchitect()
    pb = _builder(dirs, architect=arch, builder=FakeBuilder())
    result = pb.build(plan, root, src, tests)

    assert arch.seen_contract_yaml == ["module: db\ndepends_on: []\n", None]
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


def test_a_failed_module_is_retried_once_automatically(dirs):
    """Issue #52: a failure already ran Reflector/Curator, writing fresh
    playbook bullets diagnosing it -- retry once with that guidance instead
    of stopping immediately."""
    root, src, tests = dirs
    plan = _plan(ModuleSpec("db", "the db module"))
    fb = FlakyBuilder(fail_first={"db"})
    pb = _builder(dirs, architect=FakeArchitect(), builder=fb)
    result = pb.build(plan, root, src, tests, stop_on_failure=True)

    assert result.outcomes[0].status is ModuleStatus.BUILT
    assert fb.attempts["db"] == 2


def test_a_permanently_failing_module_is_only_retried_once(dirs):
    root, src, tests = dirs
    plan = _plan(ModuleSpec("db", "the db module"))
    fb = FakeBuilder(fail={"db"})
    pb = _builder(dirs, architect=FakeArchitect(), builder=fb)
    result = pb.build(plan, root, src, tests, stop_on_failure=True)

    assert result.outcomes[0].status is ModuleStatus.FAILED
    assert len(fb.seen_deps) == 2  # one retry, not an unbounded loop


def test_module_status_is_persisted_after_build(dirs):
    root, src, tests = dirs
    plan = _plan(
        ModuleSpec("db", "the db module"),
        ModuleSpec("api", "the api module", depends_on=("db",)),
    )
    pb = _builder(dirs, architect=FakeArchitect(), builder=FakeBuilder(fail={"api"}))
    pb.build(plan, root, src, tests, stop_on_failure=False)

    status = json.loads((root / MODULE_STATUS_RELPATH).read_text())
    assert status == {"db": "built", "api": "failed"}


def test_resume_rebuilds_a_module_that_previously_failed(dirs):
    """A stale src/test file pair left behind by a failed build must not be
    treated as a pass just because --resume sees files on disk (issue #52)."""
    root, src, tests = dirs
    src.mkdir()
    tests.mkdir()
    (src / "db.py").write_text("# broken from a prior failed attempt\n")
    (tests / "test_db.py").write_text("def test_x(): assert False\n")
    (root / MODULE_STATUS_RELPATH).parent.mkdir(parents=True, exist_ok=True)
    (root / MODULE_STATUS_RELPATH).write_text(json.dumps({"db": "failed"}))

    plan = _plan(ModuleSpec("db", "the db module"))
    arch = FakeArchitect()
    pb = _builder(dirs, architect=arch, builder=FakeBuilder())
    result = pb.build(plan, root, src, tests, resume=True)

    assert result.outcomes[0].status is ModuleStatus.BUILT
    assert arch.seen  # rebuilt for real, not skipped
    assert "db_fn" in (src / "db.py").read_text()  # stale content replaced


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


def test_later_modules_get_prior_shared_constants_as_context(dirs):
    """Regression for #56: a sibling module's already-defined constant
    (e.g. DATA_FILE) is surfaced to the next module's architect, so it can
    reuse the same value instead of independently picking a different one."""
    root, src, tests = dirs
    plan = _plan(
        ModuleSpec("storage", "the storage module"),
        ModuleSpec("api", "the api module", depends_on=("storage",)),
    )
    arch = FakeArchitect()
    pb = _builder(dirs, architect=arch, builder=ConstantEmittingBuilder())
    pb.build(plan, root, src, tests)

    contexts = dict(arch.seen)
    assert contexts["the storage module"] is None
    api_ctx = contexts["the api module"]
    assert api_ctx is not None
    assert any(
        c.name == "DATA_FILE" and c.value == "'shared.json'" for c in api_ctx.constants
    )


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


def test_known_project_modules_includes_every_built_module_not_just_declared_deps(dirs):
    """Regression for #53's transitive-sibling bug: `api` only declares
    `service`, but `known_project_modules` must still include `storage`
    (built earlier, not api's declared dependency) so third-party-package
    inference downstream doesn't mistake it for a PyPI package."""
    root, src, tests = dirs
    plan = _plan(
        ModuleSpec("storage", "the storage module"),
        ModuleSpec("service", "the service module", depends_on=("storage",)),
        ModuleSpec("api", "the api module", depends_on=("service",)),
    )
    fb = FakeBuilder()
    _builder(dirs, architect=FakeArchitect(), builder=fb).build(plan, root, src, tests)

    by_order = dict(zip(["storage", "service", "api"], fb.seen_known_project_modules, strict=True))
    assert by_order["storage"] == set()
    assert by_order["service"] == {"storage"}
    assert by_order["api"] == {"storage", "service"}  # not just {"service"}


def test_transitive_dependency_sources_are_handed_to_the_builder(dirs):
    """Regression: api only declares service, but service itself imports
    from storage -- api's validation sandbox needs storage.py mounted too,
    or `from storage import ...` inside service.py raises ModuleNotFoundError
    the moment api's code (transitively) runs it. Same failure this
    resume hit live once #53 stopped masking it as a missing-package error."""
    root, src, tests = dirs
    plan = _plan(
        ModuleSpec("storage", "the storage module"),
        ModuleSpec("service", "the service module", depends_on=("storage",)),
        ModuleSpec("api", "the api module", depends_on=("service",)),
    )
    fb = FakeBuilder()
    _builder(dirs, architect=FakeArchitect(), builder=fb).build(plan, root, src, tests)

    by_order = dict(zip(["storage", "service", "api"], fb.seen_deps, strict=True))
    assert set(by_order["api"]) == {"storage", "service"}  # not just {"service"}


def test_undeclared_sibling_call_adds_the_edge_and_rebuilds(dirs):
    """A module that calls a built sibling it never declared gets the edge
    added and is rebuilt with that sibling wired in (issue #30)."""
    root, src, tests = dirs
    # build_order is lexical (no deps): core, then web. web's code calls core_fn().
    plan = _plan(
        ModuleSpec("web", "the web module"),
        ModuleSpec("core", "the core module"),
    )
    fb = SiblingCallingBuilder()
    result = _builder(dirs, architect=FakeArchitect(), builder=fb).build(plan, root, src, tests)

    web_deps = [deps for name, deps in fb.calls if name == "web"]
    assert web_deps == [set(), {"core"}]          # built once bare, then rebuilt with core
    assert all(o.status is ModuleStatus.BUILT for o in result.outcomes)


def test_declared_sibling_call_does_not_trigger_a_rebuild(dirs):
    root, src, tests = dirs
    plan = _plan(
        ModuleSpec("web", "the web module", depends_on=("core",)),
        ModuleSpec("core", "the core module"),
    )
    fb = SiblingCallingBuilder()
    _builder(dirs, architect=FakeArchitect(), builder=fb).build(plan, root, src, tests)
    assert [name for name, _ in fb.calls if name == "web"] == ["web"]   # built once


def test_undeclared_sibling_deps_detects_a_bare_call(dirs, tmp_path):
    from src.cli.project_builder import _undeclared_sibling_deps

    core = tmp_path / "core.py"
    core.write_text("def core_fn():\n    return 1\n")
    web = tmp_path / "web.py"
    web.write_text("def web_fn():\n    return core_fn()\n")
    spec = ModuleSpec("web", "the web module")
    missing = _undeclared_sibling_deps(
        web, spec, {"web": spec, "core": ModuleSpec("core", "c")}, [core]
    )
    assert missing == {"core"}


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


def test_dependency_graph_is_persisted_into_the_target_project(dirs):
    """Task B: the graph of the code this run built is a deliverable of the
    *target* project (root), not ace_enterprise's own .ace/ directory."""
    root, src, tests = dirs
    plan = _plan(
        ModuleSpec("api", "the api module", depends_on=("db",)),
        ModuleSpec("db", "the db module"),
    )
    pb = _builder(dirs, architect=FakeArchitect(), builder=FakeBuilder())
    result = pb.build(plan, root, src, tests)

    manifest_path = root / ".ace" / "architecture_graph.json"
    doc_path = root / "docs" / "ARCHITECTURE_GRAPH.md"
    assert manifest_path.exists()
    assert doc_path.exists()
    assert result.dependency_graph_path == ".ace/architecture_graph.json"
    assert result.to_payload()["dependency_graph_path"] == ".ace/architecture_graph.json"

    import json

    data = json.loads(manifest_path.read_text())
    assert set(data["modules"]) == {"src/api.py", "src/db.py"}
    assert "api_fn" in data["modules"]["src/api.py"]["provides"]
    assert "```mermaid" in doc_path.read_text()


def test_dependency_graph_is_not_persisted_when_nothing_built(dirs):
    root, src, tests = dirs
    plan = _plan(
        ModuleSpec("api", "the api module", depends_on=("db",)),
        ModuleSpec("db", "the db module"),
    )
    pb = _builder(dirs, architect=FakeArchitect(), builder=FakeBuilder(fail={"db"}))
    result = pb.build(plan, root, src, tests, stop_on_failure=True)

    assert result.dependency_graph_path is None
    assert not (root / ".ace" / "architecture_graph.json").exists()


def test_dependency_graph_persistence_failure_does_not_fail_the_build(dirs):
    root, src, tests = dirs
    plan = _plan(ModuleSpec("db", "the db module"))
    pb = _builder(dirs, architect=FakeArchitect(), builder=FakeBuilder())

    with patch("src.utils.dependency_graph.scan", side_effect=RuntimeError("boom")):
        result = pb.build(plan, root, src, tests)

    assert result.outcomes[0].status is ModuleStatus.BUILT
    assert result.dependency_graph_path is None


def test_module_outcome_records_learned_bullet_count(dirs):
    root, src, tests = dirs
    plan = _plan(ModuleSpec("db", "the db module"))
    result = _builder(dirs, architect=FakeArchitect(), builder=FakeBuilder()).build(
        plan, root, src, tests
    )
    assert result.outcomes[0].learned == 2
    assert result.outcomes[0].to_dict()["learned"] == 2


def test_learn_is_wired_when_a_playbook_id_is_given():
    pb = ProjectBuilder(llm_client=object(), playbook_id="test_proj_33_learn_wire")
    assert pb._reflector is not None
    assert pb._curator is not None
    assert pb._playbook_manager is not None


def test_no_learn_flag_loads_the_playbook_but_no_reflector():
    pb = ProjectBuilder(
        llm_client=object(), playbook_id="test_proj_33_skip", skip_learn=True
    )
    assert pb._reflector is None and pb._curator is None
    assert pb._playbook_manager is not None  # still read prior bullets


def test_no_playbook_id_means_no_learn_machinery():
    pb = ProjectBuilder(llm_client=object())
    assert pb._reflector is None
    assert pb._playbook_manager is None


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


# ---------------------------------------------------------------------------
# Per-role model wiring (#40) — exercises the real _default_architect /
# _default_builder factories (no architect_factory/builder_factory override).
# ---------------------------------------------------------------------------

def test_default_builder_uses_the_worker_repair_and_escalation_clients():
    architect_llm = SimpleNamespace(model="architect")
    worker_llm = SimpleNamespace(model="worker")
    repair_llm = SimpleNamespace(model="repair")
    escalation_llm = SimpleNamespace(model="escalation")

    pb = ProjectBuilder(
        llm_client=architect_llm, model_id="architect-model",
        worker_llm=worker_llm, worker_model_id="worker-model",
        repair_llm=repair_llm, repair_model_id="repair-model",
        escalation_llm=escalation_llm, escalation_model_id="escalation-model",
    )
    with patch("src.contracts.module_tdd_builder.ModuleTDDBuilder") as MockBuilder:
        pb._default_builder()
    args, kwargs = MockBuilder.call_args
    assert args[0] is worker_llm
    assert args[2] == "worker-model"
    assert kwargs["repair_llm_client"] is repair_llm
    assert kwargs["escalation_llm_client"] is escalation_llm
    assert kwargs["escalation_model_id"] == "escalation-model"


def test_default_architect_uses_the_architect_tier_client_not_worker():
    architect_llm = SimpleNamespace(model="architect")
    worker_llm = SimpleNamespace(model="worker")
    pb = ProjectBuilder(
        llm_client=architect_llm, model_id="architect-model", worker_llm=worker_llm,
    )
    with patch("src.contracts.module_architect.ModuleArchitect") as MockArchitect:
        pb._default_architect()
    assert MockArchitect.call_args[0][0] is architect_llm


def test_repair_client_falls_back_to_worker_when_not_configured():
    worker_llm = SimpleNamespace(model="worker")
    pb = ProjectBuilder(llm_client=object(), worker_llm=worker_llm)
    with patch("src.contracts.module_tdd_builder.ModuleTDDBuilder") as MockBuilder:
        pb._default_builder()
    assert MockBuilder.call_args[1]["repair_llm_client"] is worker_llm


def test_worker_and_repair_fall_back_to_the_base_llm_when_nothing_is_configured():
    base_llm = object()
    pb = ProjectBuilder(llm_client=base_llm, model_id="base-model")
    with patch("src.contracts.module_tdd_builder.ModuleTDDBuilder") as MockBuilder:
        pb._default_builder()
    args, kwargs = MockBuilder.call_args
    assert args[0] is base_llm
    assert args[2] == "base-model"
    assert kwargs["repair_llm_client"] is base_llm
    assert kwargs["escalation_llm_client"] is None


def test_escalation_client_is_disabled_by_default():
    pb = ProjectBuilder(llm_client=object())
    assert pb._escalation_llm is None


class TestAssemblySandboxImage:
    """_run_assembly infers third-party imports across every module's real
    source and installs them into a derived sandbox image (#53). subprocess
    is mocked throughout -- no real podman needed."""

    def test_sandbox_image_build_failure_short_circuits_with_a_clear_message(self, tmp_path):
        from src.agents.sandbox_image_builder import SandboxImageBuildError

        src, tests = tmp_path / "src", tmp_path / "tests"
        src.mkdir()
        tests.mkdir()
        (src / "api.py").write_text("from flask import Flask\napp = Flask(__name__)\n")
        (tests / "test_api.py").write_text("def test_x(): pass\n")

        with patch(
            "src.agents.sandbox_image_builder.ensure_image_with_packages",
            side_effect=SandboxImageBuildError("no matching distribution"),
        ):
            passed, failures = _run_assembly(tests, src)
        assert passed is False
        assert any("sandbox image build failed" in f for f in failures)

    def test_inferred_packages_exclude_sibling_modules(self, tmp_path):
        src, tests = tmp_path / "src", tmp_path / "tests"
        src.mkdir()
        tests.mkdir()
        (src / "storage.py").write_text("def load_data(): return {}\n")
        (src / "api.py").write_text("from flask import Flask\nimport storage\n")
        (tests / "test_api.py").write_text("def test_x(): pass\n")

        with (
            patch(
                "src.agents.sandbox_image_builder.ensure_image_with_packages",
                return_value="localhost/ace-harness-deps:abc123",
            ) as ensure,
            patch("src.agents.podman_runner.PodmanRunner") as runner_cls,
            patch("src.agents.podman_orchestrator.PodmanOrchestrator") as orch_cls,
        ):
            orch_cls.return_value.pulse.return_value = MagicMock(passed=True, error="")
            _run_assembly(tests, src)

        assert ensure.call_args[0][0] == frozenset({"flask"})  # not "storage"
        assert runner_cls.call_args.kwargs["image"] == "localhost/ace-harness-deps:abc123"
