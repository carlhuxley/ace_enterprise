"""Tests for GoLanguagePod (ace_enterprise-j5s)."""
import shutil
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.agents.language_pod import LanguagePod, PhaseResult, PodSpec, TokenUsage
from src.agents.go_language_pod import GoLanguagePod


def make_llm_client(content="package main\n\nfunc Foo() {}", tokens_used=100):
    client = MagicMock()
    client.generate.return_value = {
        "content": content,
        "tokens_used": tokens_used,
        "latency_ms": 40,
        "model": "gpt-4o",
    }
    return client


def make_pod(tmp_path, playbook_manager=None):
    return GoLanguagePod(llm_client=make_llm_client(), playbook_manager=playbook_manager)


def spec(tmp_path, cycle=1):
    return PodSpec(
        feature_requirement="User authentication with JWT",
        test_file=tmp_path / "auth_test.go",
        implementation_file=tmp_path / "auth.go",
        cycle_number=cycle,
    )


def _failed_proc():
    m = MagicMock()
    m.returncode = 1
    m.stdout = "FAIL"
    m.stderr = "--- FAIL: TestFoo (0.00s)"
    return m


def _passed_proc():
    m = MagicMock()
    m.returncode = 0
    m.stdout = "ok"
    m.stderr = ""
    return m


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

class TestProtocolConformance:
    def test_isinstance_language_pod(self, tmp_path):
        pod = make_pod(tmp_path)
        assert isinstance(pod, LanguagePod)

    def test_has_all_required_methods(self, tmp_path):
        pod = make_pod(tmp_path)
        assert callable(pod.run_red)
        assert callable(pod.run_green)
        assert callable(pod.run_refactor)
        assert callable(pod.token_usage)


# ---------------------------------------------------------------------------
# run_red
# ---------------------------------------------------------------------------

class TestRunRed:
    def test_returns_phase_result(self, tmp_path):
        pod = make_pod(tmp_path)
        with patch("subprocess.run", return_value=_failed_proc()):
            result = pod.run_red(spec(tmp_path))
        assert isinstance(result, PhaseResult)

    def test_writes_test_file(self, tmp_path):
        pod = make_pod(tmp_path)
        s = spec(tmp_path)
        with patch("subprocess.run", return_value=_failed_proc()):
            pod.run_red(s)
        assert s.test_file.exists()

    def test_runs_go_test(self, tmp_path):
        pod = make_pod(tmp_path)
        with patch("subprocess.run", return_value=_failed_proc()) as mock_run:
            pod.run_red(spec(tmp_path))
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "go"
        assert "test" in cmd

    def test_passed_false_when_tests_fail(self, tmp_path):
        pod = make_pod(tmp_path)
        with patch("subprocess.run", return_value=_failed_proc()):
            result = pod.run_red(spec(tmp_path))
        assert not result.passed

    def test_passed_true_when_tests_unexpectedly_pass(self, tmp_path):
        pod = make_pod(tmp_path)
        with patch("subprocess.run", return_value=_passed_proc()):
            result = pod.run_red(spec(tmp_path))
        assert result.passed

    def test_llm_exception_returns_failed_result(self, tmp_path):
        client = MagicMock()
        client.generate.side_effect = RuntimeError("LLM unavailable")
        pod = GoLanguagePod(llm_client=client)
        result = pod.run_red(spec(tmp_path))
        assert not result.passed
        assert result.error is not None


# ---------------------------------------------------------------------------
# run_green
# ---------------------------------------------------------------------------

class TestRunGreen:
    def test_returns_phase_result(self, tmp_path):
        pod = make_pod(tmp_path)
        with patch("subprocess.run", return_value=_passed_proc()):
            result = pod.run_green(spec(tmp_path))
        assert isinstance(result, PhaseResult)

    def test_writes_implementation_file(self, tmp_path):
        pod = make_pod(tmp_path)
        s = spec(tmp_path)
        with patch("subprocess.run", return_value=_passed_proc()):
            pod.run_green(s)
        assert s.implementation_file.exists()

    def test_passed_when_tests_pass(self, tmp_path):
        pod = make_pod(tmp_path)
        with patch("subprocess.run", return_value=_passed_proc()):
            result = pod.run_green(spec(tmp_path))
        assert result.passed

    def test_failed_when_tests_fail(self, tmp_path):
        pod = make_pod(tmp_path)
        with patch("subprocess.run", return_value=_failed_proc()):
            result = pod.run_green(spec(tmp_path))
        assert not result.passed

    def test_queries_playbook_for_go_bullets(self, tmp_path):
        pm = MagicMock()
        pm.get_bullets.return_value = ["use errors.New for sentinel errors"]
        pod = GoLanguagePod(llm_client=make_llm_client(), playbook_manager=pm)
        with patch("subprocess.run", return_value=_passed_proc()):
            pod.run_green(spec(tmp_path))
        pm.get_bullets.assert_called_once_with("global-go-bullets")

    def test_no_error_when_no_playbook(self, tmp_path):
        pod = GoLanguagePod(llm_client=make_llm_client(), playbook_manager=None)
        with patch("subprocess.run", return_value=_passed_proc()):
            result = pod.run_green(spec(tmp_path))
        assert isinstance(result, PhaseResult)


