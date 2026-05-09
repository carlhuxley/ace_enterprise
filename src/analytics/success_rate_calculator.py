"""Overall system success rate — across experiment types, playbook versions, and time."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.storage.experiment_logger import ExperimentLogger


@dataclass
class RatePeriod:
    period_start: datetime
    period_end: datetime
    total: int
    success_count: int
    success_rate: float


@dataclass
class VersionRate:
    playbook_version: str
    total: int
    success_count: int
    success_rate: float


class SuccessRateCalculator:
    """Measures experiment success rates across the system."""

    def __init__(self, experiment_logger: ExperimentLogger) -> None:
        self._logger = experiment_logger

    def overall_rate(
        self,
        experiment_type: str | None = None,
        since: datetime | None = None,
    ) -> float:
        """Fraction of experiments with result == SUCCESS."""
        records = self._logger.get_experiment_records(
            experiment_type=experiment_type, since=since
        )
        if not records:
            return 0.0
        successes = [r for r in records if r["result"] == "SUCCESS"]
        return len(successes) / len(records)

    def rate_by_type(self, since: datetime | None = None) -> dict[str, float]:
        """Success rate per experiment type."""
        records = self._logger.get_experiment_records(since=since)
        by_type: dict[str, list] = {}
        for r in records:
            by_type.setdefault(r["experiment_type"], []).append(r)
        return {
            t: len([r for r in recs if r["result"] == "SUCCESS"]) / len(recs)
            for t, recs in by_type.items()
        }

    def rate_by_playbook_version(
        self,
        experiment_type: str | None = None,
    ) -> list[VersionRate]:
        """Per-version success rates, sorted newest version first."""
        records = self._logger.get_experiment_records(experiment_type=experiment_type)
        by_version: dict[str, list] = {}
        for r in records:
            by_version.setdefault(r["playbook_version"], []).append(r)
        result = [
            VersionRate(
                playbook_version=v,
                total=len(recs),
                success_count=len([r for r in recs if r["result"] == "SUCCESS"]),
                success_rate=len([r for r in recs if r["result"] == "SUCCESS"]) / len(recs),
            )
            for v, recs in by_version.items()
        ]
        result.sort(key=lambda r: r.playbook_version, reverse=True)
        return result

    def trend(
        self,
        experiment_type: str | None = None,
        periods: int = 10,
        period_days: int = 7,
    ) -> list[RatePeriod]:
        """Success rate over equal time windows, oldest first.

        Windows with no experiments are omitted.
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(days=periods * period_days)
        records = self._logger.get_experiment_records(
            experiment_type=experiment_type, since=cutoff
        )

        result: list[RatePeriod] = []
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
            success_count = len([r for r in bucket if r["result"] == "SUCCESS"])
            result.append(RatePeriod(
                period_start=period_start,
                period_end=period_end,
                total=len(bucket),
                success_count=success_count,
                success_rate=success_count / len(bucket),
            ))

        result.reverse()  # oldest first
        return result
