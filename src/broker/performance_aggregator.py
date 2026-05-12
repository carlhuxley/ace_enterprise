"""Performance Aggregator - Extracts metrics from audit trail.

This component queries the audit trail and extracts ONLY performance
metrics (success rate, latency, cost, complexity). It maintains the
double-blind principle: no content, prompts, or agent identities.

Bead: ace_enterprise-lfu
"""

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.audit.store import AuditStore, AuditQuery
from src.audit.schemas import AuditEventType

logger = logging.getLogger(__name__)


@dataclass
class ModelProfile:
    """Strength/weakness profile derived from per-model task-type metrics."""

    model_id: str
    strengths: list[str]          # task types where rate > avg + 0.10
    weaknesses: list[str]         # task types where rate < avg - 0.10
    optimal_complexity: int | None  # complexity level with best success rate
    avoid_complexity: int | None    # complexity level with worst success rate


@dataclass
class LatencyQualityReport:
    """Latency-quality correlation summary for one agent."""

    agent_ref: str
    latency_quality_correlation: float | None  # Pearson r; None = insufficient data
    latency_p50_seconds: float
    latency_p95_seconds: float
    latency_p50_by_quality_tier: dict[str, float]  # "low"|"mid"|"high" → p50 latency
    sample_count: int


@dataclass
class AgentPerformanceMetrics:
    """Performance metrics for an agent (anonymized by agent_ref)."""

    agent_ref: str  # Opaque reference, not identity

    # Success metrics
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0

    # Timing metrics
    avg_latency_seconds: float = 0.0
    min_latency_seconds: float = 0.0
    max_latency_seconds: float = 0.0

    # Complexity breakdown
    success_by_complexity: dict[int, float] = field(default_factory=dict)

    # Task type breakdown
    success_by_task_type: dict[str, float] = field(default_factory=dict)

    # Cost (if tracked)
    total_cost: float = 0.0
    avg_cost_per_task: float = 0.0

    # Variance / consistency (from quality_score audit field)
    variance_coefficient: float = 0.0   # std_dev / mean of quality scores; 0 = no data
    consistency_rate: float = 1.0       # max(success_rate, 1-success_rate); 1 = no data

    # Latency-quality correlation (requires both fields in audit events)
    latency_quality_correlation: float | None = None  # Pearson r; None = insufficient data
    latency_p50_seconds: float = 0.0
    latency_p95_seconds: float = 0.0
    latency_p50_by_quality_tier: dict[str, float] = field(default_factory=dict)

    # Per-version quality tracking (for regression detection)
    quality_by_version: dict[str, list[float]] = field(default_factory=dict)

    # Temporal
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    @property
    def success_rate(self) -> float:
        """Overall success rate."""
        if self.total_tasks == 0:
            return 0.0
        return self.successful_tasks / self.total_tasks

    @property
    def reliability_score(self) -> float:
        """Reliability based on volume and success."""
        if self.total_tasks < 5:
            # Low confidence with few samples
            return self.success_rate * 0.5
        elif self.total_tasks < 20:
            return self.success_rate * 0.8
        else:
            return self.success_rate

    @property
    def variance_adjusted_reliability(self) -> float:
        """Reliability penalised for inconsistency and quality variance.

        Formula: reliability_score * consistency_rate * (1 - variance_coefficient)
        Defaults (consistency_rate=1.0, variance_coefficient=0.0) reproduce
        reliability_score exactly so behaviour is unchanged when no variance
        data is present.
        """
        vc = min(self.variance_coefficient, 1.0)
        return self.reliability_score * self.consistency_rate * (1.0 - vc)

    def can_handle_complexity(self, level: int, min_success_rate: float = 0.7) -> bool:
        """Check if agent can handle a complexity level."""
        if level not in self.success_by_complexity:
            return False
        return self.success_by_complexity[level] >= min_success_rate


