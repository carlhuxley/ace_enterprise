"""Real-podman tests for SimulationPodmanRunner and SimulationOracle's
containerized execution path. Skipped when podman is not in PATH.

Unlike tests/test_simulation_oracle.py's real-physics tests, these need no
pybullet on the *host* -- the physics runs entirely inside the container
(localhost/ace-sim-harness:latest, built by build_simulation_image()), so
these are gated on podman + that image existing, not on the host's own
pybullet installation.
"""
import shutil

import pytest

from src.agents.simulation_oracle import SimulationOracle
from src.agents.simulation_scenarios.peg_in_hole import PegInHoleScenario
from tests.conftest import podman_available

skip_no_podman = pytest.mark.skipif(not podman_available(), reason="podman not in PATH")

_GOOD_CONTROLLER = """\
def compute_action(observation):
    kp = 2.0
    x, y = observation['x'], observation['y']
    radial = (x ** 2 + y ** 2) ** 0.5
    vz = -0.03 if radial <= 0.001 else -0.005
    return {'vx': -kp * x, 'vy': -kp * y, 'vz': vz}
"""


@skip_no_podman
class TestSimulationPodmanRunnerRealContainer:
    def test_send_pulse_is_not_supported(self, shared_sim_podman_runner):
        """SimulationPodmanRunner needs a JSON args payload the generic
        ContainerRunner.send_pulse(files) protocol has no slot for -- it
        uses run_simulation_pulse() instead. See the class docstring."""
        with pytest.raises(NotImplementedError):
            shared_sim_podman_runner.send_pulse({"controller.py": "x = 1"})

    def test_is_alive_after_start(self, shared_sim_podman_runner):
        assert shared_sim_podman_runner.is_alive() is True

    def test_good_controller_converges_inside_the_container(self, shared_sim_podman_runner):
        scenario = PegInHoleScenario()
        oracle = SimulationOracle(scenario, timeout_s=60, runner=shared_sim_podman_runner)
        oracle._runner_started = True  # already started by the shared fixture

        telemetry = oracle.run(_GOOD_CONTROLLER, scenario.default_invariants())

        assert telemetry.success is True
        assert telemetry.phase == "converged"
        assert telemetry.final_metrics["peak_force"] <= 12.0

    def test_null_controller_stalls_inside_the_container(self, shared_sim_podman_runner):
        scenario = PegInHoleScenario()
        oracle = SimulationOracle(scenario, timeout_s=60, runner=shared_sim_podman_runner)
        oracle._runner_started = True

        telemetry = oracle.run(scenario.null_action_source(), scenario.default_invariants())

        assert telemetry.success is False
        assert telemetry.stalled is True

    def test_matches_bare_subprocess_result_for_the_same_controller(self, shared_sim_podman_runner):
        """Same telemetry contract, only the transport differs -- the
        containerized and bare-subprocess paths must agree on outcome for
        an identical controller/scenario/invariants combination."""
        scenario = PegInHoleScenario()
        invariants = scenario.default_invariants()

        containerized = SimulationOracle(scenario, timeout_s=60, runner=shared_sim_podman_runner)
        containerized._runner_started = True
        contained_result = containerized.run(_GOOD_CONTROLLER, invariants)

        bare = SimulationOracle(PegInHoleScenario(), timeout_s=60)
        bare_result = bare.run(_GOOD_CONTROLLER, invariants)

        assert contained_result.success == bare_result.success is True
        assert contained_result.steps_taken == bare_result.steps_taken


@skip_no_podman
def test_image_missing_raises_a_clear_error():
    """A misconfigured environment (image never built) should fail loudly on
    start(), not hang or silently fall back -- same behavior as the other
    per-language harness images already rely on (see conftest.py's
    shared_podman_runner, which has no build-on-missing fallback either)."""
    import subprocess

    from src.agents.simulation_podman_runner import SimulationPodmanRunner

    runner = SimulationPodmanRunner(container_name="sim_missing_image_test", cpus="0.1", memory="64m")
    runner._image = "localhost/ace-sim-harness-does-not-exist:latest"
    with pytest.raises(subprocess.CalledProcessError):
        runner.start()


def test_shutil_which_is_the_only_podman_dependency_for_skip_detection():
    """Sanity check that the skip predicate this module relies on is cheap
    and doesn't itself require podman to be running."""
    assert podman_available() == (shutil.which("podman") is not None)