# ---------------------------------------------------------------------------
# run_refactor
# ---------------------------------------------------------------------------

class TestRunRefactor:
    def test_returns_phase_result(self, tmp_path):
        pod = make_pod(tmp_path)
        with patch("subprocess.run", return_value=_passed_proc()):
            result = pod.run_refactor(spec(tmp_path))
        assert isinstance(result, PhaseResult)

    def test_runs_gofmt_when_impl_exists(self, tmp_path):
        pod = make_pod(tmp_path)
        s = spec(tmp_path)
        s.implementation_file.write_text("package foo\nfunc Foo() {}")
        calls = []
        with patch("subprocess.run", side_effect=lambda cmd, **kw: calls.append(cmd) or _passed_proc()):
            pod.run_refactor(s)
        assert any(c[0] == "gofmt" for c in calls)

    def test_runs_go_vet_when_impl_exists(self, tmp_path):
        pod = make_pod(tmp_path)
        s = spec(tmp_path)
        s.implementation_file.write_text("package foo\nfunc Foo() {}")
        calls = []
        with patch("subprocess.run", side_effect=lambda cmd, **kw: calls.append(cmd) or _passed_proc()):
            pod.run_refactor(s)
        assert any(c[0] == "go" and "vet" in c for c in calls)

    def test_passed_when_tests_green_after_refactor(self, tmp_path):
        pod = make_pod(tmp_path)
        with patch("subprocess.run", return_value=_passed_proc()):
            result = pod.run_refactor(spec(tmp_path))
        assert result.passed

    def test_failed_when_tests_red_after_refactor(self, tmp_path):
        pod = make_pod(tmp_path)
        with patch("subprocess.run", return_value=_failed_proc()):
            result = pod.run_refactor(spec(tmp_path))
        assert not result.passed


# ---------------------------------------------------------------------------
# token_usage
# ---------------------------------------------------------------------------

class TestTokenUsage:
    def test_returns_list(self, tmp_path):
        pod = make_pod(tmp_path)
        assert isinstance(pod.token_usage(), list)

    def test_empty_before_any_phase(self, tmp_path):
        pod = make_pod(tmp_path)
        assert pod.token_usage() == []

    def test_records_usage_after_red(self, tmp_path):
        pod = make_pod(tmp_path)
        with patch("subprocess.run", return_value=_failed_proc()):
            pod.run_red(spec(tmp_path, cycle=1))
        usage = pod.token_usage()
        assert len(usage) == 1
        assert usage[0].cycle_number == 1
        assert usage[0].input_tokens == 100

    def test_accumulates_across_cycles(self, tmp_path):
        pod = make_pod(tmp_path)
        with patch("subprocess.run", return_value=_failed_proc()):
            pod.run_red(spec(tmp_path, cycle=1))
            pod.run_red(spec(tmp_path, cycle=2))
        assert len(pod.token_usage()) == 2
        assert pod.token_usage()[0].cycle_number == 1
        assert pod.token_usage()[1].cycle_number == 2

    def test_token_usage_entries_are_token_usage_type(self, tmp_path):
        pod = make_pod(tmp_path)
        with patch("subprocess.run", return_value=_failed_proc()):
            pod.run_red(spec(tmp_path, cycle=1))
        assert all(isinstance(u, TokenUsage) for u in pod.token_usage())

    def test_refactor_records_zero_llm_tokens(self, tmp_path):
        pod = make_pod(tmp_path)
        with patch("subprocess.run", return_value=_passed_proc()):
            pod.run_refactor(spec(tmp_path, cycle=1))
        usage = pod.token_usage()
        assert len(usage) == 1
        assert usage[0].input_tokens == 0


# ---------------------------------------------------------------------------
# Integration (requires Go toolchain)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("go") is None, reason="Go not installed")
class TestGoIntegration:
    def test_run_red_writes_failing_test(self, tmp_path):
        client = make_llm_client(content=(
            'package main\n\nimport "testing"\n\n'
            'func TestAlwaysFail(t *testing.T) {\n\tt.Fatal("red phase")\n}\n'
        ))
        pod = GoLanguagePod(llm_client=client)
        s = PodSpec(
            feature_requirement="Always fail",
            test_file=tmp_path / "fail_test.go",
            implementation_file=tmp_path / "fail.go",
            cycle_number=1,
        )
        (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
        result = pod.run_red(s)
        assert isinstance(result, PhaseResult)
        assert s.test_file.exists()
