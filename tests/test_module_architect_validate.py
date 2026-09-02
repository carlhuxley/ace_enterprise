"""Tests for module_architect.py's validate_module().

Same defect class as ContractValidator (contract_driven.py): used to
exec()/eval() implementer-submitted module code directly in-process, no
sandbox at all. Now runs inside the same Podman sandbox the TDD engine's
language pods use. module_architect.py had zero test coverage before this.
"""
import ast
import shutil

import pytest

from src.contracts.module_architect import (
    FunctionSpec,
    IntegrationTest,
    ModuleContract,
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
        assert any("not found" in f for f in failures)

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
