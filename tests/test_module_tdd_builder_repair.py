"""The integration-repair loop in ModuleTDDBuilder.build_module.

Functions are built in isolation from the integration tests, so build_module
runs the tests then repairs the whole module against any failures. The LLM,
the per-function build, and the sandbox run are all faked here.
"""
from types import SimpleNamespace
from unittest.mock import patch

from src.contracts.module_architect import FunctionSpec, IntegrationTest, ModuleContract
from src.contracts.module_tdd_builder import (
    FunctionBuildResult,
    ModuleTDDBuilder,
    _dep_import_lines,
    _redeclared_upstream,
    _upstream_symbols,
)


def _contract() -> ModuleContract:
    return ModuleContract(
        id="m1", name="counter", description="d", shared_state="_n = 0",
        functions=[FunctionSpec("bump", "() -> int", "increment")],
        integration_tests=[IntegrationTest("bumps", "_n = 0", ["bump()"], "_n == 1")],
        complexity=1,
    )


def _builder(**kw):
    b = ModuleTDDBuilder(llm_client=SimpleNamespace(model="x"), **kw)
    # every function "builds" fine
    b._build_function = lambda **_: FunctionBuildResult(
        function_name="bump", code="def bump():\n    global _n\n    _n += 1\n    return _n\n",
        tdd_cycles=1, success=True,
    )
    return b


def test_no_repair_when_integration_tests_pass_first_time():
    b = _builder()
    with patch.object(b, "_run_integration_tests", return_value=({"bumps": True}, [])) as run, \
         patch.object(b, "_repair_module") as repair:
        result = b.build_module(_contract())
    assert result.success is True
    assert run.call_count == 1
    repair.assert_not_called()


def test_repair_loop_fixes_a_failing_module():
    b = _builder(max_repair_attempts=2)
    runs = [
        ({"bumps": False}, ["bumps: assertion failed"]),   # first run: fail
        ({"bumps": True}, []),                              # after repair: pass
    ]
    with patch.object(b, "_run_integration_tests", side_effect=runs), \
         patch.object(b, "_repair_module", return_value="def bump():\n    return 1\n") as repair:
        result = b.build_module(_contract())
    assert result.success is True
    repair.assert_called_once()
    assert "assertion failed" in repair.call_args[0][2][0]


def test_repair_loop_gives_up_after_max_attempts():
    b = _builder(max_repair_attempts=2)
    with patch.object(b, "_run_integration_tests",
                      return_value=({"bumps": False}, ["still broken"])), \
         patch.object(b, "_repair_module", side_effect=["v2\n", "v3\n"]) as repair:
        result = b.build_module(_contract())
    assert result.success is False
    assert repair.call_count == 2   # bounded


def test_validate_function_accepts_exception_classes():
    b = ModuleTDDBuilder(llm_client=SimpleNamespace(model="x"))
    spec = FunctionSpec("CircularDependencyError", "(Exception)", "raised on a cycle")
    assert b._validate_function("class CircularDependencyError(Exception):\n    pass\n", spec) is None
    assert b._validate_function("def register(): pass\n", spec) is not None  # neither def nor class of that name


def test_dep_import_lines_lists_public_symbols_grouped_by_module():
    deps = {
        "dag_graph": "def add_edge(a, b): pass\ndef _private(): pass\nclass Node: pass\n",
        "manifest_io": "def load(): pass\n",
    }
    assert _dep_import_lines(deps) == [
        "from dag_graph import Node, add_edge",
        "from manifest_io import load",
    ]


def test_redeclared_upstream_flags_a_local_shadow_of_a_dependency_symbol():
    upstream = _upstream_symbols({"dag_graph": "def add_edge(a, b): pass\n"})
    msgs = _redeclared_upstream("def add_edge(a, b):\n    return 1\n", upstream)
    assert len(msgs) == 1
    assert "add_edge" in msgs[0] and "dag_graph" in msgs[0]


def test_redeclared_upstream_clean_when_the_module_imports_instead():
    upstream = _upstream_symbols({"dag_graph": "def add_edge(a, b): pass\n"})
    code = "from dag_graph import add_edge\n\ndef register(x):\n    add_edge(x, x)\n"
    assert _redeclared_upstream(code, upstream) == []


def test_redeclared_upstream_catches_a_def_guarded_by_try_except():
    # the exact shape Haiku produced: a "fallback" duplicate under ImportError
    upstream = _upstream_symbols({"dag_graph": "def add_edge(a, b): pass\n"})
    code = (
        "try:\n"
        "    from graph import add_edge\n"
        "except ImportError:\n"
        "    def add_edge(a, b):\n"
        "        pass\n"
    )
    msgs = _redeclared_upstream(code, upstream)
    assert len(msgs) == 1 and "dag_graph" in msgs[0]


