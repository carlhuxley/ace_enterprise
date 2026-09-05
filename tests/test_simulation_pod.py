"""Tests for SimulationPod (LanguagePod implementation backed by a PyBullet
test oracle instead of a CLI test runner).

The scenario and oracle are faked here so these tests run fast and without
pybullet installed -- see tests/test_simulation_oracle.py for real-physics
coverage against the concrete PegInHoleScenario/TrajectoryFollowingScenario.
"""
from unittest.mock import MagicMock

from src.agents.language_pod import LanguagePod, PodSpec
from src.agents.simulation_invariants import MetricBound
from src.agents.simulation_oracle import SimulationEnvironmentError
from src.agents.simulation_pod import SimulationPod
from src.agents.simulation_runner import SimulationTelemetry


def make_telemetry(success=True, **overrides):
    fields = {
        "success": success,
        "steps_taken": 120,
        "violated": False,
        "violated_metric": None,
        "stalled": not success,
        "phase": "converged" if success else "stalled",
        "peak_metrics": {"force": 1.0},
        "final_metrics": {"error": 0.0001},
        "metric_traces": {"force": [0.0, 1.0], "error": [1.0, 0.0001]},
        "failure_reason": None if success else "stalled: exhausted steps",
    }
    fields.update(overrides)
    return SimulationTelemetry(**fields)


def make_scenario():
    scenario = MagicMock()
    scenario.null_action_source.return_value = "def compute_action(observation):\n    return {}\n"
    scenario.default_invariants.return_value = [MetricBound("error", "<=", 0.001, "final", within_steps=500)]
    scenario.controller_contract.return_value = "Write compute_action(observation) -> dict."
    return scenario


def make_llm_client(content="def compute_action(observation):\n    return {'vx': 0.0, 'vy': 0.0, 'vz': -0.01}\n", tokens_used=80):
    client = MagicMock()
    client.generate.return_value = {
        "content": content,
        "tokens_used": tokens_used,
        "latency_ms": 10,
        "model": "gpt-4o",
    }
    return client


def make_pod(tmp_path, oracle=None, llm_client=None, scenario=None):
    return SimulationPod(
        llm_client=llm_client or make_llm_client(),
        project_root=tmp_path,
        scenario=scenario or make_scenario(),
        oracle=oracle or MagicMock(),
    )


def spec(tmp_path, cycle=1, gherkin_context=None, error_output=""):
    return PodSpec(
        feature_requirement="Track a target without violating limits",
        test_file=tmp_path / "scenario.json",
        implementation_file=tmp_path / "controller.py",
        cycle_number=cycle,
        gherkin_context=gherkin_context,
        error_output=error_output,
    )


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
    def test_red_fails_against_null_controller(self, tmp_path):
        scenario = make_scenario()
        oracle = MagicMock()
        oracle.run.return_value = make_telemetry(success=False)
        pod = make_pod(tmp_path, oracle=oracle, scenario=scenario)

        result = pod.run_red(spec(tmp_path))

        assert result.passed is False
        assert oracle.run.call_args.args[0] == scenario.null_action_source.return_value

    def test_red_writes_invariants_to_test_file(self, tmp_path):
        oracle = MagicMock()
        oracle.run.return_value = make_telemetry(success=False)
        pod = make_pod(tmp_path, oracle=oracle)

        s = spec(tmp_path)
        pod.run_red(s)

        assert s.test_file.exists()
        assert '"metric"' in s.test_file.read_text()

    def test_red_flags_unexpected_success_as_error(self, tmp_path):
        oracle = MagicMock()
        oracle.run.return_value = make_telemetry(success=True)
        pod = make_pod(tmp_path, oracle=oracle)

        result = pod.run_red(spec(tmp_path))

        assert result.passed is True
        assert result.error is not None

    def test_red_surfaces_environment_error(self, tmp_path):
        oracle = MagicMock()
        oracle.run.side_effect = SimulationEnvironmentError("pybullet not installed")
        pod = make_pod(tmp_path, oracle=oracle)

        result = pod.run_red(spec(tmp_path))

        assert result.passed is False
        assert "SimulationEnvironment" in result.error

    def test_red_uses_extracted_invariants_when_gherkin_declares_them(self, tmp_path):
        oracle = MagicMock()
        oracle.run.return_value = make_telemetry(success=False)
        pod = make_pod(tmp_path, oracle=oracle)

        gherkin = "Then the peak force must never exceed 9.0"
        pod.run_red(spec(tmp_path, gherkin_context=gherkin))

        used_invariants = oracle.run.call_args.args[1]
        assert used_invariants == [MetricBound("peak_force", "<=", 9.0, "instantaneous")]

    def test_red_falls_back_to_scenario_defaults_when_gherkin_declares_nothing(self, tmp_path):
        scenario = make_scenario()
        oracle = MagicMock()
        oracle.run.return_value = make_telemetry(success=False)
        pod = make_pod(tmp_path, oracle=oracle, scenario=scenario)

        pod.run_red(spec(tmp_path, gherkin_context="no thresholds here"))

        used_invariants = oracle.run.call_args.args[1]
        assert used_invariants == scenario.default_invariants.return_value


# ---------------------------------------------------------------------------
# run_green
# ---------------------------------------------------------------------------

