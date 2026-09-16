"""Tests for src/utils/patcher.py -- deterministic SEARCH/REPLACE patching."""

import pytest

from src.utils.patcher import (
    PatchError,
    apply_patch,
    apply_search_replace_blocks,
    parse_search_replace_blocks,
)


def _block(search: str, replace: str) -> str:
    return f"<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE"


class TestParseBlocks:
    def test_single_block(self):
        text = _block("x = 1", "x = 2")
        blocks = parse_search_replace_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].search == "x = 1"
        assert blocks[0].replace == "x = 2"

    def test_multiple_blocks(self):
        text = _block("a = 1", "a = 2") + "\n\n" + _block("b = 1", "b = 2")
        blocks = parse_search_replace_blocks(text)
        assert len(blocks) == 2
        assert blocks[1].search == "b = 1"

    def test_no_blocks_returns_empty_list(self):
        assert parse_search_replace_blocks("just some prose, no blocks here") == []

    def test_multiline_search_and_replace(self):
        search = "def foo():\n    return 1"
        replace = "def foo():\n    return 2\n\ndef bar():\n    return 3"
        blocks = parse_search_replace_blocks(_block(search, replace))
        assert blocks[0].search == search
        assert blocks[0].replace == replace


class TestApplyExactMatch:
    def test_unique_match_is_replaced(self):
        original = "x = 1\ny = 2\n"
        blocks = parse_search_replace_blocks(_block("x = 1", "x = 100"))
        assert apply_search_replace_blocks(original, blocks) == "x = 100\ny = 2\n"

    def test_ambiguous_match_raises(self):
        original = "x = 1\nx = 1\n"
        blocks = parse_search_replace_blocks(_block("x = 1", "x = 2"))
        with pytest.raises(PatchError, match="2 locations") as exc_info:
            apply_search_replace_blocks(original, blocks)
        assert "ambiguous" in str(exc_info.value)

    def test_no_blocks_raises(self):
        with pytest.raises(PatchError, match="no SEARCH/REPLACE blocks"):
            apply_search_replace_blocks("x = 1", [])

    def test_multiple_blocks_apply_in_order_and_compose(self):
        original = "def foo():\n    return 1\n"
        text = (
            _block("def foo():\n    return 1", "def foo():\n    return 2")
            + "\n\n"
            + _block("return 2", "return 3")
        )
        blocks = parse_search_replace_blocks(text)
        result = apply_search_replace_blocks(original, blocks)
        assert result == "def foo():\n    return 3\n"


class TestApplyFuzzyFallback:
    def test_trailing_whitespace_drift_still_matches(self):
        original = "def foo():  \n    return 1\n"  # trailing spaces on line 1
        blocks = parse_search_replace_blocks(_block("def foo():\n    return 1", "def foo():\n    return 2"))
        result = apply_search_replace_blocks(original, blocks)
        assert "return 2" in result

    def test_completely_unrelated_search_raises(self):
        original = "def foo():\n    return 1\n"
        blocks = parse_search_replace_blocks(_block("class Unrelated:\n    pass\n    pass\n    pass", "x"))
        with pytest.raises(PatchError, match="not found"):
            apply_search_replace_blocks(original, blocks)


class TestApplyPatchEndToEnd:
    def test_successful_patch_returns_code(self):
        original = "def foo():\n    return 1\n"
        patch = _block("return 1", "return 2")
        result = apply_patch(original, patch)
        assert result.success is True
        assert result.code == "def foo():\n    return 2\n"
        assert result.blocks_applied == 1
        assert result.error is None

    def test_patch_producing_invalid_python_is_rejected(self):
        original = "def foo():\n    return 1\n"
        patch = _block("return 1", "return 2 +")  # syntax error
        result = apply_patch(original, patch)
        assert result.success is False
        assert "syntax error" in result.error

    def test_validate_python_false_skips_syntax_check(self):
        original = "def foo():\n    return 1\n"
        patch = _block("return 1", "return 2 +")
        result = apply_patch(original, patch, validate_python=False)
        assert result.success is True

    def test_no_blocks_in_response_is_a_clean_failure(self):
        result = apply_patch("x = 1\n", "sorry, I can't help with that")
        assert result.success is False
        assert result.code is None
        assert "no SEARCH/REPLACE blocks" in result.error

    def test_ambiguous_match_surfaces_as_patch_result_error(self):
        original = "x = 1\nx = 1\n"
        result = apply_patch(original, _block("x = 1", "x = 2"))
        assert result.success is False
        assert "ambiguous" in result.error

    def test_never_raises_on_malformed_input(self):
        # Garbage input must come back as a PatchResult, not propagate.
        result = apply_patch("", "<<<<<<< SEARCH\nfoo\n>>>>>>> REPLACE")  # missing =======
        assert result.success is False
