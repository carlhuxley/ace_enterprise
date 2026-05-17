"""
Hazardous Pipeline — Milestone 1: Malformed HTML Parsing.

Verifies that the safety sandwich (ImportFilter → Bandit → container + timeout)
handles an HTML parsing feature correctly:

  - stdlib html.parser is allowed and runs safely in the container
  - An implementation that smuggles 'socket' is caught by ImportFilter
    before the container is even touched
  - Deeply malformed / pathologically nested HTML does not hang: the
    10-second per-test timeout kills it inside the container
"""
import pytest

from src.agents.import_filter import ForbiddenImportError, ImportFilter
from src.agents.podman_orchestrator import PodmanOrchestrator

# ---------------------------------------------------------------------------
# Representative LLM outputs for this feature
# ---------------------------------------------------------------------------

SAFE_IMPL = """\
import html.parser


class _TextExtractor(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_data(self, data):
        text = data.strip()
        if text:
            self._parts.append(text)

    def get_text(self):
        return " ".join(self._parts)


def parse_html(html_string: str) -> str:
    parser = _TextExtractor()
    parser.feed(html_string)
    return parser.get_text()
"""

FORBIDDEN_IMPL = """\
import socket
import html.parser


def parse_html(html_string: str) -> str:
    # pretend to verify the string via an internal service
    _ = socket.gethostname()
    parser = html.parser.HTMLParser()
    return html_string
"""

TEST_FILE = """\
from html_parser import parse_html


def test_simple_paragraph():
    assert parse_html("<p>Hello World</p>") == "Hello World"


def test_unclosed_tag():
    result = parse_html("<p>Unclosed paragraph")
    assert "Unclosed paragraph" in result


def test_nested_tags():
    assert parse_html("<div><b>bold</b></div>") == "bold"


def test_empty_string():
    assert parse_html("") == ""


def test_html_entities():
    result = parse_html("<p>caf&eacute;</p>")
    assert "caf" in result
"""

DEEP_NESTING_TEST = """\
from html_parser import parse_html


def test_deeply_nested_html_completes():
    html = "<div>" * 500 + "core" + "</div>" * 500
    result = parse_html(html)
    assert "core" in result


def test_very_long_malformed_string():
    html = "<p>" * 1000 + "text"   # no closing tags
    result = parse_html(html)
    assert "text" in result
"""


# ---------------------------------------------------------------------------
# Unit: ImportFilter (no container)
# ---------------------------------------------------------------------------

def test_import_filter_permits_html_parser():
    ImportFilter().check(SAFE_IMPL)   # must not raise


def test_import_filter_blocks_socket_in_html_code():
    with pytest.raises(ForbiddenImportError, match="socket"):
        ImportFilter().check(FORBIDDEN_IMPL)


# ---------------------------------------------------------------------------
# Integration: full safety sandwich via shared container
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    __import__("shutil").which("podman") is None,
    reason="podman not in PATH",
)
class TestMilestone1Integration:

    def test_safe_impl_passes_in_container(self, shared_podman_runner, tmp_path):
        orchestrator = PodmanOrchestrator(
            runner=shared_podman_runner,
            work_dir=tmp_path / "work",
        )
        result = orchestrator.pulse({
            "html_parser.py": SAFE_IMPL,
            "test_html_parser.py": TEST_FILE,
        })
        assert result.passed, f"Expected pass; output:\n{result.output}\n{result.error}"

    def test_bandit_accepts_safe_impl(self, shared_podman_runner, tmp_path):
        orchestrator = PodmanOrchestrator(
            runner=shared_podman_runner,
            work_dir=tmp_path / "work",
        )
        result = orchestrator.pulse({
            "html_parser.py": SAFE_IMPL,
            "test_html_parser.py": TEST_FILE,
        })
        assert result.error is None or not result.error.startswith("Bandit gate:"), (
            f"Bandit blocked safe code: {result.error}"
        )

    def test_deeply_nested_html_completes_within_timeout(self, shared_podman_runner, tmp_path):
        """stdlib html.parser must finish well within the 10 s per-test timeout."""
        orchestrator = PodmanOrchestrator(
            runner=shared_podman_runner,
            work_dir=tmp_path / "work",
        )
        result = orchestrator.pulse({
            "html_parser.py": SAFE_IMPL,
            "test_html_parser.py": DEEP_NESTING_TEST,
        })
        assert result.passed, (
            f"HTML parsing timed out or failed:\n{result.output}\n{result.error}"
        )
