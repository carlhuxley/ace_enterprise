"""
GoRunner — PodmanRunner variant for the Go TDD harness.

Overrides send_pulse() to run `go vet` + `go test` (instead of pytest) and
gosec (instead of Bandit) for static security scanning, parsing gosec's JSON
output into the shared PulseResult fields. Also captures `gofmt`'s
reformatted output (read-only-workspace-safe: gofmt without -w only reads
the file and prints to stdout) so GoLanguagePod's REFACTOR phase can apply
real formatting without needing write access inside the container.
"""
import json
import subprocess

from src.agents.podman_orchestrator import PulseResult
from src.agents.podman_runner import PodmanRunner

_GO_BIN = "go"
_GOFMT_BIN = "gofmt"
_GOSEC_BIN = "gosec"
_REMOTE_WS = "/workspace"

_WORKSPACE_GO_MOD = "module pulse\n\ngo 1.23\n"

# gosec's own HIGH/MEDIUM/LOW severities are trusted as-is, except this rule,
# escalated from gosec's default MEDIUM to HIGH to match the cross-language
# gate for command injection (Bandit B602 for Python, eslint-plugin-security's
# detect-child-process for TypeScript).
_ESCALATE_TO_HIGH = frozenset({"G204"})  # "Subprocess launched with variable"


class GoRunner(PodmanRunner):
    """PodmanRunner pre-configured for the Go harness image.

    Defaults to more CPU/memory than Python/TypeScript (0.5 cpus / 256m
    there): fractional CFS CPU quotas hit the Go toolchain's runtime
    scheduler much harder than Python or Node's, and the first `go
    vet`/`go test` in a fresh container compiles a chunk of the standard
    library from an empty GOCACHE. Confirmed live -- at 0.5 cpus the first
    call hung indefinitely (>60s, negligible actual CPU-seconds consumed,
    i.e. blocked on scheduling, not doing real work); at 2 cpus/1g it
    completes in ~13s. GOCACHE lives on the container's tmpfs /tmp and
    persists for the container's lifetime (one persistent container per
    session, matching PodmanRunner), so this cold-start cost is paid once
    per session, not once per pulse -- subsequent pulses reuse the warmed
    cache and take well under a second.
    """

    def __init__(
        self,
        container_name: str | None = None,
        cpus: str = "2",
        memory: str = "1g",
        test_timeout: int = 10,
    ) -> None:
        super().__init__(
            image="localhost/ace-go-harness:latest",
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

        (self._host_ws / "go.mod").write_text(_WORKSPACE_GO_MOD)
        for name, content in files.items():
            (self._host_ws / name).write_text(content)

        # 60s floor comfortably covers the one-time cold-GOCACHE first pulse
        # of a session (~13s observed at cpus=2/memory=1g); subsequent
        # pulses in the same session reuse the warmed cache and are fast.
        _timeout = max(60, self._test_timeout * 6)

        vet_proc = subprocess.run(
            ["podman", "exec", "--workdir", _REMOTE_WS, self._name, _GO_BIN, "vet", "./..."],
            capture_output=True, text=True, timeout=_timeout,
        )
        test_proc = subprocess.run(
            [
                "podman", "exec", "--workdir", _REMOTE_WS, self._name,
                _GO_BIN, "test", "./...",
            ],
            capture_output=True, text=True, timeout=_timeout,
        )

        # gofmt without -w only reads the file and prints the reformatted
        # source to stdout — safe against the read-only workspace mount, and
        # semantically inert (gofmt never changes program behavior, only
        # whitespace/style), so the caller can commit its output without
        # re-verifying vet/test against the reformatted version.
        formatted: dict[str, str] = {}
        for name in files:
            if not name.endswith(".go"):
                continue
            fmt_proc = subprocess.run(
                ["podman", "exec", "--workdir", _REMOTE_WS, self._name, _GOFMT_BIN, name],
                capture_output=True, text=True, timeout=_timeout,
            )
            if fmt_proc.returncode == 0 and fmt_proc.stdout:
                formatted[name] = fmt_proc.stdout

        gosec_proc = subprocess.run(
            [
                "podman", "exec", "--workdir", _REMOTE_WS, self._name,
                _GOSEC_BIN, "-fmt=json", "./...",
            ],
            capture_output=True, text=True, timeout=_timeout,
        )
        gosec_output = gosec_proc.stdout or gosec_proc.stderr
        high, medium, low = _parse_gosec(gosec_output)

        passed = vet_proc.returncode == 0 and test_proc.returncode == 0
        stdout = test_proc.stdout
        if vet_proc.returncode != 0:
            stdout = f"go vet failed:\n{vet_proc.stdout}\n\n{stdout}"
        stderr = "\n".join(s for s in (vet_proc.stderr, test_proc.stderr) if s)

        h_executed = self._compute_workspace_hash(list(files.keys()))

        return PulseResult(
            exit_code=0 if passed else 1,
            stdout=stdout,
            stderr=stderr,
            bandit_output=gosec_output,
            bandit_high=high,
            bandit_medium=medium,
            bandit_low=low,
            bandit_clean=high == 0,
            h_executed=h_executed,
            formatted_files=formatted or None,
        )


def _parse_gosec(raw: str) -> tuple[int, int, int]:
    """Parse gosec -fmt=json output. Returns (high, medium, low) counts."""
    high = medium = low = 0
    try:
        data = json.loads(raw)
        for issue in data.get("Issues", []):
            severity = str(issue.get("severity", "")).upper()
            rule_id = issue.get("rule_id", "")
            if rule_id in _ESCALATE_TO_HIGH or severity == "HIGH":
                high += 1
            elif severity == "MEDIUM":
                medium += 1
            elif severity == "LOW":
                low += 1
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return high, medium, low
