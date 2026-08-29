"""Tests for contract_driven.py's ContractValidator/ContractOrchestrator.

ContractValidator.validate() used to exec()/eval() implementer-submitted
code directly in-process -- no sandbox at all, worse than BlindEvaluator's
unsandboxed subprocess bug, since there wasn't even a process boundary.
It now runs inside the same Podman sandbox the TDD engine's language pods
use. These tests cover both the sandboxed behavior (needs podman) and the
static guarantee that no in-process exec/eval remains.
"""
import ast
import shutil

import pytest

from src.contracts.contract_driven import (
    ContractOrchestrator,
    ContractStatus,
    ContractValidator,
    Fixtures,
    InterfaceContract,
    TestCase,
)

skip_no_podman = pytest.mark.skipif(
    not shutil.which("podman"),
    reason="podman not in PATH",
)


def _contract(**overrides) -> InterfaceContract:
    defaults = dict(
        contract_id="c1",
        function_name="add",
        signature="(a: int, b: int) -> int",
        docstring="Add two integers.",
        test_cases=[
            TestCase(name="basic", input_expr="(1, 2)", expected_expr="3"),
            TestCase(name="negative", input_expr="(-1, 1)", expected_expr="0"),
        ],
    )
    defaults.update(overrides)
    return InterfaceContract(**defaults)


class TestStaticGuarantee:
    """Regression: no in-process exec()/eval() of untrusted code remains."""

    def test_no_module_level_exec_or_eval_calls(self):
        """The only 'exec'/'eval' text left is inside string literals (the
        f-string template built for the sandboxed script) -- never a real
        Call node in this module's own AST."""
        import src.contracts.contract_driven as mod

        tree = ast.parse(open(mod.__file__).read())
        offending = [
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("exec", "eval")
        ]
        assert offending == []


class TestContractValidatorSyntaxError:
    """No podman needed -- validate() short-circuits on ast.parse() before
    ever building/running a sandboxed script."""

    def test_syntax_error_short_circuits_before_sandbox(self):
        validator = ContractValidator()
        result = validator.validate(_contract(), "def add(: broken")
        assert result.status == ContractStatus.FAILED
        assert "Syntax error" in result.error


class TestContractValidatorSandboxed:
    @skip_no_podman
    def test_correct_implementation_validates(self):
        validator = ContractValidator()
        result = validator.validate(_contract(), "def add(a, b): return a + b")
        assert result.status == ContractStatus.VALIDATED
        assert result.test_results == {"basic": True, "negative": True}

    @skip_no_podman
    def test_wrong_implementation_fails_with_per_case_results(self):
        validator = ContractValidator()
        result = validator.validate(_contract(), "def add(a, b): return a - b")
        assert result.status == ContractStatus.FAILED
        assert result.test_results["basic"] is False

    @skip_no_podman
    def test_missing_function_reports_error(self):
        validator = ContractValidator()
        result = validator.validate(_contract(), "def not_add(a, b): return a + b")
        assert result.status == ContractStatus.FAILED
        assert "not found" in result.error

    @skip_no_podman
    def test_fixtures_setup_and_teardown_run(self):
        contract = _contract(
            function_name="get_count",
            test_cases=[TestCase(name="count", input_expr="()", expected_expr="1")],
            fixtures=Fixtures(setup="_state = {'count': 1}", teardown="_state.clear()"),
        )
        code = "def get_count(): return _state['count']"
        validator = ContractValidator()
        result = validator.validate(contract, code)
        assert result.status == ContractStatus.VALIDATED

    @skip_no_podman
    def test_implementation_never_touches_host_process(self):
        """A submission that would corrupt host state if run in-process
        (e.g. mutating sys.modules) must not affect this test process --
        proves execution genuinely happened in the container, not here."""
        import sys

        marker_name = "_contract_validator_escape_marker_should_never_exist"
        code = (
            "import sys\n"
            f"sys.modules['{marker_name}'] = True\n"
            "def add(a, b): return a + b\n"
        )
        validator = ContractValidator()
        result = validator.validate(_contract(), code)
        assert result.status == ContractStatus.VALIDATED
        assert marker_name not in sys.modules


class TestContractOrchestrator:
    @skip_no_podman
    def test_submit_implementation_validates_via_sandbox(self):
        orchestrator = ContractOrchestrator()
        orchestrator.register_contract(_contract())
        impl = orchestrator.submit_implementation(
            "c1", "def add(a, b): return a + b", agent_ref="agent-x"
        )
        assert impl.status == ContractStatus.VALIDATED
        assert impl.agent_ref == "agent-x"
        assert orchestrator.get_contract_status("c1") == ContractStatus.VALIDATED

    def test_unknown_contract_raises(self):
        orchestrator = ContractOrchestrator()
        with pytest.raises(ValueError):
            orchestrator.submit_implementation("missing", "def x(): pass")
