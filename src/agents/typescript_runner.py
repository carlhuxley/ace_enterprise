"""
TypeScriptRunner — PodmanRunner variant for the TypeScript TDD harness.

Overrides send_pulse() to run vitest instead of pytest+bandit and parse
the vitest JSON reporter output. All container lifecycle and tmpfs workspace
machinery is inherited from PodmanRunner unchanged.
"""
import json
import subprocess
from pathlib import Path

from src.agents.podman_orchestrator import PulseResult, canonical_hash
from src.agents.podman_runner import PodmanRunner

_TS_PROJECT = "/opt/ts-project"
_VITEST_BIN = f"{_TS_PROJECT}/node_modules/.bin/vitest"
_RESULTS_JSON = "/tmp/vitest-results.json"
_REMOTE_WS = "/workspace"

# Injected alongside every pulse so vitest knows this is an ESM workspace
_WORKSPACE_PACKAGE_JSON = '{"type":"module","name":"pulse"}'

# Vitest config written to /workspace each pulse so Vite can write its timestamp
# cache alongside it (ace user owns /workspace, not /opt/ts-project)
_WORKSPACE_VITEST_CONFIG = """\
import { defineConfig } from 'vitest/config';
export default defineConfig({
  cacheDir: '/tmp/vitest-cache',
  test: {
    globals: true,
    environment: 'node',
    root: '/workspace',
    include: ['**/*.{test,spec}.ts', '**/test_*.ts'],
    reporters: ['verbose', 'json'],
    outputFile: '/tmp/vitest-results.json',
    testTimeout: 10000,
  },
});
"""


def build_ts_image(
    containerfile: str = "docker/harness/Containerfile.ts",
    context: str = "docker/harness",
    tag: str = "localhost/ace-ts-harness:latest",
) -> None:
    """Build the TypeScript harness image. Safe to call repeatedly (no-op if up to date)."""
    subprocess.run(
        ["podman", "build", "-f", containerfile, "-t", tag, context],
        check=True,
    )


class TypeScriptRunner(PodmanRunner):
    """PodmanRunner pre-configured for the TypeScript harness image."""

    def __init__(
        self,
        container_name: str | None = None,
        cpus: str = "0.5",
        memory: str = "256m",
        test_timeout: int = 10,
    ) -> None:
        super().__init__(
            image="localhost/ace-ts-harness:latest",
            container_name=container_name,
            cpus=cpus,
            memory=memory,
            test_timeout=test_timeout,
        )

    def send_pulse(self, files: dict[str, str]) -> PulseResult:
        import shutil

        # Clear and repopulate the tmpfs workspace
        for existing in self._host_ws.iterdir():
            if existing.is_dir():
                shutil.rmtree(existing)
            else:
                existing.unlink()

        # Inject ESM marker and vitest config into workspace (ace owns /workspace,
        # so Vite can write its .timestamp cache file alongside the config)
        (self._host_ws / "package.json").write_text(_WORKSPACE_PACKAGE_JSON)
        (self._host_ws / "vitest.config.ts").write_text(_WORKSPACE_VITEST_CONFIG)

        for name, content in files.items():
            (self._host_ws / name).write_text(content)

        # Symlink node_modules into workspace so vitest.config.ts can resolve
        # 'vitest/config' via ESM without NODE_PATH (which ESM ignores).
        subprocess.run(
            ["podman", "exec", self._name,
             "ln", "-sf", f"{_TS_PROJECT}/node_modules", f"{_REMOTE_WS}/node_modules"],
            capture_output=True,
        )

        vitest_proc = subprocess.run(
            [
                "podman", "exec", "--workdir", _TS_PROJECT, self._name,
                "node", _VITEST_BIN,
                "run",
                "--config", f"{_REMOTE_WS}/vitest.config.ts",
                "--reporter", "json",
                "--outputFile", _RESULTS_JSON,
            ],
            capture_output=True,
            text=True,
        )

        # Read the JSON results file from inside the container
        read_proc = subprocess.run(
            ["podman", "exec", self._name, "cat", _RESULTS_JSON],
            capture_output=True,
            text=True,
        )

        stdout, stderr, passed = _parse_vitest(
            vitest_stdout=vitest_proc.stdout,
            vitest_stderr=vitest_proc.stderr,
            results_json=read_proc.stdout,
        )

        h_executed = self._compute_workspace_hash(list(files.keys()))

        return PulseResult(
            exit_code=0 if passed else 1,
            stdout=stdout,
            stderr=stderr,
            bandit_output="",
            bandit_high=0,
            bandit_medium=0,
            bandit_low=0,
            bandit_clean=True,  # no bandit for TS; clean-room gate is the security layer
            h_executed=h_executed,
        )


def _parse_vitest(
    vitest_stdout: str,
    vitest_stderr: str,
    results_json: str,
) -> tuple[str, str, bool]:
    """Parse vitest JSON output. Returns (stdout, stderr, passed)."""
    try:
        data = json.loads(results_json)
    except (json.JSONDecodeError, TypeError):
        # vitest failed to start or produce output — treat as failed
        return vitest_stdout, vitest_stderr, False

    passed = data.get("numFailedTests", 1) == 0 and data.get("numFailedTestSuites", 1) == 0

    # Build a human-readable summary of failures for the GREEN prompt
    failure_lines: list[str] = []
    for suite in data.get("testResults", []):
        for assertion in suite.get("assertionResults", []):
            if assertion.get("status") == "failed":
                title = " > ".join(
                    assertion.get("ancestorTitles", []) + [assertion.get("title", "")]
                )
                failure_lines.append(f"FAIL {title}")
                for msg in assertion.get("failureMessages", []):
                    failure_lines.append(f"  {msg}")

    stdout = vitest_stdout
    if failure_lines:
        stdout = "\n".join(failure_lines) + "\n\n" + vitest_stdout

    return stdout, vitest_stderr, passed
