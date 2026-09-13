"""Permanent regression test for the clean-room air-gap claim: the Go
synthesis engine (GoLanguagePod, driven by PolyglotTDDRunner) never sees
literal source lines from the module being migrated -- only the abstracted
behavioral specification GherkinFeatureBridge.as_requirement() produces
(scenario names + step counts, never step text, never the raw source or
the full .feature file text -- see language_pod.py's PodSpec.gherkin_context,
which stays unset on this path by construction).

Methodology (the same one used to manually verify this live against a real
migration): wrap the real LLM client to capture every prompt verbatim, run
a real RED->GREEN->REFACTOR cycle through the real Podman sandbox, then
assert zero lines (>=15 chars, to skip trivial noise like "}" or blank
lines) of the source module appear verbatim in any captured prompt. Every
captured prompt is also dumped to tests/artifacts/clean_room_air_gap/ so
this is inspectable after the fact, not a black-box pass/fail -- open the
files directly to see exactly what the LLM received.

This is deliberately a live integration test, not a mocked unit test: the
claim being verified is "what actually gets sent over the wire to a real
model," which a scripted/mocked LLM client can't falsify or confirm.
Skipped without a real podman + a real claude CLI session, same pattern as
test_go_language_pod.py's integration section.

Known, expected, and NOT a leak: functional identifier names (e.g. an
error type both the source and the Go output might independently call
something like "MalformedPayloadError" or "SlidingWindowDeduplicator")
can recur because the Go engine invents idiomatic Go names from the
plain-English scenario description, then reuses its *own* prior output in
later prompts (RED's test code feeds GREEN's prompt) -- never because it
read the source. That's convergent naming on a generic/functional
description, not source-code copying, and this test does not (and should
not) fail on it -- it only asserts on verbatim *source lines*, not on
identifier-name overlap.
"""
import shutil
from pathlib import Path

import pytest

from src.agents.gherkin_extraction_agent import GherkinExtractionAgent
from src.agents.polyglot_pod_builder import build_all_pod_kwargs
from src.agents.polyglot_tdd_runner import PodFactory, PolyglotTDDRunner

skip_no_podman = pytest.mark.skipif(shutil.which("podman") is None, reason="podman not in PATH")
skip_no_claude = pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not in PATH")

MIN_LEAK_LINE_LEN = 15
ARTIFACTS_DIR = Path(__file__).parent / "artifacts" / "clean_room_air_gap"

# A standalone fixture module, not a copy of any real migration target --
# this test must be able to run (and be understood) independently of any
# specific customer codebase. Includes a deliberately distinctive class
# name (QuarantineLedger) and a real, slightly-unusual behavior (readmits
# a key once its window expires) so a convergent-naming false pass would
# be as easy to spot here as it was against the real migration.
_SOURCE_MODULE = '''"""A rolling-window admission ledger with no test coverage."""


class QuarantineLedger:
    """Tracks which keys have already been admitted, within a rolling window."""

    def __init__(self, window_seconds=60):
        self.window_seconds = window_seconds
        self._admitted = {}

    def admit(self, key, now):
        cutoff = now - self.window_seconds
        self._admitted = {k: t for k, t in self._admitted.items() if t >= cutoff}
        if key in self._admitted:
            return False
        self._admitted[key] = now
        return True
'''

_TEST_MODULE = '''from quarantine_ledger import QuarantineLedger


def test_admits_a_new_key():
    ledger = QuarantineLedger(window_seconds=60)
    assert ledger.admit("a", 1000.0) is True


def test_rejects_a_duplicate_key_within_window():
    ledger = QuarantineLedger(window_seconds=60)
    ledger.admit("a", 1000.0)
    assert ledger.admit("a", 1010.0) is False


def test_readmits_a_key_after_the_window_expires():
    ledger = QuarantineLedger(window_seconds=60)
    ledger.admit("a", 1000.0)
    assert ledger.admit("a", 1100.0) is True
'''


def _capture_prompts(llm_client) -> list[str]:
    """Wrap llm_client.generate to record every prompt verbatim, in call order."""
    captured: list[str] = []
    original = llm_client.generate

    def _wrapped(prompt, *args, **kwargs):
        captured.append(prompt)
        return original(prompt, *args, **kwargs)

    llm_client.generate = _wrapped
    return captured


