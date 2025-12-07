"""
PostgreSQL-backed MLflow callback for ACE knowledge capture.

Replaces file-based storage with PostgreSQL experiment_logs table.
"""
import logging
from datetime import datetime
from typing import Any, Optional

try:
    import mlflow
    from mlflow.tracking import MlflowClient
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False

from src.storage.experiment_logger import ExperimentLogger
from src.playbook.postgres_adapter import PostgresPlaybookAdapter
from src.storage.schemas import BulletCreate

logger = logging.getLogger(__name__)


class PostgresACEMLflowCallback:
    """
    MLflow callback that stores knowledge in PostgreSQL.

    Usage:
        ace = PostgresACEMLflowCallback(
            experiment_name="sentiment_classifier",
            playbook_id="ml_nlp_experiments"
        )

        with mlflow.start_run():
            # Log decision
            ace.log_decision(
                question="Which optimizer to use?",
                decision="Adam with lr=0.001",
                rationale="Better convergence in pilot runs"
            )

            # Train model
            model.fit(X_train, y_train)

            # Log metrics
            mlflow.log_metric("accuracy", 0.95)

            # Log what was learned
            ace.log_pattern(
                pattern_name="Adam works well for BERT fine-tuning",
                description="Adam optimizer with lr=1e-5 gives best results",
                when_to_apply="When fine-tuning BERT models on text classification",
                success_rate=0.95
            )
    """

    def __init__(
        self,
        experiment_name: str,
        playbook_id: str,
        playbook_version: str = "1.0.0",
        human_contributor: Optional[str] = None,
    ):
        """
        Initialize PostgreSQL-backed MLflow callback.

        Args:
            experiment_name: Name of ML experiment
            playbook_id: Playbook to store learned patterns
            playbook_version: Playbook version
            human_contributor: Name/email of human experimenter
        """
        if not MLFLOW_AVAILABLE:
            raise ImportError("MLflow required. Install: pip install mlflow")

        self.experiment_name = experiment_name
        self.playbook_id = playbook_id
        self.playbook_version = playbook_version
        self.human_contributor = human_contributor

        # PostgreSQL components
        self.experiment_logger = ExperimentLogger(playbook_version=playbook_version)
        self.playbook_adapter = PostgresPlaybookAdapter()

        # MLflow client
        self.mlflow_client = MlflowClient()

        # Track current experiment
        self.current_run_id: Optional[str] = None
        self.decisions: list[dict[str, Any]] = []
        self.patterns: list[dict[str, Any]] = []

        logger.info(f"Initialized PostgreSQL MLflow callback for: {experiment_name}")

    def _get_current_run_id(self) -> Optional[str]:
        """Get current MLflow run ID."""
        active_run = mlflow.active_run()
        return active_run.info.run_id if active_run else None

    def log_decision(
        self,
        question: str,
        decision: str,
        rationale: str,
        alternatives_considered: Optional[list[str]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Log a decision made during experimentation.

        Args:
            question: Question being answered
            decision: Decision made
            rationale: Why this decision was made
            alternatives_considered: Other options considered
            context: Additional context

        Returns:
            Decision dictionary
        """
        run_id = self._get_current_run_id()

        decision_obj = {
            "question": question,
            "decision": decision,
            "rationale": rationale,
            "alternatives": alternatives_considered or [],
            "context": context or {},
            "mlflow_run_id": run_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

        self.decisions.append(decision_obj)

        # Log to MLflow tags for discoverability
        if run_id:
            try:
                mlflow.set_tag(f"ace.decision.{len(self.decisions)}.question", question)
                mlflow.set_tag(f"ace.decision.{len(self.decisions)}.decision", decision)
            except Exception as e:
                logger.warning(f"Failed to log to MLflow tags: {e}")

        logger.info(f"Logged decision: {question} → {decision}")
        return decision_obj

    def log_pattern(
        self,
        pattern_name: str,
        description: str,
        when_to_apply: str,
        success_rate: float,
        implementation: Optional[str] = None,
        antipatterns: Optional[list[str]] = None,
        domain_tags: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Log a learned pattern that should be added to playbook.

        Args:
            pattern_name: Name of the pattern
            description: What the pattern does
            when_to_apply: When to use this pattern
            success_rate: How successful is this pattern (0.0-1.0)
            implementation: How to implement
            antipatterns: Things to avoid
            domain_tags: Domain tags (e.g., ["nlp", "computer_vision"])

        Returns:
            Pattern dictionary
        """
        run_id = self._get_current_run_id()

        pattern_obj = {
            "pattern_name": pattern_name,
            "description": description,
            "when_to_apply": when_to_apply,
            "success_rate": success_rate,
            "implementation": implementation or "",
            "antipatterns": antipatterns or [],
            "domain_tags": domain_tags or [],
            "mlflow_run_id": run_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

        self.patterns.append(pattern_obj)

        # Add to playbook immediately
        self._add_pattern_to_playbook(pattern_obj)

        logger.info(f"Logged pattern: {pattern_name} (success={success_rate:.2f})")
        return pattern_obj

    def _add_pattern_to_playbook(self, pattern: dict[str, Any]) -> None:
        """Add a learned pattern to the playbook."""
        try:
            # Format as bullet content
            content = f"""**{pattern['pattern_name']}**

{pattern['description']}

**When to apply:** {pattern['when_to_apply']}

**Success rate:** {pattern['success_rate']:.1%}

**Implementation:**
{pattern['implementation']}
"""

            if pattern['antipatterns']:
                content += "\n**Antipatterns:**\n"
                for ap in pattern['antipatterns']:
                    content += f"- {ap}\n"

            # Add to playbook
            self.playbook_adapter.add_bullet(
                playbook_id=self.playbook_id,
                bullet_data=BulletCreate(
                    content=content,
                    section="domain_knowledge",
                    tags=pattern['domain_tags'] + ["ml_experiment", "mlflow"],
                )
            )

            logger.info(f"Added pattern to playbook: {pattern['pattern_name']}")

        except Exception as e:
            logger.error(f"Failed to add pattern to playbook: {e}")

    def finalize_experiment(
        self,
        hyperparameters: dict[str, Any],
        metrics: dict[str, float],
        success: bool = True,
    ) -> None:
        """
        Finalize experiment and log to PostgreSQL.

        Call this at the end of your MLflow run to store everything.

        Args:
            hyperparameters: Final hyperparameters used
            metrics: Final metrics achieved
            success: Whether experiment succeeded
        """
        run_id = self._get_current_run_id()
        experiment_id = f"ml_{self.experiment_name}_{run_id or 'unknown'}"

        # Log to PostgreSQL experiment_logs
        self.experiment_logger.log_ml_experiment(
            experiment_id=experiment_id,
            experiment_name=self.experiment_name,
            hyperparameters=hyperparameters,
            metrics=metrics,
            decisions=self.decisions,
            patterns_learned=self.patterns,
            mlflow_run_id=run_id,
            success=success,
        )

        logger.info(
            f"Finalized ML experiment: {experiment_id} "
            f"({len(self.decisions)} decisions, {len(self.patterns)} patterns)"
        )

    def __enter__(self):
        """Context manager entry."""
        self.current_run_id = self._get_current_run_id()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        # Don't auto-finalize - let user call finalize_experiment explicitly
        pass
