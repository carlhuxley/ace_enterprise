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
