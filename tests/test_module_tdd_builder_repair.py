"""The integration-repair loop in ModuleTDDBuilder.build_module.

Functions are built in isolation from the integration tests, so build_module
runs the tests then repairs the whole module against any failures. The LLM,
the per-function build, and the sandbox run are all faked here.
"""
from types import SimpleNamespace
from unittest.mock import patch

from src.contracts.module_architect import FunctionSpec, IntegrationTest, ModuleContract
from src.contracts.module_tdd_builder import FunctionBuildResult, ModuleTDDBuilder


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


def test_repair_loop_stops_if_repair_returns_unchanged_code():
    b = _builder(max_repair_attempts=3)
    with patch.object(b, "_run_integration_tests",
                      return_value=({"bumps": False}, ["broken"])), \
         patch.object(b, "_repair_module",
                      side_effect=lambda contract, code, failures: code) as repair:
        result = b.build_module(_contract())
    assert result.success is False
    # repair returned the same module -> loop breaks, no 2nd call
    assert repair.call_count == 1
