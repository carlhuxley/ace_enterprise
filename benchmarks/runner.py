"""Steps 2 & 3 of the ACE pre-launch proof: a 3-arm ablation isolating the
causal effect of ACE's curated playbook from the baseline stochasticity of
simply retrying with a raw error message.

For each task:
  Arm 1 (zero-shot)    - generate from the spec alone, no playbook context of
                         any kind (even bullets curated by earlier tasks in
                         this same run are withheld here, so Pass@1 stays a
                         clean, comparable baseline). Run against the task's
                         pytest suite inside the sandbox (bandit gate
                         included -- see PodmanOrchestrator).
  Curate               - on failure, run the real Reflector -> Curator
                         pipeline on Arm 1's failure and apply the resulting
                         delta bullets to the (session-accumulated) playbook.
  Arm 2 (blind retry)  - control. Re-prompt with the exact same spec, the
                         Arm 1 failing code, and its raw pytest failure
                         output -- but no curated bullets. Isolates "did the
                         model just need a second look at its own error."
  Arm 3 (ACE playbook) - experimental. Identical prompt to Arm 2, plus the
                         curated bullets appended. Arm 2 and Arm 3 differ in
                         exactly one thing -- the playbook heuristics -- so
                         any gap between them is attributable to curation,
                         not to prompt differences or model stochasticity.

Net causal uplift = ace_recovery_rate - control_recovery_rate, computed over
the subset of tasks that failed Arm 1 (see BenchmarkReport.summary()). A
uplift near zero means the model only needed to see its own error trace and
the curation layer added nothing; a large positive uplift is the actual
evidence that ACE's playbook -- not token-sampling jitter -- rescued those
tasks.

Playbook context (Arm 3 only) is built directly from
PlaybookManager.get_all_bullets() rather than via
src.core.generator.module.Generator: Curator seeds new bullets at
confidence_score=0.3 pending human review (see apply_delta in
src/playbook/manager.py), which is below BulletRetriever.retrieve()'s
default min_confidence=0.5 -- going through Generator would silently starve
Arm 3 of the very bullet curation just wrote. Reflector and Curator
themselves are used unmodified; only the Generator's LLM-calling half is
replaced with a direct, code-focused prompt.

A single run's net_causal_uplift is noisy on a small failure set (N of
order 10) -- pass --runs N (N=3-5) to repeat the whole ablation across N
independent, freshly-playbooked trials and report mean +/- stdev instead of
a single point estimate. Meaningless at --temperature 0.0 (greedy decoding
is deterministic: every run would be identical).

Usage:
    .venv/bin/python -m benchmarks.runner --model qwen2.5-coder:7b --tasks 30
    .venv/bin/python -m benchmarks.runner --model qwen2.5-coder:7b --provider ollama --sandbox podman
    .venv/bin/python -m benchmarks.runner --model qwen/qwen-2.5-coder-32b-instruct --provider openrouter
    .venv/bin/python -m benchmarks.runner --model qwen2.5-coder:7b --runs 5
"""
import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.sandbox import LocalSubprocessRunner, build_podman_runner
from benchmarks.tasks import BenchmarkTask, Domain, get_tasks
from src.agents.language_pod import PhaseResult
from src.agents.podman_orchestrator import PodmanOrchestrator
from src.core.curator.module import Curator
from src.core.reflector.module import Reflector
from src.playbook.manager import PlaybookManager
from src.storage.schemas import Bullet, EnvironmentFeedback, GeneratorOutput, TaskInput
from src.utils.code_extraction import extract_code
from src.utils.llm_client import LLMClient

REPORTS_DIR = Path(__file__).parent / "reports"

CODE_SYSTEM_PROMPT = (
    "You are an expert Python engineer completing a coding benchmark task. "
    "If a '# Lessons Learned' section is present, it was extracted from real "
    "mistakes on earlier tasks -- apply every rule in it. Return ONLY the "
    "requested code as a single ```python code block, with no explanation "
    "before or after it."
)

MAX_CONTEXT_BULLETS = 12
# Tail of pytest output actually shown to the model in a retry prompt --
# keeps the prompt bounded on long traceback/bandit dumps.
MAX_ERROR_CHARS = 2000


