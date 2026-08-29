"""Stage 1 — Translate private source modules to pure Gherkin feature files.

For each source file:
  - If a .feature file already exists AND its recorded source hash
    (<stem>.src.sha256, sitting alongside it in features_dir) matches the
    source file's current content, records GHERKIN_CACHED and skips the
    LLM call.
  - Otherwise (no .feature file yet, or the source has changed since it
    was last extracted) records SOURCE_READ, calls the LLM, strips
    markdown fences, writes the feature file and its source-hash marker,
    and records GHERKIN_EMIT.

Mirrors the "verified marker vs current hash" pattern orchestrate.py's
_resume_decision() uses one stage downstream (.spec.sha256) -- without
this, a .feature file's mere presence was treated as permanently valid
regardless of how much the source it was extracted from had changed
since, so a resumed run could silently re-verify stale specs against
heavily-rewritten source and skip re-synthesis entirely.

.feature filenames are keyed by _module_key() (full path relative to
src_root, joined with "_"), not the bare filename stem. Plain stems
collide in this repo -- e.g. src/audit/schemas.py, src/retrieval/schemas.py,
and src/storage/schemas.py are three unrelated modules that all used to
map to the same schemas.feature and, one stage downstream, the same OSS
output directory -- whichever was synthesised last silently overwrote the
others (discovered live: schemas/config/models ended up with a verified
.spec.sha256 marker but zero surviving .ts files in the OSS repo).

Per-file error isolation: a single LLM call failure no longer aborts the
whole run. Transient failures (confirmed live, twice: the local `claude`
CLI self-updating mid-run leaves a few-second window where the binary
resolves to nothing, so subprocess.run raises FileNotFoundError) are
retried a few times with a short delay; if a file still fails after that,
it's logged as GHERKIN_ERROR and skipped -- it has no .feature/.src.sha256
written, so the content-hash cache picks it up as "fresh" again on the
next resume, same as any other not-yet-extracted module. LLMQuotaExhaustedError
is the one exception: it means every subsequent call would fail identically,
so it's never retried and re-raises immediately to abort the whole run
(mirrors orchestrate.py's Stage 2/3 synthesis loops).

The LLM prompt is the clean-room barrier: it explicitly forbids referencing
internal names and asks only for observable Given/When/Then behavior.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bootstrap.audit_log import BootstrapAuditLog
from src.utils.llm_client import LLMQuotaExhaustedError

_MAX_EXTRACT_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 3.0


def _module_key(src_file: Path, src_root: Path) -> str:
    """Collision-free module identifier: src_file's path relative to
    src_root, directory separators joined with "_", extension stripped.

    Falls back to the bare stem if src_file isn't actually under src_root
    (e.g. an ad-hoc --file path outside the configured source tree) --
    there's no meaningful relative path to qualify with in that case, and
    a single file passed explicitly can't collide with anything else in
    the same invocation.
    """
    try:
        rel = src_file.resolve().relative_to(src_root.resolve()).with_suffix("")
        return "_".join(rel.parts)
    except ValueError:
        return src_file.stem

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
    src_root: Path = Path("src"),
) -> list[Path]:
    """Generate a .feature file for each source file. Returns paths of produced files."""
    if llm_client is None:
        from src.utils.llm_client import LLMClient
        llm_client = LLMClient(provider="openrouter", model=model or "google/gemini-3.5-flash")
    features_dir.mkdir(parents=True, exist_ok=True)
    produced: list[Path] = []

    for src_file in src_files:
        source = src_file.read_text(encoding="utf-8")
        if len(source.strip()) < 80:
            continue

        module_key = _module_key(src_file, src_root)

        feature_path = features_dir / f"{module_key}.feature"
        src_hash_path = features_dir / f"{module_key}.src.sha256"
        current_src_sha = BootstrapAuditLog.sha256(src_file)

        if feature_path.exists() and src_hash_path.exists() \
                and src_hash_path.read_text().strip() == current_src_sha:
            log.record(
                "GHERKIN_CACHED",
                src_file=str(src_file),
                feature_file=str(feature_path),
                sha256=BootstrapAuditLog.sha256(feature_path),
            )
            produced.append(feature_path)
            print(f"  [cached] {feature_path.name}")
            continue

        if feature_path.exists():
            # Either no recorded source hash (predates this check) or the
            # source has genuinely changed since last extraction -- either
            # way the existing .feature can't be trusted as still accurate.
            reason = "source changed since last extraction" if src_hash_path.exists() \
                else "no recorded source hash (predates content-hash caching)"
            log.record("GHERKIN_STALE", src_file=str(src_file), feature_file=str(feature_path), reason=reason)
            print(f"  [stale] {feature_path.name} — {reason}, re-extracting")

        log.record(
            "SOURCE_READ",
            file=str(src_file),
            sha256=current_src_sha,
            lines=source.count("\n"),
        )

        prompt = _EXTRACTION_PROMPT.format(filename=src_file.name, source=source)
        response = None
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_EXTRACT_ATTEMPTS + 1):
            try:
                response = llm_client.generate(prompt, temperature=0.0)
                break
            except LLMQuotaExhaustedError:
                raise  # every remaining call would fail identically -- abort the whole run
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_EXTRACT_ATTEMPTS:
                    log.record("GHERKIN_RETRY", file=str(src_file), attempt=attempt, error=str(exc))
                    print(f"  [retry {attempt}/{_MAX_EXTRACT_ATTEMPTS - 1}] {src_file.name}: {exc}")
                    time.sleep(_RETRY_DELAY_SECONDS)

        if response is None:
            print(f"  [error] {src_file.name}: {last_exc} — skipping, will retry on next run")
            log.record("GHERKIN_ERROR", file=str(src_file), error=str(last_exc), attempts=_MAX_EXTRACT_ATTEMPTS)
            continue

        gherkin = _strip_fences(response.get("content", "").strip())

        # Trim any prose preamble — find the first Feature: line
        if "Feature:" in gherkin:
            gherkin = gherkin[gherkin.index("Feature:"):]
        else:
            print(f"  [skip] no Feature: header for {src_file.name}")
            log.record("GHERKIN_SKIP", file=str(src_file), reason="no Feature: header in response")
            continue

        feature_path.write_text(gherkin, encoding="utf-8")
        src_hash_path.write_text(current_src_sha, encoding="utf-8")

        log.record(
            "GHERKIN_EMIT",
            src_file=str(src_file),
            feature_file=str(feature_path),
            sha256=BootstrapAuditLog.sha256(feature_path),
            model=model or llm_client.model,
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
