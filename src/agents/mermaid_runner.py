"""
MermaidRunner — PodmanRunner variant for validating generated mermaid
diagrams against the real mermaid.js parser, sandboxed like every other
third-party toolchain this project runs (Go modules, TS/npm packages,
pybullet) -- see docker/harness/Containerfile.mermaid.

What's being sandboxed here isn't untrusted *content* the way GREEN-phase
LLM-generated code is -- a mermaid diagram can't escape a JS parser the
way generated code could escape a test harness. It's the *toolchain*:
mermaid + jsdom pull in ~140 third-party npm packages (jsdom alone brings
in undici, whatwg-url, and a long transitive tree), and running that
directly on a host or CI runner via bare subprocess carries the same
supply-chain exposure this project already isolates for the Go and
TypeScript toolchains. This runner keeps that dependency tree entirely
inside the container -- the host (or a developer's own machine, if this
runs from a pre-commit hook) never executes `npm` or `node` directly.

No test/impl pair or RED/GREEN semantics here, unlike GoRunner/
TypeScriptRunner -- send_pulse() takes exactly one file (the mermaid text
to validate) and returns pass/fail against the real parser, baked into
the image at build time (no npm calls at runtime, matching
TypeScriptRunner's "node_modules baked into the image" convention).
"""
import shutil
import subprocess

from src.agents.podman_orchestrator import PulseResult
from src.agents.podman_runner import PodmanRunner

_VALIDATE_SCRIPT = "/opt/mermaid_check/validate.mjs"
_REMOTE_WS = "/workspace"


def build_mermaid_image(
    containerfile: str = "docker/harness/Containerfile.mermaid",
    context: str = ".",
    tag: str = "localhost/ace-mermaid-harness:latest",
) -> None:
    """Build the mermaid-validation harness image. Safe to call repeatedly
    (no-op if up to date). Context is the repo root, not docker/harness/ --
    the Containerfile COPYs tools/mermaid_check/* with repo-relative paths,
    same convention build_simulation_image() uses for the same reason."""
    subprocess.run(
        ["podman", "build", "-f", containerfile, "-t", tag, context],
        check=True,
    )


class MermaidRunner(PodmanRunner):
    """PodmanRunner pre-configured for the mermaid-validation harness image."""

    def __init__(
        self,
        container_name: str | None = None,
        cpus: str = "0.5",
        memory: str = "256m",
        test_timeout: int = 15,
    ) -> None:
        super().__init__(
            image="localhost/ace-mermaid-harness:latest",
            container_name=container_name,
            cpus=cpus,
            memory=memory,
            test_timeout=test_timeout,
        )

    def send_pulse(self, files: dict[str, str]) -> PulseResult:
        """`files` must contain exactly one entry: the mermaid diagram text
        to validate, under any filename (extension doesn't matter to
        validate.mjs)."""
        if len(files) != 1:
            raise ValueError(f"MermaidRunner.send_pulse() takes exactly one file, got {len(files)}")
        (name, content), = files.items()

        for existing in self._host_ws.iterdir():
            if existing.is_dir():
                shutil.rmtree(existing)
            else:
                existing.unlink()
        (self._host_ws / name).write_text(content)

        result = subprocess.run(
            [
                "podman", "exec", "--workdir", _REMOTE_WS, self._name,
                "node", _VALIDATE_SCRIPT, name,
            ],
            capture_output=True, text=True, timeout=self._test_timeout,
        )

        h_executed = self._compute_workspace_hash(list(files.keys()))
        return PulseResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            h_executed=h_executed,
        )