def test_redeclared_upstream_ignores_a_method_named_like_an_upstream_symbol():
    upstream = _upstream_symbols({"dag_graph": "def add_edge(a, b): pass\n"})
    code = "class Graph:\n    def add_edge(self, a, b):\n        pass\n"
    assert _redeclared_upstream(code, upstream) == []


def test_locally_redefined_dependency_triggers_a_repair_pass():
    b = _builder(max_repair_attempts=1)
    # the isolated per-function build hands back code that reimplements an
    # upstream symbol (add_edge) — exactly the Haiku failure mode from #28.
    b._build_function = lambda **_: FunctionBuildResult(
        function_name="bump",
        code="def add_edge(a, b):\n    return None\n\ndef bump():\n    return 1\n",
        tdd_cycles=1, success=True,
    )
    dep = {"dag_graph": "def add_edge(a, b):\n    pass\n"}
    fixed = "from dag_graph import add_edge\n\ndef bump():\n    return 1\n"
    with patch("src.contracts.module_tdd_builder.validate_module", return_value=(True, [])), \
         patch.object(b, "_repair_module", return_value=fixed) as repair:
        result = b.build_module(_contract(), dep_modules=dep)
    repair.assert_called_once()
    # the repair prompt was told which symbol was wrongly duplicated
    assert any("add_edge" in f for f in repair.call_args[0][2])
    assert result.success is True


def test_repair_loop_stops_if_repair_returns_unchanged_code():
    b = _builder(max_repair_attempts=3)
    with patch.object(b, "_run_integration_tests",
                      return_value=({"bumps": False}, ["broken"])), \
         patch.object(b, "_repair_module",
                      side_effect=lambda contract, code, failures, **kw: code) as repair:
        result = b.build_module(_contract())
    assert result.success is False
    # repair returned the same module -> loop breaks, no 2nd call
    assert repair.call_count == 1


# ---------------------------------------------------------------------------
# LEARN pass (#33)
# ---------------------------------------------------------------------------

class _FakeReflector:
    def reflect(self, task, gen, env):
        self.task, self.gen, self.env = task, gen, env
        return "reflection"


class _FakeCurator:
    def __init__(self):
        self.applied = []

    def curate(self, reflector_output, playbook_id, task_context=None):
        self.task_context = task_context
        return SimpleNamespace(
            delta_bullets=[SimpleNamespace(section="strategies_and_hard_rules")]
        )

    def apply_updates(self, playbook_id, output):
        self.applied.append((playbook_id, output))


def _learning_builder(**kw):
    b = _builder(**kw)
    b._reflector, b._curator = _FakeReflector(), _FakeCurator()
    b._playbook_id = "proj_pb"
    return b


def test_learn_pass_writes_bullets_and_populates_the_result():
    b = _learning_builder()
    with patch.object(b, "_run_integration_tests", return_value=({"bumps": True}, [])):
        result = b.build_module(_contract())
    assert len(result.learned_bullets) == 1
    assert b._curator.applied and b._curator.applied[0][0] == "proj_pb"
    assert b._reflector.env.result == "SUCCESS"


def test_learn_pass_carries_the_failure_signal():
    b = _learning_builder(max_repair_attempts=0)
    with patch.object(b, "_run_integration_tests",
                      return_value=({"bumps": False}, ["bumps: boom"])):
        b.build_module(_contract())
    assert b._reflector.env.result == "FAILED"
    assert "boom" in b._reflector.env.actual


def test_no_learn_pass_without_reflector_or_playbook():
    b = _builder()  # no reflector / curator / playbook_id
    with patch.object(b, "_run_integration_tests", return_value=({"bumps": True}, [])):
        result = b.build_module(_contract())
    assert result.learned_bullets == []


def test_learn_pass_never_fails_the_build():
    b = _learning_builder()
    b._reflector.reflect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("reflect boom"))
    with patch.object(b, "_run_integration_tests", return_value=({"bumps": True}, [])):
        result = b.build_module(_contract())
    assert result.success is True
    assert result.learned_bullets == []


def test_prior_lessons_reach_the_function_build_prompt():
    prompts: list[str] = []
    llm = SimpleNamespace(
        model="x",
        generate=lambda p, **k: prompts.append(p)
        or {"content": "def bump():\n    return 1\n", "actual_model": "x", "provider": "y"},
    )
    b = ModuleTDDBuilder(
        llm_client=llm,
        playbook_manager=SimpleNamespace(
            get_section_bullets=lambda pid, s: [
                SimpleNamespace(content="always foo the bar first")
            ]
        ),
        playbook_id="proj_pb",
    )
    assert b._prior_lessons() == ["always foo the bar first"]
    b._build_function(
        FunctionSpec("bump", "() -> int", "d"), "_n = 0", [], "",
        prior_lessons=["always foo the bar first"],
    )
    assert any("always foo the bar first" in p for p in prompts)
