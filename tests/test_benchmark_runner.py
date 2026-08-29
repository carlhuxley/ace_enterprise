"""Tests for benchmarks.runner.run_benchmark()'s 3-arm ablation: Arm 1
(zero-shot), Arm 2 (blind retry control), Arm 3 (ACE playbook).

Patches LLMClient.generate with a stub that can respond differently to a
zero-shot prompt vs. a bare retry vs. a retry augmented with curated
bullets -- no real model call, no network, no podman. This is what CI can
run on every commit; benchmarks/verify_oracles.py (the paired canonical/buggy
audit of the task bank itself) and an actual `python -m benchmarks.runner`
run against a real model are complementary, not replaced by this.
"""
from unittest.mock import patch

from src.agents.language_pod import PhaseResult

from benchmarks.runner import (
    BenchmarkReport,
    MultiRunReport,
    TaskRunResult,
    _failure_signature,
    _failure_text,
    run_benchmark,
    run_multi_benchmark,
)
from benchmarks.tasks import get_tasks

_BUGGY_DIV_ZERO = '''```python
def safe_divide(a, b):
    return a / b
```'''

_CORRECT_DIV_ZERO = '''```python
import math

def safe_divide(a, b):
    if b == 0.0:
        if a == 0.0:
            return math.nan
        sign = math.copysign(1.0, a) * math.copysign(1.0, b)
        return math.inf if sign > 0 else -math.inf
    return a / b
```'''

_REFLECTOR_ANALYSIS = """## Error Identification
ZeroDivisionError was raised instead of returning inf/-inf/nan.

## Root Cause
The implementation used plain division without checking for a zero divisor.

## Correct Approach
Check the divisor and return math.inf/-math.inf/math.nan per IEEE 754.

## Key Insight
Division by zero must be handled explicitly for float semantics.

Quality: 0.9
"""

_CURATOR_SYNTHESIS = """## Reasoning
Division must handle a zero divisor explicitly.

## Delta Bullets
#### Section: strategies_and_hard_rules
- When implementing float division, check for a zero divisor and return math.inf/-math.inf/math.nan per IEEE 754 instead of letting ZeroDivisionError propagate.
"""


def _only_ace_fixes_it(self, prompt, system_prompt=None, max_tokens=None, temperature=0.7):
    """Arm 1 and Arm 2 (no 'Lessons Learned' in the prompt) both get the buggy
    solution; only a prompt carrying curated bullets (Arm 3) gets the fix.
    This is the case that should produce a positive net causal uplift."""
    sp = system_prompt or ""
    if "analyzing AI system performance" in sp:
        return {"content": _REFLECTOR_ANALYSIS, "tokens_used": 10}
    if "synthesizing learning insights" in sp:
        return {"content": _CURATOR_SYNTHESIS, "tokens_used": 10}
    content = _CORRECT_DIV_ZERO if "Lessons Learned" in prompt else _BUGGY_DIV_ZERO
    return {"content": content, "tokens_used": 10}


def _retry_alone_fixes_it(self, prompt, system_prompt=None, max_tokens=None, temperature=0.7):
    """Both the blind retry (Arm 2) and the ACE retry (Arm 3) get the fix as
    soon as the failing code + error trace are in the prompt, regardless of
    curated bullets. This is the "playbook was redundant" case -- net causal
    uplift should be zero."""
    sp = system_prompt or ""
    if "analyzing AI system performance" in sp:
        return {"content": _REFLECTOR_ANALYSIS, "tokens_used": 10}
    if "synthesizing learning insights" in sp:
        return {"content": _CURATOR_SYNTHESIS, "tokens_used": 10}
    content = _CORRECT_DIV_ZERO if "Your previous attempt" in prompt else _BUGGY_DIV_ZERO
    return {"content": content, "tokens_used": 10}


def _get_div_zero_task():
    return next(t for t in get_tasks("numeric_edge_cases") if t.id == "num_div_zero")


