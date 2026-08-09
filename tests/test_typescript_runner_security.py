"""Tests for TypeScriptRunner's static security scan (ace_enterprise-85u).

Integration tests only — no unit-mockable seam for the eslint subprocess call,
and no TS-runner test file existed before this (the harness was previously
untested beyond the bootstrap .feature file). Skipped when podman is absent.
"""
import shutil

import pytest

from src.agents.podman_orchestrator import PodmanOrchestrator
from src.agents.typescript_runner import TypeScriptRunner, _parse_eslint

skip_no_podman = pytest.mark.skipif(
    shutil.which("podman") is None,
    reason="podman not in PATH",
)


# ---------------------------------------------------------------------------
# Unit: _parse_eslint
# ---------------------------------------------------------------------------

def test_parse_eslint_empty_results():
    high, medium, raw = _parse_eslint("[]")
    assert high == 0
    assert medium == 0


def test_parse_eslint_counts_error_as_high():
    raw = '[{"messages":[{"severity":2,"ruleId":"security/detect-child-process"}]}]'
    high, medium, _ = _parse_eslint(raw)
    assert high == 1
    assert medium == 0


def test_parse_eslint_counts_warn_as_medium():
    raw = '[{"messages":[{"severity":1,"ruleId":"security/detect-object-injection"}]}]'
    high, medium, _ = _parse_eslint(raw)
    assert high == 0
    assert medium == 1


def test_parse_eslint_mixed_severities_across_files():
    raw = (
        '[{"messages":[{"severity":2},{"severity":1}]},'
        '{"messages":[{"severity":2}]}]'
    )
    high, medium, _ = _parse_eslint(raw)
    assert high == 2
    assert medium == 1


def test_parse_eslint_malformed_json_does_not_crash():
    high, medium, raw = _parse_eslint("not json")
    assert high == 0
    assert medium == 0
    assert raw == "not json"


def test_parse_eslint_empty_string_does_not_crash():
    high, medium, _ = _parse_eslint("")
    assert high == 0
    assert medium == 0


# ---------------------------------------------------------------------------
# Integration: real container, real eslint
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ts_runner():
    if shutil.which("podman") is None:
        pytest.skip("podman not in PATH")
    runner = TypeScriptRunner(container_name="ts_security_test_session")
    runner.start()
    yield runner
    runner.stop()


_SAFE_TS = {
    "add.ts": "export function add(a: number, b: number): number { return a + b; }\n",
    "add.test.ts": (
        "import { add } from './add';\n"
        "import { test, expect } from 'vitest';\n"
        "test('add', () => { expect(add(1, 2)).toBe(3); });\n"
    ),
}

_VULN_TS = {
    "runner.ts": (
        "import { exec } from 'child_process';\n"
        "export function runCmd(userInput: string): void {\n"
        "  exec(userInput);\n"
        "}\n"
    ),
    "runner.test.ts": (
        "import { runCmd } from './runner';\n"
        "import { test, expect } from 'vitest';\n"
        "test('runs', () => { expect(typeof runCmd).toBe('function'); });\n"
    ),
}


@skip_no_podman
def test_safe_code_has_no_high_findings(ts_runner):
    result = ts_runner.send_pulse(_SAFE_TS)
    assert result.bandit_high == 0
    assert result.bandit_clean is True


@skip_no_podman
def test_child_process_exec_flagged_high(ts_runner):
    result = ts_runner.send_pulse(_VULN_TS)
    assert result.bandit_high >= 1
    assert result.bandit_clean is False
    assert "detect-child-process" in result.bandit_output


@skip_no_podman
def test_orchestrator_pulse_blocks_vulnerable_code(ts_runner):
    """Full safety sandwich: HIGH eslint-security finding must fail the pulse
    even though vitest itself would pass (the test only checks the function
    exists, not what it does)."""
    orchestrator = PodmanOrchestrator(runner=ts_runner)
    result = orchestrator.pulse(_VULN_TS)
    assert result.passed is False
    assert result.error is not None and result.error.startswith("Security gate:")


@skip_no_podman
def test_orchestrator_pulse_allows_safe_code(ts_runner):
    orchestrator = PodmanOrchestrator(runner=ts_runner)
    result = orchestrator.pulse(_SAFE_TS)
    assert result.passed is True
