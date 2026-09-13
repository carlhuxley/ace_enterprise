"""Tests for CharacterizationTestGenerator (ace migrate pre-pass).

Fast tests below use fake LLM/runner doubles and exercise the retry/prune
control flow in isolation. The live section at the bottom runs the real
claude CLI + real Podman sandbox end-to-end and is skipped when either
isn't available -- same pattern test_go_language_pod.py uses.
"""
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.agents.characterization_test_generator import (
    CharacterizationError,
    CharacterizationTestGenerator,
)

_SOURCE = "def add(a, b):\n    return a + b\n"


class FakeLLM:
    """Scripted responses: first call is the draft, subsequent calls are retries."""

    def __init__(self, draft, retry_responses=None):
        self.draft = draft
        self.retry_responses = retry_responses or {}
        self.calls: list[str] = []

    def generate(self, prompt, system_prompt=None, temperature=0.0):
        self.calls.append(prompt)
        if len(self.calls) == 1:
            return {"content": self.draft}
        for name, responses in self.retry_responses.items():
            if f"function `{name}`" in prompt:
                idx = sum(1 for p in self.calls[:-1] if f"function `{name}`" in p)
                return {"content": responses[min(idx, len(responses) - 1)]}
        return {"content": "```python\ndef _unused(): pass\n```"}