def test_failure_text_does_not_drop_stdout_behind_incidental_stderr():
    """Found via forensic analysis of a real run (conc_graceful_shutdown,
    benchmarks/reports/20260825T205139Z_qwen2.5-coder_7b.json): stderr can
    be non-empty for reasons unrelated to the actual pytest failure (e.g.
    asyncio's default handler printing "Task exception was never retrieved"
    for an un-awaited failed Task). The old `phase.error or phase.output`
    picked stderr and silently discarded the real assertion failure sitting
    in stdout -- neither the retry prompt nor the Reflector ever saw it."""
    phase = PhaseResult(
        passed=False,
        output="FAILURES: test_x -- AssertionError: expected True, got False",
        error="Task exception was never retrieved\nfuture: <Task ...>",
    )
    text = _failure_text(phase)
    assert "AssertionError" in text
    assert "Task exception was never retrieved" in text


def test_failure_text_preserves_security_gate_message():
    phase = PhaseResult(
        passed=False,
        output="5 passed in 0.02s",
        error="Security gate: HIGH=1 MEDIUM=0 LOW=0\n<bandit output>",
    )
    text = _failure_text(phase)
    assert "Security gate" in text


def test_ace_playbook_rescues_what_blind_retry_cannot(tmp_path):
    task = _get_div_zero_task()

    with patch("src.utils.llm_client.LLMClient.generate", _only_ace_fixes_it):
        report = run_benchmark(
            tasks=[task],
            model="fake-model",
            provider="ollama",
            sandbox="local",
            playbook_id="test_ace_rescue",
            playbook_storage_path=str(tmp_path),
            verbose=False,
        )

    result = report.results[0]
    assert result.pass_arm1_zero_shot is False, "buggy solution.py must fail Arm 1's pytest suite"
    assert result.pass_arm2_control_blind is False, "blind retry (no bullets) must still fail"
    assert result.pass_arm3_ace_playbook is True, f"ACE arm must pass, error={result.arm3_error}"
    assert result.bullets_curated == 1
    assert "zero divisor" in result.curated_bullet_contents[0]

    summary = report.summary()
    assert summary["pass_at_1_zero_shot"]["count"] == 0
    assert summary["pass_at_2_control_blind"]["recovered"] == 0
    assert summary["pass_at_2_ace_playbook"]["recovered"] == 1
    assert summary["net_causal_uplift"] == 1.0, "sole rescue came from the playbook -> full uplift"


def test_zero_uplift_when_blind_retry_is_just_as_good(tmp_path):
    task = _get_div_zero_task()

    with patch("src.utils.llm_client.LLMClient.generate", _retry_alone_fixes_it):
        report = run_benchmark(
            tasks=[task],
            model="fake-model",
            provider="ollama",
            sandbox="local",
            playbook_id="test_no_uplift",
            playbook_storage_path=str(tmp_path),
            verbose=False,
        )

    result = report.results[0]
    assert result.pass_arm1_zero_shot is False
    assert result.pass_arm2_control_blind is True
    assert result.pass_arm3_ace_playbook is True

    summary = report.summary()
    assert summary["net_causal_uplift"] == 0.0, "both arms recovered equally -> playbook added nothing"