@dataclass
class TaskRunResult:
    task_id: str
    domain: str
    title: str
    trap: str
    pass_arm1_zero_shot: bool
    pass_arm2_control_blind: bool | None  # None if Arm 1 already passed (no retry needed)
    pass_arm3_ace_playbook: bool | None
    bullets_curated: int
    curated_bullet_contents: list[str]
    arm1_error: str | None
    arm2_error: str | None
    arm3_error: str | None
    # Normalized one-line-ish summary of arm*_error (see _failure_signature),
    # e.g. "FAILED test_x - TypeError: Passing coroutines is forbidden..." or
    # "TIMEOUT". Lets error *progression* across arms be compared
    # programmatically instead of eyeballing full tracebacks -- found doing
    # this by hand for conc_first_to_finish: Arm 3 reliably progressed past
    # Arm 2's mistake (wrapping coroutines in tasks) even in runs where it
    # still didn't fully pass, which pass/fail alone hides completely.
    arm1_signature: str | None
    arm2_signature: str | None
    arm3_signature: str | None
    arm1_tokens: int
    arm2_tokens: int
    arm3_tokens: int
    # Reflector.reflect() (up to max_refinement_rounds LLM calls internally)
    # and Curator.curate() (one call) were previously untracked -- only the
    # three generation arms had a token count at all, so any total-cost
    # estimate for a run was silently missing these two calls per failing
    # task. 0 when Arm 1 passed (neither ever runs) or on total curate/reflect
    # failure before any LLM call completed.
    reflect_tokens: int
    curate_tokens: int


@dataclass
class BenchmarkReport:
    model: str
    provider: str
    sandbox: str
    playbook_id: str
    started_at: str
    finished_at: str
    temperature: float = 0.2
    # False (default): strict ablation -- Arm 1 is a clean, order-independent
    # zero-shot baseline; the report's net_causal_uplift isolates the
    # playbook's causal contribution (recommended for the primary proof).
    # True: Arm 1 uses bullets accumulated from earlier tasks in this run --
    # tells the complementary "online institutional memory over a session"
    # story instead. Run both ways rather than blending them into one number.
    sequential: bool = False
    results: list[TaskRunResult] = field(default_factory=list)

    def summary(self) -> dict:
        return _summarize(self.results)


@dataclass
class MultiRunReport:
    """N independent trials of the same 3-arm benchmark, for variance
    estimates on top of a single run's point estimate.

    Found necessary by direct comparison: qwen2.5-coder:7b on this 30-task
    bank measured +25% net causal uplift at temperature=0.2 and +0% at
    temperature=0.0 (greedy) -- with only 8 failing tasks, a single task
    flipping arms swings the recovery rate by 1/8 = 12.5 points. A single
    run's uplift figure isn't a reliable number on its own; report a mean
    and stdev across several independent trials instead.
    """
    model: str
    provider: str
    sandbox: str
    temperature: float
    runs: list[BenchmarkReport] = field(default_factory=list)

    def aggregate(self) -> dict:
        summaries = [r.summary() for r in self.runs]

        def series(*key_path: str) -> list[float]:
            values = []
            for s in summaries:
                d: dict = s
                for k in key_path:
                    d = d[k]
                values.append(d)
            return values

        def stats(values: list[float]) -> dict:
            n = len(values)
            return {
                "values": [round(v, 4) for v in values],
                "mean": round(statistics.mean(values), 4) if values else 0.0,
                # Sample stdev (n-1): these are independent trials estimating
                # a population value, not the population itself. Undefined
                # (0.0) for a single run -- there's nothing to estimate
                # variance from.
                "std": round(statistics.stdev(values), 4) if n > 1 else 0.0,
                "n": n,
            }

        return {
            "n_runs": len(self.runs),
            "pass_at_1_rate": stats(series("pass_at_1_zero_shot", "rate")),
            "control_recovery_rate": stats(series("pass_at_2_control_blind", "recovery_rate")),
            "ace_recovery_rate": stats(series("pass_at_2_ace_playbook", "recovery_rate")),
            "net_causal_uplift": stats(series("net_causal_uplift")),
            "total_tokens_all_runs": sum(series("total_tokens")),
        }


