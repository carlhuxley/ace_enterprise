"""Phase 1 of real-world trajectory ingestion (see benchmarks/tasks.py's
module docstring for how this complements the 30 synthetic tasks): parse
SWE-bench/OpenHands-format JSONL logs into a structured record, then feed
the real error tracebacks through the *existing* Reflector to check whether
it produces concrete, invariant-grounded analysis on genuine bugs -- not
just our hand-authored edge cases.

This is ingestion + qualitative inspection only. There is deliberately no
execution or pass/fail scoring here (that needs SWE-bench's per-instance
Docker images and is scoped separately as Phase 2) -- this module never
runs untrusted code, patches, or tests.

Three real, distinct schemas exist in the wild, confirmed live against
public sources rather than assumed -- two named candidates a prior pass at
this (Gemini's suggestion of princeton-nlp/SWE-bench_eval_logs,
SWE-Gym/SWE-Gym-Trajectories, all-hands/openhands-eval-logs) turned out not
to exist at all (HuggingFace returns the identical "Invalid username or
password" error for these as for a deliberately-made-up repo name), so
don't take dataset names on faith -- verify with
`curl https://huggingface.co/api/datasets/<name>` before building against one:

  - "predictions" format -- the standard SWE-bench leaderboard submission
    shape (e.g. the public OpenHandsCommunity/Devin-SWE-bench-output
    dataset on HuggingFace, confirmed via its dataset viewer -- note the
    org is OpenHandsCommunity, not OpenHands or all-hands, both of which
    also 404): instance_id, model_patch, model_name_or_path, pass_or_fail.
    This is the format most publicly available trajectory dumps actually
    use, and it carries NO traceback at all -- just the final patch and a
    pass/fail bit. Confirmed by downloading 20 real rows: 0/20 had a
    usable traceback. Useful for identifying *which* real instances a
    model failed, not *why*.

  - "eval_output" format -- OpenHands' own local evaluation harness output
    (see docs.openhands.dev/openhands/usage/developers/evaluation-harness,
    the EvalOutput dataclass): instance_id, instruction, test_result,
    metadata, history, metrics, error. Richer, and can carry a real
    traceback -- but test_result's internal structure is not fully
    documented publicly and appears to vary by benchmark/version.
    Extraction here is best-effort across several plausible field paths,
    not a guaranteed-correct parse. No confirmed-real public dataset for
    this shape was found; support here is speculative pending one.

  - "traceback_dataset" format -- waleko/SWE-bench-traceback on
    HuggingFace (1,850 rows, confirmed real and downloaded directly):
    the standard SWE-bench instance fields (repo, instance_id,
    base_commit, patch, test_patch, problem_statement, hints_text,
    FAIL_TO_PASS, PASS_TO_PASS, environment_setup_commit) plus an actual
    `traceback` field with the real pre-patch failure -- e.g. a genuine
    `ValueError: need more than 1 value to unpack` from
    DataDog/integrations-core's postgres.py. This is the one confirmed
    source that actually satisfies this phase's goal: real repos, real
    bugs, real tracebacks, no Docker required. FAIL_TO_PASS/PASS_TO_PASS
    are JSON-encoded strings (e.g. "[]"), and were empty in every row
    sampled -- don't rely on them being populated.

fetch_traceback_dataset_slice() pulls rows directly from HuggingFace's
public datasets-server HTTP API (no `datasets` library dependency, no
auth needed for this public dataset) for exactly this format.
"""
import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from src.core.reflector.module import Reflector
from src.storage.schemas import EnvironmentFeedback, GeneratorOutput, ReflectorOutput, TaskInput

_HF_DATASETS_SERVER = "https://datasets-server.huggingface.co/rows"
_TRACEBACK_DATASET = "waleko/SWE-bench-traceback"

# SWE-bench's own documented instance_id convention:
# "{repo_owner}__{repo_name}-{issue_or_pr_number}", e.g. "astropy__astropy-12907".
_INSTANCE_ID_RE = re.compile(r"^(?P<owner>[^_]+(?:_[^_]+)*)__(?P<repo>.+)-(?P<number>\d+)$")