def _verbatim_line_leaks(source_text: str, prompts: list[str], min_len: int = MIN_LEAK_LINE_LEN) -> list[str]:
    """Lines (>= min_len chars, to skip trivial noise) of source_text found
    verbatim in any captured prompt."""
    source_lines = [ln.strip() for ln in source_text.splitlines() if len(ln.strip()) >= min_len]
    haystack = "\n---PROMPT BOUNDARY---\n".join(prompts)
    return [ln for ln in source_lines if ln in haystack]


@skip_no_podman
@skip_no_claude
def test_go_synthesis_never_sees_source_lines(tmp_path):
    """Full real chain: extraction -> feature file -> PolyglotTDDRunner ->
    GoLanguagePod, every LLM prompt captured and checked against the source."""
    from src.utils.claude_cli_client import ClaudeCliClient

    source_path = tmp_path / "quarantine_ledger.py"
    source_path.write_text(_SOURCE_MODULE)
    test_path = tmp_path / "test_quarantine_ledger.py"
    test_path.write_text(_TEST_MODULE)

    extractor = GherkinExtractionAgent()
    extraction = extractor.extract_from_codebase(
        code_path=source_path, test_path=test_path, feature_name="Quarantine Ledger"
    )
    assert extraction.feature.scenarios, "fixture produced no scenarios -- test isn't exercising anything"

    feature_path = tmp_path / "quarantine_ledger.feature"
    extractor.write_gherkin_file(extraction.feature, feature_path)

    llm = ClaudeCliClient(model="haiku")
    captured_prompts = _capture_prompts(llm)

    go_out = tmp_path / "go_out"
    go_out.mkdir()
    pod_kwargs = build_all_pod_kwargs(["go"], project_root=go_out, llm_client=llm)
    runner = PolyglotTDDRunner(pod_factory=PodFactory, pod_kwargs=pod_kwargs, max_cycles=5)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    for old in ARTIFACTS_DIR.glob("prompt_*.txt"):
        old.unlink()

    try:
        runner.run_from_feature(
            feature_path=feature_path,
            languages=["go"],
            test_file=go_out / "impl_test.go",
            implementation_file=go_out / "impl.go",
        )
    finally:
        # Dumped pass or fail -- the point is that this is inspectable after
        # the fact, not a black-box pass/fail. See the module docstring.
        for i, prompt in enumerate(captured_prompts, start=1):
            (ARTIFACTS_DIR / f"prompt_{i:02d}.txt").write_text(prompt)

    assert captured_prompts, "no LLM calls were captured -- instrumentation didn't attach to the real client"

    leaks = _verbatim_line_leaks(_SOURCE_MODULE, captured_prompts)
    assert leaks == [], (
        f"Python source line(s) leaked verbatim into a Go-synthesis prompt: {leaks!r}\n"
        f"Inspect {ARTIFACTS_DIR} for the full captured prompts."
    )


def test_gherkin_context_stays_unset_on_the_polyglot_path():
    """Structural guard, not a live run: if a future change ever populates
    PodSpec.gherkin_context (full .feature file text -- WorkerAgent and
    TypeScriptWorkerAgent both put it straight into their prompts) on the
    PolyglotTDDRunner->GoLanguagePod path, the live test above would still
    likely pass by luck on any given fixture. This pins the actual
    mechanism the air gap depends on, so a regression is caught even if
    nobody happens to write a source line long/distinctive enough for the
    live test to catch that run.
    """
    import inspect

    from src.agents.polyglot_tdd_runner import PolyglotTDDRunner

    source = inspect.getsource(PolyglotTDDRunner._run_one)
    assert "gherkin_context" not in source, (
        "PolyglotTDDRunner._run_one() now references gherkin_context -- if it's being "
        "populated with the full .feature file text (or worse, source text) for the Go "
        "pod, that reopens the leak test_go_synthesis_never_sees_source_lines exists to "
        "catch. Verify what's being passed before removing this guard."
    )
