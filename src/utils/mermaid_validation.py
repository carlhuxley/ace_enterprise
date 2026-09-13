"""Shared helpers for validating generated mermaid diagrams against the
real mermaid.js parser, via the sandboxed MermaidRunner (see
src/agents/mermaid_runner.py and docker/harness/Containerfile.mermaid --
mermaid+jsdom's ~140 third-party npm packages never run on the host).

Used by both tests/test_mermaid_validity.py (the permanent regression
test) and validate_docs_mermaid.py (the pre-commit hook's blocking check),
so the extraction/validation logic isn't duplicated between them.
"""
import re

_MERMAID_BLOCK_RE = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)


def extract_mermaid_blocks(markdown_text: str) -> list[str]:
    return _MERMAID_BLOCK_RE.findall(markdown_text)


def validate_with_runner(runner, mermaid_text: str) -> tuple[bool, str]:
    """`runner` is a started MermaidRunner. Returns (is_valid, message) --
    message is "PARSE OK" on success or the real mermaid parser's error on
    failure."""
    result = runner.send_pulse({"diagram.mmd": mermaid_text})
    return result.exit_code == 0, (result.stdout + result.stderr).strip()
