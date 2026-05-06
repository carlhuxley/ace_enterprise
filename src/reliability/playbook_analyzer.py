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
