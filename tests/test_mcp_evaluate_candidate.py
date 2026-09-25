"""Tests for the evaluate_candidate MCP tool.

evaluate_candidate wires a one-shot PodmanOrchestrator/PodmanRunner pulse
into MCP, then scores the resulting PhaseResult via the sibling dream_rsi
repo's AssertionError-JSON-payload convention (see mcp_server/tools.py's
_extract_assertion_json_payload / _score_phase_result docstrings). These
tests replace PodmanOrchestrator with a stub so no real podman/container
calls happen, and separately unit-test the pure scoring functions with no
mocks at all.
"""
from unittest.mock import patch

import pytest

from mcp_server.tools import (
    _EVALUATE_CRASH_SCORE,
    _EVALUATE_INCORRECT_SCORE,
    ACETools,
    _extract_assertion_json_payload,
    _score_phase_result,
)
from src.agents.language_pod import PhaseResult
from src.audit.local_client import LocalAuditClient


@pytest.fixture
def tools(tmp_path):
    t = ACETools(playbook_id="pb1")
    t._audit = LocalAuditClient(database_url=f"sqlite:///{tmp_path}/audit.db")
    return t


@pytest.fixture
def stub_orchestrator_cls():
    """Patch PodmanOrchestrator so evaluate_candidate never touches real containers."""
    with patch("src.agents.podman_orchestrator.PodmanOrchestrator") as cls:
        yield cls


def _assertion_output(payload: dict) -> str:
    import json as _json
    return f"some pytest preamble\nE   AssertionError: {_json.dumps(payload)}"


class TestExtractAssertionJsonPayload:
    def test_extracts_the_last_assertion_error_json_line(self):
        output = "noise\nAssertionError: {\"a\": 1}\nmore noise\nAssertionError: {\"a\": 2}"
        assert _extract_assertion_json_payload(output) == {"a": 2}

    def test_returns_none_when_no_assertion_error_present(self):
        assert _extract_assertion_json_payload("Traceback...\nTimeoutError") is None

    def test_returns_none_for_malformed_json(self):
        assert _extract_assertion_json_payload("AssertionError: {not json}") is None

    def test_returns_none_for_non_dict_json(self):
        assert _extract_assertion_json_payload("AssertionError: [1, 2, 3]") is None

    def test_never_raises_on_non_string_input(self):
        assert _extract_assertion_json_payload(None) is None
        assert _extract_assertion_json_payload(12345) is None


class TestScorePhaseResult:
    def test_correct_candidate_maps_to_success_with_positive_score(self):
        payload = {"correct": True, "n_valid": 5, "n_total": 5, "latency_ns": 1_000_000}
        result = _score_phase_result(PhaseResult(passed=False, output=_assertion_output(payload)))
        assert result["status"] == "success"
        assert result["score"] > 0

    def test_wrong_but_clean_candidate_maps_to_partial(self):
        payload = {"correct": False, "n_valid": 2, "n_total": 5, "notes": "3 mismatches"}
        result = _score_phase_result(PhaseResult(passed=False, output=_assertion_output(payload)))
        assert result["status"] == "partial"
        assert result["score"] == _EVALUATE_INCORRECT_SCORE * (1 - 0.4)
        assert result["diagnostics"] == "3 mismatches"

    def test_no_payload_maps_to_error_with_crash_score(self):
        result = _score_phase_result(
            PhaseResult(passed=False, output="Traceback...\nTimeoutError", error="timed out")
        )
        assert result["status"] == "error"
        assert result["score"] == _EVALUATE_CRASH_SCORE
        assert result["diagnostics"] == "timed out"

    def test_security_gate_rejection_maps_to_error(self):
        result = _score_phase_result(
            PhaseResult(passed=False, output="", error="Security gate: HIGH=1 MEDIUM=0 LOW=0")
        )
        assert result["status"] == "error"
        assert "Security gate" in result["diagnostics"]

    @pytest.mark.parametrize("bad_latency", [0, -5, float("nan"), "not-a-number", True])
    def test_non_numeric_or_non_positive_latency_defaults_to_one_instead_of_raising(self, bad_latency):
        payload = {"correct": True, "n_valid": 1, "n_total": 1, "latency_ns": bad_latency}
        result = _score_phase_result(PhaseResult(passed=False, output=_assertion_output(payload)))
        assert result["status"] == "success"
        assert result["score"] == pytest.approx(1e9)

    def test_correct_true_without_n_valid_key_assumes_fully_passed(self):
        payload = {"correct": True, "n_total": 3, "latency_ns": 1.0}
        result = _score_phase_result(PhaseResult(passed=False, output=_assertion_output(payload)))
        assert result["status"] == "success"
        assert result["score"] == pytest.approx(1e9)


