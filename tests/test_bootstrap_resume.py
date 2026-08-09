"""Tests for bootstrap resume/verification logic and the credit-exhaustion
circuit breaker (ace_enterprise-ykl, ace_enterprise-wki)."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from bootstrap.audit_log import BootstrapAuditLog
from bootstrap.orchestrate import (
    BootstrapAbortError,
    _contract_synth_path,
    _resume_decision,
)
from src.utils.llm_client import LLMQuotaExhaustedError


@pytest.fixture
def audit_path(tmp_path):
    return tmp_path / "audit.jsonl"


@pytest.fixture
def log(audit_path):
    return BootstrapAuditLog(audit_path)


@pytest.fixture
def feature_file(tmp_path):
    f = tmp_path / "widget.feature"
    f.write_text("Feature: widget\n")
    return f


# ---------------------------------------------------------------------------
# _resume_decision
# ---------------------------------------------------------------------------

def test_fresh_when_out_dir_missing(tmp_path, feature_file):
    out_dir = tmp_path / "out" / "widget"
    action, existing, _, recorded = _resume_decision(out_dir, feature_file, "*.py", force=False)
    assert action == "fresh"
    assert existing == []
    assert recorded is None


def test_fresh_when_out_dir_empty(tmp_path, feature_file):
    out_dir = tmp_path / "out" / "widget"
    out_dir.mkdir(parents=True)
    action, existing, _, _ = _resume_decision(out_dir, feature_file, "*.py", force=False)
    assert action == "fresh"


def test_force_always_fresh_even_with_verified_marker(tmp_path, feature_file):
    out_dir = tmp_path / "out" / "widget"
    out_dir.mkdir(parents=True)
    (out_dir / "widget.py").write_text("x = 1\n")
    (out_dir / ".spec.sha256").write_text(BootstrapAuditLog.sha256(feature_file))
    action, _, _, _ = _resume_decision(out_dir, feature_file, "*.py", force=True)
    assert action == "fresh"


def test_unverified_when_output_present_but_no_marker(tmp_path, feature_file):
    """The core bug: output files from a killed run must not be trusted."""
    out_dir = tmp_path / "out" / "widget"
    out_dir.mkdir(parents=True)
    (out_dir / "widget.py").write_text("x = 1\n")
    action, existing, _, recorded = _resume_decision(out_dir, feature_file, "*.py", force=False)
    assert action == "unverified"
    assert len(existing) == 1
    assert recorded is None


def test_cached_when_marker_matches_current_spec(tmp_path, feature_file):
    out_dir = tmp_path / "out" / "widget"
    out_dir.mkdir(parents=True)
    (out_dir / "widget.py").write_text("x = 1\n")
    (out_dir / ".spec.sha256").write_text(BootstrapAuditLog.sha256(feature_file))
    action, existing, current, recorded = _resume_decision(out_dir, feature_file, "*.py", force=False)
    assert action == "cached"
    assert len(existing) == 1
    assert recorded == current


def test_cache_bust_when_marker_present_but_spec_changed(tmp_path, feature_file):
    out_dir = tmp_path / "out" / "widget"
    out_dir.mkdir(parents=True)
    (out_dir / "widget.py").write_text("x = 1\n")
    (out_dir / ".spec.sha256").write_text("stale-hash-from-a-different-spec")
    action, existing, current, recorded = _resume_decision(out_dir, feature_file, "*.py", force=False)
    assert action == "cache_bust"
    assert recorded == "stale-hash-from-a-different-spec"
    assert current != recorded


def test_glob_pattern_is_respected(tmp_path, feature_file):
    """A .ts-glob loop shouldn't be tricked by stray .py files, and vice versa."""
    out_dir = tmp_path / "out" / "widget"
    out_dir.mkdir(parents=True)
    (out_dir / "widget.py").write_text("x = 1\n")
    action, existing, _, _ = _resume_decision(out_dir, feature_file, "*.ts", force=False)
    assert action == "fresh"
    assert existing == []


# ---------------------------------------------------------------------------
# Credit-exhaustion circuit breaker: _contract_synth_path is the cheapest of
# the three synthesis loops to exercise end-to-end (no Podman/playbook deps).
# ---------------------------------------------------------------------------

def _write_contract(tmp_path, name: str, module: str) -> Path:
    source = tmp_path / f"{module}.py"
    source.write_text(f"def {module}(): pass\n")
    contract = tmp_path / f"{name}.contract.yml"
    contract.write_text(f"module: {module}\nsource_file: {source}\n")
    return contract


def test_quota_exhausted_aborts_run_without_processing_remaining_modules(tmp_path, log, audit_path):
    oss_dir = tmp_path / "oss"
    oss_dir.mkdir()
    contract_a = _write_contract(tmp_path, "a", "module_a")
    contract_b = _write_contract(tmp_path, "b", "module_b")

    calls = []

    def fake_generate(self, prompt, **kwargs):
        calls.append(prompt)
        raise LLMQuotaExhaustedError("OpenRouter quota/credit exhausted (status=402): out of credits")

    with patch("src.utils.llm_client.LLMClient.generate", fake_generate):
        with pytest.raises(BootstrapAbortError):
            _contract_synth_path([contract_a, contract_b], oss_dir, log, force=False)

    # Circuit breaker: must stop after the first failure, not grind through both.
    assert len(calls) == 1

    import json
    events = [
        json.loads(line)["event"]
        for line in audit_path.read_text().splitlines()
        if line.strip()
    ]
    assert "RUN_ABORT" in events


def test_non_quota_error_does_not_abort_and_continues_to_next_module(tmp_path, log):
    """Sanity check the fix is scoped to quota errors, not all failures."""
    oss_dir = tmp_path / "oss"
    oss_dir.mkdir()
    contract_a = _write_contract(tmp_path, "a", "module_a")
    contract_b = _write_contract(tmp_path, "b", "module_b")

    calls = []

    def fake_generate(self, prompt, **kwargs):
        calls.append(prompt)
        raise RuntimeError("transient LLM hiccup")

    with patch("src.utils.llm_client.LLMClient.generate", fake_generate):
        passed, failed = _contract_synth_path([contract_a, contract_b], oss_dir, log, force=False)

    # Both modules attempted — no abort for an ordinary (non-quota) failure.
    assert len(calls) == 2
