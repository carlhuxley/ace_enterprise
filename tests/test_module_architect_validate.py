"""Tests for module_architect.py's validate_module().

Same defect class as ContractValidator (contract_driven.py): used to
exec()/eval() implementer-submitted module code directly in-process, no
sandbox at all. Now runs inside the same Podman sandbox the TDD engine's
language pods use. module_architect.py had zero test coverage before this.
"""
import ast
import shutil
from unittest.mock import MagicMock

import pytest

from src.contracts.module_architect import (
    CodebaseContext,
    ExistingFunction,
    FunctionSpec,
    IntegrationTest,
    ModuleArchitect,
    ModuleContract,
    check_contract_consistency,
    validate_module,
)

skip_no_podman = pytest.mark.skipif(
    not shutil.which("podman"),
    reason="podman not in PATH",
)


def _contract(**overrides) -> ModuleContract:
    defaults = {
        "id": "m1",
        "name": "counter",
        "description": "A simple counter module.",
        "shared_state": "_count = 0",
        "functions": [
            FunctionSpec(name="increment", signature="() -> int", docstring="Increment and return count.")
        ],
        "integration_tests": [
            IntegrationTest(
                name="increments_twice",
                setup="",
                steps=["increment()", "increment()"],
                assertion="_count == 2",
            ),
        ],
        "complexity": 1,
    }
    defaults.update(overrides)
    return ModuleContract(**defaults)


class TestStaticGuarantee:
    """Regression: no in-process exec()/eval() of untrusted code remains."""

    def test_no_module_level_exec_or_eval_calls(self):
        import src.contracts.module_architect as mod

        tree = ast.parse(open(mod.__file__).read())
        offending = [
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("exec", "eval")
        ]
        assert offending == []


class TestValidateModuleSyntaxError:
    def test_syntax_error_short_circuits_before_sandbox(self):
        passed, failures = validate_module(_contract(), "def increment(: broken")
        assert passed is False
        assert any("Syntax error" in f for f in failures)


class TestValidateModuleSandboxed:
    @skip_no_podman
    def test_correct_implementation_passes(self):
        code = "_count = 0\ndef increment():\n    global _count\n    _count += 1\n    return _count\n"
        passed, failures = validate_module(_contract(), code)
        assert passed is True
        assert failures == []

    @skip_no_podman
    def test_wrong_implementation_fails_assertion(self):
        code = "_count = 0\ndef increment():\n    return 0\n"
        passed, failures = validate_module(_contract(), code)
        assert passed is False
        assert any("increments_twice" in f for f in failures)

    @skip_no_podman
    def test_missing_function_reports_failure(self):
        code = "_count = 0\ndef other():\n    return 0\n"
        passed, failures = validate_module(_contract(), code)
        assert passed is False
        # the rendered test calls _module.increment() which doesn't exist
        joined = " ".join(failures).lower()
        assert "increment" in joined and ("attribute" in joined or "increments_twice" in joined)

    @skip_no_podman
    def test_module_doing_relative_path_disk_io_can_be_validated(self):
        """A module that writes/reads a file relative to cwd (atomic manifest
        writes etc.) must not fail validation with Errno 30 — the sandbox
        gives validation runs a writable working directory (#21 Part A)."""
        contract = _contract(
            shared_state="_store: dict = {}",
            functions=[
                FunctionSpec("save", "(key: str, value: str) -> None", "persist a pair"),
                FunctionSpec("load_all", "() -> dict", "read the persisted pairs"),
            ],
            integration_tests=[
                IntegrationTest(
                    name="round_trip",
                    setup="_store.clear()",
                    steps=["save('a', '1')", "save('b', '2')", "result = load_all()"],
                    assertion="result == {'a': '1', 'b': '2'}",
                ),
            ],
        )
        code = (
            "import json\n"
            "from pathlib import Path\n"
            "_store: dict = {}\n"
            "_PATH = Path('state.json')\n"
            "def save(key, value):\n"
            "    _store[key] = value\n"
            "    tmp = _PATH.with_suffix('.tmp')\n"
            "    tmp.write_text(json.dumps(_store))\n"
            "    tmp.replace(_PATH)\n"
            "def load_all():\n"
            "    return json.loads(_PATH.read_text()) if _PATH.exists() else {}\n"
        )
        passed, failures = validate_module(contract, code)
        assert passed is True, failures

    @skip_no_podman
    def test_implementation_never_touches_host_process(self):
        """A submission that would corrupt host state if run in-process
        must not affect this test process -- proves execution genuinely
        happened in the container."""
        import sys

        marker_name = "_module_validate_escape_marker_should_never_exist"
        code = (
            "import sys\n"
            f"sys.modules['{marker_name}'] = True\n"
            "_count = 0\n"
            "def increment():\n"
            "    global _count\n"
            "    _count += 1\n"
            "    return _count\n"
        )
        passed, _ = validate_module(_contract(), code)
        assert passed is True
        assert marker_name not in sys.modules


class TestArchitectPromptsAreSelfContained:
    """The architect prompts must not teach models to reference ambient
    helpers (init_db/clear_db/execute_sql/create_*) in integration tests —
    those NameError inside validate_module's sandbox (regression: every
    `ace project` module failed this way)."""

    def test_no_phantom_helpers_in_example_setup(self):
        from src.contracts.module_architect import (
            MODULE_ARCHITECT_CONTEXT_PROMPT,
            MODULE_ARCHITECT_PROMPT,
        )

        for prompt in (MODULE_ARCHITECT_PROMPT, MODULE_ARCHITECT_CONTEXT_PROMPT):
            for line in prompt.splitlines():
                if "NEVER invent" in line:
                    continue  # the prohibition itself names them — that's fine
                assert "init_db(" not in line
                assert '"setup":' not in line or "clear_db(" not in line

    def test_prompts_state_the_stdlib_only_rule(self):
        from src.contracts.module_architect import (
            MODULE_ARCHITECT_CONTEXT_PROMPT,
            MODULE_ARCHITECT_PROMPT,
        )

        for prompt in (MODULE_ARCHITECT_PROMPT, MODULE_ARCHITECT_CONTEXT_PROMPT):
            assert "standard library" in prompt or "stdlib" in prompt
            assert "NEVER invent helpers" in prompt


