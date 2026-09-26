"""Tests for src/utils/patcher.py -- deterministic SEARCH/REPLACE patching."""

from types import SimpleNamespace

import pytest

from src.utils.patcher import (
    PatchError,
    apply_multi_file_patch,
    apply_patch,
    apply_search_replace_blocks,
    parse_multi_file_blocks,
    parse_search_replace_blocks,
)


def _block(search: str, replace: str) -> str:
    return f"<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE"


def _file_section(filename: str, *blocks: str) -> str:
    return f"### FILE: {filename}\n" + "\n\n".join(blocks)


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


class TestParseMultiFileBlocks:
    def test_single_file_single_block(self):
        text = _file_section("a.py", _block("x = 1", "x = 2"))
        by_file = parse_multi_file_blocks(text)
        assert set(by_file) == {"a.py"}
        assert by_file["a.py"][0].search == "x = 1"

    def test_multiple_files(self):
        text = (
            _file_section("a.py", _block("x = 1", "x = 2"))
            + "\n\n"
            + _file_section("b.py", _block("y = 1", "y = 2"))
        )
        by_file = parse_multi_file_blocks(text)
        assert set(by_file) == {"a.py", "b.py"}
        assert by_file["a.py"][0].replace == "x = 2"
        assert by_file["b.py"][0].replace == "y = 2"

    def test_multiple_blocks_within_one_file(self):
        text = _file_section("a.py", _block("x = 1", "x = 2"), _block("y = 1", "y = 2"))
        by_file = parse_multi_file_blocks(text)
        assert len(by_file["a.py"]) == 2

    def test_same_file_referenced_twice_concatenates_blocks(self):
        text = (
            _file_section("a.py", _block("x = 1", "x = 2"))
            + "\n\n"
            + _file_section("a.py", _block("y = 1", "y = 2"))
        )
        by_file = parse_multi_file_blocks(text)
        assert len(by_file["a.py"]) == 2

    def test_no_file_markers_returns_empty_dict(self):
        assert parse_multi_file_blocks(_block("x = 1", "x = 2")) == {}

    def test_no_content_returns_empty_dict(self):
        assert parse_multi_file_blocks("just some prose, no markers here") == {}


class TestApplyMultiFilePatch:
    def test_successful_patch_across_two_files(self):
        files = {"a.py": "x = 1\n", "b.py": "y = 1\n"}
        patch_text = (
            _file_section("a.py", _block("x = 1", "x = 2"))
            + "\n\n"
            + _file_section("b.py", _block("y = 1", "y = 2"))
        )
        result = apply_multi_file_patch(files, patch_text)
        assert result.success is True
        assert result.patched == {"a.py": "x = 2\n", "b.py": "y = 2\n"}
        assert result.blocks_applied == 2

    def test_untouched_file_keeps_its_original_content(self):
        files = {"a.py": "x = 1\n", "b.py": "y = 1\n"}
        patch_text = _file_section("a.py", _block("x = 1", "x = 2"))
        result = apply_multi_file_patch(files, patch_text)
        assert result.success is True
        assert result.patched == {"a.py": "x = 2\n", "b.py": "y = 1\n"}
        assert result.blocks_applied == 1

    def test_no_sections_in_response_is_a_clean_failure(self):
        result = apply_multi_file_patch({"a.py": "x = 1\n"}, "sorry, I can't help with that")
        assert result.success is False
        assert result.patched is None
        assert "no '### FILE:" in result.error

    def test_unknown_filename_is_rejected(self):
        files = {"a.py": "x = 1\n"}
        patch_text = _file_section("nope.py", _block("x = 1", "x = 2"))
        result = apply_multi_file_patch(files, patch_text)
        assert result.success is False
        assert "nope.py" in result.error
        assert "a.py" in result.error

    def test_a_failing_block_in_one_file_fails_the_whole_patch(self):
        # All-or-nothing: a coordinated edit that only partially lands is
        # not a success, even if the other file's block would have applied
        # cleanly.
        files = {"a.py": "x = 1\n", "b.py": "y = 1\n"}
        patch_text = (
            _file_section("a.py", _block("x = 999", "x = 2"))  # search text absent
            + "\n\n"
            + _file_section("b.py", _block("y = 1", "y = 2"))
        )
        result = apply_multi_file_patch(files, patch_text)
        assert result.success is False
        assert "a.py" in result.error
        assert result.patched is None

    def test_syntax_error_in_one_patched_file_fails_the_whole_patch(self):
        files = {"a.py": "x = 1\n", "b.py": "y = 1\n"}
        patch_text = (
            _file_section("a.py", _block("x = 1", "x = 2 +"))  # syntax error
            + "\n\n"
            + _file_section("b.py", _block("y = 1", "y = 2"))
        )
        result = apply_multi_file_patch(files, patch_text)
        assert result.success is False
        assert "a.py" in result.error
        assert "syntax error" in result.error

    def test_non_python_file_is_not_syntax_checked(self):
        files = {"a.py": "x = 1\n", "notes.md": "# hi\n"}
        patch_text = (
            _file_section("a.py", _block("x = 1", "x = 2"))
            + "\n\n"
            + _file_section("notes.md", _block("# hi", "# bye ((("))
        )
        result = apply_multi_file_patch(files, patch_text)
        assert result.success is True
        assert result.patched["notes.md"] == "# bye (((\n"

    def test_never_raises_on_malformed_input(self):
        result = apply_multi_file_patch({"a.py": ""}, "### FILE: a.py\n<<<<<<< SEARCH\nfoo\n>>>>>>> REPLACE")
        assert result.success is False


