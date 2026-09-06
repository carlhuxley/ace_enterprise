import shutil

import pytest


def podman_available() -> bool:
    return shutil.which("podman") is not None


@pytest.fixture(scope="session")
def shared_podman_runner():
    """One container for the whole test session — avoids per-test start/stop overhead."""
    if not podman_available():
        pytest.skip("podman not in PATH")
    from src.agents.podman_runner import PodmanRunner
    runner = PodmanRunner(container_name="harness_test_session")
    runner.start()
    yield runner
    runner.stop()


@pytest.fixture(scope="session")
def shared_sim_podman_runner():
    """One simulation-harness container for the whole test session. Assumes
    localhost/ace-sim-harness:latest is already built (build_simulation_image()
    in src/agents/simulation_podman_runner.py) -- same precedent as
    shared_podman_runner above for ace-harness/ace-ts-harness/ace-go-harness."""
    if not podman_available():
        pytest.skip("podman not in PATH")
    from src.agents.simulation_podman_runner import SimulationPodmanRunner
    runner = SimulationPodmanRunner(container_name="sim_harness_test_session", sim_timeout=60)
    runner.start()
    yield runner
    runner.stop()
