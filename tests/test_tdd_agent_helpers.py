"""Additional tests for AutonomousTDDAgent helper methods (ace_enterprise-l0q).

Covers branches and methods not reached by test_autonomous_tdd_agent.py:
- _get_license_type: deepseek, vllm, openrouter, unknown-provider branches
- _validate_hardcode_implementation: all forbidden-pattern branches
- _extract_single_function: found, not-found, syntax-error paths
- _get_module_path: explicit constraint, src-in-path, fallback
- _assemble_test_file: no-functions no-op, writes correct content
- CycleResult / TDDResult / TestIncrement dataclasses
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.agents.autonomous_tdd_agent import (
    AutonomousTDDAgent,
    CycleResult,
    TDDResult,
    TestIncrement,
    TestResult,
)

# Shorthand: call unbound methods with a fake self (MagicMock or None)
_A = AutonomousTDDAgent


# ---------------------------------------------------------------------------
# TestIncrement / CycleResult / TDDResult dataclasses
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_test_increment_fields(self, tmp_path):
        inc = TestIncrement(
            test_name="test_process_order",
            description="Process an order",
            test_file=tmp_path / "test_order.py",
            implementation_file=tmp_path / "order.py",
        )
        assert inc.test_name == "test_process_order"
        assert inc.description == "Process an order"

    def test_cycle_result_fields(self, tmp_path):
        inc = TestIncrement(
            test_name="t",
            description="d",
            test_file=tmp_path / "t.py",
            implementation_file=tmp_path / "i.py",
        )
        red = TestResult(passed=False, failed=True, output="fail")
        green = TestResult(passed=True, failed=False, output="pass")
        cr = CycleResult(
            increment=inc,
            test_code="def test_t(): pass",
            implementation_code="def t(): pass",
            red_result=red,
            green_result=green,
            refactored=False,
            learned_bullets=[],
            cycle_number=1,
        )
        assert cr.cycle_number == 1
        assert cr.skipped is False

    def test_tdd_result_fields(self, tmp_path):
        result = TDDResult(
            requirement="req",
            test_files=[],
            implementation_files=[],
            cycles_executed=2,
            all_tests_passed=True,
            playbook_bullets_added=3,
            total_time_seconds=5.0,
        )
        assert result.cycles_executed == 2
        assert result.all_tests_passed is True

    def test_test_result_all_passed_false_when_failed_count_nonzero(self):
        r = TestResult(passed=True, failed=False, output="", test_count=2, failed_count=1)
        assert r.all_passed is False

    def test_test_result_all_passed_true_when_no_failures(self):
        r = TestResult(passed=True, failed=False, output="", test_count=2, failed_count=0)
        assert r.all_passed is True


# ---------------------------------------------------------------------------
# _get_license_type — additional branches
# ---------------------------------------------------------------------------

class TestGetLicenseTypeAdditionalBranches:
    def test_deepseek_provider_returns_mit(self):
        assert _A._get_license_type(None, "deepseek", "deepseek-v2") == "mit"

    def test_vllm_qwen_returns_apache(self):
        assert _A._get_license_type(None, "vllm", "qwen2.5-72b") == "apache-2.0"

    def test_vllm_llama_returns_llama_license(self):
        result = _A._get_license_type(None, "vllm", "llama3-8b")
        assert "llama" in result.lower()

    def test_vllm_unknown_model_returns_open_source_unknown(self):
        result = _A._get_license_type(None, "vllm", "some-unknown-model")
        assert result == "open-source-unknown"

    def test_openrouter_openai_model_returns_proprietary(self):
        result = _A._get_license_type(None, "openrouter", "openai/gpt-4o")
        assert result == "proprietary"

    def test_openrouter_qwen_returns_apache(self):
        result = _A._get_license_type(None, "openrouter", "qwen/qwen2.5-72b")
        assert result == "apache-2.0"

    def test_openrouter_deepseek_returns_mit(self):
        result = _A._get_license_type(None, "openrouter", "deepseek/deepseek-v2")
        assert result == "mit"

    def test_openrouter_llama_returns_llama_license(self):
        result = _A._get_license_type(None, "openrouter", "meta-llama/llama-3-70b")
        assert "llama" in result.lower()

    def test_openrouter_free_prefix_returns_open_source_unknown(self):
        result = _A._get_license_type(None, "openrouter", "openrouter/free")
        assert result == "open-source-unknown"

    def test_unknown_provider_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            _A._get_license_type(None, "mystery-cloud", "model-x")


# ---------------------------------------------------------------------------
# _validate_hardcode_implementation
# ---------------------------------------------------------------------------

class TestValidateHardcodeImplementation:
    def test_pure_literal_return_is_valid(self):
        code = "def get_url(self):\n    return 'https://example.com'"
        ok, msg = _A._validate_hardcode_implementation(None, code, "get_url")
        assert ok is True
        assert msg == ""

    def test_f_string_is_invalid(self):
        code = "def get_url(self):\n    return f'https://{self.host}'"
        ok, msg = _A._validate_hardcode_implementation(None, code, "get_url")
        assert ok is False
        assert "f-string" in msg

    def test_format_method_is_invalid(self):
        code = "def get_url(self):\n    return 'https://{}'.format(self.host)"
        ok, msg = _A._validate_hardcode_implementation(None, code, "get_url")
        assert ok is False
        assert ".format()" in msg

    def test_for_loop_is_invalid(self):
        code = "def process(self):\n    for x in [1, 2]: pass\n    return 'done'"
        ok, msg = _A._validate_hardcode_implementation(None, code, "process")
        assert ok is False
        assert "loop" in msg

    def test_list_comprehension_is_invalid(self):
        code = "def items(self):\n    return [x for x in range(3)]"
        ok, msg = _A._validate_hardcode_implementation(None, code, "items")
        assert ok is False
        assert "comprehension" in msg

    def test_lambda_is_invalid(self):
        code = "def transform(self):\n    fn = lambda x: x\n    return fn(1)"
        ok, msg = _A._validate_hardcode_implementation(None, code, "transform")
        assert ok is False
        assert "lambda" in msg

    def test_urlencode_call_is_invalid(self):
        code = "def get_url(self):\n    return urlencode({'a': 'b'})"
        ok, msg = _A._validate_hardcode_implementation(None, code, "get_url")
        assert ok is False
        assert "urlencode" in msg

    def test_function_not_found_returns_valid(self):
        code = "def other_func(self):\n    return 42"
        ok, msg = _A._validate_hardcode_implementation(None, code, "missing_func")
        assert ok is True

    def test_syntax_error_returns_valid(self):
        code = "def bad(:\n    pass"
        ok, msg = _A._validate_hardcode_implementation(None, code, "bad")
        assert ok is True

    def test_nested_if_is_invalid(self):
        code = "def f(self):\n    if True:\n        if True:\n            return 1\n    return 0"
        ok, msg = _A._validate_hardcode_implementation(None, code, "f")
        assert ok is False
        assert "nested if" in msg


# ---------------------------------------------------------------------------
# _extract_single_function
# ---------------------------------------------------------------------------

class TestExtractSingleFunction:
    def test_extracts_named_function(self):
        code = "def foo():\n    return 1\n\ndef bar():\n    return 2"
        result = _A._extract_single_function(None, code, "foo")
        assert "def foo" in result
        assert "def bar" not in result

    def test_returns_original_when_function_not_found(self):
        code = "def foo():\n    return 1"
        result = _A._extract_single_function(None, code, "missing")
        assert result == code

    def test_returns_original_on_syntax_error(self):
        code = "def bad(:\n    pass"
        result = _A._extract_single_function(None, code, "bad")
        assert result == code

    def test_extracts_function_with_body(self):
        code = "def process(x):\n    return x * 2\n\ndef other():\n    pass"
        result = _A._extract_single_function(None, code, "process")
        assert "x * 2" in result


# ---------------------------------------------------------------------------
# _get_module_path
# ---------------------------------------------------------------------------

class TestGetModulePath:
    def test_uses_explicit_file_path_when_set(self, tmp_path):
        agent = MagicMock()
        agent._explicit_file_path = "src/playbook/manager.py"
        result = _A._get_module_path(agent, tmp_path / "anything.py")
        assert result == "src.playbook.manager"

    def test_derives_from_file_path_with_src(self, tmp_path):
        agent = MagicMock()
        agent._explicit_file_path = None
        file_path = tmp_path / "src" / "playbook" / "manager.py"
        result = _A._get_module_path(agent, file_path)
        assert result == "src.playbook.manager"

    def test_falls_back_to_stem_when_no_src_in_path(self, tmp_path):
        agent = MagicMock()
        agent._explicit_file_path = None
        file_path = tmp_path / "mymodule.py"
        result = _A._get_module_path(agent, file_path)
        assert "mymodule" in result

    def test_explicit_path_strips_py_extension(self, tmp_path):
        agent = MagicMock()
        agent._explicit_file_path = "src/utils/helpers.py"
        result = _A._get_module_path(agent, tmp_path / "x.py")
        assert not result.endswith(".py")


# ---------------------------------------------------------------------------
# _assemble_test_file
# ---------------------------------------------------------------------------

class TestAssembleTestFile:
    def test_no_op_when_no_functions_registered(self, tmp_path):
        agent = MagicMock()
        agent.test_functions = {}
        agent._explicit_file_path = None

        test_file = tmp_path / "test_foo.py"
        impl_file = tmp_path / "src" / "foo.py"

        _A._assemble_test_file(agent, test_file, impl_file)
        assert not test_file.exists()

    def test_writes_file_when_functions_registered(self, tmp_path):
        agent = MagicMock()
        test_file = tmp_path / "test_foo.py"
        impl_file = tmp_path / "src" / "foo.py"

        agent.test_functions = {
            str(test_file): [
                {"cycle": 1, "name": "test_add", "code": "def test_add():\n    assert 1 == 1"},
            ]
        }
        agent._explicit_file_path = None
        agent._get_module_path = lambda f: "src.foo"

        _A._assemble_test_file(agent, test_file, impl_file)
        assert test_file.exists()

    def test_written_file_contains_test_function_code(self, tmp_path):
        agent = MagicMock()
        test_file = tmp_path / "test_foo.py"
        impl_file = tmp_path / "src" / "foo.py"

        agent.test_functions = {
            str(test_file): [
                {"cycle": 1, "name": "test_add", "code": "def test_add():\n    assert 1 == 1"},
            ]
        }
        agent._explicit_file_path = None
        agent._get_module_path = lambda f: "src.foo"

        _A._assemble_test_file(agent, test_file, impl_file)
        content = test_file.read_text()
        assert "def test_add" in content

    def test_written_file_contains_import_statement(self, tmp_path):
        agent = MagicMock()
        test_file = tmp_path / "test_foo.py"
        impl_file = tmp_path / "src" / "foo.py"

        agent.test_functions = {
            str(test_file): [
                {"cycle": 1, "name": "test_x", "code": "def test_x():\n    pass"},
            ]
        }
        agent._explicit_file_path = None
        agent._get_module_path = lambda f: "src.foo"

        _A._assemble_test_file(agent, test_file, impl_file)
        content = test_file.read_text()
        assert "from src.foo import" in content

    def test_assembles_multiple_functions_in_order(self, tmp_path):
        agent = MagicMock()
        test_file = tmp_path / "test_foo.py"
        impl_file = tmp_path / "src" / "foo.py"

        agent.test_functions = {
            str(test_file): [
                {"cycle": 1, "name": "test_a", "code": "def test_a():\n    pass"},
                {"cycle": 2, "name": "test_b", "code": "def test_b():\n    pass"},
            ]
        }
        agent._explicit_file_path = None
        agent._get_module_path = lambda f: "src.foo"

        _A._assemble_test_file(agent, test_file, impl_file)
        content = test_file.read_text()
        assert "def test_a" in content
        assert "def test_b" in content
        assert content.index("def test_a") < content.index("def test_b")