class TestApplyPatchProtectedShape:
    """#70: apply_patch's optional protected_shape param rejects a patch
    that changes a pre-scaffolded signature, but allows a pure body change
    or an added method -- and its rejection is a normal, non-abort
    PatchResult error, so it flows through the existing retry-with-feedback
    loop exactly like a syntax error does."""

    def _shape(self, source: str):
        from src.utils.ast_shape import extract_protected_shape

        return extract_protected_shape(source)

    def test_body_only_change_is_accepted(self):
        original = "class Thing:\n    def run(self) -> int:\n        raise NotImplementedError\n"
        shape = self._shape(original)
        patch_text = _block(
            "        raise NotImplementedError", "        return 42",
        )
        result = apply_patch(original, patch_text, protected_shape=shape)
        assert result.success is True
        assert "return 42" in result.code

    def test_changed_method_signature_is_rejected(self):
        original = "class Thing:\n    def run(self, x: int) -> int:\n        return x\n"
        shape = self._shape(original)
        patch_text = _block(
            "    def run(self, x: int) -> int:", "    def run(self, x: str) -> int:",
        )
        result = apply_patch(original, patch_text, protected_shape=shape)
        assert result.success is False
        assert "PROTECTED_SIGNATURE_CHANGED" in result.error
        assert "run" in result.error

    def test_rejection_is_not_an_abort_error(self):
        """A protected-shape rejection must retry-with-feedback like
        PATCH_APPLY_FAILED, never hard-stop like ForbiddenImport."""
        from src.agents.tdd_cycle_runner import _is_abort

        original = "class Thing:\n    def run(self, x: int) -> int:\n        return x\n"
        shape = self._shape(original)
        patch_text = _block(
            "    def run(self, x: int) -> int:", "    def run(self, x: str) -> int:",
        )
        result = apply_patch(original, patch_text, protected_shape=shape)
        phase_result = SimpleNamespace(error=f"PATCH_APPLY_FAILED: {result.error}")
        assert _is_abort(phase_result) is False

    def test_added_method_is_accepted(self):
        original = "class Thing:\n    def run(self) -> int:\n        return 1\n"
        shape = self._shape(original)
        patch_text = _block(
            "class Thing:\n    def run(self) -> int:\n        return 1",
            "class Thing:\n    def run(self) -> int:\n        return 1\n\n"
            "    def helper(self) -> None:\n        pass",
        )
        result = apply_patch(original, patch_text, protected_shape=shape)
        assert result.success is True

    def test_no_protected_shape_means_no_new_restriction(self):
        original = "class Thing:\n    def run(self, x: int) -> int:\n        return x\n"
        patch_text = _block(
            "    def run(self, x: int) -> int:", "    def run(self, x: str) -> int:",
        )
        result = apply_patch(original, patch_text)
        assert result.success is True


class TestApplyMultiFilePatchProtectedShape:
    def test_protected_file_rejected_unprotected_file_ignored(self):
        from src.utils.ast_shape import extract_protected_shape

        files = {
            "a.py": "class Thing:\n    def run(self, x: int) -> int:\n        return x\n",
            "b.py": "y = 1\n",
        }
        shape = extract_protected_shape(files["a.py"])
        patch_text = (
            _file_section("a.py", _block(
                "    def run(self, x: int) -> int:", "    def run(self, x: str) -> int:",
            ))
            + "\n\n"
            + _file_section("b.py", _block("y = 1", "y = 2"))
        )
        result = apply_multi_file_patch(files, patch_text, protected_shapes={"a.py": shape})
        assert result.success is False
        assert "a.py" in result.error
        assert "PROTECTED_SIGNATURE_CHANGED" in result.error

    def test_compatible_change_to_protected_file_succeeds(self):
        from src.utils.ast_shape import extract_protected_shape

        files = {"a.py": "class Thing:\n    def run(self) -> int:\n        raise NotImplementedError\n"}
        shape = extract_protected_shape(files["a.py"])
        patch_text = _file_section(
            "a.py", _block("        raise NotImplementedError", "        return 1"),
        )
        result = apply_multi_file_patch(files, patch_text, protected_shapes={"a.py": shape})
        assert result.success is True
