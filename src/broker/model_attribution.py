"""
OpenRouter Model Attribution for Performance Metrics

Tracks which OpenRouter model was actually used for each task and provides
aggregated performance metrics by model ID.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal


@dataclass
class TaskCompletion:
    """Record of a completed task with model attribution."""
    model_id: str
    requested_model: str
    provider: str
    task_type: str
    success: bool
    quality_score: float
    timestamp: datetime = field(default_factory=datetime.now)
    latency_ms: float | None = None
    cost_usd: float | None = None


@dataclass
class ModelMetrics:
    """Aggregated performance metrics for a model."""
    model_id: str
    task_count: int
    success_count: int
    total_quality_score: float
    first_seen: datetime
    last_seen: datetime

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0.0 to 1.0)."""
        if self.task_count == 0:
            return 0.0
        return self.success_count / self.task_count

    @property
    def avg_quality_score(self) -> float:
        """Calculate average quality score."""
        if self.task_count == 0:
            return 0.0
        return self.total_quality_score / self.task_count


@dataclass
class ModelFamilyMetrics:
    """Aggregated metrics for a model family (e.g., all qwen/ models)."""
    family: str
    models: list[str]
    task_count: int
    success_count: int
    total_quality_score: float

    @property
    def success_rate(self) -> float:
        if self.task_count == 0:
            return 0.0
        return self.success_count / self.task_count

    @property
    def avg_quality_score(self) -> float:
        if self.task_count == 0:
            return 0.0
        return self.total_quality_score / self.task_count


@dataclass
class DailyMetrics:
    """Performance metrics for a single day."""
    date: datetime
    task_count: int
    success_count: int
    total_quality_score: float

    @property
    def success_rate(self) -> float:
        if self.task_count == 0:
            return 0.0
        return self.success_count / self.task_count

    @property
    def avg_quality_score(self) -> float:
        if self.task_count == 0:
            return 0.0
        return self.total_quality_score / self.task_count


