#!/usr/bin/env python3
"""Validate every mermaid block in the generated architecture docs against
the real mermaid.js parser, sandboxed (see src/agents/mermaid_runner.py --
mermaid+jsdom's ~140 third-party npm packages never run on the host).

Used by the pre-commit hook to BLOCK a commit that would ship an
ungrammatical diagram -- unlike the LLM doc-gen step, this is a
deterministic pass/fail against a real parser, not a "the LLM might be
wrong" situation worth being lenient about. tests/test_mermaid_validity.py
is the permanent regression-test version of the same check, run in CI
against whatever's currently committed.

Usage: .venv/bin/python validate_docs_mermaid.py
Exit 0 if every diagram parses; exit 1 (printing every failure) otherwise.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.agents.mermaid_runner import MermaidRunner
from src.utils.mermaid_validation import extract_mermaid_blocks, validate_with_runner

REPO_ROOT = Path(__file__).parent
DOCS = [
    REPO_ROOT / "docs" / "SYSTEM_ARCHITECTURE.md",
    REPO_ROOT / "docs" / "ARCHITECTURE_GRAPH.md",
]


def main() -> None:
    runner = MermaidRunner(container_name="mermaid_precommit_check")
    runner.start()
    failures: list[str] = []
    try:
        for doc_path in DOCS:
            if not doc_path.exists():
                continue
            blocks = extract_mermaid_blocks(doc_path.read_text())
            for i, block in enumerate(blocks):
                ok, message = validate_with_runner(runner, block)
                if not ok:
                    failures.append(f"{doc_path} (diagram {i + 1}): {message}")
    finally:
        runner.stop()

    if failures:
        print("mermaid validation FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        sys.exit(1)

    print("mermaid validation OK")


if __name__ == "__main__":
    main()
