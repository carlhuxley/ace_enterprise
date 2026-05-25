"""Stage 1 — Translate private source modules to pure Gherkin feature files.

For each source file:
  - Records SOURCE_READ event (file path + sha256) in the audit log
  - Calls the LLM with a behavior-only extraction prompt
  - Strips accidental markdown fences from the response
  - Writes the feature file and records GHERKIN_EMIT event

The LLM prompt is the clean-room barrier: it explicitly forbids referencing
internal names and asks only for observable Given/When/Then behavior.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bootstrap.audit_log import BootstrapAuditLog

_EXTRACTION_PROMPT = """\
You are a behavior analyst performing a clean-room specification extraction.

Task: read the Python module below and produce a Gherkin feature file that \
describes ONLY the observable, externally-visible behavior of its public API.

Rules:
- Do NOT reference internal implementation details, private methods \
(names starting with _), or internal helper class names
- Describe behavior from the perspective of an external caller — \
inputs go in, outputs come out
- Use concrete, specific examples with real values in Given/When/Then steps
- Each scenario must be independently testable from the public API alone
- Aim for 3–8 scenarios covering the meaningful behavioral envelope
- Output ONLY valid Gherkin — no markdown fences, no prose explanation, \
no step definitions

Module filename: {filename}

Source code:
{source}

Gherkin feature file:"""


def extract_features(
    src_files: list[Path],
    features_dir: Path,
    log: BootstrapAuditLog,
    model: str | None = None,
    llm_client=None,
) -> list[Path]:
    """Generate a .feature file for each source file. Returns paths of produced files."""
    if llm_client is None:
        from src.utils.claude_cli_client import ClaudeCliClient
        llm_client = ClaudeCliClient()
    features_dir.mkdir(parents=True, exist_ok=True)
    produced: list[Path] = []

    for src_file in src_files:
        source = src_file.read_text(encoding="utf-8")
        if len(source.strip()) < 80:
            continue

        log.record(
            "SOURCE_READ",
            file=str(src_file),
            sha256=BootstrapAuditLog.sha256(src_file),
            lines=source.count("\n"),
        )

        prompt = _EXTRACTION_PROMPT.format(filename=src_file.name, source=source)
        response = llm_client.generate(prompt, temperature=0.0)
        gherkin = _strip_fences(response.get("content", "").strip())

        if not gherkin.startswith("Feature:"):
            print(f"  [skip] no Feature: header for {src_file.name}")
            log.record("GHERKIN_SKIP", file=str(src_file), reason="no Feature: header in response")
            continue

        feature_path = features_dir / f"{src_file.stem}.feature"
        feature_path.write_text(gherkin, encoding="utf-8")

        log.record(
            "GHERKIN_EMIT",
            src_file=str(src_file),
            feature_file=str(feature_path),
            sha256=BootstrapAuditLog.sha256(feature_path),
            model=model or "claude-cli",
            prompt_sha256=BootstrapAuditLog.sha256_str(prompt),
        )

        produced.append(feature_path)
        print(f"  [extract] {src_file.name} → {feature_path.name}")

    return produced


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that models sometimes emit despite instructions."""
    lines = text.splitlines()
    return "\n".join(
        line for line in lines if not line.strip().startswith("```")
    ).strip()
