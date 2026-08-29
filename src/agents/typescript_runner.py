"""
TypeScriptRunner — PodmanRunner variant for the TypeScript TDD harness.

Overrides send_pulse() to run vitest (instead of pytest) for tests and
eslint + eslint-plugin-security (instead of Bandit) for static security
scanning, parsing both JSON outputs into the shared PulseResult fields. All
container lifecycle and tmpfs workspace machinery is inherited from
PodmanRunner unchanged.
"""
import json
import subprocess
import tempfile
from pathlib import Path

from src.agents.podman_orchestrator import PulseResult
from src.agents.podman_runner import PodmanRunner

_TS_PROJECT = "/opt/ts-project"
_VITEST_BIN = f"{_TS_PROJECT}/node_modules/.bin/vitest"
_ESLINT_BIN = f"{_TS_PROJECT}/node_modules/.bin/eslint"
_ESLINT_CONFIG = f"{_TS_PROJECT}/eslint.config.js"
_RESULTS_JSON = "/tmp/vitest-results.json"
_REMOTE_WS = "/workspace"
_REMOTE_CONFIG = "/tmp/vitest.config.ts"

# Injected alongside every pulse so vitest knows this is an ESM workspace
_WORKSPACE_PACKAGE_JSON = '{"type":"module","name":"pulse"}'

# Vitest config is copied into the container's writable /tmp (not /workspace)
# each pulse. Vite's config loader bundles this file and writes a compiled
# `<config>.timestamp-*.mjs` file *next to it* as an unavoidable side effect of
# loading it — that write target has to be writable, and /workspace is now
# read-only (see podman_runner.py), so the config can't live there anymore.
_VITEST_CONFIG = """\
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

    def start(self) -> None:
        super().start()
        # The vitest config now lives in /tmp (see _REMOTE_CONFIG), so it needs
        # its own node_modules symlink to resolve 'vitest/config' — the one in
        # /workspace only helps modules loaded from within the workspace.
        subprocess.run(
            ["podman", "exec", self._name,
             "ln", "-sf", f"{_TS_PROJECT}/node_modules", "/tmp/node_modules"],
            capture_output=True,
        )

    def send_pulse(self, files: dict[str, str]) -> PulseResult:
        import shutil

        # Clear and repopulate the tmpfs workspace
        for existing in self._host_ws.iterdir():
            if existing.is_dir():
                shutil.rmtree(existing)
            else:
                existing.unlink()

        # Inject ESM marker (read-only workspace is fine for this — node only
        # reads package.json, never writes it)
        (self._host_ws / "package.json").write_text(_WORKSPACE_PACKAGE_JSON)

        # Vitest config goes into the container's writable /tmp via podman cp,
        # not the read-only workspace (see _VITEST_CONFIG docstring above).
        with tempfile.NamedTemporaryFile("w", suffix=".ts", delete=False) as f:
            f.write(_VITEST_CONFIG)
            local_config = f.name
        try:
            subprocess.run(
                ["podman", "cp", local_config, f"{self._name}:{_REMOTE_CONFIG}"],
                check=True,
                capture_output=True,
            )
        finally:
            Path(local_config).unlink(missing_ok=True)

        for name, content in files.items():
            (self._host_ws / name).write_text(content)

        # Symlink node_modules into workspace so vitest.config.ts can resolve
        # 'vitest/config' via ESM without NODE_PATH (which ESM ignores). Created
        # from the host side, not via podman exec: the workspace mount is
        # read-only inside the container, so the container can't create it
        # itself. The symlink target ("/opt/ts-project/node_modules") only needs
        # to resolve inside the container's filesystem, not the host's — that's
        # fine, since only the container ever reads through it.
        (self._host_ws / "node_modules").symlink_to(f"{_TS_PROJECT}/node_modules")

        _vitest_timeout = max(60, self._test_timeout * 6)
        try:
            vitest_proc = subprocess.run(
                [
                    "podman", "exec", "--workdir", _TS_PROJECT, self._name,
                    "node", _VITEST_BIN,
                    "run",
                    "--config", _REMOTE_CONFIG,
                    "--reporter", "json",
                    "--outputFile", _RESULTS_JSON,
                ],
                capture_output=True,
                text=True,
                timeout=_vitest_timeout,
            )
        except subprocess.TimeoutExpired:
            import time
            # Kill the saturated container.
            subprocess.run(["podman", "rm", "-f", self._name], capture_output=True)
            # Wait until Podman confirms it's gone before restarting (avoids name collision).
            for _ in range(10):
                check = subprocess.run(
                    ["podman", "ps", "-a", "--filter", f"name={self._name}", "-q"],
                    capture_output=True, text=True,
                )
                if not check.stdout.strip():
                    break
                time.sleep(0.5)
            self.start()
            return PulseResult(
                exit_code=1,
                stdout="",
                stderr=f"vitest timed out after {_vitest_timeout}s (esbuild hang); container restarted",
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

        # Static security scan (ace_enterprise-85u) — the TS analog of Bandit
        # for Python. Only .ts files from this pulse are scanned (package.json
        # etc aren't source). cwd=/workspace so eslint resolves file patterns
        # relative to the (read-only) workspace instead of /opt/ts-project.
        ts_files = [name for name in files if name.endswith(".ts")]
        eslint_output = ""
        if ts_files:
            eslint_proc = subprocess.run(
                [
                    "podman", "exec", "--workdir", _REMOTE_WS, self._name,
                    _ESLINT_BIN, "--format", "json",
                    "--no-config-lookup", "--config", _ESLINT_CONFIG,
                    *ts_files,
                ],
                capture_output=True,
                text=True,
            )
            eslint_output = eslint_proc.stdout or eslint_proc.stderr
        eslint_high, eslint_medium, eslint_output = _parse_eslint(eslint_output)

        h_executed = self._compute_workspace_hash(list(files.keys()))

        return PulseResult(
            exit_code=0 if passed else 1,
            stdout=stdout,
            stderr=stderr,
            bandit_output=eslint_output,
            bandit_high=eslint_high,
            bandit_medium=eslint_medium,
            bandit_low=0,
            bandit_clean=eslint_high == 0,
            h_executed=h_executed,
        )


def _parse_eslint(raw: str) -> tuple[int, int, str]:
    """Parse eslint --format json output. Returns (high_count, medium_count, raw).

    eslint severity 2 ("error", escalated rules in eslint.config.js) maps to
    HIGH; severity 1 ("warn", the rest of eslint-plugin-security's recommended
    set) maps to MEDIUM — mirroring Bandit's HIGH/MEDIUM split for Python.
    """
    high = medium = 0
    try:
        results = json.loads(raw)
        for file_result in results:
            for msg in file_result.get("messages", []):
                if msg.get("severity") == 2:
                    high += 1
                elif msg.get("severity") == 1:
                    medium += 1
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return high, medium, raw


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
