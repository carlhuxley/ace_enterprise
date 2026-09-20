"""Playbook reliability — which bullets correlate with first-pass GREEN success."""

from dataclasses import dataclass

from src.playbook.manager import PlaybookManager
from src.storage.experiment_logger import ExperimentLogger


@dataclass
class BulletReliability:
    bullet_id: str
    times_retrieved: int
    first_pass_count: int
    first_pass_rate: float


@dataclass
class BulletUplift:
    """Causal uplift for one bullet: does retrieving it correlate with a
    HIGHER first-pass GREEN rate than cycles that didn't retrieve it, over
    the same playbook's cycle history?"""

    bullet_id: str
    treatment_samples: int          # cycles that retrieved this bullet
    control_samples: int            # cycles that did not
    treatment_first_pass_rate: float
    control_first_pass_rate: float | None  # None when control_samples == 0
    uplift: float | None            # treatment - control; None when control is undefined


class PlaybookReliabilityAnalyzer:
    """Correlates bullet retrieval with first-pass GREEN outcomes."""

    def __init__(
        self,
        experiment_logger: ExperimentLogger,
        playbook_manager: PlaybookManager,
    ) -> None:
        self._logger = experiment_logger
        self._playbook_manager = playbook_manager

    def bullet_reliability(self, playbook_id: str) -> list[BulletReliability]:
        """For each bullet in the playbook, compute first-pass rate across cycles
        where it was retrieved.

        Bullets with zero retrievals are excluded.
        Results are sorted by first_pass_rate descending.
        """
        records = self._logger.get_tdd_cycle_records(playbook_id=playbook_id)

        # Accumulate per-bullet stats
        times_retrieved: dict[str, int] = {}
        first_pass_hits: dict[str, int] = {}

        for record in records:
            is_first_pass = (
                record["result"] == "SUCCESS" and record["retry_count"] == 0
            )
            for bullet_id in record.get("retrieved_bullet_ids") or []:
                times_retrieved[bullet_id] = times_retrieved.get(bullet_id, 0) + 1
                if is_first_pass:
                    first_pass_hits[bullet_id] = first_pass_hits.get(bullet_id, 0) + 1

        result = [
            BulletReliability(
                bullet_id=bid,
                times_retrieved=count,
                first_pass_count=first_pass_hits.get(bid, 0),
                first_pass_rate=first_pass_hits.get(bid, 0) / count,
            )
            for bid, count in times_retrieved.items()
        ]
        result.sort(key=lambda r: r.first_pass_rate, reverse=True)
        return result

    def bullet_uplift(self, playbook_id: str, min_samples: int = 1) -> list[BulletUplift]:
        """Causal uplift per bullet: Uplift(b) = P(GREEN | b retrieved) -
        P(GREEN | b not retrieved), computed over the SAME playbook's full
        cycle history for both groups. Unlike bullet_reliability() (which
        only ever looks at cycles that retrieved a bullet, so it can't say
        whether that rate is actually better or worse than not using it),
        this gives every bullet a real control group: every cycle for the
        playbook that did NOT retrieve it.

        A bullet is excluded entirely if its treatment sample count is
        below min_samples (not enough evidence). uplift/control_first_pass_rate
        are None, never a fabricated 0.0, when a bullet was retrieved in
        every recorded cycle (no control group exists to compare against).

        Sorted worst-first (most negative uplift first, undefined-uplift
        bullets last) -- the order a pruning tool actually wants.
        """
        records = self._logger.get_tdd_cycle_records(playbook_id=playbook_id)

        all_bullet_ids: set[str] = set()
        for record in records:
            all_bullet_ids.update(record.get("retrieved_bullet_ids") or [])

        treatment_total: dict[str, int] = {}
        treatment_hits: dict[str, int] = {}
        control_total: dict[str, int] = {}
        control_hits: dict[str, int] = {}

        for record in records:
            is_first_pass = record["result"] == "SUCCESS" and record["retry_count"] == 0
            retrieved = set(record.get("retrieved_bullet_ids") or [])
            for bullet_id in all_bullet_ids:
                if bullet_id in retrieved:
                    treatment_total[bullet_id] = treatment_total.get(bullet_id, 0) + 1
                    if is_first_pass:
                        treatment_hits[bullet_id] = treatment_hits.get(bullet_id, 0) + 1
                else:
                    control_total[bullet_id] = control_total.get(bullet_id, 0) + 1
                    if is_first_pass:
                        control_hits[bullet_id] = control_hits.get(bullet_id, 0) + 1

        result = []
        for bullet_id in all_bullet_ids:
            t_total = treatment_total.get(bullet_id, 0)
            if t_total < min_samples:
                continue
            t_rate = treatment_hits.get(bullet_id, 0) / t_total
            c_total = control_total.get(bullet_id, 0)
            c_rate = (control_hits.get(bullet_id, 0) / c_total) if c_total else None
            result.append(BulletUplift(
                bullet_id=bullet_id,
                treatment_samples=t_total,
                control_samples=c_total,
                treatment_first_pass_rate=t_rate,
                control_first_pass_rate=c_rate,
                uplift=(t_rate - c_rate) if c_rate is not None else None,
            ))

        result.sort(key=lambda r: (r.uplift is None, r.uplift if r.uplift is not None else 0.0))
        return result
