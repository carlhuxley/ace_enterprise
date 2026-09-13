"""Permanent regression test for the class of bug that broke
docs/SYSTEM_ARCHITECTURE.md's rendering on GitHub: a mermaid diagram that
looks fine by inspection but is ungrammatical (mismatched activate/
deactivate pairing, in that case).

Validates against the *real* mermaid.js parser (tools/mermaid_check/,
mermaid 10.9.8 + jsdom 30.0.1, exact versions pinned), not a hand-written
approximation of its grammar -- the same authoritative check used to
manually diagnose and verify the original fix. Requires Node.js and the
npm deps installed (`cd tools/mermaid_check && npm install`); CI installs
both before running tests (see .github/workflows/ci.yml). Skipped locally
if either isn't available, same pattern as skip_no_podman/skip_no_claude
elsewhere in this suite.

Covers every generated-mermaid source in the repo as of this writing:
docs/SYSTEM_ARCHITECTURE.md (LLM-narrated, regenerated non-deterministically
on src/ changes -- the actual source of the original bug) and
docs/ARCHITECTURE_GRAPH.md (deterministic, from dependency_graph.py).
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
MERMAID_CHECK_DIR = REPO_ROOT / "tools" / "mermaid_check"

skip_no_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not in PATH")
skip_no_mermaid_check_deps = pytest.mark.skipif(
    not (MERMAID_CHECK_DIR / "node_modules" / "mermaid").is_dir(),
    reason="tools/mermaid_check dependencies not installed (cd tools/mermaid_check && npm install)",
)


def _extract_mermaid_blocks(markdown_text: str) -> list[str]:
    return re.findall(r"```mermaid\n(.*?)```", markdown_text, re.DOTALL)


def _validate(mermaid_text: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as f:
        f.write(mermaid_text)
        tmp_path = f.name
    try:
        result = subprocess.run(
            ["node", "validate.mjs", tmp_path],
            cwd=MERMAID_CHECK_DIR, capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@skip_no_node
@skip_no_mermaid_check_deps
def test_validator_itself_rejects_known_invalid_mermaid():
    """Sanity check the checker before trusting its PASS on real docs --
    reproduces the exact class of bug this test exists to catch (a second
    deactivate on an already-inactive participant)."""
    bad = "sequenceDiagram\n    participant A\n    activate A\n    deactivate A\n    deactivate A\n"
    ok, message = _validate(bad)
    assert not ok
    assert "inactivate an inactive participant" in message


@skip_no_node
@skip_no_mermaid_check_deps
def test_validator_itself_accepts_known_valid_mermaid():
    ok, message = _validate("flowchart TD\n    a --> b\n")
    assert ok, message


@skip_no_node
@skip_no_mermaid_check_deps
@pytest.mark.parametrize(
    "doc_path",
    [
        REPO_ROOT / "docs" / "SYSTEM_ARCHITECTURE.md",
        REPO_ROOT / "docs" / "ARCHITECTURE_GRAPH.md",
    ],
)
def test_generated_doc_mermaid_is_valid(doc_path):
    if not doc_path.exists():
        pytest.skip(f"{doc_path} not generated yet")
    blocks = _extract_mermaid_blocks(doc_path.read_text())
    assert blocks, f"no mermaid block found in {doc_path}"
    for block in blocks:
        ok, message = _validate(block)
        assert ok, f"{doc_path}: {message}"
