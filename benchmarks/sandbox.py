"""Execution backends for benchmarks.runner.

Both backends implement the `ContainerRunner` protocol from
src/agents/podman_orchestrator.py (start/stop/is_alive/send_pulse), so
`PodmanOrchestrator.pulse()` -- which already knows how to turn a bandit
HIGH finding into a "Security gate" PhaseResult failure -- works unchanged
against either one.

  - build_podman_runner(): the hardened path. Reuses PodmanRunner as-is
    (--network none, read-only bind mount, dropped capabilities -- see
    src/agents/podman_runner.py). Requires podman and the
    localhost/ace-harness:latest image (docker/harness/Containerfile).
  - LocalSubprocessRunner: zero-setup fallback that runs pytest + bandit
    directly on the host. No sandboxing beyond a subprocess timeout --
    only use this against models/output you already trust, or when podman
    isn't available.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from src.agents.podman_orchestrator import PulseResult, canonical_hash


class LocalSubprocessRunner:
    """ContainerRunner that runs pytest + bandit on the host, no container."""

    def __init__(self, test_timeout: int = 10) -> None:
        self._test_timeout = test_timeout
        self._alive = False

    def start(self) -> None:
        self._alive = True

    def stop(self) -> None:
        self._alive = False

    def is_alive(self) -> bool:
        return self._alive

    def send_pulse(self, files: dict[str, str]) -> PulseResult:
        with tempfile.TemporaryDirectory(prefix="ace_bench_") as ws:
            ws_path = Path(ws)
            for name, content in files.items():
                (ws_path / name).write_text(content)

            try:
                pytest_result = subprocess.run(
                    [
                        sys.executable, "-B", "-m", "pytest", ".", "-v",
                        "--tb=short", "-p", "no:cacheprovider",
                    ],
                    cwd=ws_path,
                    capture_output=True,
                    text=True,
                    timeout=self._test_timeout,
                )
                pytest_exit, pytest_out, pytest_err = (
                    pytest_result.returncode, pytest_result.stdout, pytest_result.stderr,
                )
            except subprocess.TimeoutExpired as exc:
                # subprocess.TimeoutExpired.stdout/.stderr are the raw bytes
                # captured by Popen.communicate() before the timeout fired --
                # unlike the normal subprocess.run() return path, they are
                # NOT decoded even though text=True was passed above. Left
                # as bytes, this silently poisons everything downstream that
                # expects str (PulseResult/PhaseResult.output, then
                # EnvironmentFeedback.test_report, which Reflector
                # json.dumps()s -- "Object of type bytes is not JSON
                # serializable", discovered on a real timing-out task).
                raw_out = exc.stdout or b""
                pytest_out = raw_out.decode("utf-8", errors="replace") if isinstance(raw_out, bytes) else raw_out
                pytest_exit = 1
                pytest_err = f"Execution timed out after {self._test_timeout}s (possible hang/deadlock)"

            bandit_result = subprocess.run(
                [sys.executable, "-m", "bandit", "-r", str(ws_path), "--format", "json", "-q"],
                capture_output=True,
                text=True,
            )

            executed = {
                name: (ws_path / name).read_text()
                for name in files
                if (ws_path / name).exists()
            }

        return PulseResult(
            exit_code=pytest_exit,
            stdout=pytest_out,
            stderr=pytest_err,
            **_parse_bandit(bandit_result.stdout or bandit_result.stderr),
            h_executed=canonical_hash(executed),
        )


def _parse_bandit(raw: str) -> dict:
    high = medium = low = 0
    try:
        data = json.loads(raw)
        totals = data.get("metrics", {}).get("_totals", {})
        high = int(totals.get("SEVERITY.HIGH", 0))
        medium = int(totals.get("SEVERITY.MEDIUM", 0))
        low = int(totals.get("SEVERITY.LOW", 0))
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return {
        "bandit_output": raw,
        "bandit_high": high,
        "bandit_medium": medium,
        "bandit_low": low,
        "bandit_clean": high == 0,
    }


def build_podman_runner(container_name: str = "ace_benchmark", test_timeout: int = 10):
    """Lazily imports PodmanRunner so `--sandbox local` never needs podman installed."""
    from src.agents.podman_runner import PodmanRunner

    return PodmanRunner(container_name=container_name, test_timeout=test_timeout)
