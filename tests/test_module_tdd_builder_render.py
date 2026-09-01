"""Tests for render_integration_tests() in src/contracts/module_tdd_builder.py."""
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


def test_output_is_valid_python():
    src = render_integration_tests(_contract(), "counter")
    ast.parse(src)


def test_imports_public_api_and_shared_state_names():
    src = render_integration_tests(_contract(), "counter")
    assert "from counter import *" in src
    assert "from counter import _count" in src  # underscore name import * would skip


def test_one_test_function_per_integration_test():
    src = render_integration_tests(
        _contract(
            integration_tests=[
                IntegrationTest("does a", "", ["a()"], "True"),
                IntegrationTest("does b", "", ["b()"], "True"),
            ]
        ),
        "counter",
    )
    tree = ast.parse(src)
    fns = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert fns == ["test_does_a", "test_does_b"]


def test_setup_steps_and_assertion_are_emitted_in_order():
    src = render_integration_tests(
        _contract(
            integration_tests=[
                IntegrationTest("t", setup="reset()", steps=["push(1)", "push(2)"], assertion="size() == 2")
            ]
        ),
        "stack",
    )
    body = src.split("def test_t():\n", 1)[1]
    assert body.index("reset()") < body.index("push(1)") < body.index("push(2)") < body.index("assert size() == 2")


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