def test_strict_mode_keeps_arm1_clean_across_tasks(tmp_path):
    """Default (sequential=False): Arm 1 must never see bullets curated by
    an earlier task in the same run, even though the playbook persists
    across tasks -- otherwise Pass@1 depends on task order."""
    prompts = []

    def fake(self, prompt, system_prompt=None, max_tokens=None, temperature=0.7):
        sp = system_prompt or ""
        if "analyzing AI system performance" in sp:
            return {"content": _REFLECTOR_ANALYSIS, "tokens_used": 5}
        if "synthesizing learning insights" in sp:
            return {"content": _CURATOR_SYNTHESIS, "tokens_used": 5}
        prompts.append(prompt)
        return {"content": _BUGGY_DIV_ZERO, "tokens_used": 5}

    # Both tasks are numeric_edge_cases, so a leaked bullet would be visible
    # to either regardless of which is "task 1" -- use two div-zero-shaped
    # calls by reusing the same task twice under different ids isn't
    # possible here, so just confirm no task-1-derived bullet appears in
    # task 2's very first (Arm 1) prompt.
    tasks = [t for t in get_tasks("numeric_edge_cases") if t.id in ("num_div_zero", "num_neg_zero")]
    with patch("src.utils.llm_client.LLMClient.generate", fake):
        run_benchmark(
            tasks=tasks,
            model="fake-model",
            provider="ollama",
            sandbox="local",
            playbook_id="test_strict_no_leak",
            playbook_storage_path=str(tmp_path),
            sequential=False,
            verbose=False,
        )

    task2_arm1_prompt = prompts[3]  # [task1: arm1, arm2, arm3, task2: arm1, ...]
    assert "Lessons Learned" not in task2_arm1_prompt


def test_sequential_mode_lets_arm1_use_accumulated_bullets(tmp_path):
    prompts = []

    def fake(self, prompt, system_prompt=None, max_tokens=None, temperature=0.7):
        sp = system_prompt or ""
        if "analyzing AI system performance" in sp:
            return {"content": _REFLECTOR_ANALYSIS, "tokens_used": 5}
        if "synthesizing learning insights" in sp:
            return {"content": _CURATOR_SYNTHESIS, "tokens_used": 5}
        prompts.append(prompt)
        return {"content": _BUGGY_DIV_ZERO, "tokens_used": 5}

    tasks = [t for t in get_tasks("numeric_edge_cases") if t.id in ("num_div_zero", "num_neg_zero")]
    with patch("src.utils.llm_client.LLMClient.generate", fake):
        run_benchmark(
            tasks=tasks,
            model="fake-model",
            provider="ollama",
            sandbox="local",
            playbook_id="test_sequential_leak_allowed",
            playbook_storage_path=str(tmp_path),
            sequential=True,
            verbose=False,
        )

    task2_arm1_prompt = prompts[3]
    assert "Lessons Learned" in task2_arm1_prompt


def test_arm2_and_arm3_share_identical_base_prompt(tmp_path):
    """Arm 2 and Arm 3 must differ ONLY in whether curated bullets are
    appended -- same spec, same failing code, same error trace -- otherwise
    a gap between them isn't attributable to the playbook."""
    prompts_seen = []

    def capture(self, prompt, system_prompt=None, max_tokens=None, temperature=0.7):
        sp = system_prompt or ""
        if "analyzing AI system performance" in sp:
            return {"content": _REFLECTOR_ANALYSIS, "tokens_used": 10}
        if "synthesizing learning insights" in sp:
            return {"content": _CURATOR_SYNTHESIS, "tokens_used": 10}
        prompts_seen.append(prompt)
        return {"content": _BUGGY_DIV_ZERO, "tokens_used": 10}

    task = _get_div_zero_task()
    with patch("src.utils.llm_client.LLMClient.generate", capture):
        run_benchmark(
            tasks=[task],
            model="fake-model",
            provider="ollama",
            sandbox="local",
            playbook_id="test_shared_base",
            playbook_storage_path=str(tmp_path),
            verbose=False,
        )

    # [0] = Arm 1 (zero-shot), [1] = Arm 2 (control), [2] = Arm 3 (ACE)
    assert len(prompts_seen) == 3
    arm2_prompt, arm3_prompt = prompts_seen[1], prompts_seen[2]
    assert "Lessons Learned" not in arm2_prompt
    assert "Lessons Learned" in arm3_prompt
    base_arm3 = arm3_prompt.split("\n\n# Lessons Learned")[0]
    assert arm2_prompt == base_arm3, "Arm 2 and Arm 3 must share an identical base prompt"