def _summarize(results: list[TaskRunResult], include_by_domain: bool = True) -> dict:
    n = len(results)
    pass1 = sum(1 for r in results if r.pass_arm1_zero_shot)
    failed_arm1 = [r for r in results if not r.pass_arm1_zero_shot]
    n_failed = len(failed_arm1)

    control_rescued = sum(1 for r in failed_arm1 if r.pass_arm2_control_blind)
    ace_rescued = sum(1 for r in failed_arm1 if r.pass_arm3_ace_playbook)

    pass1_rate = pass1 / n if n else 0.0
    pass2_control_rate = (pass1 + control_rescued) / n if n else 0.0
    pass2_ace_rate = (pass1 + ace_rescued) / n if n else 0.0
    control_recovery_rate = control_rescued / n_failed if n_failed else 0.0
    ace_recovery_rate = ace_rescued / n_failed if n_failed else 0.0
    net_causal_uplift = ace_recovery_rate - control_recovery_rate

    # Error progression: among tasks where BOTH retries still failed (no
    # pass/fail signal at all), did the playbook at least change *what* the
    # model got wrong? A pass/fail-only view can't distinguish "ACE made no
    # difference" from "ACE fixed the first bug but a second one was still
    # there" -- found needing this the hard way for conc_first_to_finish,
    # where Arm 3 reliably progressed past Arm 2's exact mistake (never
    # wrapping coroutines in tasks) in every run, yet still failed on a
    # second bug (`next(done)` vs `next(iter(done))`) the curated bullets
    # never mentioned -- net_causal_uplift alone reports that as "no effect".
    still_failing_both = [
        r for r in failed_arm1
        if r.pass_arm2_control_blind is False and r.pass_arm3_ace_playbook is False
    ]
    changed_approach = sum(
        1 for r in still_failing_both if r.arm2_signature != r.arm3_signature
    )

    by_domain: dict[str, dict] = {}
    if include_by_domain:
        for domain in sorted({r.domain for r in results}):
            by_domain[domain] = _summarize(
                [r for r in results if r.domain == domain], include_by_domain=False
            )

    return {
        "n_tasks": n,
        "pass_at_1_zero_shot": {"count": pass1, "rate": round(pass1_rate, 4)},
        "n_failed_arm1": n_failed,
        "pass_at_2_control_blind": {
            "count": pass1 + control_rescued,
            "rate": round(pass2_control_rate, 4),
            "recovered": control_rescued,
            "recovery_rate": round(control_recovery_rate, 4),
        },
        "pass_at_2_ace_playbook": {
            "count": pass1 + ace_rescued,
            "rate": round(pass2_ace_rate, 4),
            "recovered": ace_rescued,
            "recovery_rate": round(ace_recovery_rate, 4),
        },
        "net_causal_uplift": round(net_causal_uplift, 4),
        "ace_changed_approach_when_still_failing": {
            "count": changed_approach,
            "of": len(still_failing_both),
        },
        "total_bullets_curated": sum(r.bullets_curated for r in results),
        "total_tokens": sum(
            r.arm1_tokens + r.arm2_tokens + r.arm3_tokens + r.reflect_tokens + r.curate_tokens
            for r in results
        ),
        "by_domain": by_domain,
    }


def _select_context_bullets(
    all_bullets: list[Bullet], domain: Domain, tags: list[str] | None = None,
) -> list[Bullet]:
    """`domain` (e.g. "numeric_edge_cases") is a coarse bucket shared by up
    to 10 genuinely unrelated tasks in this task bank -- a bullet curated
    for one task's bug passes the domain filter for every other task in the
    same domain even though it has nothing to do with their bugs. Found via
    forensic analysis of a real run: by the time num_currency_cents's Arm 3
    ran, 21 domain-tagged-but-task-irrelevant bullets from three earlier
    numeric tasks were already sitting in the playbook, and up to 12 of them
    (MAX_CONTEXT_BULLETS) were being handed to the model alongside the 6
    bullets actually about currency parsing -- Arm 3 lost to a blind retry
    on that task in 5/5 runs. When `tags` is given (Arm 3's retry only --
    NOT Arm 1's `sequential` bullets, which deliberately test the broader
    "does session-accumulated knowledge help" question), require at least
    one tag in common on top of the domain filter, scoping context down to
    bullets actually about this task's own bug.
    """
    relevant = [
        b for b in all_bullets
        if not b.applicable_domains or domain in b.applicable_domains
    ]
    if tags:
        relevant = [b for b in relevant if any(t in (b.tags or []) for t in tags)]
    # Most-recently-added first, capped so the prompt doesn't grow unbounded
    # over a long run.
    return list(reversed(relevant))[:MAX_CONTEXT_BULLETS]


def _build_zero_shot_prompt(task: BenchmarkTask, bullets: list[Bullet] | None = None) -> str:
    """Arm 1: the spec alone by default -- no playbook bullets, which is what
    makes Pass@1 a stable, order-independent baseline for the strict causal
    ablation (the default; see run_benchmark's `sequential` param). Passing
    `bullets` switches to the complementary "sequential" story instead: does
    the playbook accumulated so far in this run help a task's FIRST attempt,
    not just its retry. The two stories answer different questions and
    shouldn't be blended into one number -- run once each way instead."""
    if not bullets:
        return task.prompt
    lines = "\n".join(f"- {b.content}" for b in bullets)
    return f"{task.prompt}\n\n# Lessons Learned (from earlier tasks -- apply these)\n{lines}"


def _build_retry_prompt(
    task: BenchmarkTask,
    failing_code: str,
    error_trace: str,
    bullets: list[Bullet] | None,
) -> str:
    """Shared base for Arm 2 (control) and Arm 3 (ACE): identical spec,
    failing code, and error trace. `bullets` is the only thing allowed to
    differ between the two calling arms -- that's what isolates the
    playbook's causal contribution."""
    prompt = (
        f"{task.prompt}\n\n"
        f"Your previous attempt:\n```python\n{failing_code}\n```\n\n"
        f"Test failure output:\n```\n{error_trace[-MAX_ERROR_CHARS:]}\n```\n\n"
        "Fix the code so all tests pass."
    )
    if bullets:
        lines = "\n".join(f"- {b.content}" for b in bullets)
        prompt += f"\n\n# Lessons Learned (from earlier tasks -- apply these)\n{lines}"
    return prompt