# Plausible field paths for a traceback-like string inside an eval_output
# record's test_result -- tried in order, first non-empty match wins. Not a
# documented contract; OpenHands' own eval scripts vary this per benchmark.
_TEST_RESULT_TEXT_KEYS = ("report", "log", "output", "stdout", "stderr", "traceback", "message")

# When history entries are dicts (the common OpenHands trajectory shape),
# an observation step's payload is typically under one of these keys.
_HISTORY_CONTENT_KEYS = ("content", "observation", "message", "output")

_FAILURE_MARKERS = ("traceback", "assert", "failed", "error")


@dataclass(frozen=True)
class RealFailureCase:
    """A single real (not synthetic) SWE task instance, extracted from a
    trajectory/prediction log. Fields are best-effort: only instance_id is
    guaranteed non-None, since it's the one field both known formats always
    carry."""
    instance_id: str
    repo: str | None
    failing_tests: list[str]
    error_traceback: str | None
    patch_diff: str | None
    problem_statement: str | None
    resolved: bool | None  # None if the source record didn't say
    source_format: str  # "predictions" | "eval_output" | "unknown"

    def to_dict(self) -> dict:
        return asdict(self)


def _extract_repo_from_instance_id(instance_id: str) -> str | None:
    m = _INSTANCE_ID_RE.match(instance_id)
    if not m:
        return None
    return f"{m.group('owner')}/{m.group('repo')}"


def _detect_format(record: dict[str, Any]) -> str:
    if "traceback" in record and "patch" in record and "problem_statement" in record:
        return "traceback_dataset"
    if "model_patch" in record and "pass_or_fail" in record:
        return "predictions"
    if "test_result" in record or "history" in record:
        return "eval_output"
    return "unknown"


def _extract_traceback_from_test_result(test_result: Any) -> str | None:
    if test_result is None:
        return None
    if isinstance(test_result, str):
        return test_result.strip() or None
    if isinstance(test_result, dict):
        for key in _TEST_RESULT_TEXT_KEYS:
            value = test_result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        # Some harnesses nest the real report one level down, e.g.
        # {"report": {"failure_output": "..."}}.
        for value in test_result.values():
            if isinstance(value, dict):
                nested = _extract_traceback_from_test_result(value)
                if nested:
                    return nested
    return None


def _extract_traceback_from_history(history: Any) -> str | None:
    """Best-effort fallback: scan trajectory steps for an observation that
    looks like a failing test run (contains a recognizable failure marker),
    most-recent first."""
    if not isinstance(history, list):
        return None
    for step in reversed(history):
        text = None
        if isinstance(step, str):
            text = step
        elif isinstance(step, dict):
            for key in _HISTORY_CONTENT_KEYS:
                value = step.get(key)
                if isinstance(value, str) and value.strip():
                    text = value
                    break
        if text and any(marker in text.lower() for marker in _FAILURE_MARKERS):
            return text.strip()
    return None


def _extract_failing_tests(record: dict[str, Any]) -> list[str]:
    test_result = record.get("test_result")
    candidates: list[Any] = []
    if isinstance(test_result, dict):
        candidates = [
            test_result.get("FAIL_TO_PASS"),
            test_result.get("fail_to_pass"),
            test_result.get("failed_tests"),
        ]
    candidates.append(record.get("FAIL_TO_PASS"))
    for c in candidates:
        if isinstance(c, list) and c:
            return [str(t) for t in c]
        if isinstance(c, str) and c.strip():
            # Sometimes stored as a JSON-encoded string list.
            try:
                parsed = json.loads(c)
                if isinstance(parsed, list):
                    return [str(t) for t in parsed]
            except (json.JSONDecodeError, TypeError):
                pass
    return []


def parse_predictions_record(record: dict[str, Any]) -> RealFailureCase:
    instance_id = record["instance_id"]
    pass_or_fail = record.get("pass_or_fail")
    resolved = None
    if isinstance(pass_or_fail, str):
        resolved = pass_or_fail.strip().upper() in ("PASS", "PASSED", "RESOLVED", "TRUE")
    return RealFailureCase(
        instance_id=instance_id,
        repo=_extract_repo_from_instance_id(instance_id),
        failing_tests=[],
        error_traceback=None,  # never available in this format -- see module docstring
        patch_diff=record.get("model_patch") or None,
        problem_statement=None,
        resolved=resolved,
        source_format="predictions",
    )