class PerformanceAggregator:
    """Aggregates performance metrics from audit trail.

    Key principle: Extract ONLY metrics, never content.

    What it extracts:
    - Success/failure counts
    - Latency statistics
    - Complexity level performance
    - Task type performance
    - Cost summaries

    What it NEVER extracts:
    - Prompt contents
    - Output contents
    - Agent identity/model names
    - Business logic
    """

    def __init__(self, audit_store: AuditStore):
        """Initialize with audit store connection."""
        self._store = audit_store
        self._cache: dict[str, AgentPerformanceMetrics] = {}
        self._cache_expiry: datetime | None = None
        self._cache_ttl = timedelta(minutes=5)

    def get_agent_metrics(
        self,
        agent_ref: str,
        time_window: timedelta | None = None,
    ) -> AgentPerformanceMetrics:
        """Get performance metrics for a specific agent.

        Args:
            agent_ref: Agent reference (opaque ID)
            time_window: Only consider events within this window

        Returns:
            AgentPerformanceMetrics (never includes content)
        """
        # Check cache
        if self._is_cache_valid() and agent_ref in self._cache:
            return self._cache[agent_ref]

        # Query audit for this agent's events
        query = AuditQuery(
            actor_id=agent_ref,
            event_types=[AuditEventType.CYCLE_COMPLETED],
            limit=1000,
        )

        result = self._store.query(query)

        metrics = self._aggregate_metrics(agent_ref, result.events, time_window)

        # Cache result
        self._cache[agent_ref] = metrics
        self._cache_expiry = datetime.now() + self._cache_ttl

        return metrics

    def get_all_agent_metrics(
        self,
        time_window: timedelta | None = None,
    ) -> dict[str, AgentPerformanceMetrics]:
        """Get metrics for all known agents.

        Returns:
            Dict of agent_ref -> metrics
        """
        if self._is_cache_valid() and self._cache:
            return self._cache

        # Query all cycle_completed events (max 1000 per query)
        query = AuditQuery(
            event_types=[AuditEventType.CYCLE_COMPLETED],
            limit=1000,
        )

        result = self._store.query(query)

        # Group by agent
        events_by_agent: dict[str, list] = {}
        for event in result.events:
            agent_ref = event.actor_id
            if agent_ref not in events_by_agent:
                events_by_agent[agent_ref] = []
            events_by_agent[agent_ref].append(event)

        # Aggregate each
        all_metrics = {}
        for agent_ref, events in events_by_agent.items():
            all_metrics[agent_ref] = self._aggregate_metrics(
                agent_ref, events, time_window
            )

        # Cache
        self._cache = all_metrics
        self._cache_expiry = datetime.now() + self._cache_ttl

        return all_metrics

    def get_best_agent_for_task(
        self,
        task_type: str | None = None,
        complexity: int | None = None,
        min_success_rate: float = 0.7,
    ) -> list[tuple[str, float]]:
        """Suggest best agents for a task based on historical performance.

        Args:
            task_type: Type of task (e.g., "coding", "math")
            complexity: Complexity level (1-6)
            min_success_rate: Minimum acceptable success rate

        Returns:
            List of (agent_ref, confidence_score) sorted by confidence
        """
        all_metrics = self.get_all_agent_metrics()

        candidates = []

        for agent_ref, metrics in all_metrics.items():
            score = 0.0

            # Base score from overall reliability
            score = metrics.reliability_score

            # Adjust for task type match
            if task_type and task_type in metrics.success_by_task_type:
                type_success = metrics.success_by_task_type[task_type]
                if type_success >= min_success_rate:
                    score = (score + type_success) / 2
                else:
                    score *= 0.5  # Penalize poor task type performance

            # Adjust for complexity match
            if complexity and complexity in metrics.success_by_complexity:
                complexity_success = metrics.success_by_complexity[complexity]
                if complexity_success >= min_success_rate:
                    score = (score + complexity_success) / 2
                else:
                    score *= 0.3  # Heavy penalty for complexity mismatch
            elif complexity:
                # No data for this complexity - uncertain
                score *= 0.6

            if score >= min_success_rate * 0.5:  # Allow some tolerance
                candidates.append((agent_ref, score))

        # Sort by score descending
        candidates.sort(key=lambda x: x[1], reverse=True)

        return candidates

    def build_model_profile(
        self,
        agent_ref: str,
        metrics: AgentPerformanceMetrics,
    ) -> ModelProfile:
        """Derive a ModelProfile from pre-computed metrics.

        Strengths: task types where success rate exceeds the agent's own average
        by more than 10 percentage points.
        Weaknesses: task types where rate falls more than 10pp below average.
        """
        rates = metrics.success_by_task_type
        if rates:
            avg = sum(rates.values()) / len(rates)
            strengths = [t for t, r in rates.items() if r > avg + 0.10]
            weaknesses = [t for t, r in rates.items() if r < avg - 0.10]
        else:
            strengths = []
            weaknesses = []

        complexity_rates = metrics.success_by_complexity
        if complexity_rates:
            optimal_complexity = max(complexity_rates, key=complexity_rates.get)
            avoid_complexity = min(complexity_rates, key=complexity_rates.get)
        else:
            optimal_complexity = None
            avoid_complexity = None

        return ModelProfile(
            model_id=agent_ref,
            strengths=strengths,
            weaknesses=weaknesses,
            optimal_complexity=optimal_complexity,
            avoid_complexity=avoid_complexity,
        )

    def get_model_profile(self, agent_ref: str) -> ModelProfile:
        """Compute the ModelProfile for one agent from live metrics."""
        metrics = self.get_agent_metrics(agent_ref)
        return self.build_model_profile(agent_ref, metrics)

    def get_all_model_profiles(self) -> dict[str, ModelProfile]:
        """Compute ModelProfiles for every known agent."""
        return {
            ref: self.build_model_profile(ref, m)
            for ref, m in self.get_all_agent_metrics().items()
        }

    def get_feedback_adjusted_score(
        self,
        agent_ref: str,
        evaluation_ids: list[str],
        feedback_collector,  # FeedbackCollector — avoid circular import via type hint
    ) -> float:
        """Return the agent's automated quality score blended with human feedback.

        Each evaluation_id in evaluation_ids is blended individually using the
        FeedbackCollector, then the results are averaged.  If no evaluation has
        feedback, the raw reliability score is returned unchanged.

        Args:
            agent_ref:          Agent whose metrics to use as the automated baseline.
            evaluation_ids:     Evaluation IDs whose feedback should be considered.
            feedback_collector: FeedbackCollector instance.

        Returns:
            Blended score in [0, 100].
        """
        metrics = self.get_agent_metrics(agent_ref)
        automated_score = metrics.reliability_score * 100.0

        blended_scores = []
        for eid in evaluation_ids:
            if feedback_collector.has_feedback(eid):
                blended = feedback_collector.blended_score(automated_score, eid)
                blended_scores.append(blended)

        if not blended_scores:
            return automated_score

        return sum(blended_scores) / len(blended_scores)

    def _aggregate_metrics(
        self,
        agent_ref: str,
        events: list,
        time_window: timedelta | None = None,
    ) -> AgentPerformanceMetrics:
        """Aggregate events into metrics.

        IMPORTANT: Only extracts metrics, never content.
        """
        metrics = AgentPerformanceMetrics(agent_ref=agent_ref)

        latencies: list[float] = []
        quality_scores: list[float] = []
        lq_pairs: list[tuple[float, float]] = []   # (latency, quality_score) when both present
        complexity_results: dict[int, list[bool]] = {}
        task_type_results: dict[str, list[bool]] = {}

        cutoff = None
        if time_window:
            cutoff = datetime.now() - time_window

        for event in events:
            # Apply time filter
            if cutoff and event.timestamp < cutoff:
                continue

            payload = event.payload or {}

            # Track timing
            if metrics.first_seen is None or event.timestamp < metrics.first_seen:
                metrics.first_seen = event.timestamp
            if metrics.last_seen is None or event.timestamp > metrics.last_seen:
                metrics.last_seen = event.timestamp

            # Extract ONLY metrics from payload
            success = payload.get("success", False)
            elapsed = payload.get("elapsed_seconds", 0)
            complexity = payload.get("complexity", None)
            task_type = payload.get("task_type", None)
            cost = payload.get("cost", None)
            quality_score = payload.get("quality_score", None)
            model_version = payload.get("model_version", None)

            # Never extract: prompt, output, content, agent identity

            metrics.total_tasks += 1
            if success:
                metrics.successful_tasks += 1
            else:
                metrics.failed_tasks += 1

            if elapsed:
                latencies.append(elapsed)

            if cost is not None:
                metrics.total_cost += cost

            if quality_score is not None:
                quality_scores.append(float(quality_score))
                if model_version:
                    metrics.quality_by_version.setdefault(model_version, []).append(
                        float(quality_score)
                    )

            if elapsed and quality_score is not None:
                lq_pairs.append((float(elapsed), float(quality_score)))

            # Track by complexity
            if complexity is not None:
                if complexity not in complexity_results:
                    complexity_results[complexity] = []
                complexity_results[complexity].append(success)

            # Track by task type
            if task_type:
                if task_type not in task_type_results:
                    task_type_results[task_type] = []
                task_type_results[task_type].append(success)

        # Compute averages
        if latencies:
            metrics.avg_latency_seconds = sum(latencies) / len(latencies)
            metrics.min_latency_seconds = min(latencies)
            metrics.max_latency_seconds = max(latencies)
            metrics.latency_p50_seconds = self._percentile(latencies, 50)
            metrics.latency_p95_seconds = self._percentile(latencies, 95)

        if metrics.total_tasks > 0 and metrics.total_cost > 0:
            metrics.avg_cost_per_task = metrics.total_cost / metrics.total_tasks

        # Latency-quality correlation and tier breakdown
        if len(lq_pairs) >= 2:
            lats = [p[0] for p in lq_pairs]
            quals = [p[1] for p in lq_pairs]
            try:
                metrics.latency_quality_correlation = statistics.correlation(lats, quals)
            except statistics.StatisticsError:
                pass  # constant series → correlation undefined

            tier_buckets: dict[str, list[float]] = {"low": [], "mid": [], "high": []}
            for lat, q in lq_pairs:
                if q < 40:
                    tier_buckets["low"].append(lat)
                elif q < 70:
                    tier_buckets["mid"].append(lat)
                else:
                    tier_buckets["high"].append(lat)
            metrics.latency_p50_by_quality_tier = {
                tier: self._percentile(lats_in_tier, 50)
                for tier, lats_in_tier in tier_buckets.items()
                if lats_in_tier
            }

        # Variance coefficient from quality scores
        if len(quality_scores) > 1:
            mean_q = statistics.mean(quality_scores)
            if mean_q > 0:
                metrics.variance_coefficient = statistics.stdev(quality_scores) / mean_q

        # Consistency rate from binary success/fail outcomes
        if metrics.total_tasks > 0:
            sr = metrics.success_rate
            metrics.consistency_rate = max(sr, 1.0 - sr)

        # Compute success rates by complexity
        for level, results in complexity_results.items():
            if results:
                metrics.success_by_complexity[level] = sum(results) / len(results)

        # Compute success rates by task type
        for ttype, results in task_type_results.items():
            if results:
                metrics.success_by_task_type[ttype] = sum(results) / len(results)

        return metrics

    # ------------------------------------------------------------------
    # Latency-quality analysis
    # ------------------------------------------------------------------

    def get_latency_quality_report(self, agent_ref: str) -> LatencyQualityReport:
        """Return a latency-quality correlation report for one agent."""
        m = self.get_agent_metrics(agent_ref)
        return LatencyQualityReport(
            agent_ref=agent_ref,
            latency_quality_correlation=m.latency_quality_correlation,
            latency_p50_seconds=m.latency_p50_seconds,
            latency_p95_seconds=m.latency_p95_seconds,
            latency_p50_by_quality_tier=m.latency_p50_by_quality_tier,
            sample_count=m.total_tasks,
        )

    def get_all_latency_quality_reports(self) -> dict[str, LatencyQualityReport]:
        """Return latency-quality reports for every known agent."""
        return {
            ref: LatencyQualityReport(
                agent_ref=ref,
                latency_quality_correlation=m.latency_quality_correlation,
                latency_p50_seconds=m.latency_p50_seconds,
                latency_p95_seconds=m.latency_p95_seconds,
                latency_p50_by_quality_tier=m.latency_p50_by_quality_tier,
                sample_count=m.total_tasks,
            )
            for ref, m in self.get_all_agent_metrics().items()
        }

    def fastest_model_meeting_quality(
        self,
        min_quality: float,
        agent_refs: list[str] | None = None,
    ) -> str | None:
        """Return the agent_ref with the lowest avg latency whose reliability
        score (0-1) is at or above *min_quality*.

        Args:
            min_quality:  Minimum reliability_score threshold (0.0 – 1.0).
            agent_refs:   Restrict search to these refs; None = all known agents.

        Returns:
            agent_ref of the fastest qualifying agent, or None if none qualify.
        """
        all_metrics = self.get_all_agent_metrics()
        candidates = {
            ref: m for ref, m in all_metrics.items()
            if (agent_refs is None or ref in agent_refs)
            and m.reliability_score >= min_quality
            and m.avg_latency_seconds > 0
        }
        if not candidates:
            return None
        return min(candidates, key=lambda ref: candidates[ref].avg_latency_seconds)

    def get_regression_alerts(
        self,
        agent_refs: list[str] | None = None,
        regression_threshold: float = 0.15,
        warning_threshold: float = 0.07,
        window: int = 10,
    ) -> list:
        """Run regression detection across all (or specified) agents.

        Populates a RegressionDetector from each agent's quality_by_version
        data and returns any alerts found.

        Args:
            agent_refs:           Restrict to these agents; None = all known.
            regression_threshold: Fraction drop to trigger REGRESSION_DETECTED.
            warning_threshold:    Fraction drop to trigger WARNING.
            window:               Max tasks from the new version to evaluate.

        Returns:
            List of RegressionAlert objects (may be empty).
        """
        from src.broker.regression_detector import RegressionDetector

        detector = RegressionDetector(
            regression_threshold=regression_threshold,
            warning_threshold=warning_threshold,
            window=window,
        )
        all_metrics = self.get_all_agent_metrics()
        for ref, m in all_metrics.items():
            if agent_refs is not None and ref not in agent_refs:
                continue
            for version, scores in m.quality_by_version.items():
                for score in scores:
                    detector.record(ref, version, score)

        return detector.check_all()

    @staticmethod
    def _percentile(data: list[float], p: float) -> float:
        """Return the p-th percentile of *data* (0 ≤ p ≤ 100)."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * p / 100)
        return sorted_data[min(idx, len(sorted_data) - 1)]

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if self._cache_expiry is None:
            return False
        return datetime.now() < self._cache_expiry

    def invalidate_cache(self) -> None:
        """Force cache invalidation."""
        self._cache = {}
        self._cache_expiry = None