def _generate(llm: LLMClient, prompt: str, temperature: float) -> tuple[str, str, int]:
    """Returns (raw_content, extracted_code, tokens_used)."""
    response = llm.generate(prompt=prompt, system_prompt=CODE_SYSTEM_PROMPT, temperature=temperature)
    code = extract_code(response["content"])
    return response["content"], code, response.get("tokens_used", 0)


def _wrap_llm_with_token_counter(llm: LLMClient) -> list[int]:
    """Monkey-patch llm.generate to accumulate tokens_used into a mutable
    single-element list (same pattern as PythonLanguagePod._intercept_tokens
    in src/agents/python_language_pod.py). Reflector.reflect() (up to
    max_refinement_rounds internal LLM calls) and Curator.curate() (one
    call) call this same llm instance but return no token count of their
    own -- bracketing a call with a before/after snapshot of the returned
    counter measures its cost without touching either module.
    """
    counter = [0]
    original_generate = llm.generate

    def _tracking_generate(*args, **kwargs):
        result = original_generate(*args, **kwargs)
        counter[0] += result.get("tokens_used", 0)
        return result

    llm.generate = _tracking_generate
    return counter


def _failure_text(phase: PhaseResult) -> str:
    """Combine a failed PhaseResult's stdout and stderr into one string.

    `phase.error or phase.output` (the original approach) picks whichever is
    non-empty FIRST -- but pytest writes the actual assertion failure to
    stdout, while stderr can be empty, or can hold something else entirely
    (PodmanOrchestrator's "Security gate: ..." message on a bandit HIGH
    finding, but also just incidental noise -- e.g. asyncio's default
    exception handler prints "Task exception was never retrieved" to stderr
    for an un-awaited failed Task). When stderr happens to be non-empty for
    an unrelated reason, `or` silently drops the real pytest failure and the
    retry/Reflector never sees it at all (found via forensic analysis of a
    real run: benchmarks/reports/20260825T205139Z_qwen2.5-coder_7b.json,
    conc_graceful_shutdown). Concatenating both is strictly safer.
    """
    parts = [p for p in (phase.output, phase.error) if p]
    return "\n".join(parts)


def _failure_signature(failure_text: str | None) -> str | None:
    """Normalize a failed arm's raw output into a short, comparable
    signature -- the specific exception/assertion, not the full traceback.

    Lets error *progression* be measured programmatically instead of
    eyeballed diffs between arm2_error/arm3_error: e.g. did Arm 3 fail on a
    literally different bug than Arm 2, or on exactly the same one? Used by
    _summarize()'s "ace_changed_approach_when_still_failing" metric.
    """
    if not failure_text:
        return None
    if "generation error" in failure_text:
        return f"GENERATION_ERROR: {failure_text.split('generation error:', 1)[-1].strip()[:200]}"
    if "timed out" in failure_text.lower():
        return "TIMEOUT"
    if "Security gate:" in failure_text:
        line = next(
            (l for l in failure_text.splitlines() if l.startswith("Security gate:")),
            "Security gate",
        )
        return line.strip()

    lines = failure_text.splitlines()

    # Prefer pytest's own "short test summary info" section: one compact
    # "FAILED <test> - <ExceptionType>: <message>" line per failing test --
    # already pytest-truncated to a sane length, and there's one per test
    # if several failed, which a single "last E line" wouldn't capture.
    try:
        start = next(i for i, l in enumerate(lines) if "short test summary info" in l)
    except StopIteration:
        start = None
    if start is not None:
        summary_lines = []
        for l in lines[start + 1:]:
            if l.strip().startswith("="):
                break
            if l.strip():
                summary_lines.append(l.strip())
        if summary_lines:
            return " | ".join(summary_lines)

    # Fall back to pytest's "E   ..." traceback line(s) -- more detail than
    # the summary section alone, when present without one (e.g. a single
    # assertion with a long diff pytest didn't compress into the summary).
    e_lines = [l.strip()[2:].strip() for l in lines if l.strip().startswith("E ")]
    if e_lines:
        return e_lines[-1]

    # Last resort: no recognizable pytest structure at all (e.g. a
    # collection-time crash, or pure incidental warning noise) -- the first
    # non-empty line is still more useful than nothing.
    for l in lines:
        if l.strip():
            return l.strip()[:200]
    return "UNKNOWN"


