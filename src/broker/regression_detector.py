"""Regression detector for tracking quality changes across model versions.

Bead: ace_enterprise-qo1

Two complementary detection strategies:
 1. Version-based: compare mean quality of the current version's first
    WINDOW tasks against the previous version's baseline.  If the drop
    exceeds THRESHOLD, emit a RegressionAlert.
 2. CUSUM: time-series change-point detection on a raw quality sequence
    without requiring explicit version labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

REGRESSION_THRESHOLD = 0.15   # 15 % quality drop → REGRESSION_DETECTED
WARNING_THRESHOLD = 0.07      # 7 % drop → WARNING
DEFAULT_WINDOW = 10           # compare first N tasks of new version


@dataclass
class QualityBaseline:
    """Quality summary for one (model_id, version) pair."""

    model_id: str
    version: str
    mean_score: float
    std_dev: float
    sample_count: int
    established_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class RegressionAlert:
    """Fired when a quality regression is detected."""

    model_id: str
    baseline_version: str
    current_version: str
    baseline_mean: float
    current_mean: float
    drop_fraction: float     # (baseline_mean - current_mean) / baseline_mean
    sample_count: int        # number of samples in current version window
    severity: str            # "REGRESSION_DETECTED" | "WARNING"
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class RegressionDetector:
    """Tracks quality scores by (model_id, version) and detects regressions.

    Usage::

        detector = RegressionDetector()
        detector.record("gpt-4", "2024-01", 85.0)
        detector.record("gpt-4", "2024-01", 88.0)
        detector.record("gpt-4", "2024-02", 65.0)  # new version, lower quality
        alerts = detector.check_all()
    """

    def __init__(
        self,
        regression_threshold: float = REGRESSION_THRESHOLD,
        warning_threshold: float = WARNING_THRESHOLD,
        window: int = DEFAULT_WINDOW,
    ) -> None:
        self._regression_threshold = regression_threshold
        self._warning_threshold = warning_threshold
        self._window = window

        # model_id → version → [quality_scores]
        self._scores: dict[str, dict[str, list[float]]] = {}
        # model_id → ordered list of versions (first-seen order)
        self._version_order: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def record(
        self,
        model_id: str,
        version: str,
        quality_score: float,
        timestamp: datetime | None = None,  # reserved for future use
    ) -> None:
        """Record a quality score for a specific model version."""
        if model_id not in self._scores:
            self._scores[model_id] = {}
            self._version_order[model_id] = []

        if version not in self._scores[model_id]:
            self._scores[model_id][version] = []
            self._version_order[model_id].append(version)

        self._scores[model_id][version].append(float(quality_score))

    # ------------------------------------------------------------------
    # Baselines
    # ------------------------------------------------------------------

    def get_baseline(self, model_id: str, version: str) -> QualityBaseline | None:
        """Return the quality baseline for a specific model/version pair."""
        scores = self._scores.get(model_id, {}).get(version)
        if not scores:
            return None

        import statistics as _stats

        mean = _stats.mean(scores)
        std = _stats.stdev(scores) if len(scores) > 1 else 0.0
        return QualityBaseline(
            model_id=model_id,
            version=version,
            mean_score=mean,
            std_dev=std,
            sample_count=len(scores),
        )

    def get_version_history(self, model_id: str) -> list[str]:
        """Return versions for model_id in first-seen order."""
        return list(self._version_order.get(model_id, []))

    def get_known_models(self) -> list[str]:
        """Return all model IDs that have been recorded."""
        return list(self._scores.keys())

    # ------------------------------------------------------------------
    # Regression detection
    # ------------------------------------------------------------------

    def detect_regression(
        self,
        model_id: str,
        baseline_version: str,
        current_version: str,
    ) -> RegressionAlert | None:
        """Compare current_version against baseline_version for model_id.

        Uses the first WINDOW scores of current_version.
        Returns an alert if quality dropped beyond warning/regression thresholds,
        or None if no regression is detected.
        """
        baseline = self.get_baseline(model_id, baseline_version)
        if baseline is None or baseline.mean_score == 0:
            return None

        current_scores = (
            self._scores.get(model_id, {}).get(current_version, [])
        )
        if not current_scores:
            return None

        window_scores = current_scores[: self._window]

        import statistics as _stats

        current_mean = _stats.mean(window_scores)
        drop = (baseline.mean_score - current_mean) / baseline.mean_score

        if drop >= self._regression_threshold:
            severity = "REGRESSION_DETECTED"
        elif drop >= self._warning_threshold:
            severity = "WARNING"
        else:
            return None

        return RegressionAlert(
            model_id=model_id,
            baseline_version=baseline_version,
            current_version=current_version,
            baseline_mean=baseline.mean_score,
            current_mean=current_mean,
            drop_fraction=drop,
            sample_count=len(window_scores),
            severity=severity,
        )

    def check_all(self) -> list[RegressionAlert]:
        """Check every model for regressions between consecutive versions.

        Compares each version against its immediate predecessor and returns
        all alerts found.
        """
        alerts: list[RegressionAlert] = []
        for model_id, versions in self._version_order.items():
            for i in range(1, len(versions)):
                alert = self.detect_regression(
                    model_id, versions[i - 1], versions[i]
                )
                if alert:
                    alerts.append(alert)
        return alerts

    # ------------------------------------------------------------------
    # CUSUM change-point detection
    # ------------------------------------------------------------------

    @staticmethod
    def detect_cusum(
        scores: list[float],
        baseline_mean: float,
        k_factor: float = 0.05,
        threshold: float = 5.0,
    ) -> int | None:
        """Return the index of the first detected downward change-point.

        Uses a lower one-sided CUSUM filter:
            S_i = max(0, S_{i-1} + (baseline_mean - x_i - k))
        A change-point is signalled when S_i > threshold.

        Args:
            scores:         Quality score sequence to analyse.
            baseline_mean:  Expected mean under normal operation.
            k_factor:       Slack as a fraction of baseline_mean (default 0.05).
                            A smaller value makes the detector more sensitive.
            threshold:      Detection threshold in the same units as quality
                            scores; tune to avoid false positives.

        Returns:
            Index of first detected change-point, or None if none found.
        """
        if not scores or baseline_mean <= 0:
            return None

        k = k_factor * baseline_mean
        S = 0.0
        for i, x in enumerate(scores):
            S = max(0.0, S + (baseline_mean - x - k))
            if S > threshold:
                return i
        return None

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def generate_report(self, model_id: str) -> dict:
        """Return a summary dict for model_id across all versions."""
        versions = self.get_version_history(model_id)
        baselines = {v: self.get_baseline(model_id, v) for v in versions}
        alerts = [
            self.detect_regression(model_id, versions[i - 1], versions[i])
            for i in range(1, len(versions))
        ]
        return {
            "model_id": model_id,
            "versions": versions,
            "baselines": {
                v: {
                    "mean": b.mean_score,
                    "std_dev": b.std_dev,
                    "sample_count": b.sample_count,
                }
                for v, b in baselines.items()
                if b is not None
            },
            "alerts": [
                {
                    "baseline_version": a.baseline_version,
                    "current_version": a.current_version,
                    "drop_fraction": a.drop_fraction,
                    "severity": a.severity,
                }
                for a in alerts
                if a is not None
            ],
        }
