"""TDD cycle reliability — first-pass rate and trend over time."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.storage.experiment_logger import ExperimentLogger


@dataclass
class CyclePeriod:
    period_start: datetime
    period_end: datetime
    total_cycles: int
    first_pass_count: int
    first_pass_rate: float


class TDDCycleAnalyzer:
    """Measures first-pass GREEN rate and whether it improves over time."""

    def __init__(self, experiment_logger: ExperimentLogger) -> None:
        self._logger = experiment_logger

    def first_pass_rate(
        self,
        playbook_id: str | None = None,
        since: datetime | None = None,
    ) -> float:
        """Fraction of cycles that passed GREEN on the first attempt (retry_count == 0)."""
        records = self._logger.get_tdd_cycle_records(
            playbook_id=playbook_id, since=since
        )
        if not records:
            return 0.0
        successes = [r for r in records if r["result"] == "SUCCESS"]
        first_pass = [r for r in successes if r["retry_count"] == 0]
        return len(first_pass) / len(records)

    def trend(
        self,
        playbook_id: str | None = None,
        periods: int = 10,
        period_days: int = 7,
    ) -> list[CyclePeriod]:
        """First-pass rate broken into equal-width time windows, oldest first.

        Returns up to `periods` windows of `period_days` days each, working
        backwards from now. Windows with no cycles are omitted.
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(days=periods * period_days)
        records = self._logger.get_tdd_cycle_records(
            playbook_id=playbook_id, since=cutoff
        )

        result: list[CyclePeriod] = []
        for i in range(periods):
            period_end = now - timedelta(days=i * period_days)
            period_start = period_end - timedelta(days=period_days)
            bucket = [
                r for r in records
                if r["timestamp"] is not None
                and period_start <= r["timestamp"] < period_end
            ]
            if not bucket:
                continue
            successes = [r for r in bucket if r["result"] == "SUCCESS"]
            first_pass = [r for r in successes if r["retry_count"] == 0]
            result.append(CyclePeriod(
                period_start=period_start,
                period_end=period_end,
                total_cycles=len(bucket),
                first_pass_count=len(first_pass),
                first_pass_rate=len(first_pass) / len(bucket),
            ))

        result.reverse()  # oldest first
        return result