class TestRunGreen:
    def test_green_passes_and_commits_controller(self, tmp_path):
        oracle = MagicMock()
        oracle.run.return_value = make_telemetry(success=True)
        pod = make_pod(tmp_path, oracle=oracle)

        s = spec(tmp_path)
        result = pod.run_green(s)

        assert result.passed is True
        assert s.implementation_file.exists()
        assert "compute_action" in s.implementation_file.read_text()

    def test_green_failure_does_not_commit(self, tmp_path):
        oracle = MagicMock()
        oracle.run.return_value = make_telemetry(success=False)
        pod = make_pod(tmp_path, oracle=oracle)

        s = spec(tmp_path)
        result = pod.run_green(s)

        assert result.passed is False
        assert not s.implementation_file.exists()
        assert result.error == "stalled: exhausted steps"

    def test_green_rejects_forbidden_imports(self, tmp_path):
        llm_client = make_llm_client(content="import os\ndef compute_action(observation):\n    return {'vx':0,'vy':0,'vz':0}\n")
        oracle = MagicMock()
        pod = make_pod(tmp_path, oracle=oracle, llm_client=llm_client)

        result = pod.run_green(spec(tmp_path))

        assert result.passed is False
        assert "ForbiddenImport" in result.error
        oracle.run.assert_not_called()

    def test_green_extracts_code_from_markdown_fence(self, tmp_path):
        fenced = "Here is the controller:\n```python\ndef compute_action(observation):\n    return {'vx': 0.0, 'vy': 0.0, 'vz': -0.01}\n```"
        llm_client = make_llm_client(content=fenced)
        oracle = MagicMock()
        oracle.run.return_value = make_telemetry(success=True)
        pod = make_pod(tmp_path, oracle=oracle, llm_client=llm_client)

        s = spec(tmp_path)
        pod.run_green(s)

        committed = s.implementation_file.read_text()
        assert "```" not in committed
        assert "def compute_action" in committed

    def test_green_surfaces_environment_error(self, tmp_path):
        oracle = MagicMock()
        oracle.run.side_effect = SimulationEnvironmentError("timed out")
        pod = make_pod(tmp_path, oracle=oracle)

        result = pod.run_green(spec(tmp_path))

        assert result.passed is False
        assert "SimulationEnvironment" in result.error

    def test_green_passes_previous_error_feedback_into_prompt(self, tmp_path):
        llm_client = make_llm_client()
        original_generate = llm_client.generate  # _intercept_tokens replaces llm_client.generate itself
        oracle = MagicMock()
        oracle.run.return_value = make_telemetry(success=True)
        pod = make_pod(tmp_path, oracle=oracle, llm_client=llm_client)

        pod.run_green(spec(tmp_path, error_output="violated:force peak too high"))

        prompt = original_generate.call_args.args[0]
        assert "violated:force peak too high" in prompt

    def test_green_prompt_includes_scenarios_controller_contract(self, tmp_path):
        llm_client = make_llm_client()
        original_generate = llm_client.generate
        scenario = make_scenario()
        oracle = MagicMock()
        oracle.run.return_value = make_telemetry(success=True)
        pod = make_pod(tmp_path, oracle=oracle, llm_client=llm_client, scenario=scenario)

        pod.run_green(spec(tmp_path))

        prompt = original_generate.call_args.args[0]
        assert scenario.controller_contract.return_value in prompt


# ---------------------------------------------------------------------------
# run_refactor
# ---------------------------------------------------------------------------

class TestRunRefactor:
    def test_refactor_commits_when_still_passing(self, tmp_path):
        oracle = MagicMock()
        oracle.run.return_value = make_telemetry(success=True)
        llm_client = make_llm_client(content="def compute_action(observation):\n    return {'vx': 0.0, 'vy': 0.0, 'vz': -0.02}\n")
        pod = make_pod(tmp_path, oracle=oracle, llm_client=llm_client)

        s = spec(tmp_path)
        s.implementation_file.write_text("def compute_action(observation):\n    return {'vx': 0.0, 'vy': 0.0, 'vz': -0.01}\n")

        result = pod.run_refactor(s)

        assert result.passed is True
        assert "-0.02" in s.implementation_file.read_text()

    def test_refactor_does_not_clobber_working_controller_on_failure(self, tmp_path):
        oracle = MagicMock()
        oracle.run.return_value = make_telemetry(success=False)
        llm_client = make_llm_client(content="def compute_action(observation):\n    return {'vx': 0.0, 'vy': 0.0, 'vz': -0.02}\n")
        pod = make_pod(tmp_path, oracle=oracle, llm_client=llm_client)

        s = spec(tmp_path)
        original = "def compute_action(observation):\n    return {'vx': 0.0, 'vy': 0.0, 'vz': -0.01}\n"
        s.implementation_file.write_text(original)

        result = pod.run_refactor(s)

        assert result.passed is False
        assert s.implementation_file.read_text() == original


# ---------------------------------------------------------------------------
# token_usage
# ---------------------------------------------------------------------------

class TestTokenUsage:
    def test_records_usage_per_cycle(self, tmp_path):
        oracle = MagicMock()
        oracle.run.return_value = make_telemetry(success=False)
        llm_client = make_llm_client(tokens_used=250)
        pod = make_pod(tmp_path, oracle=oracle, llm_client=llm_client)

        pod.run_green(spec(tmp_path, cycle=1))
        pod.run_green(spec(tmp_path, cycle=2))

        usage = pod.token_usage()
        assert [u.cycle_number for u in usage] == [1, 2]
        assert usage[0].input_tokens == 250

    def test_run_red_does_not_consume_llm_tokens(self, tmp_path):
        oracle = MagicMock()
        oracle.run.return_value = make_telemetry(success=False)
        llm_client = make_llm_client(tokens_used=250)
        original_generate = llm_client.generate  # _intercept_tokens replaces llm_client.generate itself
        pod = make_pod(tmp_path, oracle=oracle, llm_client=llm_client)

        pod.run_red(spec(tmp_path))

        assert pod.token_usage()[0].input_tokens == 0
        original_generate.assert_not_called()
