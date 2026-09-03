"""Tests for render_integration_tests() in src/contracts/module_tdd_builder.py.

The rendered file is a real pytest module: `import <mod> as _module`, an
autouse state-reset fixture, and one `def test_*()` per integration test with
bare module names rewritten to `_module.<name>` so tests act on the live
module (no stale `import *` copy). See #25.
"""
import ast

from src.contracts.module_architect import FunctionSpec, IntegrationTest, ModuleContract
from src.contracts.module_tdd_builder import render_integration_tests


def _contract(**overrides) -> ModuleContract:
    defaults = {
        "id": "m1",
        "name": "counter",
        "description": "A counter.",
        "shared_state": "_count = 0",
        "functions": [FunctionSpec("increment", "() -> int", "bump the count")],
        "integration_tests": [
            IntegrationTest(
                name="increments twice",
                setup="",
                steps=["increment()", "increment()"],
                assertion="_count == 2",
            )
        ],
        "complexity": 1,
    }
    defaults.update(overrides)
    return ModuleContract(**defaults)


def _test_fns(src: str) -> list[str]:
    return [
        n.name for n in ast.parse(src).body
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    ]


def test_output_is_valid_python():
    ast.parse(render_integration_tests(_contract(), "counter"))


def test_imports_the_module_as_a_reference_not_star():
    src = render_integration_tests(_contract(), "counter")
    assert "import counter as _module" in src
    assert "from counter import *" not in src


def test_emits_an_autouse_state_reset_fixture():
    src = render_integration_tests(_contract(), "counter")
    assert "@_pytest.fixture(autouse=True)" in src
    assert "def _reset_module_state():" in src
    assert "_INITIAL_STATE" in src


def test_module_functions_and_state_are_qualified_locals_are_not():
    src = render_integration_tests(
        _contract(
            functions=[FunctionSpec("increment", "()", "")],
            integration_tests=[
                IntegrationTest("t", "_count = 0", ["r = increment()"], "r == 1 and _count == 1"),
            ],
        ),
        "counter",
    )
    body = src.split("def test_t():\n", 1)[1]
    assert "_module._count = 0" in body          # shared-state assignment -> module
    assert "r = _module.increment()" in body     # module function call -> module
    assert "assert r == 1 and _module._count == 1" in body  # r stays local


def test_one_test_function_per_integration_test():
    src = render_integration_tests(
        _contract(
            integration_tests=[
                IntegrationTest("does a", "", ["increment()"], "True"),
                IntegrationTest("does b", "", ["increment()"], "True"),
            ]
        ),
        "counter",
    )
    assert _test_fns(src) == ["test_does_a", "test_does_b"]


def test_no_integration_tests_yields_a_smoke_test():
    src = render_integration_tests(_contract(integration_tests=[]), "counter")
    ast.parse(src)
    assert "def test_module_importable():" in src


def test_test_name_is_sanitised():
    src = render_integration_tests(
        _contract(integration_tests=[IntegrationTest("adds A & B (happy path)", "", ["x()"], "True")]),
        "m",
    )
    assert "def test_adds_a_b_happy_path():" in src


def test_dep_module_public_symbols_are_imported():
    dep = {"dag_graph": "def add_edge(a, b):\n    pass\n\ndef has_cycle():\n    return False\n"}
    src = render_integration_tests(_contract(), "counter", dep_modules=dep)
    ast.parse(src)
    assert "import counter as _module" in src
    assert "from dag_graph import add_edge, has_cycle" in src


def test_unparseable_step_is_left_as_is_and_still_valid_module():
    # a malformed step shouldn't crash rendering; the test just fails visibly
    src = render_integration_tests(
        _contract(integration_tests=[IntegrationTest("bad", "increment(", ["increment()"], "True")]),
        "counter",
    )
    ast.parse(src)
