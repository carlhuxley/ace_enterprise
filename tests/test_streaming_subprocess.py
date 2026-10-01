"""Tests for src/agents/podman_runner.py's _run_streaming() helper (issue
#77): a Popen-based subprocess.run(capture_output=True, text=True)
equivalent that additionally broadcasts one ExecutionStreamEvent("chunk")
per line of stdout/stderr as it's produced.

No podman needed -- these exercise _run_streaming directly against real
local subprocesses (plain `python -c ...`), not the containerized harness.
"""
import subprocess
import sys
import time
from unittest.mock import patch

import pytest

from src.agents.podman_runner import _run_streaming
from src.ui.broadcaster import set_current_phase


@pytest.fixture(autouse=True)
def _reset_phase():
    set_current_phase(None)
    yield
    set_current_phase(None)


def test_captures_stdout_and_stderr_like_subprocess_run():
    result = _run_streaming([
        sys.executable, "-c",
        "import sys; print('to stdout'); print('to stderr', file=sys.stderr)",
    ])
    assert result.returncode == 0
    assert "to stdout" in result.stdout
    assert "to stderr" in result.stderr


def test_nonzero_exit_code_is_preserved():
    result = _run_streaming([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert result.returncode == 3


def test_no_phase_set_broadcasts_nothing():
    with patch("src.agents.podman_runner.broadcast_event") as mock_broadcast:
        _run_streaming([sys.executable, "-c", "print('line one')"])
    mock_broadcast.assert_not_called()


def test_one_chunk_event_broadcast_per_line_when_phase_is_set():
    set_current_phase("GREEN")
    with patch("src.agents.podman_runner.broadcast_event") as mock_broadcast:
        _run_streaming([
            sys.executable, "-c",
            "print('line one'); print('line two'); print('line three')",
        ])

    chunks = [call.args[0] for call in mock_broadcast.call_args_list]
    assert [c.stdout_chunk for c in chunks] == ["line one", "line two", "line three"]
    assert all(c.phase == "GREEN" and c.status == "chunk" for c in chunks)


def test_timeout_raises_and_kills_the_process():
    with pytest.raises(subprocess.TimeoutExpired):
        _run_streaming([sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.3)
    # No hang, no zombie left blocking -- _run_streaming's own proc.wait()
    # after kill() already reaped it; a second immediate call must not be
    # blocked by anything left over from the first.
    result = _run_streaming([sys.executable, "-c", "print('still works')"])
    assert "still works" in result.stdout


def test_concurrent_stdout_and_stderr_draining_does_not_deadlock():
    # The regression this helper exists to fix: writing enough to BOTH
    # stdout and stderr to exceed a typical OS pipe buffer (64KB) would hang
    # forever under a naive sequential .stdout.read() then .stderr.read(),
    # since the child blocks writing to whichever pipe fills up first while
    # nothing drains it. Bounded wall-clock time proves both are drained
    # concurrently, not sequentially.
    code = (
        "import sys\n"
        "chunk = 'x' * 1000 + chr(10)\n"
        "for _ in range(100):\n"
        "    sys.stdout.write(chunk)\n"
        "    sys.stderr.write(chunk)\n"
        "sys.stdout.flush(); sys.stderr.flush()\n"
    )
    start = time.monotonic()
    result = _run_streaming([sys.executable, "-c", code], timeout=10)
    elapsed = time.monotonic() - start

    assert result.returncode == 0
    assert elapsed < 5, "likely deadlocked on an undrained pipe"
    assert len(result.stdout) > 100_000
    assert len(result.stderr) > 100_000
