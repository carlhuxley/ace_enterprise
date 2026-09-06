"""Tests for src/broker/calibration.py -- cold-start model calibration (#5).

The real sandboxed runner (PolyglotTDDRunner/PodmanOrchestrator/LLMClient) is
never exercised here -- these tests inject a fake runner_factory.
"""
import pytest

from src.broker.calibration import CALIBRATION_REQUIREMENT, calibrate_cold_start_models


class _FakeRunner:
    def __init__(self, calls: list[dict]):
        self._calls = calls

    def run(self, **kwargs):
        self._calls.append(kwargs)


@pytest.fixture
def audit_url(tmp_path):
    return f"sqlite:///{tmp_path / 'audit.db'}"


def test_calibrates_each_model_ref_with_the_fixed_requirement(audit_url):
    run_calls: list[dict] = []
    factory_calls: list[dict] = []

    def factory(**kwargs):
        factory_calls.append(kwargs)
        return _FakeRunner(run_calls)

    calibrate_cold_start_models(
        ["openrouter/qwen/q1", "ollama/q2"],
        audit_database_url=audit_url,
        runner_factory=factory,
    )

    assert len(run_calls) == 2
    assert all(c["feature_requirement"] == CALIBRATION_REQUIREMENT for c in run_calls)
    assert all(c["languages"] == ["python"] for c in run_calls)
    assert {fc["model_ref"] for fc in factory_calls} == {"openrouter/qwen/q1", "ollama/q2"}


def test_runner_factory_raising_is_caught_and_does_not_propagate(audit_url):
    def factory(**kwargs):
        raise RuntimeError("sandbox unavailable")

    calibrate_cold_start_models(
        ["openrouter/qwen/q1"], audit_database_url=audit_url, runner_factory=factory,
    )  # must not raise


def test_runner_run_raising_is_caught_and_does_not_propagate(audit_url):
    class _RaisingRunner:
        def run(self, **kwargs):
            raise RuntimeError("boom")

    calibrate_cold_start_models(
        ["openrouter/qwen/q1"],
        audit_database_url=audit_url,
        runner_factory=lambda **kw: _RaisingRunner(),
    )  # must not raise


def test_workspace_is_cleaned_up_even_on_failure(audit_url):
    captured = {}

    def factory(**kwargs):
        captured["project_path"] = kwargs["project_path"]
        raise RuntimeError("boom")

    calibrate_cold_start_models(
        ["openrouter/qwen/q1"], audit_database_url=audit_url, runner_factory=factory,
    )

    assert not captured["project_path"].exists()


def test_no_cold_candidates_means_no_runner_calls(audit_url):
    def factory(**kwargs):
        raise AssertionError("must not be called")

    calibrate_cold_start_models([], audit_database_url=audit_url, runner_factory=factory)
