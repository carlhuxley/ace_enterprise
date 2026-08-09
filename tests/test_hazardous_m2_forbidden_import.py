"""
Hazardous Pipeline — Milestone 2: Forbidden Import Trap.

Scenario: a 'file ingestor' feature whose obvious implementation uses os or
subprocess. Verifies that every layer of the safety sandwich responds
correctly:

  Unit layer
    - ImportFilter blocks os / subprocess / os.path; permits pathlib
    - _is_abort() recognises the ForbiddenImport prefix
    - TDDCycleRunner stops retrying after a GREEN abort

  Pod layer (mock worker + spy orchestrator — no Podman)
    - When the LLM returns forbidden code, PythonLanguagePod never calls
      orchestrator.pulse(), so the container is never touched

  Container layer (real Podman)
    - The safe pathlib alternative passes the full safety sandwich
"""
import shutil

import pytest

from src.agents.import_filter import ForbiddenImportError, ImportFilter
from src.agents.language_pod import PhaseResult, PodSpec
from src.agents.podman_orchestrator import PodmanOrchestrator
from src.agents.python_language_pod import PythonLanguagePod
from src.agents.tdd_cycle_runner import CycleResult, TDDCycleRunner, _is_abort

# ---------------------------------------------------------------------------
# Representative LLM outputs for the 'ingest_files' feature
# ---------------------------------------------------------------------------

SAFE_IMPL = """\
from pathlib import Path


def ingest_files(directory: str) -> list[str]:
    return [p.read_text() for p in Path(directory).glob("*.txt")]
"""

FORBIDDEN_OS_IMPL = """\
import os


def ingest_files(directory: str) -> list[str]:
    contents = []
    for fname in os.listdir(directory):
        if fname.endswith(".txt"):
            with open(os.path.join(directory, fname)) as fh:
                contents.append(fh.read())
    return contents
"""

FORBIDDEN_SUBPROCESS_IMPL = """\
import subprocess


def ingest_files(directory: str) -> list[str]:
    out = subprocess.run(
        ["find", directory, "-name", "*.txt"],
        capture_output=True,
        text=True,
    ).stdout.strip().splitlines()
    return [open(f).read() for f in out if f]
"""

TEST_FILE = """\
import tempfile
from pathlib import Path
from ingest_files import ingest_files


def test_reads_txt_files():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "a.txt").write_text("hello")
        (Path(d) / "b.txt").write_text("world")
        result = ingest_files(d)
        assert "hello" in result
        assert "world" in result


def test_ignores_non_txt():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "a.txt").write_text("text")
        (Path(d) / "b.csv").write_text("csv")
        result = ingest_files(d)
        assert len(result) == 1


def test_empty_directory():
    with tempfile.TemporaryDirectory() as d:
        assert ingest_files(d) == []
"""


# ---------------------------------------------------------------------------
# Unit: ImportFilter
# ---------------------------------------------------------------------------

def test_import_filter_blocks_os():
    with pytest.raises(ForbiddenImportError, match="os"):
        ImportFilter().check(FORBIDDEN_OS_IMPL)


def test_import_filter_blocks_subprocess():
    with pytest.raises(ForbiddenImportError, match="subprocess"):
        ImportFilter().check(FORBIDDEN_SUBPROCESS_IMPL)


def test_import_filter_blocks_os_nested_import():
    with pytest.raises(ForbiddenImportError, match="os"):
        ImportFilter().check("import os.path\nprint(os.path.join('a', 'b'))")


def test_import_filter_permits_pathlib():
    ImportFilter().check(SAFE_IMPL)   # must not raise


# ---------------------------------------------------------------------------
# Unit: _is_abort
# ---------------------------------------------------------------------------

def test_is_abort_true_for_forbidden_import():
    result = PhaseResult(passed=False, output="", error="ForbiddenImport: Forbidden import: os")
    assert _is_abort(result) is True


def test_is_abort_false_for_ordinary_failure():
    result = PhaseResult(passed=False, output="AssertionError", error=None)
    assert _is_abort(result) is False


def test_is_abort_false_when_error_is_none():
    assert _is_abort(PhaseResult(passed=True, output="ok", error=None)) is False