def test_passing_arm1_needs_no_retry(tmp_path):
    def always_correct(self, prompt, system_prompt=None, max_tokens=None, temperature=0.7):
        return {"content": _CORRECT_DIV_ZERO, "tokens_used": 10}

    task = _get_div_zero_task()
    with patch("src.utils.llm_client.LLMClient.generate", always_correct):
        report = run_benchmark(
            tasks=[task],
            model="fake-model",
            provider="ollama",
            sandbox="local",
            playbook_id="test_no_retry_needed",
            playbook_storage_path=str(tmp_path),
            verbose=False,
        )

    result = report.results[0]
    assert result.pass_arm1_zero_shot is True
    assert result.pass_arm2_control_blind is None
    assert result.pass_arm3_ace_playbook is None
    assert result.bullets_curated == 0


def test_generation_error_does_not_abort_the_batch(tmp_path):
    calls = {"n": 0}

    def flaky_then_fine(self, prompt, system_prompt=None, max_tokens=None, temperature=0.7):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated timeout")
        return {"content": _CORRECT_DIV_ZERO, "tokens_used": 10}

    tasks = [t for t in get_tasks("numeric_edge_cases") if t.id in ("num_div_zero", "num_neg_zero")]

    with patch("src.utils.llm_client.LLMClient.generate", flaky_then_fine):
        report = run_benchmark(
            tasks=tasks,
            model="fake-model",
            provider="ollama",
            sandbox="local",
            playbook_id="test_resilience",
            playbook_storage_path=str(tmp_path),
            verbose=False,
        )

    assert len(report.results) == 2
    failed = next(r for r in report.results if r.task_id == "num_div_zero")
    assert failed.pass_arm1_zero_shot is False
    assert failed.arm1_error is not None and "generation error" in failed.arm1_error


def test_curated_bullet_persists_at_low_confidence(tmp_path):
    # Curator seeds new bullets at confidence_score=0.3 pending human review
    # (see apply_delta in src/playbook/manager.py) -- below
    # BulletRetriever.retrieve()'s default min_confidence=0.5. This is *why*
    # run_benchmark() builds its own prompt from PlaybookManager.get_all_bullets()
    # instead of going through src.core.generator.module.Generator (see
    # benchmarks/runner.py's module docstring): Generator's default retrieval
    # would silently filter the bullet back out before Arm 3 ever saw it.
    task = _get_div_zero_task()

    with patch("src.utils.llm_client.LLMClient.generate", _only_ace_fixes_it):
        run_benchmark(
            tasks=[task],
            model="fake-model",
            provider="ollama",
            sandbox="local",
            playbook_id="test_confidence",
            playbook_storage_path=str(tmp_path),
            verbose=False,
        )

    from src.playbook.manager import PlaybookManager

    pm = PlaybookManager(storage_path=str(tmp_path))
    bullets = pm.get_all_bullets("test_confidence")
    assert len(bullets) == 1
    assert bullets[0].confidence_score == 0.3