class FakeRunner:
    """Runs pytest for real, locally, without a container -- validates the
    actual generated file's control flow without needing podman."""

    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def send_pulse(self, files):
        with __import__("tempfile").TemporaryDirectory() as d:
            for name, content in files.items():
                (Path(d) / name).write_text(content)
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-v", "--tb=short", d],
                capture_output=True, text=True, cwd=d,
            )
            return SimpleNamespace(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def test_all_pass_first_try(tmp_path):
    src = tmp_path / "mathutil.py"
    src.write_text(_SOURCE)
    draft = (
        "```python\n"
        "import mathutil\n\n"
        "def test_add_two_positive_numbers():\n"
        "    assert mathutil.add(2, 3) == 5\n\n"
        "def test_add_negative_numbers():\n"
        "    assert mathutil.add(-1, -1) == -2\n"
        "```"
    )
    gen = CharacterizationTestGenerator(llm_client=FakeLLM(draft), runner=FakeRunner())
    result = gen.generate(src, min_core_passed=1)

    assert set(result.passed_tests) == {"test_add_two_positive_numbers", "test_add_negative_numbers"}
    assert result.pruned_tests == []
    assert "AUTO-CHARACTERIZED" in result.test_code
    assert "@pytest.mark.auto_characterized" in result.test_code


def test_one_test_wrong_gets_retried_then_fixed(tmp_path):
    src = tmp_path / "mathutil2.py"
    src.write_text(_SOURCE)
    draft = (
        "```python\n"
        "import mathutil2\n\n"
        "def test_add_correct():\n"
        "    assert mathutil2.add(2, 3) == 5\n\n"
        "def test_add_wrong_initially():\n"
        "    assert mathutil2.add(1, 1) == 99\n"
        "```"
    )
    fixed = "```python\ndef test_add_wrong_initially():\n    assert mathutil2.add(1, 1) == 2\n```"
    llm = FakeLLM(draft, retry_responses={"test_add_wrong_initially": [fixed]})
    gen = CharacterizationTestGenerator(llm_client=llm, runner=FakeRunner())
    result = gen.generate(src, min_core_passed=1, max_retries_per_test=3)

    assert set(result.passed_tests) == {"test_add_correct", "test_add_wrong_initially"}
    assert result.pruned_tests == []
    assert result.retry_counts["test_add_wrong_initially"] == 1


def test_stubborn_test_pruned_when_baseline_sufficient(tmp_path):
    src = tmp_path / "mathutil3.py"
    src.write_text(_SOURCE)
    draft = (
        "```python\n"
        "import mathutil3\n\n"
        "def test_add_correct():\n"
        "    assert mathutil3.add(2, 3) == 5\n\n"
        "def test_never_right():\n"
        "    assert mathutil3.add(1, 1) == 999\n"
        "```"
    )
    still_wrong = "```python\ndef test_never_right():\n    assert mathutil3.add(1, 1) == 888\n```"
    llm = FakeLLM(draft, retry_responses={"test_never_right": [still_wrong] * 5})
    gen = CharacterizationTestGenerator(llm_client=llm, runner=FakeRunner())
    result = gen.generate(src, min_core_passed=1, max_retries_per_test=3)

    assert result.passed_tests == ["test_add_correct"]
    assert result.pruned_tests == ["test_never_right"]
    assert result.retry_counts["test_never_right"] == 3


def test_hard_abort_when_pruning_would_drop_below_min_core(tmp_path):
    src = tmp_path / "mathutil4.py"
    src.write_text(_SOURCE)
    draft = (
        "```python\n"
        "import mathutil4\n\n"
        "def test_never_right_either():\n"
        "    assert mathutil4.add(1, 1) == 999\n"
        "```"
    )
    still_wrong = "```python\ndef test_never_right_either():\n    assert mathutil4.add(1, 1) == 888\n```"
    llm = FakeLLM(draft, retry_responses={"test_never_right_either": [still_wrong] * 5})
    gen = CharacterizationTestGenerator(llm_client=llm, runner=FakeRunner())

    with pytest.raises(CharacterizationError):
        gen.generate(src, min_core_passed=1, max_retries_per_test=3)


def test_empty_draft_raises_immediately(tmp_path):
    src = tmp_path / "mathutil5.py"
    src.write_text(_SOURCE)
    gen = CharacterizationTestGenerator(llm_client=FakeLLM("```python\nimport mathutil5\n```"), runner=FakeRunner())

    with pytest.raises(CharacterizationError):
        gen.generate(src)


def test_audit_event_emitted_on_success(tmp_path):
    from unittest.mock import MagicMock

    src = tmp_path / "mathutil6.py"
    src.write_text(_SOURCE)
    draft = (
        "```python\n"
        "import mathutil6\n\n"
        "def test_add_correct():\n"
        "    assert mathutil6.add(2, 3) == 5\n"
        "```"
    )
    audit = MagicMock()
    gen = CharacterizationTestGenerator(llm_client=FakeLLM(draft), runner=FakeRunner(), audit_client=audit)
    gen.generate(src, min_core_passed=1)

    from src.audit.schemas import AuditEventType
    audit.emit_simple.assert_called_once()
    args, kwargs = audit.emit_simple.call_args
    assert args[0] == AuditEventType.CHARACTERIZATION_TEST_GENERATED


# ---------------------------------------------------------------------------
# Integration: real Podman container, real claude CLI
# ---------------------------------------------------------------------------

skip_no_podman = pytest.mark.skipif(shutil.which("podman") is None, reason="podman not in PATH")
skip_no_claude = pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not in PATH")


@skip_no_podman
@skip_no_claude
def test_live_characterization_and_extraction_handoff(tmp_path):
    """End-to-end: real ClaudeCliClient + real PodmanRunner produce a passing
    characterization suite for untested code, and GherkinExtractionAgent
    consumes it directly, tagging every resulting scenario."""
    from src.agents.gherkin_extraction_agent import GherkinExtractionAgent
    from src.agents.podman_runner import PodmanRunner
    from src.utils.claude_cli_client import ClaudeCliClient

    src = tmp_path / "counter.py"
    src.write_text(
        "class Counter:\n"
        "    def __init__(self):\n"
        "        self.count = 0\n\n"
        "    def increment(self, by=1):\n"
        "        self.count += by\n"
        "        return self.count\n"
    )

    gen = CharacterizationTestGenerator(
        llm_client=ClaudeCliClient(model="haiku"),
        runner=PodmanRunner(container_name="char_gen_test_live"),
    )
    result = gen.generate(src, min_core_passed=1)
    assert result.passed_tests
    assert not result.pruned_tests or len(result.passed_tests) >= 1

    test_path = tmp_path / "test_counter_characterized.py"
    test_path.write_text(result.test_code)

    extraction = GherkinExtractionAgent().extract_from_codebase(
        code_path=src, test_path=test_path, feature_name="Counter"
    )
    assert len(extraction.feature.scenarios) == len(result.passed_tests)
    assert all(scenario.tags == ["@auto-characterized"] for scenario in extraction.feature.scenarios)
