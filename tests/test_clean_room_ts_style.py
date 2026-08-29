"""Tests for verify_ts_style() (bootstrap/clean_room.py).

No prior coverage existed for this function. Regression coverage for a
bug discovered live: orchestrate.py's _synthesis_loop_ts globs *.ts,
which also matches *.test.ts, so the "no hardcoded stub IDs" rule --
meant to catch implementation code faking dynamic ID generation with a
literal string -- was deleting passing *.test.ts files whose fixtures
legitimately used a literal example ID (e.g. asserting behavior for
id === 'ctx-00001'). The module then never got marked verified, but its
implementation file survived on disk with no test, looking exactly like
TDD hadn't run when it in fact had (RED failed, GREEN passed).
"""
from pathlib import Path

from bootstrap.clean_room import verify_ts_style


def _write(tmp_path: Path, name: str, content: str) -> Path:
    f = tmp_path / name
    f.write_text(content)
    return f


class TestHardcodedStubIdRule:
    def test_flags_hardcoded_stub_id_in_implementation_file(self, tmp_path):
        f = _write(tmp_path, "widget.ts", "export const id = 'ctx-00001';\n")
        result = verify_ts_style(f)
        assert not result.passed
        assert any("Hardcoded stub IDs" in v for v in result.violations)

    def test_does_not_flag_same_literal_in_test_file(self, tmp_path):
        f = _write(
            tmp_path, "widget.test.ts",
            "import { describe, it, expect } from 'vitest';\n"
            "describe('widget', () => {\n"
            "  it('returns the record for a known id', () => {\n"
            "    expect(lookup('ctx-00001')).toEqual({ id: 'ctx-00001' });\n"
            "  });\n"
            "});\n",
        )
        result = verify_ts_style(f)
        assert result.passed
        assert result.violations == []

    def test_other_rules_still_apply_to_test_files(self, tmp_path):
        """Only Rule 4 is test-file-exempt -- snake_case etc. still matter."""
        f = _write(tmp_path, "widget.test.ts", "const my_variable = 1;\n")
        result = verify_ts_style(f)
        assert not result.passed
        assert any("snake_case" in v for v in result.violations)


class TestOtherStyleRulesUnaffected:
    def test_math_random_flagged(self, tmp_path):
        f = _write(tmp_path, "widget.ts", "const x = Math.random();\n")
        result = verify_ts_style(f)
        assert not result.passed
        assert any("Math.random" in v for v in result.violations)

    def test_clean_file_passes(self, tmp_path):
        f = _write(
            tmp_path, "widget.ts",
            "export function add(a: number, b: number): number {\n  return a + b;\n}\n",
        )
        result = verify_ts_style(f)
        assert result.passed
        assert result.violations == []