def _make_report(pass1_rate, control_recovery, ace_recovery) -> BenchmarkReport:
    """Fabricate a BenchmarkReport with exactly the aggregate stats implied
    by the given rates, for testing MultiRunReport.aggregate()'s math in
    isolation from run_benchmark()'s LLM-calling machinery. Uses 4 tasks
    (2 passing, 2 failing) so recovery rates land on exact eighths/quarters
    without rounding surprises: n_failed=2, so recovered in {0, 1, 2}."""
    n_pass1 = round(pass1_rate * 4)
    results = []
    for i in range(n_pass1):
        results.append(TaskRunResult(
            task_id=f"p{i}", domain="numeric_edge_cases", title="", trap="",
            pass_arm1_zero_shot=True, pass_arm2_control_blind=None, pass_arm3_ace_playbook=None,
            bullets_curated=0, curated_bullet_contents=[], arm1_error=None, arm2_error=None,
            arm3_error=None, arm1_signature=None, arm2_signature=None, arm3_signature=None,
            arm1_tokens=0, arm2_tokens=0, arm3_tokens=0, reflect_tokens=0, curate_tokens=0,
        ))
    n_failed = 4 - n_pass1
    n_control_rescued = round(control_recovery * n_failed)
    n_ace_rescued = round(ace_recovery * n_failed)
    for i in range(n_failed):
        control_passed = i < n_control_rescued
        ace_passed = i < n_ace_rescued
        results.append(TaskRunResult(
            task_id=f"f{i}", domain="numeric_edge_cases", title="", trap="",
            pass_arm1_zero_shot=False,
            pass_arm2_control_blind=control_passed,
            pass_arm3_ace_playbook=ace_passed,
            bullets_curated=1, curated_bullet_contents=["x"], arm1_error="e",
            arm2_error=None if control_passed else "e2", arm3_error=None if ace_passed else "e3",
            arm1_signature="SIG_E", arm2_signature=None if control_passed else "SIG_E2",
            arm3_signature=None if ace_passed else "SIG_E3",
            arm1_tokens=0, arm2_tokens=0, arm3_tokens=0, reflect_tokens=0, curate_tokens=0,
        ))
    return BenchmarkReport(
        model="fake", provider="ollama", sandbox="local", playbook_id="p",
        started_at="t0", finished_at="t1", results=results,
    )


def test_multi_run_aggregate_mean_and_std():
    # Three runs with known, distinct net_causal_uplift values.
    runs = [
        _make_report(pass1_rate=0.5, control_recovery=0.5, ace_recovery=0.5),   # uplift 0.0
        _make_report(pass1_rate=0.5, control_recovery=0.0, ace_recovery=0.5),   # uplift 0.5
        _make_report(pass1_rate=0.5, control_recovery=0.0, ace_recovery=1.0),   # uplift 1.0
    ]
    multi = MultiRunReport(model="fake", provider="ollama", sandbox="local", temperature=0.2, runs=runs)
    agg = multi.aggregate()

    assert agg["n_runs"] == 3
    assert agg["net_causal_uplift"]["values"] == [0.0, 0.5, 1.0]
    assert agg["net_causal_uplift"]["mean"] == 0.5
    # sample stdev of [0.0, 0.5, 1.0]: mean=0.5, sq devs sum=0.5, /2 = 0.25, sqrt=0.5
    assert agg["net_causal_uplift"]["std"] == 0.5


def test_single_run_aggregate_has_zero_std():
    runs = [_make_report(pass1_rate=0.5, control_recovery=0.5, ace_recovery=0.5)]
    multi = MultiRunReport(model="fake", provider="ollama", sandbox="local", temperature=0.2, runs=runs)
    agg = multi.aggregate()
    assert agg["n_runs"] == 1
    assert agg["net_causal_uplift"]["std"] == 0.0


def test_run_multi_benchmark_uses_independent_playbooks_per_run(tmp_path):
    """Each run must curate into its own playbook -- otherwise run 2 starts
    with run 1's bullets already in Arm 3's context, which is a continuation
    of the same trial, not a second independent sample."""
    from src.playbook.manager import PlaybookManager

    def fake(self, prompt, system_prompt=None, max_tokens=None, temperature=0.7):
        sp = system_prompt or ""
        if "analyzing AI system performance" in sp:
            return {"content": _REFLECTOR_ANALYSIS, "tokens_used": 5}
        if "synthesizing learning insights" in sp:
            return {"content": _CURATOR_SYNTHESIS, "tokens_used": 5}
        return {"content": _BUGGY_DIV_ZERO, "tokens_used": 5}

    task = _get_div_zero_task()
    with patch("src.utils.llm_client.LLMClient.generate", fake):
        multi = run_multi_benchmark(
            tasks=[task], model="fake-model", provider="ollama", sandbox="local",
            playbook_id="multitest", runs=3, playbook_storage_path=str(tmp_path),
            verbose=False,
        )

    assert len(multi.runs) == 3
    assert [r.playbook_id for r in multi.runs] == ["multitest_run1", "multitest_run2", "multitest_run3"]

    pm = PlaybookManager(storage_path=str(tmp_path))
    for i in range(1, 4):
        bullets = pm.get_all_bullets(f"multitest_run{i}")
        # Each run curates its own bullet from its own (independent) failure
        # -- not 1, 2, 3 accumulating across runs.
        assert len(bullets) == 1


