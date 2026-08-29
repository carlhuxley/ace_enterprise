"""
Production Data Analyzer for TDD Quality Metrics.

Analyzes quality data from existing experiment_logs to understand
which models perform best in production TDD cycles.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from src.benchmark.blind_evaluation import BlindEvaluator, Submission
from src.benchmark.model_attribution import ModelAttributionTracker
from src.storage.models import ExperimentLogModel
from src.storage.repository import PlaybookRepository

logger = logging.getLogger(__name__)


@dataclass
class ModelPerformance:
    """Performance metrics for a single model."""

    model_id: str
    task_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    error_count: int = 0
    total_latency_ms: float = 0.0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    tasks_by_type: dict[str, int] = field(default_factory=dict)
    quality_scores: list[float] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.task_count == 0:
            return 0.0
        return self.success_count / self.task_count

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency."""
        if self.task_count == 0:
            return 0.0
        return self.total_latency_ms / self.task_count

    @property
    def avg_cost_usd(self) -> float:
        """Calculate average cost per task in USD."""
        if self.task_count == 0:
            return 0.0
        return self.total_cost_usd / self.task_count

    @property
    def avg_tokens(self) -> float:
        """Calculate average tokens per task."""
        if self.task_count == 0:
            return 0.0
        return self.total_tokens / self.task_count

    @property
    def avg_quality_score(self) -> float:
        """Calculate average quality score."""
        if not self.quality_scores:
            return 0.0
        return sum(self.quality_scores) / len(self.quality_scores)


@dataclass
class ProductionReport:
    """Comprehensive production quality report."""

    period_start: datetime
    period_end: datetime
    total_cycles: int
    unique_models: int
    model_performance: dict[str, ModelPerformance]
    best_model_overall: str | None
    best_model_by_task_type: dict[str, str]
    trends: dict[str, Any]

    def print_summary(self) -> None:
        """Print a formatted summary of the report."""
        print("\n" + "=" * 60)
        print("Production Quality Analysis")
        print("=" * 60)
        print(f"Period: {self.period_start.date()} to {self.period_end.date()}")
        print(f"Total cycles: {self.total_cycles}")
        print(f"Unique models: {self.unique_models}")
        print()

        if not self.model_performance:
            print("No model performance data available.")
            print("(Model attribution may not be captured in historical data)")
            return

        # Model Performance Table
        print("Model Performance:")
        print("┌" + "─" * 35 + "┬" + "─" * 7 + "┬" + "─" * 9 + "┬" + "─" * 10 + "┐")
        print(f"│ {'Model':<33} │ {'Tasks':>5} │ {'Success':>7} │ {'Avg Time':>8} │")
        print("├" + "─" * 35 + "┼" + "─" * 7 + "┼" + "─" * 9 + "┼" + "─" * 10 + "┤")

        # Sort by success rate descending
        sorted_models = sorted(
            self.model_performance.values(),
            key=lambda m: (m.success_rate, m.task_count),
            reverse=True
        )

        for perf in sorted_models:
            model_name = perf.model_id[:33] if len(perf.model_id) > 33 else perf.model_id
            success_pct = f"{perf.success_rate * 100:.0f}%"
            avg_time = f"{perf.avg_latency_ms / 1000:.1f}s" if perf.avg_latency_ms else "N/A"
            print(f"│ {model_name:<33} │ {perf.task_count:>5} │ {success_pct:>7} │ {avg_time:>8} │")

        print("└" + "─" * 35 + "┴" + "─" * 7 + "┴" + "─" * 9 + "┴" + "─" * 10 + "┘")

        # Best model by task type
        if self.best_model_by_task_type:
            print("\nBest Model by Task Type:")
            for task_type, model in self.best_model_by_task_type.items():
                print(f"  - {task_type}: {model}")

        print()