def _consistent_contract(**overrides) -> ModuleContract:
    defaults = {
        "id": "g1", "name": "graph", "description": "directed graph",
        "shared_state": "_edges: dict = {}",
        "functions": [
            FunctionSpec("add_edge", "(a: str, b: str) -> None", "edge a->b"),
            FunctionSpec("dependents", "(n: str) -> list", "nodes with an edge into n"),
        ],
        "integration_tests": [
            IntegrationTest(
                name="direct_dependent",
                setup="_edges.clear()",
                steps=["add_edge('a', 'b')", "result = dependents('b')"],
                assertion="result == ['a']",
            ),
        ],
        "complexity": 2,
    }
    defaults.update(overrides)
    return ModuleContract(**defaults)


class TestCheckContractConsistency:
    def test_clean_contract_has_no_problems(self):
        assert check_contract_consistency(_consistent_contract()) == []

    def test_flags_call_to_a_function_not_in_the_module(self):
        c = _consistent_contract(
            integration_tests=[
                IntegrationTest("t", "add_node('x')", ["add_edge('x', 'y')"], "True"),
            ]
        )
        problems = check_contract_consistency(c)
        assert any("add_node()" in p for p in problems)

    def test_accepts_a_function_from_an_already_built_dependency(self):
        ctx = CodebaseContext(
            existing_functions=[ExistingFunction("has_cycle", "()", "", "cycle_detector")]
        )
        c = _consistent_contract(
            integration_tests=[
                IntegrationTest("t", "_edges.clear()", ["c = has_cycle()", "add_edge('a', 'b')"], "c is False"),
            ]
        )
        assert check_contract_consistency(c, ctx) == []

    def test_accepts_names_bound_within_the_test(self):
        c = _consistent_contract(
            integration_tests=[
                IntegrationTest(
                    "t", "_edges.clear()",
                    ["items = [('a', 'b'), ('b', 'c')]", "for x, y in items: add_edge(x, y)",
                     "result = dependents('c')"],
                    "result == ['b']",
                ),
            ]
        )
        assert check_contract_consistency(c) == []

    def test_flags_unparseable_setup(self):
        c = _consistent_contract(
            integration_tests=[IntegrationTest("t", "add_edge('a',", ["add_edge('a','b')"], "True")]
        )
        assert any("do not parse" in p for p in check_contract_consistency(c))

    def test_stdlib_and_builtins_are_allowed(self):
        c = _consistent_contract(
            integration_tests=[
                IntegrationTest("t", "_edges.clear()",
                                ["add_edge('a', 'b')", "n = len(dependents('b'))"], "n == 1"),
            ]
        )
        assert check_contract_consistency(c) == []

    def test_flags_a_module_function_that_duplicates_an_upstream_one(self):
        # 'add_edge' is already provided by the built dag_graph module — this
        # contract should import it, not put it back on its own surface (#28).
        ctx = CodebaseContext(
            existing_functions=[ExistingFunction("add_edge", "(a, b)", "", "dag_graph")]
        )
        problems = check_contract_consistency(_consistent_contract(), ctx)
        assert any("add_edge" in p and "dag_graph" in p for p in problems)


class TestGenerateModuleContractReAsks:
    def _architect(self, *responses):
        llm = MagicMock()
        llm.generate.side_effect = [{"content": r} for r in responses]
        return ModuleArchitect(llm_client=llm, model_id="test")

    def _json(self, calls_helper: bool) -> str:
        step = "add_node('x')" if calls_helper else "add_edge('a', 'b')"
        return (
            '{"module": {"id": "g", "name": "graph", "description": "d", "complexity": 2,'
            '"shared_state": "_edges: dict = {}",'
            '"functions": [{"name": "add_edge", "signature": "(a, b)", "docstring": "e"}],'
            f'"integration_tests": [{{"name": "t", "setup": "_edges.clear()", "steps": ["{step}"], "assertion": "True"}}]}}}}'
        )

    def test_re_asks_once_then_accepts_a_fixed_contract(self):
        arch = self._architect(self._json(calls_helper=True), self._json(calls_helper=False))
        result = arch.generate_module_contract("build a graph")
        assert result.success is True
        assert arch._llm.generate.call_count == 2
        assert "re-emit" in arch._llm.generate.call_args_list[1][0][0]

    def test_fails_cleanly_when_the_re_ask_is_still_inconsistent(self):
        arch = self._architect(self._json(calls_helper=True), self._json(calls_helper=True))
        result = arch.generate_module_contract("build a graph")
        assert result.success is False
        assert result.contract is None
        assert "inconsistent contract" in result.error
        assert "add_node()" in result.error

    def test_prior_lessons_are_prepended_to_the_architect_prompt(self):
        from types import SimpleNamespace

        arch = self._architect(self._json(calls_helper=False))
        arch._playbook_manager = SimpleNamespace(
            get_section_bullets=lambda pid, section: [
                SimpleNamespace(content="import upstream modules, never reimplement them")
            ]
        )
        arch._playbook_id = "proj_pb"
        arch.generate_module_contract("build a graph")
        sent = arch._llm.generate.call_args_list[0][0][0]
        assert "PRIOR LESSONS" in sent
        assert "import upstream modules" in sent