def test_run_multi_benchmark_single_run_keeps_original_playbook_id(tmp_path):
    def fake(self, prompt, system_prompt=None, max_tokens=None, temperature=0.7):
        return {"content": _CORRECT_DIV_ZERO, "tokens_used": 5}

    task = _get_div_zero_task()
    with patch("src.utils.llm_client.LLMClient.generate", fake):
        multi = run_multi_benchmark(
            tasks=[task], model="fake-model", provider="ollama", sandbox="local",
            playbook_id="singlerun", runs=1, playbook_storage_path=str(tmp_path),
            verbose=False,
        )

    assert multi.runs[0].playbook_id == "singlerun"


# --- _failure_signature ------------------------------------------------

def _phase_text(output="", error=""):
    return "\n".join(p for p in (output, error) if p)


def test_signature_prefers_short_test_summary_info():
    text = _phase_text(output="""
============================= test session starts ==============================
test_solution.py::test_a FAILED

=================================== FAILURES ===================================
_________________________ test_a __________________________
E   TypeError: Passing coroutines is forbidden, use tasks explicitly.
=========================== short test summary info ============================
FAILED test_solution.py::test_a - TypeError: Passing coroutines is forbidden...
""")
    sig = _failure_signature(text)
    assert sig == "FAILED test_solution.py::test_a - TypeError: Passing coroutines is forbidden..."


def test_signature_distinguishes_different_bugs_on_the_same_task():
    """The exact conc_first_to_finish pattern: Arm 2 never wraps coroutines
    in tasks, Arm 3 does but then mishandles the returned set -- two
    genuinely different bugs that must produce different signatures."""
    arm2_text = _phase_text(
        error=(
            "sys:1: RuntimeWarning: coroutine '_fast' was never awaited\n"
            "sys:1: RuntimeWarning: coroutine '_slow' was never awaited"
        ),
        output="""=========================== short test summary info ============================
FAILED test_solution.py::test_returns_fastest_result - TypeError: Passing cor...""",
    )
    arm3_text = _phase_text(output="""=========================== short test summary info ============================
FAILED test_solution.py::test_returns_fastest_result - TypeError: 'set' objec...""")

    sig2 = _failure_signature(arm2_text)
    sig3 = _failure_signature(arm3_text)
    assert sig2 != sig3
    assert "Passing cor" in sig2
    assert "'set' objec" in sig3


def test_signature_falls_back_to_e_line_without_summary_section():
    text = "E   assert 3.0 == 2.0"
    assert _failure_signature(text) == "assert 3.0 == 2.0"


def test_signature_recognizes_timeout():
    assert _failure_signature("Execution timed out after 10s (possible hang/deadlock)") == "TIMEOUT"


def test_signature_recognizes_security_gate():
    sig = _failure_signature("Security gate: HIGH=1 MEDIUM=0 LOW=0\n<bandit output>")
    assert sig == "Security gate: HIGH=1 MEDIUM=0 LOW=0"


def test_signature_recognizes_generation_error():
    sig = _failure_signature("generation error: RuntimeError('timed out')")
    assert sig == "GENERATION_ERROR: RuntimeError('timed out')"


def test_signature_none_for_no_failure():
    assert _failure_signature(None) is None
    assert _failure_signature("") is None


def test_signature_falls_back_to_first_line_when_unrecognizable():
    assert _failure_signature("sys:1: RuntimeWarning: coroutine '_fast' was never awaited") == \
        "sys:1: RuntimeWarning: coroutine '_fast' was never awaited"


