"""Permanent regression test for the class of bug that broke
docs/SYSTEM_ARCHITECTURE.md's rendering on GitHub: a mermaid diagram that
looks fine by inspection but is ungrammatical (mismatched activate/
deactivate pairing, in that case).

Validates against the *real* mermaid.js parser (mermaid 10.9.8 + jsdom
30.0.1, exact versions pinned), not a hand-written approximation of its
grammar -- the same authoritative check used to manually diagnose and
verify the original fix. Runs inside the sandboxed MermaidRunner
(src/agents/mermaid_runner.py), not via a bare host subprocess: mermaid +
jsdom pull in ~140 third-party npm packages, and this project already
sandboxes every other third-party toolchain it runs (Go modules, TS/npm,
pybullet) for exactly that supply-chain reason -- the host (or CI runner,
or eventually a developer's own machine via a pre-commit hook) never runs
`npm` or `node` directly. Skipped without podman, same pattern as every
other podman-backed test in this suite.

Covers every generated-mermaid source in the repo as of this writing:
docs/SYSTEM_ARCHITECTURE.md (LLM-narrated, regenerated non-deterministically
on src/ changes -- the actual source of the original bug) and
docs/ARCHITECTURE_GRAPH.md (deterministic, from dependency_graph.py).
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


def _extract_mermaid_blocks(markdown_text: str) -> list[str]:
    return re.findall(r"```mermaid\n(.*?)```", markdown_text, re.DOTALL)


def _validate(runner, mermaid_text: str) -> tuple[bool, str]:
    result = runner.send_pulse({"diagram.mmd": mermaid_text})
    return result.exit_code == 0, (result.stdout + result.stderr).strip()


def test_validator_itself_rejects_known_invalid_mermaid(shared_mermaid_runner):
    """Sanity check the checker before trusting its PASS on real docs --
    reproduces the exact class of bug this test exists to catch (a second
    deactivate on an already-inactive participant)."""
    bad = "sequenceDiagram\n    participant A\n    activate A\n    deactivate A\n    deactivate A\n"
    ok, message = _validate(shared_mermaid_runner, bad)
    assert not ok
    assert "inactivate an inactive participant" in message


def test_validator_itself_accepts_known_valid_mermaid(shared_mermaid_runner):
    ok, message = _validate(shared_mermaid_runner, "flowchart TD\n    a --> b\n")
    assert ok, message


@pytest.mark.parametrize(
    "doc_path",
    [
        REPO_ROOT / "docs" / "SYSTEM_ARCHITECTURE.md",
        REPO_ROOT / "docs" / "ARCHITECTURE_GRAPH.md",
    ],
)
def test_generated_doc_mermaid_is_valid(shared_mermaid_runner, doc_path):
    if not doc_path.exists():
        pytest.skip(f"{doc_path} not generated yet")
    blocks = _extract_mermaid_blocks(doc_path.read_text())
    assert blocks, f"no mermaid block found in {doc_path}"
    for block in blocks:
        ok, message = _validate(shared_mermaid_runner, block)
        assert ok, f"{doc_path}: {message}"