class ProductionDataAnalyzer:
    """
    Analyze quality data from existing experiment_logs.

    Extracts model attribution, calculates metrics, and generates reports
    for understanding which models perform best in production TDD cycles.
    """

    def __init__(self, repository: PlaybookRepository | None = None):
        """
        Initialize the analyzer.

        Args:
            repository: Optional repository instance for database access
        """
        self.repo = repository or PlaybookRepository()
        self.evaluator = BlindEvaluator()

    def _normalize_model_name(self, model_name: str) -> str:
        """
        Normalize model names for consistent comparison.

        Handles variations like:
        - gemini-2.0-flash-001 vs google/gemini-2.0-flash-001
        - GEMINI vs gemini (case)
        - Preserves :free suffix for cost analysis
        """
        if not model_name:
            return model_name

        # Lowercase for consistent comparison
        normalized = model_name.lower()

        # Ensure provider prefix for known model families
        if "/" not in normalized:
            normalized = self._add_provider_prefix(normalized)

        return normalized

    def _add_provider_prefix(self, model_name: str) -> str:
        """
        Add provider prefix to model names that are missing it.

        OpenRouter sometimes returns models without provider prefix.
        """
        # Known model prefixes and their providers
        provider_patterns = [
            ("gemini", "google"),
            ("gemma", "google"),
            ("claude", "anthropic"),
            ("gpt-", "openai"),
            ("o1", "openai"),
            ("llama", "meta-llama"),
            ("qwen", "qwen"),
            ("mistral", "mistralai"),
            ("mixtral", "mistralai"),
            ("deepseek", "deepseek"),
            ("phi-", "microsoft"),
            ("codestral", "mistralai"),
        ]

        for prefix, provider in provider_patterns:
            if model_name.startswith(prefix):
                return f"{provider}/{model_name}"

        # Unknown provider - return as-is
        return model_name

    def _get_canonical_model_name(
        self, actual_model: str | None, requested_model: str | None
    ) -> str | None:
        """
        Get canonical model name, preferring requested_model to preserve :free suffix.

        OpenRouter returns actual_model without :free suffix even when free tier
        was requested. We prefer requested_model to preserve cost tier info.

        Example:
        - requested_model: google/gemini-2.0-flash:free
        - actual_model: google/gemini-2.0-flash
        - canonical: google/gemini-2.0-flash:free (preserves free tier info)
        """
        # Prefer requested_model - it preserves :free suffix for cost tracking
        if requested_model:
            return self._normalize_model_name(requested_model)

        # Fall back to actual_model if no requested_model
        if actual_model:
            return self._normalize_model_name(actual_model)

        return None

    def extract_model_performance(self, days: int = 30) -> dict[str, ModelPerformance]:
        """
        Query experiment_logs and extract model performance metrics.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary mapping model_id to ModelPerformance
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        performance: dict[str, ModelPerformance] = {}

        with self.repo.get_session() as session:
            # Query TDD cycles from experiment_logs
            experiments = session.query(ExperimentLogModel).filter(
                ExperimentLogModel.timestamp >= cutoff,
                ExperimentLogModel.task_data["type"].as_string().in_(["tdd_cycle", "build_feature", "bug_fix"])
            ).all()

            for exp in experiments:
                # Extract model attribution from generator_data
                generator_data = exp.generator_data or {}
                actual_model = generator_data.get("actual_model")
                requested_model = generator_data.get("requested_model")
                model = generator_data.get("model")  # Used by build_feature

                # Get canonical name - check actual_model, requested_model, then model
                model_id = self._get_canonical_model_name(actual_model, requested_model)
                if model_id is None and model:
                    model_id = self._normalize_model_name(model)

                # Skip records without model attribution
                if model_id is None:
                    continue

                # Initialize performance record if needed
                if model_id not in performance:
                    performance[model_id] = ModelPerformance(model_id=model_id)

                perf = performance[model_id]
                perf.task_count += 1

                # Track result
                if exp.result == "SUCCESS":
                    perf.success_count += 1
                elif exp.result == "FAILED":
                    perf.failed_count += 1
                else:
                    perf.error_count += 1

                # Track latency and tokens if available
                latency = generator_data.get("latency_ms")
                if latency:
                    perf.total_latency_ms += latency

                tokens = generator_data.get("tokens_used")
                if tokens:
                    perf.total_tokens += tokens

                # Track cost if available
                cost = generator_data.get("cost_usd")
                if cost:
                    perf.total_cost_usd += cost

                # Track by task type (test_name or requirement)
                task_data = exp.task_data or {}
                test_name = task_data.get("test_name", "unknown")
                # Simplify test name to category
                task_type = self._categorize_task(test_name)
                perf.tasks_by_type[task_type] = perf.tasks_by_type.get(task_type, 0) + 1

        logger.info(f"Extracted performance for {len(performance)} models from {days} days of data")
        return performance

    def _categorize_task(self, test_name: str) -> str:
        """Categorize a test name into a task type."""
        test_name_lower = test_name.lower()

        if "create" in test_name_lower or "init" in test_name_lower:
            return "creation"
        elif "update" in test_name_lower or "modify" in test_name_lower:
            return "update"
        elif "delete" in test_name_lower or "remove" in test_name_lower:
            return "deletion"
        elif "validate" in test_name_lower or "check" in test_name_lower:
            return "validation"
        elif "auth" in test_name_lower or "login" in test_name_lower:
            return "authentication"
        elif "api" in test_name_lower or "endpoint" in test_name_lower:
            return "api"
        else:
            return "general"

    def backfill_quality_scores(self, limit: int = 100) -> int:
        """
        For recent cycles, extract code and run BlindEvaluator.

        Args:
            limit: Maximum number of cycles to evaluate

        Returns:
            Number of cycles evaluated
        """
        evaluated = 0

        with self.repo.get_session() as session:
            # Get recent TDD cycles
            experiments = session.query(ExperimentLogModel).filter(
                ExperimentLogModel.task_data["type"].as_string().in_(["tdd_cycle", "build_feature", "bug_fix"])
            ).order_by(
                ExperimentLogModel.timestamp.desc()
            ).limit(limit).all()

            for exp in experiments:
                generator_data = exp.generator_data or {}
                impl_code = generator_data.get("implementation_code", "")
                test_code = generator_data.get("test_code", "")

                if not impl_code:
                    continue

                # Create submission for evaluation
                submission = Submission(
                    task_id=exp.experiment_id,
                    submission_id=exp.experiment_id,
                    output_type="code",
                    output_content=impl_code,
                    test_content=test_code if test_code else None
                )

                try:
                    result = self.evaluator.evaluate(submission)
                    # Store quality score back (would need schema update)
                    logger.debug(
                        f"Evaluated {exp.experiment_id}: "
                        f"quality_score={result.quality_score}"
                    )
                    evaluated += 1
                except Exception as e:
                    logger.warning(f"Failed to evaluate {exp.experiment_id}: {e}")

        logger.info(f"Backfilled quality scores for {evaluated} cycles")
        return evaluated

    def populate_model_attribution(self, days: int = 30) -> ModelAttributionTracker:
        """
        Feed historical data into ModelAttributionTracker.

        Args:
            days: Number of days to look back

        Returns:
            Populated ModelAttributionTracker for analysis
        """
        tracker = ModelAttributionTracker()
        cutoff = datetime.utcnow() - timedelta(days=days)

        with self.repo.get_session() as session:
            experiments = session.query(ExperimentLogModel).filter(
                ExperimentLogModel.timestamp >= cutoff,
                ExperimentLogModel.task_data["type"].as_string().in_(["tdd_cycle", "build_feature", "bug_fix"])
            ).all()

            for exp in experiments:
                generator_data = exp.generator_data or {}
                actual_model = generator_data.get("actual_model")
                requested_model = generator_data.get("requested_model")
                model = generator_data.get("model")  # Used by build_feature

                # Get canonical name - check actual_model, requested_model, then model
                model_id = self._get_canonical_model_name(actual_model, requested_model)
                if model_id is None and model:
                    model_id = self._normalize_model_name(model)

                # Skip records without model attribution
                if model_id is None:
                    continue

                # Normalize requested_model for tracker (or use model_id as fallback)
                normalized_requested = self._normalize_model_name(requested_model) if requested_model else model_id
                provider = generator_data.get("provider", "unknown")

                # Determine task type
                task_data = exp.task_data or {}
                test_name = task_data.get("test_name", "unknown")
                task_type = self._categorize_task(test_name)

                # Calculate quality score (simplified)
                quality_score = 100.0 if exp.result == "SUCCESS" else 0.0

                tracker.record_completion(
                    model_id=model_id,
                    requested_model=normalized_requested,
                    provider=provider,
                    task_type=task_type,
                    success=exp.result == "SUCCESS",
                    quality_score=quality_score,
                    timestamp=exp.timestamp,
                    latency_ms=generator_data.get("latency_ms"),
                )

        logger.info(f"Populated tracker with data from {len(experiments)} cycles")
        return tracker

    def generate_report(self, days: int = 30) -> ProductionReport:
        """
        Generate comprehensive production quality report.

        Args:
            days: Number of days to analyze

        Returns:
            ProductionReport with rankings, trends, and recommendations
        """
        period_end = datetime.utcnow()
        period_start = period_end - timedelta(days=days)

        # Get model performance
        performance = self.extract_model_performance(days=days)

        # Count total cycles
        total_cycles = sum(p.task_count for p in performance.values())

        # Find best model overall (by success rate, min 3 tasks)
        eligible = [p for p in performance.values() if p.task_count >= 3]
        best_overall = None
        if eligible:
            best_overall = max(eligible, key=lambda p: p.success_rate).model_id

        # Find best model by task type
        best_by_type: dict[str, str] = {}
        task_types = set()
        for p in performance.values():
            task_types.update(p.tasks_by_type.keys())

        for task_type in task_types:
            best_model = None
            best_rate = -1.0
            for p in performance.values():
                count = p.tasks_by_type.get(task_type, 0)
                if count >= 2:  # Minimum threshold
                    # Estimate success rate for this task type (simplified)
                    rate = p.success_rate
                    if rate > best_rate:
                        best_rate = rate
                        best_model = p.model_id
            if best_model:
                best_by_type[task_type] = best_model

        # Calculate trends (simplified - compare first half to second half)
        trends = self._calculate_trends(days)

        return ProductionReport(
            period_start=period_start,
            period_end=period_end,
            total_cycles=total_cycles,
            unique_models=len(performance),
            model_performance=performance,
            best_model_overall=best_overall,
            best_model_by_task_type=best_by_type,
            trends=trends
        )

    def _calculate_trends(self, days: int) -> dict[str, Any]:
        """Calculate performance trends over time."""
        # Simplified trend calculation
        return {
            "period_days": days,
            "trend_direction": "stable",  # Could be "improving", "declining"
            "note": "Trend analysis requires more data points"
        }

    def get_raw_data(self, days: int = 30, limit: int = 100) -> list[dict]:
        """
        Get raw experiment data for debugging/inspection.

        Args:
            days: Number of days to look back
            limit: Maximum records to return

        Returns:
            List of experiment records as dictionaries
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        results = []

        with self.repo.get_session() as session:
            experiments = session.query(ExperimentLogModel).filter(
                ExperimentLogModel.timestamp >= cutoff,
                ExperimentLogModel.task_data["type"].as_string().in_(["tdd_cycle", "build_feature", "bug_fix"])
            ).order_by(
                ExperimentLogModel.timestamp.desc()
            ).limit(limit).all()

            for exp in experiments:
                generator_data = exp.generator_data or {}
                task_data = exp.task_data or {}

                results.append({
                    "experiment_id": exp.experiment_id,
                    "timestamp": exp.timestamp.isoformat(),
                    "result": exp.result,
                    "test_name": task_data.get("test_name"),
                    "actual_model": generator_data.get("actual_model"),
                    "requested_model": generator_data.get("requested_model"),
                    "provider": generator_data.get("provider"),
                    "latency_ms": generator_data.get("latency_ms"),
                    "tokens_used": generator_data.get("tokens_used"),
                })

        return results
