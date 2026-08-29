"""Regression tests: LLM responses with no markdown fence at all must not
write a conversational preamble straight into the generated source file.

Reproduced live: a Go polyglot e2e run got a response with zero backticks
("Let me implement the add function...\n\npackage pulse\n...") and the old
_extract_code fallback (`return content.strip()`) wrote the whole thing --
preamble included -- to add.go, which then failed `go vet` with
"expected 'package', found Let". Each language pod's _extract_code now
searches for the first line that's actually source (package/import/def/
class/const/... at line start) when no fence is present, and drops
everything before it.
"""
from src.agents.go_language_pod import _extract_code as go_extract_code
from src.agents.typescript_worker_agent import _extract_code as ts_extract_code
from src.agents.worker_agent import _extract_code as python_extract_code


class TestGoExtractCode:
    def test_fenced_code_still_extracted(self):
        content = "```go\npackage pulse\n\nfunc Add(a, b int) int {\n\treturn a + b\n}\n```"
        assert go_extract_code(content) == "package pulse\n\nfunc Add(a, b int) int {\n\treturn a + b\n}"

    def test_no_fence_preamble_is_stripped(self):
        content = "Let me implement the add function:\n\npackage pulse\n\nfunc Add(a, b int) int {\n\treturn a + b\n}\n"
        result = go_extract_code(content)
        assert result.startswith("package pulse")
        assert "Let me" not in result

    def test_no_fence_no_recognizable_code_falls_back_unchanged(self):
        content = "I cannot help with that request."
        assert go_extract_code(content) == content


class TestPythonExtractCode:
    def test_fenced_code_still_extracted(self):
        content = "```python\ndef add(a, b):\n    return a + b\n```"
        assert python_extract_code(content) == "def add(a, b):\n    return a + b"

    def test_no_fence_preamble_is_stripped(self):
        content = "Let me implement this:\n\ndef add(a, b):\n    return a + b\n"
        result = python_extract_code(content)
        assert result.startswith("def add")
        assert "Let me" not in result

    def test_no_fence_no_recognizable_code_falls_back_unchanged(self):
        content = "I cannot help with that request."
        assert python_extract_code(content) == content


class TestTypeScriptExtractCode:
    def test_fenced_code_still_extracted(self):
        content = "```typescript\nexport function add(a: number, b: number): number {\n  return a + b;\n}\n```"
        result = ts_extract_code(content)
        assert result.startswith("export function add")

    def test_no_fence_preamble_is_stripped(self):
        content = (
            "Let me implement this:\n\n"
            "export function add(a: number, b: number): number {\n  return a + b;\n}\n"
        )
        result = ts_extract_code(content)
        assert result.startswith("export function add")
        assert "Let me" not in result

    def test_no_fence_no_recognizable_code_falls_back_unchanged(self):
        content = "I cannot help with that request."
        assert ts_extract_code(content) == content
