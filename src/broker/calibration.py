"""Cold-start model calibration for AdaptiveBroker routing (issue #5).

`AdaptiveBroker.route_task()` only scores candidates that already have real
audit history -- `PerformanceAggregator.get_all_agent_metrics()` groups
`CYCLE_COMPLETED` events by `actor_id`, so a model with zero history is never
even a key in that dict. It isn't under-scored, it's architecturally
unreachable by scoring.

Rather than teach `AdaptiveBroker`/`PerformanceAggregator` a second,
declared-capability scoring path (real surgery to a live routing system, plus
a staleness policy for when a declared score gets superseded by real history),
this gives a cold-start candidate one real audit data point: a throwaway,
real, sandboxed TDD cycle against a small fixed task. That cycle already
emits a normal `CYCLE_COMPLETED` event via the existing `TDDCycleRunner`
audit wiring (`actor_id=model_id`) -- from then on the model is
indistinguishable from any other audited model to the existing, unmodified
scoring pipeline. Whether the calibration task passes or fails, a real signal
gets recorded either way.

Mirrors `src/agents/ensemble_build.py`'s per-model throwaway-sandboxed-run
pattern (`_build_sandboxed_candidate_runner` / `_generate_candidates`).
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

CALIBRATION_REQUIREMENT = (
    "Implement a function `add(a: int, b: int) -> int` that returns the sum "
    "of the two integers."
)

CALIBRATION_PLAYBOOK_ID = "broker_calibration"


def calibrate_cold_start_models(
    model_refs: list[str],
    audit_database_url: str,
    *,
    runner_factory=None,
    max_cycles: int = 2,
) -> None:
    """One throwaway sandboxed TDD cycle per model_ref, so each gets a real
    CYCLE_COMPLETED audit event and stops being invisible to AdaptiveBroker's
    scoring. Never raises -- a calibration failure just means that model
    stays cold for this call, exactly like today.

    runner_factory is a test seam: a callable(model_ref) -> object with a
    `.run(feature_requirement, test_file, implementation_file, languages)`
    method. Defaults to the real sandboxed builder.
    """
    factory = runner_factory or _build_sandboxed_calibration_runner
    for model_ref in model_refs:
        _run_one_calibration_cycle(model_ref, audit_database_url, factory, max_cycles)


def _run_one_calibration_cycle(
    model_ref: str,
    audit_database_url: str,
    runner_factory,
    max_cycles: int,
) -> None:
    workspace = Path(tempfile.mkdtemp(prefix="ace-calibration-"))
    try:
        src_dir = workspace / "src"
        test_dir = workspace / "tests"
        src_dir.mkdir()
        test_dir.mkdir()

        runner = runner_factory(
            model_ref=model_ref,
            project_path=workspace,
            src_dir=src_dir,
            audit_database_url=audit_database_url,
            max_cycles=max_cycles,
        )
        runner.run(
            feature_requirement=CALIBRATION_REQUIREMENT,
            test_file=test_dir / "test_calibration.py",
            implementation_file=src_dir / "calibration.py",
            languages=["python"],
        )
    except Exception as exc:  # noqa: BLE001 -- calibration must never block routing
        logger.warning("calibration: %s failed to run (%s) — model stays cold-start", model_ref, exc)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _build_sandboxed_calibration_runner(
    *,
    model_ref: str,
    project_path: Path,
    src_dir: Path,
    audit_database_url: str,
    max_cycles: int,
):
    """Build a real PolyglotTDDRunner for one candidate model (Python only)."""
    from src.agents.polyglot_pod_builder import build_pod_kwargs
    from src.agents.polyglot_tdd_runner import PodFactory, PolyglotTDDRunner
    from src.audit.local_client import LocalAuditClient
    from src.utils.llm_client import LLMClient

    provider, _, model = model_ref.partition("/")
    if not model:
        raise ValueError(f"candidate model {model_ref!r} must be '<provider>/<model>'")
    llm_client = LLMClient(provider=provider, model=model)

    pod_kwargs = {"python": build_pod_kwargs("python", project_path, llm_client, src_dir=src_dir)}
    return PolyglotTDDRunner(
        PodFactory,
        max_cycles=max_cycles,
        pod_kwargs=pod_kwargs,
        audit_client=LocalAuditClient(database_url=audit_database_url),
        playbook_id=CALIBRATION_PLAYBOOK_ID,
        model_id=model_ref,
    )
