"""Tests for bootstrap/stamp.py's Apache-2.0 licensing (corrected 2026-08-09
from a stale AGPL-3.0-only stamp that didn't match this repo's own LICENSE).
"""
import json
import re
from pathlib import Path

import pytest

from bootstrap.audit_log import BootstrapAuditLog
from bootstrap.stamp import stamp_directory

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _log(tmp_path):
    return BootstrapAuditLog(tmp_path / "audit.jsonl")


class TestPythonStamping:
    def test_spdx_identifier_is_apache(self, tmp_path):
        (tmp_path / "foo.py").write_text("def foo():\n    pass\n")
        stamp_directory(tmp_path, _log(tmp_path), lang="python")
        content = (tmp_path / "foo.py").read_text()
        assert "SPDX-License-Identifier: Apache-2.0" in content

    def test_no_agpl_or_affero_text_anywhere(self, tmp_path):
        (tmp_path / "foo.py").write_text("def foo():\n    pass\n")
        stamp_directory(tmp_path, _log(tmp_path), lang="python")
        content = (tmp_path / "foo.py").read_text()
        assert "AGPL" not in content
        assert "Affero" not in content

    def test_original_content_preserved_after_header(self, tmp_path):
        (tmp_path / "foo.py").write_text("def foo():\n    pass\n")
        stamp_directory(tmp_path, _log(tmp_path), lang="python")
        assert (tmp_path / "foo.py").read_text().endswith("def foo():\n    pass\n")

    def test_file_with_existing_spdx_header_not_restamped(self, tmp_path):
        original = "# SPDX-License-Identifier: MIT\ndef foo():\n    pass\n"
        (tmp_path / "foo.py").write_text(original)
        stamp_directory(tmp_path, _log(tmp_path), lang="python")
        assert (tmp_path / "foo.py").read_text() == original

    def test_pyproject_license_field_is_apache(self, tmp_path):
        stamp_directory(tmp_path, _log(tmp_path), lang="python")
        pp = (tmp_path / "pyproject.toml").read_text()
        assert re.search(r'license\s*=\s*\{text = "Apache-2.0"\}', pp)

    def test_returns_count_of_stamped_files(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        (tmp_path / "b.py").write_text("y = 2\n")
        count = stamp_directory(tmp_path, _log(tmp_path), lang="python")
        assert count == 2


class TestTypeScriptStamping:
    def test_spdx_identifier_is_apache(self, tmp_path):
        (tmp_path / "bar.ts").write_text("export function bar(): void {}\n")
        stamp_directory(tmp_path, _log(tmp_path), lang="typescript")
        content = (tmp_path / "bar.ts").read_text()
        assert "SPDX-License-Identifier: Apache-2.0" in content
        assert "AGPL" not in content

    def test_package_json_license_field_is_apache(self, tmp_path):
        stamp_directory(tmp_path, _log(tmp_path), lang="typescript")
        pkg = json.loads((tmp_path / "package.json").read_text())
        assert pkg["license"] == "Apache-2.0"

    def test_uses_slash_slash_comment_style(self, tmp_path):
        (tmp_path / "bar.ts").write_text("export function bar(): void {}\n")
        stamp_directory(tmp_path, _log(tmp_path), lang="typescript")
        content = (tmp_path / "bar.ts").read_text()
        assert content.startswith("// SPDX-License-Identifier: Apache-2.0")


class TestLicenseFile:
    def test_matches_repo_root_license_verbatim(self, tmp_path):
        """Single source of truth: the synthesized LICENSE must be an exact
        copy of the real one, not a hand-duplicated string that could drift."""
        stamp_directory(tmp_path, _log(tmp_path), lang="python")
        root_license = (_REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
        synthesized_license = (tmp_path / "LICENSE").read_text(encoding="utf-8")
        assert synthesized_license == root_license

    def test_license_file_says_apache_not_agpl(self, tmp_path):
        stamp_directory(tmp_path, _log(tmp_path), lang="python")
        content = (tmp_path / "LICENSE").read_text()
        assert "Apache License" in content
        assert "AGPL" not in content
        assert "Affero" not in content


class TestAuditTrail:
    def test_stamp_apply_records_apache_spdx(self, tmp_path):
        (tmp_path / "foo.py").write_text("x = 1\n")
        audit_path = tmp_path / "audit.jsonl"
        stamp_directory(tmp_path, BootstrapAuditLog(audit_path), lang="python")

        events = [json.loads(line) for line in audit_path.read_text().splitlines()]
        stamp_events = [e for e in events if e["event"] == "STAMP_APPLY"]
        assert len(stamp_events) == 1
        assert stamp_events[0]["spdx"] == "Apache-2.0"
