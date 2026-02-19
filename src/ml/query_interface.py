"""Unified query interface for MLflow runs + ACE knowledge."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import mlflow
    from mlflow.entities import Run
    from mlflow.tracking import MlflowClient
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    Run = Any  # Type placeholder when MLflow not available

from .experiment_knowledge import ExperimentDecision, ExperimentPattern, MLExperimentKnowledge

logger = logging.getLogger(__name__)


@dataclass
class EnrichedRun:
    """MLflow run enriched with ACE knowledge."""

    # MLflow data
    run_id: str
    experiment_id: str
    status: str
    start_time: int
    end_time: int | None
    params: dict[str, Any]
    metrics: dict[str, float]
    tags: dict[str, str]

    # ACE knowledge
    decisions: list[ExperimentDecision]
    related_patterns: list[ExperimentPattern]

    # Computed insights
    decision_count: int
    has_failed_decisions: bool
    applied_patterns: list[str]  # Pattern names that were applied


class MLflowKnowledgeQuery:
    """Unified interface to query MLflow runs with ACE knowledge context.

    Usage:
        query = MLflowKnowledgeQuery(
            experiment_name="my_experiment",
            knowledge_dir=Path("~/.ace/ml_experiments")
        )

        # Get all runs with knowledge
        enriched_runs = query.get_enriched_runs()

        # Find runs by decision
        runs = query.find_runs_by_decision("Which optimizer to use?", "Adam")

        # Get recommendations for new run
        recommendations = query.get_recommendations_for_params({"batch_size": 128})
    """

    def __init__(
        self,
        experiment_name: str,
        knowledge_dir: Path | None = None,
        mlflow_tracking_uri: str | None = None
    ):
        """Initialize query interface.

        Args:
            experiment_name: Name of ML experiment
            knowledge_dir: Directory containing ACE knowledge files
            mlflow_tracking_uri: MLflow tracking URI (default: use current)
        """
        if not MLFLOW_AVAILABLE:
            raise ImportError("MLflow is required. Install with: pip install mlflow")

        self.experiment_name = experiment_name
        self.knowledge_dir = knowledge_dir or Path.home() / ".ace" / "ml_experiments"

        # Initialize MLflow client
        if mlflow_tracking_uri:
            mlflow.set_tracking_uri(mlflow_tracking_uri)
        self.mlflow_client = MlflowClient()

        # Load ACE knowledge
        self.knowledge_file = self.knowledge_dir / f"{experiment_name}.json"
        if self.knowledge_file.exists():
            self.knowledge = MLExperimentKnowledge.load(self.knowledge_file)
            logger.info(f"Loaded knowledge base: {self.knowledge_file}")
        else:
            self.knowledge = MLExperimentKnowledge(experiment_name=experiment_name)
            logger.warning(f"No existing knowledge found for: {experiment_name}")

        # Get MLflow experiment
        self.mlflow_experiment = self._get_or_create_experiment()

    def _get_or_create_experiment(self):
        """Get or create MLflow experiment."""
        experiment = mlflow.get_experiment_by_name(self.experiment_name)
        if experiment is None:
            experiment_id = mlflow.create_experiment(self.experiment_name)
            experiment = mlflow.get_experiment(experiment_id)
        return experiment

    def get_enriched_runs(
        self,
        filter_string: str | None = None,
        max_results: int = 100
    ) -> list[EnrichedRun]:
        """Get MLflow runs enriched with ACE knowledge.

        Args:
            filter_string: MLflow filter string (e.g., "params.learning_rate > 0.001")
            max_results: Maximum number of runs to return

        Returns:
            List of enriched runs
        """
        # Query MLflow runs
        runs = self.mlflow_client.search_runs(
            experiment_ids=[self.mlflow_experiment.experiment_id],
            filter_string=filter_string or "",
            max_results=max_results
        )

        # Enrich with ACE knowledge
        enriched = []
        for run in runs:
            enriched_run = self._enrich_run(run)
            enriched.append(enriched_run)

        return enriched

    def _enrich_run(self, run: Run) -> EnrichedRun:
        """Enrich a single MLflow run with ACE knowledge."""
        run_id = run.info.run_id

        # Get decisions for this run
        decisions = self.knowledge.get_decisions_for_run(run_id)

        # Get related patterns (patterns observed in this run)
        related_patterns = [
            p for p in self.knowledge.patterns
            if run_id in p.observed_in_experiments
        ]

        # Extract applied pattern names from tags
        applied_patterns = [
            tag_value
            for tag_key, tag_value in run.data.tags.items()
            if tag_key.startswith("ace.pattern.")
        ]

        # Compute insights
        has_failed_decisions = any(
            d.outcome == "failed" for d in decisions if d.outcome
        )

        return EnrichedRun(
            run_id=run_id,
            experiment_id=run.info.experiment_id,
            status=run.info.status,
            start_time=run.info.start_time,
            end_time=run.info.end_time,
            params=run.data.params,
            metrics={k: v for k, v in run.data.metrics.items()},
            tags=run.data.tags,
            decisions=decisions,
            related_patterns=related_patterns,
            decision_count=len(decisions),
            has_failed_decisions=has_failed_decisions,
            applied_patterns=applied_patterns
        )

    def find_runs_by_decision(
        self,
        question: str | None = None,
        decision: str | None = None,
        outcome: str | None = None
    ) -> list[EnrichedRun]:
        """Find runs by decision criteria.

        Args:
            question: Filter by decision question (substring match)
            decision: Filter by decision made (substring match)
            outcome: Filter by outcome ("successful" | "failed" | "inconclusive")

        Returns:
            List of enriched runs matching criteria
        """
        # Get all runs
        all_runs = self.get_enriched_runs()

        # Filter by decision criteria
        filtered = []
        for run in all_runs:
            for dec in run.decisions:
                match = True

                if question and question.lower() not in dec.question.lower():
                    match = False
                if decision and decision.lower() not in dec.decision.lower():
                    match = False
                if outcome and dec.outcome != outcome:
                    match = False

                if match:
                    filtered.append(run)
                    break  # Don't add same run multiple times

        return filtered

    def find_runs_by_pattern(
        self,
        pattern_name: str
    ) -> list[EnrichedRun]:
        """Find runs where a specific pattern was observed.

        Args:
            pattern_name: Name of the pattern

        Returns:
            List of enriched runs
        """
        # Find pattern
        pattern = None
        for p in self.knowledge.patterns:
            if pattern_name.lower() in p.pattern_name.lower():
                pattern = p
                break

        if not pattern:
            logger.warning(f"Pattern not found: {pattern_name}")
            return []

        # Get runs from pattern's experiment list
        run_ids = set(pattern.observed_in_experiments)

        # Filter all runs to those in the list
        all_runs = self.get_enriched_runs()
        return [run for run in all_runs if run.run_id in run_ids]

    def get_recommendations_for_params(
        self,
        params: dict[str, Any],
        domain_tags: list[str] | None = None,
        min_success_rate: float = 0.7
    ) -> list[tuple[ExperimentPattern, str]]:
        """Get pattern recommendations for given parameters.

        Args:
            params: Experiment parameters (e.g., {"batch_size": 128, "optimizer": "adam"})
            domain_tags: Domain tags for filtering
            min_success_rate: Minimum pattern success rate

        Returns:
            List of (pattern, relevance_reason) tuples
        """
        successful_patterns = self.knowledge.get_successful_patterns(min_success_rate)

        # Filter by domain
        if domain_tags:
            patterns = [
                p for p in successful_patterns
                if any(tag in p.domain_tags for tag in domain_tags)
            ]
        else:
            patterns = successful_patterns

        # Generate relevance reasons based on params
        recommendations = []
        for pattern in patterns:
            # Simple keyword matching for relevance
            relevance_reasons = []

            for param_key, param_value in params.items():
                # Check if param mentioned in pattern's when_to_apply
                if param_key.lower() in pattern.when_to_apply.lower():
                    relevance_reasons.append(f"Mentions {param_key}")

                # Check if param value mentioned
                if str(param_value).lower() in pattern.when_to_apply.lower():
                    relevance_reasons.append(f"Mentions {param_key}={param_value}")

            if relevance_reasons:
                reason = "; ".join(relevance_reasons)
            else:
                reason = f"General pattern (success_rate={pattern.success_rate:.2f})"

            recommendations.append((pattern, reason))

        # Sort by success rate
        recommendations.sort(key=lambda x: x[0].usefulness_score, reverse=True)

        return recommendations

    def get_decision_history(
        self,
        question_keyword: str | None = None
    ) -> list[ExperimentDecision]:
        """Get decision history across all runs.

        Args:
            question_keyword: Filter by keyword in question

        Returns:
            List of decisions, sorted by timestamp (newest first)
        """
        decisions = list(self.knowledge.decisions)

        # Filter by keyword
        if question_keyword:
            decisions = [
                d for d in decisions
                if question_keyword.lower() in d.question.lower()
            ]

        # Sort by timestamp
        decisions.sort(key=lambda d: d.timestamp, reverse=True)

        return decisions

    def compare_runs(
        self,
        run_id_1: str,
        run_id_2: str
    ) -> dict[str, Any]:
        """Compare two runs including their decisions and patterns.

        Args:
            run_id_1: First run ID
            run_id_2: Second run ID

        Returns:
            Comparison dictionary
        """
        # Get enriched runs
        all_runs = self.get_enriched_runs()
        run1 = next((r for r in all_runs if r.run_id == run_id_1), None)
        run2 = next((r for r in all_runs if r.run_id == run_id_2), None)

        if not run1 or not run2:
            raise ValueError(f"Run not found: {run_id_1 if not run1 else run_id_2}")

        # Compare params
        param_diff = {}
        all_param_keys = set(run1.params.keys()) | set(run2.params.keys())
        for key in all_param_keys:
            val1 = run1.params.get(key)
            val2 = run2.params.get(key)
            if val1 != val2:
                param_diff[key] = {"run1": val1, "run2": val2}

        # Compare metrics
        metric_diff = {}
        all_metric_keys = set(run1.metrics.keys()) | set(run2.metrics.keys())
        for key in all_metric_keys:
            val1 = run1.metrics.get(key)
            val2 = run2.metrics.get(key)
            if val1 is not None and val2 is not None:
                metric_diff[key] = {
                    "run1": val1,
                    "run2": val2,
                    "diff": val2 - val1,
                    "pct_change": ((val2 - val1) / val1 * 100) if val1 != 0 else None
                }

        # Compare decisions
        decisions1 = {d.question: d.decision for d in run1.decisions}
        decisions2 = {d.question: d.decision for d in run2.decisions}

        decision_diff = {}
        all_questions = set(decisions1.keys()) | set(decisions2.keys())
        for question in all_questions:
            dec1 = decisions1.get(question)
            dec2 = decisions2.get(question)
            if dec1 != dec2:
                decision_diff[question] = {"run1": dec1, "run2": dec2}

        return {
            "run1_id": run_id_1,
            "run2_id": run_id_2,
            "param_differences": param_diff,
            "metric_differences": metric_diff,
            "decision_differences": decision_diff,
            "run1_patterns": [p.pattern_name for p in run1.related_patterns],
            "run2_patterns": [p.pattern_name for p in run2.related_patterns],
        }