class ModelAttributionTracker:
    """
    Tracks OpenRouter model attribution in performance metrics.

    Stores task completions with model information and provides
    aggregation methods for analyzing model performance.
    """

    def __init__(self):
        self._completions: list[TaskCompletion] = []
        self._metrics_by_model: dict[str, ModelMetrics] = {}
        self._metrics_by_model_task_type: dict[str, dict[str, ModelMetrics]] = {}

    def record_completion(
        self,
        model_id: str,
        requested_model: str,
        provider: str,
        task_type: str,
        success: bool,
        quality_score: float,
        timestamp: datetime | None = None,
        latency_ms: float | None = None,
        cost_usd: float | None = None,
    ) -> TaskCompletion:
        """
        Record a task completion with model attribution.

        Args:
            model_id: The actual model used (from OpenRouter response)
            requested_model: The model that was requested
            provider: The provider (e.g., "openrouter")
            task_type: Type of task (e.g., "coding", "testing")
            success: Whether the task succeeded
            quality_score: Quality score (0-100)
            timestamp: When the task completed (defaults to now)
            latency_ms: Optional latency in milliseconds
            cost_usd: Optional cost in USD

        Returns:
            The recorded TaskCompletion
        """
        completion = TaskCompletion(
            model_id=model_id,
            requested_model=requested_model,
            provider=provider,
            task_type=task_type,
            success=success,
            quality_score=quality_score,
            timestamp=timestamp or datetime.now(),
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )
        self._completions.append(completion)
        self._update_metrics(completion)
        return completion

    def _update_metrics(self, completion: TaskCompletion) -> None:
        """Update aggregated metrics with a new completion."""
        model_id = completion.model_id
        task_type = completion.task_type

        # Update overall model metrics
        if model_id not in self._metrics_by_model:
            self._metrics_by_model[model_id] = ModelMetrics(
                model_id=model_id,
                task_count=0,
                success_count=0,
                total_quality_score=0.0,
                first_seen=completion.timestamp,
                last_seen=completion.timestamp,
            )

        metrics = self._metrics_by_model[model_id]
        metrics.task_count += 1
        if completion.success:
            metrics.success_count += 1
        metrics.total_quality_score += completion.quality_score
        metrics.last_seen = max(metrics.last_seen, completion.timestamp)

        # Update model+task_type metrics
        if model_id not in self._metrics_by_model_task_type:
            self._metrics_by_model_task_type[model_id] = {}

        if task_type not in self._metrics_by_model_task_type[model_id]:
            self._metrics_by_model_task_type[model_id][task_type] = ModelMetrics(
                model_id=model_id,
                task_count=0,
                success_count=0,
                total_quality_score=0.0,
                first_seen=completion.timestamp,
                last_seen=completion.timestamp,
            )

        task_metrics = self._metrics_by_model_task_type[model_id][task_type]
        task_metrics.task_count += 1
        if completion.success:
            task_metrics.success_count += 1
        task_metrics.total_quality_score += completion.quality_score
        task_metrics.last_seen = max(task_metrics.last_seen, completion.timestamp)

    def get_model_metrics(self, model_id: str) -> ModelMetrics | None:
        """Get aggregated metrics for a specific model."""
        return self._metrics_by_model.get(model_id)

    def get_all_model_metrics(self) -> dict[str, ModelMetrics]:
        """Get metrics for all tracked models."""
        return self._metrics_by_model.copy()

    def get_top_models(
        self,
        n: int = 3,
        sort_by: Literal["success_rate", "avg_quality_score", "task_count"] = "success_rate",
        min_task_count: int = 1,
    ) -> list[ModelMetrics]:
        """
        Get the top N models ranked by the specified metric.

        Args:
            n: Number of models to return
            sort_by: Metric to sort by
            min_task_count: Minimum tasks required to be included

        Returns:
            List of ModelMetrics sorted by the specified metric (descending)
        """
        eligible = [
            m for m in self._metrics_by_model.values()
            if m.task_count >= min_task_count
        ]

        if sort_by == "success_rate":
            eligible.sort(key=lambda m: m.success_rate, reverse=True)
        elif sort_by == "avg_quality_score":
            eligible.sort(key=lambda m: m.avg_quality_score, reverse=True)
        elif sort_by == "task_count":
            eligible.sort(key=lambda m: m.task_count, reverse=True)

        return eligible[:n]

    def filter_by_model_family(self, family: str) -> list[ModelMetrics]:
        """
        Get metrics for all models in a family (e.g., "qwen" -> all qwen/* models).

        Args:
            family: The model family prefix (without trailing slash)

        Returns:
            List of ModelMetrics for models in the family
        """
        prefix = f"{family}/"
        return [
            m for m in self._metrics_by_model.values()
            if m.model_id.startswith(prefix)
        ]

    def get_family_metrics(self, family: str) -> ModelFamilyMetrics:
        """
        Get aggregated metrics for an entire model family.

        Args:
            family: The model family prefix

        Returns:
            Aggregated ModelFamilyMetrics for the family
        """
        models = self.filter_by_model_family(family)

        return ModelFamilyMetrics(
            family=family,
            models=[m.model_id for m in models],
            task_count=sum(m.task_count for m in models),
            success_count=sum(m.success_count for m in models),
            total_quality_score=sum(m.total_quality_score for m in models),
        )

    def get_best_model_for_task_type(
        self,
        task_type: str,
        min_task_count: int = 1,
    ) -> str | None:
        """
        Get the best performing model for a specific task type.

        Args:
            task_type: The task type to query
            min_task_count: Minimum tasks required

        Returns:
            The model_id of the best performing model, or None if no data
        """
        best_model = None
        best_success_rate = -1.0

        for model_id, task_metrics in self._metrics_by_model_task_type.items():
            if task_type in task_metrics:
                metrics = task_metrics[task_type]
                if metrics.task_count >= min_task_count:
                    if metrics.success_rate > best_success_rate:
                        best_success_rate = metrics.success_rate
                        best_model = model_id

        return best_model

    def get_model_task_type_metrics(
        self,
        model_id: str,
        task_type: str,
    ) -> ModelMetrics | None:
        """Get metrics for a specific model and task type combination."""
        if model_id in self._metrics_by_model_task_type:
            return self._metrics_by_model_task_type[model_id].get(task_type)
        return None

    def get_daily_metrics(
        self,
        model_id: str,
        days: int = 7,
        end_date: datetime | None = None,
    ) -> list[DailyMetrics]:
        """
        Get daily performance metrics for a model over the specified period.

        Args:
            model_id: The model to query
            days: Number of days to look back
            end_date: End date (defaults to now)

        Returns:
            List of DailyMetrics for each day in the period
        """
        end = end_date or datetime.now()
        start = end - timedelta(days=days)

        # Filter completions for this model in the date range
        model_completions = [
            c for c in self._completions
            if c.model_id == model_id and start <= c.timestamp <= end
        ]

        # Group by date
        daily_data: dict[str, DailyMetrics] = {}

        for completion in model_completions:
            date_key = completion.timestamp.strftime("%Y-%m-%d")

            if date_key not in daily_data:
                daily_data[date_key] = DailyMetrics(
                    date=datetime.strptime(date_key, "%Y-%m-%d"),
                    task_count=0,
                    success_count=0,
                    total_quality_score=0.0,
                )

            daily = daily_data[date_key]
            daily.task_count += 1
            if completion.success:
                daily.success_count += 1
            daily.total_quality_score += completion.quality_score

        # Sort by date
        return sorted(daily_data.values(), key=lambda d: d.date)

    def detect_performance_trend(
        self,
        model_id: str,
        days: int = 7,
    ) -> Literal["improving", "declining", "stable"] | None:
        """
        Detect the performance trend for a model over time.

        Uses simple linear regression on daily success rates.

        Args:
            model_id: The model to analyze
            days: Number of days to analyze

        Returns:
            "improving", "declining", "stable", or None if insufficient data
        """
        daily = self.get_daily_metrics(model_id, days)

        if len(daily) < 2:
            return None

        # Calculate trend using first vs second half comparison
        mid = len(daily) // 2
        first_half = daily[:mid]
        second_half = daily[mid:]

        first_avg = sum(d.success_rate for d in first_half) / len(first_half)
        second_avg = sum(d.success_rate for d in second_half) / len(second_half)

        diff = second_avg - first_avg

        # Use 5% threshold for trend detection
        if diff > 0.05:
            return "improving"
        elif diff < -0.05:
            return "declining"
        else:
            return "stable"

    def to_audit_payload(
        self,
        model_id: str,
        requested_model: str,
        provider: str,
    ) -> dict:
        """
        Create an audit payload dict with model attribution fields.

        This is used when recording CYCLE_COMPLETED events.
        """
        return {
            "model_id": model_id,
            "requested_model": requested_model,
            "provider": provider,
        }