def run_benchmark(
    tasks: list[BenchmarkTask],
    model: str,
    provider: str,
    sandbox: str,
    playbook_id: str,
    llm_timeout: float | None = None,
    playbook_storage_path: str | None = None,
    temperature: float = 0.2,
    sequential: bool = False,
    verbose: bool = True,
) -> BenchmarkReport:
    llm = LLMClient(provider=provider, model=model)
    if llm_timeout is not None:
        # LLMClient hardcodes a 120s HTTP timeout tuned for cloud APIs; local
        # open-weight models on modest (e.g. CPU-only) hardware routinely
        # need longer than that per call.
        llm.timeout = llm_timeout
    # playbook_storage_path defaults to PlaybookManager's own default
    # (data/playbooks/) when None -- overridable so tests can point it at a
    # tmp_path instead of touching real repo state.
    playbook_manager = PlaybookManager(storage_path=playbook_storage_path)
    playbook_manager.get_or_create_playbook(playbook_id, domain="benchmark_proof")
    reflector = Reflector(llm_client=llm)
    curator = Curator(playbook_manager=playbook_manager, llm_client=llm)
    token_counter = _wrap_llm_with_token_counter(llm)

    if sandbox == "podman":
        runner = build_podman_runner(container_name=f"ace_bench_{int(time.time())}")
    else:
        runner = LocalSubprocessRunner()
    orchestrator = PodmanOrchestrator(runner=runner, started=False)

    started_at = datetime.now(timezone.utc).isoformat()
    results: list[TaskRunResult] = []

    try:
        for i, task in enumerate(tasks, 1):
            if verbose:
                print(f"\n[{i}/{len(tasks)}] {task.id} ({task.domain}) -- {task.title}")

            # --- Arm 1: zero-shot baseline (or session-accumulated, see
            # `sequential`) ------------------------------------------------
            try:
                arm1_bullets = (
                    _select_context_bullets(playbook_manager.get_all_bullets(playbook_id), task.domain)
                    if sequential else None
                )
                raw1, code1, tokens1 = _generate(
                    llm, _build_zero_shot_prompt(task, arm1_bullets), temperature
                )
            except Exception as exc:
                if verbose:
                    print(f"  arm 1 (zero-shot): ERROR ({exc})")
                arm1_error = f"generation error: {exc}"
                results.append(TaskRunResult(
                    task_id=task.id, domain=task.domain, title=task.title, trap=task.trap,
                    pass_arm1_zero_shot=False, pass_arm2_control_blind=None,
                    pass_arm3_ace_playbook=None, bullets_curated=0, curated_bullet_contents=[],
                    arm1_error=arm1_error, arm2_error=None, arm3_error=None,
                    arm1_signature=_failure_signature(arm1_error), arm2_signature=None, arm3_signature=None,
                    arm1_tokens=0, arm2_tokens=0, arm3_tokens=0, reflect_tokens=0, curate_tokens=0,
                ))
                continue

            phase1 = orchestrator.pulse({"solution.py": code1, "test_solution.py": task.test_code})
            if verbose:
                print(f"  arm 1 (zero-shot): {'PASS' if phase1.passed else 'FAIL'}")

            pass_arm2: bool | None = None
            pass_arm3: bool | None = None
            arm2_error: str | None = None
            arm3_error: str | None = None
            tokens2 = tokens3 = 0
            reflect_tokens = curate_tokens = 0
            curated_contents: list[str] = []

            if not phase1.passed:
                error_trace = _failure_text(phase1)

                # --- Arm 2: blind retry control (no playbook bullets) ----
                try:
                    _, code2, tokens2 = _generate(
                        llm, _build_retry_prompt(task, code1, error_trace, bullets=None), temperature
                    )
                    phase2 = orchestrator.pulse({"solution.py": code2, "test_solution.py": task.test_code})
                    pass_arm2 = phase2.passed
                    arm2_error = None if phase2.passed else _failure_text(phase2)
                    if verbose:
                        print(f"  arm 2 (control):   {'PASS' if pass_arm2 else 'FAIL'}")
                except Exception as exc:
                    if verbose:
                        print(f"  arm 2 (control):   ERROR ({exc})")
                    pass_arm2 = False
                    arm2_error = f"generation error: {exc}"

                # --- Reflect + Curate on Arm 1's failure ------------------
                try:
                    task_input = TaskInput(
                        id=task.id, query=task.prompt, type="code_generation",
                        difficulty="hard", context={"domain": task.domain},
                    )
                    generator_output = GeneratorOutput(
                        trajectory=raw1, solution=code1, bullets_used=[],
                        bullet_feedback={}, latency_ms=0, tokens_used=tokens1,
                    )
                    env_feedback = EnvironmentFeedback(
                        result="FAILED",
                        feedback=error_trace[:4000],
                        test_report={"stdout": phase1.output, "error": phase1.error},
                    )
                    tokens_before = token_counter[0]
                    reflector_output = reflector.reflect(task_input, generator_output, env_feedback)
                    reflect_tokens = token_counter[0] - tokens_before

                    tokens_before = token_counter[0]
                    curator_output = curator.curate(
                        reflector_output=reflector_output,
                        playbook_id=playbook_id,
                        task_context={"applicable_domains": [task.domain], "tags": task.tags},
                    )
                    curate_tokens = token_counter[0] - tokens_before

                    added = playbook_manager.apply_delta(playbook_id, curator_output.delta_bullets)
                    curated_contents = [b.content for b in added]
                    if verbose:
                        print(f"  curated:           {len(added)} bullet(s)")
                        for b in added:
                            print(f"    + [{b.section}] {b.content[:100]}")
                except Exception as exc:
                    if verbose:
                        print(f"  curate:            ERROR ({exc})")

                # --- Arm 3: ACE playbook (same base prompt as Arm 2 + bullets) --
                try:
                    context_bullets = _select_context_bullets(
                        playbook_manager.get_all_bullets(playbook_id), task.domain, tags=task.tags
                    )
                    _, code3, tokens3 = _generate(
                        llm, _build_retry_prompt(task, code1, error_trace, bullets=context_bullets), temperature
                    )
                    phase3 = orchestrator.pulse({"solution.py": code3, "test_solution.py": task.test_code})
                    pass_arm3 = phase3.passed
                    arm3_error = None if phase3.passed else _failure_text(phase3)
                    if verbose:
                        print(f"  arm 3 (ACE):       {'PASS' if pass_arm3 else 'FAIL'}")
                except Exception as exc:
                    if verbose:
                        print(f"  arm 3 (ACE):       ERROR ({exc})")
                    pass_arm3 = False
                    arm3_error = f"generation error: {exc}"

            arm1_error = None if phase1.passed else _failure_text(phase1)
            results.append(TaskRunResult(
                task_id=task.id,
                domain=task.domain,
                title=task.title,
                trap=task.trap,
                pass_arm1_zero_shot=phase1.passed,
                pass_arm2_control_blind=pass_arm2,
                pass_arm3_ace_playbook=pass_arm3,
                bullets_curated=len(curated_contents),
                curated_bullet_contents=curated_contents,
                arm1_error=arm1_error,
                arm2_error=arm2_error,
                arm3_error=arm3_error,
                arm1_signature=_failure_signature(arm1_error),
                arm2_signature=_failure_signature(arm2_error),
                arm3_signature=_failure_signature(arm3_error),
                arm1_tokens=tokens1,
                arm2_tokens=tokens2,
                arm3_tokens=tokens3,
                reflect_tokens=reflect_tokens,
                curate_tokens=curate_tokens,
            ))
    finally:
        orchestrator.stop()

    finished_at = datetime.now(timezone.utc).isoformat()
    return BenchmarkReport(
        model=model, provider=provider, sandbox=sandbox, playbook_id=playbook_id,
        started_at=started_at, finished_at=finished_at, temperature=temperature,
        sequential=sequential, results=results,
    )


