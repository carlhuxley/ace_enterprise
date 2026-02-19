"""MLflow callback for automatic ACE knowledge capture during training."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import mlflow
    from mlflow.tracking import MlflowClient
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False

from .experiment_knowledge import ExperimentDecision, ExperimentPattern, MLExperimentKnowledge

logger = logging.getLogger(__name__)


class ACEMLflowCallback:
    """Callback to capture ACE knowledge during MLflow experiments.

    Usage:
        ace_callback = ACEMLflowCallback(
            experiment_name="my_experiment",
            knowledge_dir=Path("~/.ace/ml_experiments")
        )

        with mlflow.start_run():
            # Log decision
            ace_callback.log_decision(
                question="Which optimizer to use?",
                decision="Adam with lr=0.001",
                rationale="Better convergence in pilot runs",
                alternatives=["SGD", "AdamW"]
            )

            # Your training code
            model.fit(X_train, y_train)

            # Log metrics to MLflow as usual
            mlflow.log_metric("accuracy", 0.95)
    """

    def __init__(
        self,
        experiment_name: str,
        knowledge_dir: Path | None = None,
        human_contributor: str | None = None,
        auto_save: bool = True
    ):
        """Initialize ACE MLflow callback.

        Args:
            experiment_name: Name of the ML experiment
            knowledge_dir: Directory to store knowledge files (default: ~/.ace/ml_experiments)
            human_contributor: Email or name of human experimenter
            auto_save: Automatically save knowledge after each decision/pattern
        """
        if not MLFLOW_AVAILABLE:
            raise ImportError("MLflow is required. Install with: pip install mlflow")

        self.experiment_name = experiment_name
        self.knowledge_dir = knowledge_dir or Path.home() / ".ace" / "ml_experiments"
        self.human_contributor = human_contributor
        self.auto_save = auto_save

        # Initialize or load existing knowledge base
        self.knowledge_file = self.knowledge_dir / f"{experiment_name}.json"
        if self.knowledge_file.exists():
            self.knowledge = MLExperimentKnowledge.load(self.knowledge_file)
            logger.info(f"Loaded existing knowledge base: {self.knowledge_file}")
        else:
            self.knowledge = MLExperimentKnowledge(experiment_name=experiment_name)
            logger.info(f"Created new knowledge base for: {experiment_name}")

        # MLflow client
        self.mlflow_client = MlflowClient()

        # Track current run
        self._current_run_id: str | None = None
        self._decision_counter = 0

    def _get_current_run_id(self) -> str | None:
        """Get current MLflow run ID."""
        active_run = mlflow.active_run()
        if active_run:
            return active_run.info.run_id
        return None

    def log_decision(
        self,
        question: str,
        decision: str,
        rationale: str,
        alternatives_considered: list[str] | None = None,
        context: dict[str, Any] | None = None,
        ai_models: list[dict[str, str]] | None = None,
        conversation_id: str | None = None
    ) -> ExperimentDecision:
        """Log a decision made during experimentation.

        Args:
            question: The question being answered (e.g., "Which optimizer?")
            decision: The decision made (e.g., "Adam with lr=0.001")
            rationale: Why this decision was made
            alternatives_considered: Other options that were considered
            context: Additional context (previous run IDs, observed metrics, etc.)
            ai_models: AI models involved in decision
            conversation_id: Reference to full conversation

        Returns:
            ExperimentDecision object
        """
        run_id = self._get_current_run_id()
        self._decision_counter += 1

        # Build context
        full_context = context or {}
        if run_id:
            full_context["mlflow_run_id"] = run_id
            full_context["mlflow_experiment_id"] = self.knowledge.mlflow_experiment_id or ""

        # Create decision object
        decision_obj = ExperimentDecision(
            decision_id=f"dec_{self.experiment_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self._decision_counter}",
            timestamp=datetime.now(),
            question=question,
            decision=decision,
            rationale=rationale,
            alternatives_considered=alternatives_considered or [],
            context=full_context,
            human_contributor=self.human_contributor,
            ai_models=ai_models or [],
            conversation_id=conversation_id
        )

        # Add to knowledge base
        self.knowledge.add_decision(decision_obj)

        # Log to MLflow as tags for discoverability
        if run_id:
            try:
                mlflow.set_tag(f"ace.decision.{self._decision_counter}.question", question)
                mlflow.set_tag(f"ace.decision.{self._decision_counter}.decision", decision)
                mlflow.set_tag(f"ace.decision.{self._decision_counter}.id", decision_obj.decision_id)
            except Exception as e:
                logger.warning(f"Failed to log decision to MLflow tags: {e}")

        if self.auto_save:
            self.save()

        logger.info(f"Logged decision: {question} → {decision}")
        return decision_obj

    def log_pattern(
        self,
        pattern_name: str,
        description: str,
        when_to_apply: str,
        implementation: str,
        observed_in_runs: list[str],
        success_rate: float,
        domain_tags: list[str] | None = None,
        antipatterns: list[str] | None = None,
        avg_improvement: float | None = None
    ) -> ExperimentPattern:
        """Log a learned pattern from multiple experiments.

        Args:
            pattern_name: Name of the pattern
            description: Description of what the pattern does
            when_to_apply: Conditions when pattern should be applied
            implementation: How to implement the pattern
            observed_in_runs: List of MLflow run IDs where pattern was observed
            success_rate: Success rate (0.0 to 1.0)
            domain_tags: Domain tags (e.g., ["computer_vision", "image_classification"])
            antipatterns: Things to avoid
            avg_improvement: Average metric improvement

        Returns:
            ExperimentPattern object
        """
        pattern_obj = ExperimentPattern(
            pattern_id=f"pat_{self.experiment_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            pattern_name=pattern_name,
            description=description,
            observed_in_experiments=observed_in_runs,
            success_rate=success_rate,
            avg_improvement=avg_improvement,
            when_to_apply=when_to_apply,
            implementation=implementation,
            antipatterns=antipatterns or [],
            discovered_date=datetime.now(),
            experiments_count=len(observed_in_runs),
            domain_tags=domain_tags or [],
            usefulness_score=success_rate,
            times_applied=len(observed_in_runs),
            times_successful=int(len(observed_in_runs) * success_rate)
        )

        # Add to knowledge base
        self.knowledge.add_pattern(pattern_obj)

        if self.auto_save:
            self.save()

        logger.info(f"Logged pattern: {pattern_name} (success_rate={success_rate:.2f})")
        return pattern_obj

    def update_decision_outcome(
        self,
        decision_id: str,
        outcome: str,
        learned_insight: str | None = None
    ) -> None:
        """Update a decision with its outcome after experiment completes.

        Args:
            decision_id: ID of the decision to update
            outcome: "successful" | "failed" | "inconclusive"
            learned_insight: What was learned from the outcome
        """
        for decision in self.knowledge.decisions:
            if decision.decision_id == decision_id:
                decision.outcome = outcome
                decision.learned_insight = learned_insight
                if self.auto_save:
                    self.save()
                logger.info(f"Updated decision {decision_id}: outcome={outcome}")
                return

        logger.warning(f"Decision not found: {decision_id}")

    def get_recommendations(
        self,
        current_params: dict[str, Any],
        domain_tags: list[str] | None = None
    ) -> list[ExperimentPattern]:
        """Get pattern recommendations based on current experiment parameters.

        Args:
            current_params: Current experiment parameters (e.g., {"batch_size": 128, "optimizer": "adam"})
            domain_tags: Domain tags for filtering (e.g., ["computer_vision"])

        Returns:
            List of relevant patterns
        """
        patterns = self.knowledge.get_successful_patterns(min_success_rate=0.7)

        # Filter by domain if specified
        if domain_tags:
            patterns = [
                p for p in patterns
                if any(tag in p.domain_tags for tag in domain_tags)
            ]

        # Sort by usefulness score
        patterns.sort(key=lambda p: p.usefulness_score, reverse=True)

        return patterns

    def save(self) -> None:
        """Save knowledge base to disk."""
        self.knowledge.save(self.knowledge_file)
        logger.debug(f"Saved knowledge to: {self.knowledge_file}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - save on exit."""
        if self.auto_save:
            self.save()