class TestHandleEvaluateCandidate:
    def test_correct_candidate_returns_success_with_telemetry(self, tools, stub_orchestrator_cls):
        payload = {"correct": True, "n_valid": 1, "n_total": 1, "latency_ns": 1_000_000}
        stub_orchestrator_cls.return_value.pulse.return_value = PhaseResult(
            passed=False, output=_assertion_output(payload),
        )

        result = tools._handle_evaluate_candidate({
            "candidate_code": "def f(): return 1",
            "test_code": "def test_eval(): raise AssertionError('...')",
        })

        assert result["status"] == "success"
        assert result["score"] > 0
        assert result["telemetry"]["wall_clock_ms"] >= 0.0
        assert result["telemetry"]["cpu_seconds"] == 0.0

    def test_pulse_is_called_with_candidate_and_test_files(self, tools, stub_orchestrator_cls):
        payload = {"correct": True, "n_valid": 1, "n_total": 1, "latency_ns": 1.0}
        stub_orchestrator_cls.return_value.pulse.return_value = PhaseResult(
            passed=False, output=_assertion_output(payload),
        )

        tools._handle_evaluate_candidate({
            "candidate_code": "CANDIDATE_SOURCE",
            "test_code": "TEST_SOURCE",
        })

        stub_orchestrator_cls.return_value.pulse.assert_called_once_with({
            "candidate.py": "CANDIDATE_SOURCE",
            "test_eval.py": "TEST_SOURCE",
        })

    def test_orchestrator_is_stopped_even_when_pulse_raises(self, tools, stub_orchestrator_cls):
        stub_orchestrator_cls.return_value.pulse.side_effect = RuntimeError("container died")

        result = tools._handle_evaluate_candidate({
            "candidate_code": "def f(): ...",
            "test_code": "def test_eval(): ...",
        })

        assert result["status"] == "error"
        assert result["score"] == _EVALUATE_CRASH_SCORE
        assert "container died" in result["diagnostics"]
        stub_orchestrator_cls.return_value.stop.assert_called_once()

    def test_disabled_when_tdd_tools_are_off(self, stub_orchestrator_cls):
        t = ACETools(playbook_id="pb1", enable_tdd=False)
        result = t._handle_evaluate_candidate({"candidate_code": "x", "test_code": "y"})
        assert result == {"error": "TDD tools not enabled"}
        stub_orchestrator_cls.assert_not_called()

    def test_resource_limit_overrides_are_forwarded_to_podman_runner(self, tools, stub_orchestrator_cls):
        payload = {"correct": True, "n_valid": 1, "n_total": 1, "latency_ns": 1.0}
        stub_orchestrator_cls.return_value.pulse.return_value = PhaseResult(
            passed=False, output=_assertion_output(payload),
        )

        with patch("src.agents.podman_runner.PodmanRunner") as runner_cls:
            tools._handle_evaluate_candidate({
                "candidate_code": "x", "test_code": "y",
                "timeout_seconds": 30, "cpus": "1.0", "memory": "512m",
            })
            runner_cls.assert_called_once_with(cpus="1.0", memory="512m", test_timeout=30)


class TestToolListing:
    def test_evaluate_candidate_listed_when_tdd_enabled(self):
        t = ACETools(playbook_id="pb1", enable_tdd=True)
        names = [tool["name"] for tool in t.get_tool_definitions()]
        assert "evaluate_candidate" in names

    def test_evaluate_candidate_absent_when_tdd_disabled(self):
        t = ACETools(playbook_id="pb1", enable_tdd=False)
        names = [tool["name"] for tool in t.get_tool_definitions()]
        assert "evaluate_candidate" not in names

    def test_reachable_via_call_tool_dispatch(self, tools, stub_orchestrator_cls):
        payload = {"correct": True, "n_valid": 1, "n_total": 1, "latency_ns": 1.0}
        stub_orchestrator_cls.return_value.pulse.return_value = PhaseResult(
            passed=False, output=_assertion_output(payload),
        )
        result = tools.call_tool("evaluate_candidate", {"candidate_code": "x", "test_code": "y"})
        assert result["status"] == "success"