def run_multi_benchmark(
    tasks: list[BenchmarkTask],
    model: str,
    provider: str,
    sandbox: str,
    playbook_id: str,
    runs: int,
    llm_timeout: float | None = None,
    playbook_storage_path: str | None = None,
    temperature: float = 0.2,
    sequential: bool = False,
    verbose: bool = True,
) -> MultiRunReport:
    """Run `run_benchmark` `runs` times and return all of them plus aggregate
    stats. Each trial gets its own playbook_id (`{playbook_id}_run{i}`) so
    trials are independent -- reusing one playbook across runs would let run
    2 inherit run 1's curated bullets, which isn't a second independent
    sample of the same distribution, it's a continuation of the first."""
    if runs > 1 and temperature == 0.0 and verbose:
        print(
            "WARNING: --temperature 0.0 is deterministic (greedy decoding) -- "
            "every run will produce identical results and report zero "
            "variance. Use a non-zero temperature for a meaningful multi-run "
            "estimate.\n"
        )

    reports: list[BenchmarkReport] = []
    for i in range(runs):
        run_playbook_id = playbook_id if runs == 1 else f"{playbook_id}_run{i + 1}"
        if verbose:
            print(f"\n{'#' * 72}\n# Run {i + 1}/{runs}  (playbook_id={run_playbook_id})\n{'#' * 72}")
        reports.append(run_benchmark(
            tasks=tasks, model=model, provider=provider, sandbox=sandbox,
            playbook_id=run_playbook_id, llm_timeout=llm_timeout,
            playbook_storage_path=playbook_storage_path, temperature=temperature,
            sequential=sequential, verbose=verbose,
        ))

    return MultiRunReport(model=model, provider=provider, sandbox=sandbox, temperature=temperature, runs=reports)