# --- ace_changed_approach_when_still_failing ----------------------------

def test_changed_approach_metric_detects_different_bugs_across_arms(tmp_path):
    """End-to-end: Arm 2 and Arm 3 both fail conc_first_to_finish, but on
    different bugs -- net_causal_uplift reports this as "no effect" (both
    still fail), while ace_changed_approach_when_still_failing should catch
    that the playbook visibly changed the model's approach."""
    task = next(t for t in get_tasks("concurrency_boundaries") if t.id == "conc_first_to_finish")

    _NEVER_WRAPPED = '''```python
async def first_to_finish(coros):
    done, pending = await __import__("asyncio").wait(coros, return_when=__import__("asyncio").FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    return list(done)[0].result()
```'''
    _WRAPPED_BUT_BAD_NEXT = '''```python
import asyncio

async def first_to_finish(coros):
    tasks = [asyncio.ensure_future(c) for c in coros]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    return next(done).result()
```'''

    def fake(self, prompt, system_prompt=None, max_tokens=None, temperature=0.7):
        sp = system_prompt or ""
        if "analyzing AI system performance" in sp:
            return {"content": _REFLECTOR_ANALYSIS, "tokens_used": 5}
        if "synthesizing learning insights" in sp:
            return {"content": _CURATOR_SYNTHESIS, "tokens_used": 5}
        if "Lessons Learned" in prompt:
            return {"content": _WRAPPED_BUT_BAD_NEXT, "tokens_used": 5}
        return {"content": _NEVER_WRAPPED, "tokens_used": 5}

    with patch("src.utils.llm_client.LLMClient.generate", fake):
        report = run_benchmark(
            tasks=[task], model="fake-model", provider="ollama", sandbox="local",
            playbook_id="test_changed_approach", playbook_storage_path=str(tmp_path),
            verbose=False,
        )

    result = report.results[0]
    assert result.pass_arm2_control_blind is False
    assert result.pass_arm3_ace_playbook is False
    assert result.arm2_signature != result.arm3_signature

    summary = report.summary()
    assert summary["net_causal_uplift"] == 0.0, "both arms still fail -- pass/fail alone sees no effect"
    changed = summary["ace_changed_approach_when_still_failing"]
    assert changed["of"] == 1
    assert changed["count"] == 1, "but the failure signature should show ACE changed the model's approach"


