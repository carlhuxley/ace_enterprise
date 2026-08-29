"""Regression tests for src.utils.code_extraction.extract_code.

The non-```python fence-tag case is a real bug reproduced live in the ACE
benchmark: a model emitted ```code ... ``` instead of ```python ... ```,
and the old fallback (`response[start:end]` right after the opening ```)
kept "code" as the first line of extracted source, producing
`NameError: name 'code' is not defined` at import time (see
benchmarks/reports/20260828T184320Z_qwen_qwen3-coder-30b-a3b-instruct_x5runs.json,
conc_async_lock_counter and conc_cancel_on_failure).

The first fix for that (regex-based, requiring a literal "\n" right after
the language tag) was itself a regression: a CRLF-terminated fence
("```python\r\n...") doesn't match "```python\n", so extraction fell
through to a cruder fallback and left the original closing ``` embedded
as a literal line of "code" further down the file -- a SyntaxError
partway through, not at line 1 (see
benchmarks/reports/20260828T204234Z_qwen_qwen3-coder-30b-a3b-instruct_x5runs.json,
conc_cancel_on_failure, conc_timeout, sec_list_directory). The current
implementation is substring-based (like the original), not regex-anchored
on a specific newline byte sequence, specifically to avoid repeating that
mistake.
"""
from src.utils.code_extraction import extract_code


class TestExtractCode:
    def test_python_tagged_fence(self):
        content = "```python\ndef add(a, b):\n    return a + b\n```"
        assert extract_code(content) == "def add(a, b):\n    return a + b"

    def test_non_python_language_tag_does_not_leak_into_code(self):
        content = "```code\nasync def race_all_or_cancel():\n    pass\n```"
        result = extract_code(content)
        assert result == "async def race_all_or_cancel():\n    pass"
        assert "code\n" not in result

    def test_bare_fence_no_language_tag(self):
        content = "```\ndef add(a, b):\n    return a + b\n```"
        assert extract_code(content) == "def add(a, b):\n    return a + b"

    def test_unclosed_fence(self):
        content = "```python\ndef add(a, b):\n    return a + b\n"
        assert extract_code(content) == "def add(a, b):\n    return a + b"

    def test_no_fence_preamble_is_stripped(self):
        content = "Let me implement this:\n\ndef add(a, b):\n    return a + b\n"
        result = extract_code(content)
        assert result.startswith("def add")
        assert "Let me" not in result

    def test_no_fence_no_recognizable_code_falls_back_unchanged(self):
        content = "I cannot help with that request."
        assert extract_code(content) == content

    def test_crlf_terminated_fence_does_not_leak_closing_backticks(self):
        content = (
            "```python\r\n"
            "async def race_all_or_cancel(coros):\r\n"
            "    return coros\r\n"
            "```\r\n"
        )
        result = extract_code(content)
        assert "```" not in result
        assert result.startswith("async def race_all_or_cancel")

    def test_trailing_space_after_language_tag(self):
        content = "```python \ndef add(a, b):\n    return a + b\n```\n"
        assert extract_code(content) == "def add(a, b):\n    return a + b"

    def test_capitalized_language_tag_is_stripped(self):
        content = "```Python\ndef add(a, b):\n    return a + b\n```\n"
        result = extract_code(content)
        assert result == "def add(a, b):\n    return a + b"
        assert "Python" not in result

    def test_prefers_python_tagged_fence_over_earlier_untagged_one(self):
        content = (
            "Here's a draft:\n```\ndef foo():\n    pass\n```\n\n"
            "Actual answer:\n```python\ndef add(a, b):\n    return a + b\n```\n"
        )
        assert extract_code(content) == "def add(a, b):\n    return a + b"

    def test_trailing_prose_with_inline_backtick_is_excluded(self):
        content = (
            "```python\nasync def f():\n    return 1\n```\n"
            "\nUses `asyncio.wait` correctly.\n"
        )
        result = extract_code(content)
        assert result == "async def f():\n    return 1"