def parse_eval_output_record(record: dict[str, Any]) -> RealFailureCase:
    instance_id = record["instance_id"]
    test_result = record.get("test_result")

    traceback_text = record.get("error") or None
    if not traceback_text:
        traceback_text = _extract_traceback_from_test_result(test_result)
    if not traceback_text:
        traceback_text = _extract_traceback_from_history(record.get("history"))

    resolved = None
    if isinstance(test_result, dict):
        for key in ("resolved", "success", "pass_or_fail"):
            if key in test_result:
                value = test_result[key]
                resolved = bool(value) if not isinstance(value, str) else value.strip().upper() in ("PASS", "TRUE", "RESOLVED")
                break

    patch_diff = None
    for key in ("model_patch", "git_patch"):
        value = record.get(key) or (test_result.get(key) if isinstance(test_result, dict) else None)
        if value:
            patch_diff = value
            break

    return RealFailureCase(
        instance_id=instance_id,
        repo=_extract_repo_from_instance_id(instance_id),
        failing_tests=_extract_failing_tests(record),
        error_traceback=traceback_text,
        patch_diff=patch_diff,
        problem_statement=record.get("instruction") or record.get("problem_statement"),
        resolved=resolved,
        source_format="eval_output",
    )


def parse_traceback_dataset_record(record: dict[str, Any]) -> RealFailureCase:
    """waleko/SWE-bench-traceback's schema -- the confirmed-real source
    with an actual traceback field. FAIL_TO_PASS/PASS_TO_PASS are
    JSON-encoded strings here, not lists; empty ("[]") in every row
    sampled during verification, so don't assume they're populated."""
    instance_id = record["instance_id"]
    traceback_text = record.get("traceback")
    if isinstance(traceback_text, str):
        traceback_text = traceback_text.strip() or None

    failing_tests: list[str] = []
    raw_fail_to_pass = record.get("FAIL_TO_PASS")
    if isinstance(raw_fail_to_pass, list):
        failing_tests = [str(t) for t in raw_fail_to_pass]
    elif isinstance(raw_fail_to_pass, str) and raw_fail_to_pass.strip():
        try:
            parsed = json.loads(raw_fail_to_pass)
            if isinstance(parsed, list):
                failing_tests = [str(t) for t in parsed]
        except (json.JSONDecodeError, TypeError):
            pass

    return RealFailureCase(
        instance_id=instance_id,
        repo=record.get("repo") or _extract_repo_from_instance_id(instance_id),
        failing_tests=failing_tests,
        error_traceback=traceback_text,
        patch_diff=record.get("patch") or None,
        problem_statement=record.get("problem_statement") or None,
        resolved=None,  # this dataset is pre-patch task data, not a graded attempt
        source_format="traceback_dataset",
    )


def parse_record(record: dict[str, Any]) -> RealFailureCase:
    fmt = _detect_format(record)
    if fmt == "traceback_dataset":
        return parse_traceback_dataset_record(record)
    if fmt == "predictions":
        return parse_predictions_record(record)
    if fmt == "eval_output":
        return parse_eval_output_record(record)
    # Unknown shape: preserve what little we can rather than raising, since
    # a real-world dump is likely to include a stray malformed line.
    return RealFailureCase(
        instance_id=record.get("instance_id", "<unknown>"),
        repo=_extract_repo_from_instance_id(record["instance_id"]) if record.get("instance_id") else None,
        failing_tests=[], error_traceback=None, patch_diff=None,
        problem_statement=None, resolved=None, source_format="unknown",
    )


def parse_trajectory_file(path: Path, include_resolved: bool = False) -> list[RealFailureCase]:
    """Parse a JSONL file of SWE-bench/OpenHands records. By default returns
    only unresolved (failed, or unknown-outcome) instances, since ingestion
    exists to analyze failures -- pass include_resolved=True to keep
    everything."""
    cases = []
    with path.open() as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_no}: invalid JSON ({e})") from e
            cases.append(parse_record(record))

    if include_resolved:
        return cases
    return [c for c in cases if c.resolved is not True]