# ---------------------------------------------------------------------------
# Unit: TDDCycleRunner abort path
# ---------------------------------------------------------------------------

class _RedPassGreenForbiddenPod:
    """Pod whose GREEN always returns a ForbiddenImport abort."""

    def run_red(self, spec):
        return PhaseResult(passed=False, output="test fails as expected", error=None)

    def run_green(self, spec):
        return PhaseResult(
            passed=False,
            output="",
            error="ForbiddenImport: Forbidden import: os",
        )

    def run_refactor(self, spec):  # pragma: no cover
        return PhaseResult(passed=True, output="", error=None)

    def token_usage(self):
        return []


def test_cycle_runner_aborts_on_forbidden_green():
    pod = _RedPassGreenForbiddenPod()
    runner = TDDCycleRunner(pod, max_green_attempts=3)
    spec = PodSpec(
        feature_requirement="ingest files",
        test_file=__import__("pathlib").Path("/tmp/test_ingest.py"),
        implementation_file=__import__("pathlib").Path("/tmp/ingest_files.py"),
        cycle_number=1,
    )
    result = runner.run(spec)

    assert result.success is False
    assert result.green_attempts == 1, "must not retry after ForbiddenImport abort"
    assert "ForbiddenImport" in (result.error or "")


# ---------------------------------------------------------------------------
# Pod layer: mock worker + spy orchestrator (no Podman)
# ---------------------------------------------------------------------------

class _MockLLMClient:
    def generate(self, *args, **kwargs):
        return {"prompt_tokens": 0, "completion_tokens": 0, "tokens_used": 0, "content": ""}


class _MockWorker:
    def __init__(self, impl_code: str):
        self._impl = impl_code
        self.llm_client = _MockLLMClient()

    def generate_implementation(self, spec, **kwargs):
        return self._impl

    def generate_test(self, spec, **kwargs):
        return ""


class _SpyOrchestrator:
    def __init__(self):
        self.pulse_calls = 0

    def pulse(self, files):
        self.pulse_calls += 1
        return PhaseResult(passed=True, output="ok", error=None)


def _make_spec(tmp_path):
    return PodSpec(
        feature_requirement="ingest files from a directory",
        test_file=tmp_path / "test_ingest.py",
        implementation_file=tmp_path / "ingest_files.py",
        cycle_number=1,
    )


def test_forbidden_impl_never_reaches_container(tmp_path):
    worker = _MockWorker(FORBIDDEN_OS_IMPL)
    spy = _SpyOrchestrator()
    pod = PythonLanguagePod(worker, tmp_path, spy)

    # Pre-write a test file so run_green can read it
    spec = _make_spec(tmp_path)
    spec.test_file.write_text(TEST_FILE)

    result = pod.run_green(spec)

    assert result.error is not None and result.error.startswith("ForbiddenImport:"), (
        f"Expected ForbiddenImport error, got: {result.error}"
    )
    assert spy.pulse_calls == 0, "container must not be invoked when import is forbidden"


def test_safe_impl_reaches_container_via_spy(tmp_path):
    worker = _MockWorker(SAFE_IMPL)
    spy = _SpyOrchestrator()
    pod = PythonLanguagePod(worker, tmp_path, spy)

    spec = _make_spec(tmp_path)
    spec.test_file.write_text(TEST_FILE)

    pod.run_green(spec)

    assert spy.pulse_calls == 1, "container must be invoked for safe implementation"


# ---------------------------------------------------------------------------
# Container layer: full safety sandwich (real Podman)
# ---------------------------------------------------------------------------

skip_no_podman = pytest.mark.skipif(
    not shutil.which("podman"),
    reason="podman not in PATH",
)


@skip_no_podman
def test_safe_pathlib_impl_passes_full_sandwich(shared_podman_runner, tmp_path):
    orchestrator = PodmanOrchestrator(
        runner=shared_podman_runner,
        work_dir=tmp_path / "work",
    )
    result = orchestrator.pulse({
        "ingest_files.py": SAFE_IMPL,
        "test_ingest_files.py": TEST_FILE,
    })
    assert result.passed, f"Expected pass:\n{result.output}\n{result.error}"