def print_summary(report: BenchmarkReport) -> None:
    s = report.summary()
    mode = "sequential (Arm 1 uses session-accumulated bullets)" if report.sequential else "strict ablation (Arm 1 is clean zero-shot)"
    print("\n" + "=" * 72)
    print(f"ACE 3-arm benchmark -- {report.model} ({report.provider}), sandbox={report.sandbox}")
    print(f"mode={mode}  temperature={report.temperature}")
    print("=" * 72)
    p1, p2c, p2a = s["pass_at_1_zero_shot"], s["pass_at_2_control_blind"], s["pass_at_2_ace_playbook"]
    print(f"Tasks run              : {s['n_tasks']}  (failed Arm 1: {s['n_failed_arm1']})")
    print(f"Pass@1 (zero-shot)     : {p1['count']}/{s['n_tasks']}  ({p1['rate']:.1%})")
    print(
        f"Pass@2 control (blind) : {p2c['count']}/{s['n_tasks']}  ({p2c['rate']:.1%})"
        f"   recovered {p2c['recovered']}/{s['n_failed_arm1']}  ({p2c['recovery_rate']:.1%} of failures)"
    )
    print(
        f"Pass@2 ACE (playbook)  : {p2a['count']}/{s['n_tasks']}  ({p2a['rate']:.1%})"
        f"   recovered {p2a['recovered']}/{s['n_failed_arm1']}  ({p2a['recovery_rate']:.1%} of failures)"
    )
    print(f"Net causal uplift      : {s['net_causal_uplift']:+.1%}  (ACE recovery rate - control recovery rate)")
    ca = s["ace_changed_approach_when_still_failing"]
    print(
        f"Changed approach       : {ca['count']}/{ca['of']}  (still failing both arms, but Arm 3's "
        f"mistake differed from Arm 2's -- see arm2_signature/arm3_signature per task)"
    )
    print(f"Bullets curated        : {s['total_bullets_curated']}")
    print(f"Total tokens (all calls): {s['total_tokens']}  (generation + Reflector + Curator)")
    print("\nBy domain (net causal uplift):")
    for domain, d in s["by_domain"].items():
        print(
            f"  {domain:26s} pass@1={d['pass_at_1_zero_shot']['count']}/{d['n_tasks']}"
            f"  control_recovery={d['pass_at_2_control_blind']['recovery_rate']:.1%}"
            f"  ace_recovery={d['pass_at_2_ace_playbook']['recovery_rate']:.1%}"
            f"  uplift={d['net_causal_uplift']:+.1%}"
        )
    print("=" * 72)