def test_arm3_bullets_scoped_by_task_tag_not_just_domain(tmp_path):
    """Two tasks share domain=numeric_edge_cases but test unrelated bugs
    (and so have different tags). A bullet curated from task 1's failure
    must not appear in task 2's Arm 3 retry prompt just because they share
    a domain -- found via forensic analysis of a real run: by the time
    num_currency_cents's Arm 3 ran, 21 domain-tagged-but-task-irrelevant
    bullets from three earlier numeric tasks were already in the playbook,
    and Arm 3 lost to blind retry in 5/5 runs."""
    _BUGGY_DIV = '''```python
def safe_divide(a, b):
    return a / b
```'''
    _BUGGY_NEG = '''```python
def is_negative_zero(x):
    return x < 0
```'''
    # Reflector._parse_analysis only recognizes "###"/"**bold**" section
    # headers (not "##"), so this needs a different heading level than
    # _REFLECTOR_ANALYSIS above to actually route DIV_ZERO_MARKER/
    # NEG_ZERO_MARKER into error_identification and on into the Curator's
    # synthesis prompt below.
    _REFLECTOR_DIV = "### Error Identification\nDIV_ZERO_MARKER\n### Root Cause\nX\n### Correct Approach\nY\n### Key Insight\nZ\nQuality: 0.9\n"
    _REFLECTOR_NEG = "### Error Identification\nNEG_ZERO_MARKER\n### Root Cause\nX\n### Correct Approach\nY\n### Key Insight\nZ\nQuality: 0.9\n"
    _CURATOR_DIV = "## Reasoning\nR\n## Delta Bullets\n#### Section: strategies_and_hard_rules\n- DIV_ZERO_ONLY_BULLET: check divisor sign\n"
    _CURATOR_NEG = "## Reasoning\nR\n## Delta Bullets\n#### Section: strategies_and_hard_rules\n- NEG_ZERO_ONLY_BULLET: use copysign\n"

    arm3_prompts = {}

    def fake(self, prompt, system_prompt=None, max_tokens=None, temperature=0.7):
        sp = system_prompt or ""
        is_div = "safe_divide" in prompt
        if "analyzing AI system performance" in sp:
            return {"content": _REFLECTOR_DIV if is_div else _REFLECTOR_NEG, "tokens_used": 5}
        if "synthesizing learning insights" in sp:
            return {"content": _CURATOR_DIV if "DIV_ZERO_MARKER" in prompt else _CURATOR_NEG, "tokens_used": 5}
        if "Lessons Learned" in prompt:
            arm3_prompts["num_div_zero" if is_div else "num_neg_zero"] = prompt
        return {"content": _BUGGY_DIV if is_div else _BUGGY_NEG, "tokens_used": 5}

    tasks = [t for t in get_tasks("numeric_edge_cases") if t.id in ("num_div_zero", "num_neg_zero")]
    with patch("src.utils.llm_client.LLMClient.generate", fake):
        run_benchmark(
            tasks=tasks, model="fake-model", provider="ollama", sandbox="local",
            playbook_id="test_tag_scope", playbook_storage_path=str(tmp_path), verbose=False,
        )

    assert set(arm3_prompts) == {"num_div_zero", "num_neg_zero"}
    assert "DIV_ZERO_ONLY_BULLET" in arm3_prompts["num_div_zero"]
    assert "NEG_ZERO_ONLY_BULLET" not in arm3_prompts["num_div_zero"]
    assert "NEG_ZERO_ONLY_BULLET" in arm3_prompts["num_neg_zero"]
    assert "DIV_ZERO_ONLY_BULLET" not in arm3_prompts["num_neg_zero"], \
        "task 1's bullet leaked into task 2's Arm 3 prompt via the shared domain"


def test_reflect_and_curate_token_usage_is_logged(tmp_path):
    """Reflector.reflect() (up to max_refinement_rounds=3 internal LLM
    calls) and Curator.curate() (one call) previously had no token count at
    all -- only the three generation arms did, so a total-cost estimate for
    a run was silently missing two calls per failing task."""
    task = _get_div_zero_task()

    with patch("src.utils.llm_client.LLMClient.generate", _only_ace_fixes_it):
        report = run_benchmark(
            tasks=[task], model="fake-model", provider="ollama", sandbox="local",
            playbook_id="test_reflect_curate_tokens", playbook_storage_path=str(tmp_path),
            verbose=False,
        )

    result = report.results[0]
    # _only_ace_fixes_it returns tokens_used=10 for every call; reflect()
    # never reaches the quality_score>=0.8 early-exit on this fixture, so it
    # runs all 3 default refinement rounds, and curate() always makes
    # exactly one call.
    assert result.reflect_tokens == 30
    assert result.curate_tokens == 10


def test_reflect_and_curate_tokens_stay_zero_when_arm1_passes(tmp_path):
    def always_correct(self, prompt, system_prompt=None, max_tokens=None, temperature=0.7):
        return {"content": _CORRECT_DIV_ZERO, "tokens_used": 10}

    task = _get_div_zero_task()
    with patch("src.utils.llm_client.LLMClient.generate", always_correct):
        report = run_benchmark(
            tasks=[task], model="fake-model", provider="ollama", sandbox="local",
            playbook_id="test_no_reflect_curate_needed", playbook_storage_path=str(tmp_path),
            verbose=False,
        )

    result = report.results[0]
    assert result.reflect_tokens == 0
    assert result.curate_tokens == 0