def fetch_traceback_dataset_slice(
    offset: int = 0, length: int = 20, timeout: float = 30.0,
) -> list[RealFailureCase]:
    """Pull `length` rows starting at `offset` from waleko/SWE-bench-traceback
    via HuggingFace's public datasets-server HTTP API -- no `datasets`
    library, no auth (the dataset is public). Network call; raises
    httpx.HTTPError on failure rather than swallowing it, since a caller
    building a real evaluation slice needs to know if the fetch failed
    rather than silently getting zero cases."""
    response = httpx.get(
        _HF_DATASETS_SERVER,
        params={
            "dataset": _TRACEBACK_DATASET, "config": "default",
            "split": "train", "offset": offset, "length": length,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    return [parse_record(row["row"]) for row in data["rows"]]


def reflect_on_real_failure(
    reflector: Reflector, case: RealFailureCase,
) -> ReflectorOutput | None:
    """Run the existing Reflector on one real failure case's traceback.
    Returns None (not an error) when the case has no traceback to analyze
    -- expected and common for "predictions"-format cases; see module
    docstring."""
    if not case.error_traceback:
        return None

    task_input = TaskInput(
        id=case.instance_id,
        query=case.problem_statement or f"Fix the failing test(s) in {case.repo or case.instance_id}",
        type="code_generation",
        difficulty="hard",
        context={"repo": case.repo or "", "source": "swebench_ingest"},
    )
    generator_output = GeneratorOutput(
        trajectory="", solution=case.patch_diff or "",
        bullets_used=[], bullet_feedback={}, latency_ms=0, tokens_used=0,
    )
    env_feedback = EnvironmentFeedback(
        result="FAILED",
        feedback=case.error_traceback[:4000],
        test_report={"failing_tests": case.failing_tests, "traceback": case.error_traceback},
    )
    return reflector.reflect(task_input, generator_output, env_feedback)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--input", type=Path, default=None,
        help="SWE-bench/OpenHands JSONL trajectory file (mutually exclusive with --fetch-traceback-dataset)",
    )
    parser.add_argument(
        "--fetch-traceback-dataset", type=int, default=None, metavar="N",
        help=(
            "Fetch N rows directly from waleko/SWE-bench-traceback on "
            "HuggingFace instead of reading a local file (network call, "
            "no auth needed -- the dataset is public)."
        ),
    )
    parser.add_argument("--out", type=Path, default=None, help="Write parsed RealFailureCase records as JSON")
    parser.add_argument(
        "--include-resolved", action="store_true",
        help="Keep resolved/passing instances too (default: failures only)",
    )
    args = parser.parse_args(argv)

    if bool(args.input) == bool(args.fetch_traceback_dataset):
        parser.error("exactly one of --input or --fetch-traceback-dataset is required")

    if args.fetch_traceback_dataset:
        cases = fetch_traceback_dataset_slice(length=args.fetch_traceback_dataset)
        if not args.include_resolved:
            cases = [c for c in cases if c.resolved is not True]
        source_desc = f"waleko/SWE-bench-traceback[:{args.fetch_traceback_dataset}]"
    else:
        cases = parse_trajectory_file(args.input, include_resolved=args.include_resolved)
        source_desc = str(args.input)

    n_with_traceback = sum(1 for c in cases if c.error_traceback)
    by_format: dict[str, int] = {}
    for c in cases:
        by_format[c.source_format] = by_format.get(c.source_format, 0) + 1

    print(f"Parsed {len(cases)} case(s) from {source_desc}")
    for fmt, n in sorted(by_format.items()):
        print(f"  {fmt}: {n}")
    print(f"With a usable error_traceback: {n_with_traceback}/{len(cases)}")
    if by_format.get("predictions") and n_with_traceback == 0:
        print(
            "\nNote: 'predictions'-format records never carry a traceback "
            "(see module docstring) -- nothing here can be fed to the "
            "Reflector. An OpenHands eval_output-format file is needed for that."
        )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps([c.to_dict() for c in cases], indent=2))
        print(f"\nWrote {len(cases)} case(s) to {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