def print_multi_summary(multi: MultiRunReport) -> None:
    agg = multi.aggregate()
    n = agg["n_runs"]
    label_w = 8
    col_w = 20  # wide enough for the longest cell: "100.0% +/- 100.0%"
    print("\n" + "=" * 72)
    print(f"ACE 3-arm benchmark -- {multi.model} ({multi.provider}), {n} runs, temperature={multi.temperature}")
    print("=" * 72)
    print(
        f"{'Run':<{label_w}}{'Pass@1':>{col_w}}{'Control rec.':>{col_w}}"
        f"{'ACE rec.':>{col_w}}{'Net uplift':>{col_w}}"
    )
    for i in range(n):
        p1 = agg["pass_at_1_rate"]["values"][i]
        cr = agg["control_recovery_rate"]["values"][i]
        ar = agg["ace_recovery_rate"]["values"][i]
        up = agg["net_causal_uplift"]["values"][i]
        print(
            f"{i + 1:<{label_w}}{p1:>{col_w}.1%}{cr:>{col_w}.1%}"
            f"{ar:>{col_w}.1%}{up:>+{col_w}.1%}"
        )
    print("-" * 72)

    def fmt(stat: dict) -> str:
        return f"{stat['mean']:.1%} +/- {stat['std']:.1%}"

    print(
        f"{'Mean':<{label_w}}{fmt(agg['pass_at_1_rate']):>{col_w}}"
        f"{fmt(agg['control_recovery_rate']):>{col_w}}"
        f"{fmt(agg['ace_recovery_rate']):>{col_w}}{fmt(agg['net_causal_uplift']):>{col_w}}"
    )
    print(f"Total tokens (all {n} runs, all calls): {agg['total_tokens_all_runs']}")
    print("=" * 72)
    if n < 3:
        print(f"NOTE: only {n} run(s) -- treat this std as illustrative, not a real confidence interval.")
        print("=" * 72)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, help="Model name/tag (e.g. qwen2.5-coder:7b)")
    parser.add_argument(
        "--provider", default="ollama",
        choices=["ollama", "vllm", "deepseek", "togetherai", "openrouter", "openai", "anthropic"],
        help="LLM provider (default: ollama)",
    )
    parser.add_argument("--tasks", type=int, default=None, help="Number of tasks to run (default: all)")
    parser.add_argument(
        "--domain", choices=["numeric_edge_cases", "security_boundaries", "concurrency_boundaries"],
        default=None, help="Restrict to a single domain (default: all three)",
    )
    parser.add_argument(
        "--sandbox", choices=["local", "podman"], default="local",
        help=(
            "'local' runs generated code directly on the host via subprocess "
            "(no isolation beyond a timeout -- zero setup). 'podman' reuses "
            "the same rootless-podman sandbox as the rest of ACE "
            "(--network none, read-only mount, dropped capabilities); "
            "requires podman and the localhost/ace-harness:latest image."
        ),
    )
    parser.add_argument(
        "--playbook-id", default=None,
        help="Playbook to accumulate bullets into (default: benchmark_proof_<model>)",
    )
    parser.add_argument(
        "--llm-timeout", type=float, default=300.0,
        help=(
            "Per-call HTTP timeout in seconds (default: 300). LLMClient's own "
            "default of 120s is tuned for cloud APIs; local open-weight "
            "models on CPU-only hardware routinely need longer."
        ),
    )
    parser.add_argument("--out", type=Path, default=None, help="Report JSON output path")
    parser.add_argument(
        "--playbook-storage-path", default=None,
        help="Directory to persist playbook JSON files in (default: data/playbooks/)",
    )
    parser.add_argument(
        "--temperature", type=float, default=0.2,
        help=(
            "Sampling temperature, matched across all 3 arms (default: 0.2). "
            "On a small failure set (N of order 10), consider 0.0 (greedy) so "
            "random token jitter doesn't skew which arm 'happens' to recover "
            "a given task."
        ),
    )
    parser.add_argument(
        "--sequential", action="store_true",
        help=(
            "Let Arm 1 use bullets accumulated from earlier tasks in this run "
            "instead of a clean zero-shot prompt. Tells the complementary "
            "'online institutional memory over a session' story rather than "
            "isolating the playbook's causal effect -- run once each way "
            "rather than mixing them into one report."
        ),
    )
    parser.add_argument(
        "--runs", type=int, default=1,
        help=(
            "Repeat the full ablation this many times and report mean +/- "
            "stdev across runs (default: 1). With a small failure set (N of "
            "order 10), a single run's net_causal_uplift is noisy -- one "
            "task flipping arms swings it by 1/N. Each run gets its own "
            "fresh playbook (never shared across runs) so trials are "
            "independent. Meaningless at --temperature 0.0 (greedy decoding "
            "is deterministic, so every run is identical)."
        ),
    )
    args = parser.parse_args(argv)

    tasks = get_tasks(args.domain)
    if args.tasks is not None:
        tasks = tasks[: args.tasks]

    playbook_id = args.playbook_id or f"benchmark_proof_{args.model.replace('/', '_').replace(':', '_')}"

    if args.sandbox == "local":
        print(
            "WARNING: --sandbox local runs model-generated code directly on this "
            "host with no container isolation (only a subprocess timeout). Use "
            "--sandbox podman for genuinely untrusted models/output.\n"
        )

    safe_model = args.model.replace("/", "_").replace(":", "_")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if args.runs > 1:
        multi = run_multi_benchmark(
            tasks=tasks,
            model=args.model,
            provider=args.provider,
            sandbox=args.sandbox,
            playbook_id=playbook_id,
            runs=args.runs,
            llm_timeout=args.llm_timeout,
            playbook_storage_path=args.playbook_storage_path,
            temperature=args.temperature,
            sequential=args.sequential,
        )
        print_multi_summary(multi)

        out_path = args.out or REPORTS_DIR / f"{stamp}_{safe_model}_x{args.runs}runs.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_dict = {
            "model": multi.model, "provider": multi.provider, "sandbox": multi.sandbox,
            "temperature": multi.temperature,
            "runs": [{**asdict(r), "summary": r.summary()} for r in multi.runs],
            "aggregate": multi.aggregate(),
        }
        out_path.write_text(json.dumps(out_dict, indent=2))
        print(f"\nFull report written to {out_path}")
        return 0

    report = run_benchmark(
        tasks=tasks,
        model=args.model,
        provider=args.provider,
        sandbox=args.sandbox,
        playbook_id=playbook_id,
        llm_timeout=args.llm_timeout,
        playbook_storage_path=args.playbook_storage_path,
        temperature=args.temperature,
        sequential=args.sequential,
    )
    print_summary(report)

    out_path = args.out or REPORTS_DIR / f"{stamp}_{safe_model}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    report_dict = asdict(report)
    report_dict["summary"] = report.summary()
    out_path.write_text(json.dumps(report_dict, indent=2))
    print(f"\nFull report written to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
