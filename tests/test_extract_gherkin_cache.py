"""Tests for extract_features()'s content-hash caching (bootstrap/extract.py).

Regression coverage for the gap surfaced while investigating why resuming
the bootstrap pipeline wouldn't pick up today's heavily-changed source
modules: the old cache only checked "does a .feature file exist at this
path", never whether the source it was derived from had actually changed
since. A module could be rewritten entirely and a resumed run would still
silently reuse the stale spec (and, one stage downstream, skip
re-synthesis entirely via _resume_decision's now-unchanged-hash check).
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bootstrap.audit_log import BootstrapAuditLog
from bootstrap.extract import _module_key, extract_features
from src.utils.llm_client import LLMQuotaExhaustedError


def _fake_llm(content="Feature: widget\n  Scenario: it works\n"):
    client = MagicMock()
    client.model = "fake-model"
    client.generate.return_value = {"content": content}
    return client


def _src(tmp_path: Path, name: str, body: str) -> Path:
    f = tmp_path / f"{name}.py"
    f.write_text(body)
    return f


def test_fresh_extraction_calls_llm_and_writes_both_markers(tmp_path):
    src = _src(tmp_path, "widget", "def widget():\n    return 42\n" * 10)
    features_dir = tmp_path / "features"
    log = BootstrapAuditLog(tmp_path / "audit.jsonl")
    llm = _fake_llm()

    produced = extract_features([src], features_dir, log, llm_client=llm)

    assert len(produced) == 1
    assert llm.generate.call_count == 1
    feature_path = features_dir / "widget.feature"
    src_hash_path = features_dir / "widget.src.sha256"
    assert feature_path.exists()
    assert src_hash_path.exists()
    assert src_hash_path.read_text().strip() == BootstrapAuditLog.sha256(src)


def test_unchanged_source_is_cached_no_llm_call(tmp_path):
    src = _src(tmp_path, "widget", "def widget():\n    return 42\n" * 10)
    features_dir = tmp_path / "features"
    log = BootstrapAuditLog(tmp_path / "audit.jsonl")
    llm = _fake_llm()

    extract_features([src], features_dir, log, llm_client=llm)
    assert llm.generate.call_count == 1

    # Second run, same source, same llm_client -- must not call generate again.
    extract_features([src], features_dir, log, llm_client=llm)
    assert llm.generate.call_count == 1


def test_changed_source_busts_cache_and_calls_llm_again(tmp_path):
    src = _src(tmp_path, "widget", "def widget():\n    return 42\n" * 10)
    features_dir = tmp_path / "features"
    log = BootstrapAuditLog(tmp_path / "audit.jsonl")
    llm = _fake_llm()

    extract_features([src], features_dir, log, llm_client=llm)
    assert llm.generate.call_count == 1

    # Rewrite the source (like today's src/ edits) -- must re-extract.
    src.write_text("def widget():\n    return 99  # rewritten\n" * 10)

    extract_features([src], features_dir, log, llm_client=llm)
    assert llm.generate.call_count == 2

    src_hash_path = features_dir / "widget.src.sha256"
    assert src_hash_path.read_text().strip() == BootstrapAuditLog.sha256(src)


def test_feature_file_without_hash_marker_is_treated_as_stale(tmp_path):
    """Pre-existing .feature files from before this fix have no .src.sha256
    sidecar -- must be re-extracted once rather than trusted forever."""
    src = _src(tmp_path, "widget", "def widget():\n    return 42\n" * 10)
    features_dir = tmp_path / "features"
    features_dir.mkdir()
    (features_dir / "widget.feature").write_text("Feature: stale legacy spec\n")
    log = BootstrapAuditLog(tmp_path / "audit.jsonl")
    llm = _fake_llm()

    extract_features([src], features_dir, log, llm_client=llm)

    assert llm.generate.call_count == 1
    assert (features_dir / "widget.src.sha256").exists()


# ---------------------------------------------------------------------------
# _module_key -- collision-free naming (ace_enterprise real bug: schemas.py
# exists at src/audit/, src/retrieval/, and src/storage/ -- three unrelated
# modules that all used to map to the same schemas.feature and, one stage
# downstream, the same OSS output directory. Whichever synthesised last
# silently overwrote the others.)
# ---------------------------------------------------------------------------

class TestModuleKey:
    def test_qualifies_with_parent_directories(self, tmp_path):
        src_root = tmp_path / "src"
        f = src_root / "storage" / "schemas.py"
        f.parent.mkdir(parents=True)
        f.write_text("x = 1\n")
        assert _module_key(f, src_root) == "storage_schemas"

    def test_colliding_stems_get_distinct_keys(self, tmp_path):
        src_root = tmp_path / "src"
        files = {}
        for sub in ("audit", "retrieval", "storage"):
            d = src_root / sub
            d.mkdir(parents=True)
            f = d / "schemas.py"
            f.write_text(f"# {sub}\n")
            files[sub] = f

        keys = {sub: _module_key(f, src_root) for sub, f in files.items()}
        assert len(set(keys.values())) == 3  # all distinct -- the whole point
        assert keys["audit"] == "audit_schemas"
        assert keys["retrieval"] == "retrieval_schemas"
        assert keys["storage"] == "storage_schemas"

    def test_top_level_file_uses_bare_stem(self, tmp_path):
        src_root = tmp_path / "src"
        src_root.mkdir()
        f = src_root / "main.py"
        f.write_text("x = 1\n")
        assert _module_key(f, src_root) == "main"

    def test_file_outside_src_root_falls_back_to_stem(self, tmp_path):
        src_root = tmp_path / "src"
        src_root.mkdir()
        outside = tmp_path / "elsewhere" / "widget.py"
        outside.parent.mkdir()
        outside.write_text("x = 1\n")
        assert _module_key(outside, src_root) == "widget"


def test_colliding_source_files_produce_distinct_feature_files(tmp_path):
    """End-to-end: two files that share a bare stem must not clobber each
    other's .feature file (the actual bug -- src/audit/schemas.py and
    src/storage/schemas.py used to both write bootstrap/features/schemas.feature)."""
    src_root = tmp_path / "src"
    features_dir = tmp_path / "features"
    log = BootstrapAuditLog(tmp_path / "audit.jsonl")

    audit_dir = src_root / "audit"
    storage_dir = src_root / "storage"
    audit_dir.mkdir(parents=True)
    storage_dir.mkdir(parents=True)
    audit_schemas = audit_dir / "schemas.py"
    storage_schemas = storage_dir / "schemas.py"
    audit_schemas.write_text("class AuditEvent:\n    pass\n" * 10)
    storage_schemas.write_text("class Bullet:\n    pass\n" * 10)

    llm = _fake_llm()
    produced = extract_features(
        [audit_schemas, storage_schemas], features_dir, log, llm_client=llm, src_root=src_root
    )

    assert len(produced) == 2
    assert llm.generate.call_count == 2
    assert (features_dir / "audit_schemas.feature").exists()
    assert (features_dir / "storage_schemas.feature").exists()
    # Neither .src.sha256 marker was overwritten by the other's extraction.
    assert (features_dir / "audit_schemas.src.sha256").read_text().strip() \
        == BootstrapAuditLog.sha256(audit_schemas)
    assert (features_dir / "storage_schemas.src.sha256").read_text().strip() \
        == BootstrapAuditLog.sha256(storage_schemas)


# ---------------------------------------------------------------------------
# Per-file error isolation -- regression coverage for the transient failure
# that killed two live bootstrap runs: the local `claude` CLI self-updating
# mid-run leaves a few-second window where subprocess.run(["claude", ...])
# raises FileNotFoundError. A single such hiccup used to abort the entire
# Stage 1 run (no try/except around extract_features()'s LLM call at all).
# ---------------------------------------------------------------------------

class TestErrorIsolation:
    def test_transient_failure_retries_then_succeeds(self, tmp_path):
        src = _src(tmp_path, "widget", "def widget():\n    return 42\n" * 10)
        features_dir = tmp_path / "features"
        log = BootstrapAuditLog(tmp_path / "audit.jsonl")

        llm = MagicMock()
        llm.model = "fake-model"
        llm.generate.side_effect = [
            FileNotFoundError(2, "No such file or directory", "claude"),
            {"content": "Feature: widget\n  Scenario: it works\n"},
        ]

        with patch("bootstrap.extract.time.sleep"):
            produced = extract_features([src], features_dir, log, llm_client=llm)

        assert len(produced) == 1
        assert llm.generate.call_count == 2
        assert (features_dir / "widget.feature").exists()

    def test_persistent_failure_skips_file_without_crashing(self, tmp_path):
        """The whole run must survive one file failing every retry -- it
        should log GHERKIN_ERROR and move on, not raise."""
        src = _src(tmp_path, "widget", "def widget():\n    return 42\n" * 10)
        features_dir = tmp_path / "features"
        log = BootstrapAuditLog(tmp_path / "audit.jsonl")

        llm = MagicMock()
        llm.model = "fake-model"
        llm.generate.side_effect = FileNotFoundError(2, "No such file or directory", "claude")

        with patch("bootstrap.extract.time.sleep"):
            produced = extract_features([src], features_dir, log, llm_client=llm)

        assert produced == []
        assert not (features_dir / "widget.feature").exists()
        assert not (features_dir / "widget.src.sha256").exists()

    def test_persistent_failure_does_not_block_later_files(self, tmp_path):
        bad = _src(tmp_path, "bad", "def bad():\n    return 1\n" * 10)
        good = _src(tmp_path, "good", "def good():\n    return 2\n" * 10)
        features_dir = tmp_path / "features"
        log = BootstrapAuditLog(tmp_path / "audit.jsonl")

        llm = MagicMock()
        llm.model = "fake-model"
        llm.generate.side_effect = [
            FileNotFoundError(2, "No such file or directory", "claude"),
            FileNotFoundError(2, "No such file or directory", "claude"),
            FileNotFoundError(2, "No such file or directory", "claude"),
            {"content": "Feature: good\n  Scenario: it works\n"},
        ]

        with patch("bootstrap.extract.time.sleep"):
            produced = extract_features([bad, good], features_dir, log, llm_client=llm)

        assert len(produced) == 1
        assert (features_dir / "good.feature").exists()
        assert not (features_dir / "bad.feature").exists()

    def test_quota_exhausted_is_never_retried_and_aborts(self, tmp_path):
        src = _src(tmp_path, "widget", "def widget():\n    return 42\n" * 10)
        features_dir = tmp_path / "features"
        log = BootstrapAuditLog(tmp_path / "audit.jsonl")

        llm = MagicMock()
        llm.model = "fake-model"
        llm.generate.side_effect = LLMQuotaExhaustedError("out of credits")

        with patch("bootstrap.extract.time.sleep") as sleep_mock:
            with pytest.raises(LLMQuotaExhaustedError):
                extract_features([src], features_dir, log, llm_client=llm)

        assert llm.generate.call_count == 1  # never retried
        sleep_mock.assert_not_called()
