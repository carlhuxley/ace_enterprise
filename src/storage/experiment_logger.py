"""
Unified Experiment Logger for both TDD and ML experiments.

Stores all experiments in PostgreSQL experiment_logs table with a consistent
interface for both TDD cycles and ML training runs.
"""
import logging
from datetime import datetime
from typing import Any

from src.storage.models import ExperimentLogModel
from src.storage.repository import PlaybookRepository

logger = logging.getLogger(__name__)


class ExperimentLogger:
    """
    Unified logger for TDD and ML experiments.

    Stores experiments in PostgreSQL with the ACE architecture:
    - Task: What are we trying to do?
    - Generator: What did we generate/configure?
    - Environment: What happened when we ran it?
    - Reflector: What did we learn from the result?
    - Curator: What should we add to the playbook?
    """

    def __init__(self, playbook_version: str, repository: PlaybookRepository | None = None):
        """
        Initialize experiment logger.

        Args:
            playbook_version: Current playbook version
            repository: Optional repository instance
        """
        self.playbook_version = playbook_version
        self.repo = repository or PlaybookRepository()

    def log_experiment(
        self,
        experiment_id: str,
        task_data: dict[str, Any],
        generator_data: dict[str, Any],
        environment_data: dict[str, Any],
        result: str,  # "SUCCESS" | "FAILED" | "TIMEOUT" | "ERROR"
        reflector_data: dict[str, Any] | None = None,
        curator_data: dict[str, Any] | None = None,
        playbook_updated: bool = False,
        performance_delta: float = 0.0,
        checkpoint_created: bool = False,
    ) -> ExperimentLogModel:
        """
        Log a complete experiment to PostgreSQL.

        Args:
            experiment_id: Unique experiment identifier
            task_data: Task description and context
            generator_data: What was generated (code, config, hyperparameters)
            environment_data: Execution results (test output, metrics)
            result: Outcome (SUCCESS/FAILED/TIMEOUT/ERROR)
            reflector_data: Analysis of what happened (optional)
            curator_data: Decisions about what to learn (optional)
            playbook_updated: Whether playbook was updated
            performance_delta: Change in performance metric
            checkpoint_created: Whether a checkpoint was created

        Returns:
            Created experiment log model
        """
        with self.repo.get_session() as session:
            experiment = ExperimentLogModel(
                experiment_id=experiment_id,
                playbook_version=self.playbook_version,
                timestamp=datetime.utcnow(),
                task_data=task_data,
                generator_data=generator_data,
                environment_data=environment_data,
                result=result,
                reflector_data=reflector_data,
                curator_data=curator_data,
                playbook_updated=playbook_updated,
                performance_delta=performance_delta,
                checkpoint_created=checkpoint_created,
            )

            session.add(experiment)
            session.commit()
            session.refresh(experiment)

            logger.info(
                f"Logged experiment {experiment_id}: {result} "
                f"(playbook_updated={playbook_updated})"
            )

            return experiment

    def log_tdd_cycle(
        self,
        cycle_number: int,
        requirement: str,
        test_name: str,
        test_code: str,
        implementation_code: str,
        red_passed: bool,
        green_passed: bool,
        red_output: str,
        green_output: str,
        learned_bullets: list[dict[str, Any]],
        playbook_id: str,
        retrieved_bullet_ids: list[str] | None = None,
        # Model attribution fields (optional for backward compatibility)
        actual_model: str | None = None,
        requested_model: str | None = None,
        provider: str | None = None,
        latency_ms: float | None = None,
        tokens_used: int | None = None,
        cost_usd: float | None = None,
        # Failure analysis fields (new)
        failure_category: str | None = None,
        failure_root_cause: str | None = None,
        failure_lesson: str | None = None,
        retry_count: int = 0,
        human_intervention: bool = False,
    ) -> ExperimentLogModel:
        """
        Log a TDD cycle (specialized wrapper for TDD experiments).

        Args:
            cycle_number: TDD cycle number
            requirement: Feature requirement
            test_name: Name of the test
            test_code: Test code generated
            implementation_code: Implementation code generated
            red_passed: Whether RED phase passed (should be False)
            green_passed: Whether GREEN phase passed (should be True)
            red_output: Output from RED phase
            green_output: Output from GREEN phase
            learned_bullets: Bullets learned from this cycle
            playbook_id: Associated playbook ID
            actual_model: The model that actually served the request (OpenRouter)
            requested_model: The model that was requested
            provider: LLM provider (e.g., "openrouter", "ollama")
            latency_ms: Total latency in milliseconds
            tokens_used: Total tokens consumed
            cost_usd: Cost in USD (from OpenRouter)
            failure_category: Category of failure (test_design, implementation, mocking, etc.)
            failure_root_cause: Analysis of why the failure occurred
            failure_lesson: Lesson learned / anti-pattern to avoid
            retry_count: Number of retry attempts before success or giving up
            human_intervention: Whether human had to step in to fix

        Returns:
            Created experiment log
        """
        experiment_id = f"tdd_{playbook_id}_cycle_{cycle_number}"

        # Determine result
        if green_passed and not red_passed:
            result = "SUCCESS"  # Proper TDD: red then green
        elif not green_passed:
            result = "FAILED"  # Couldn't get to green
        elif red_passed:
            result = "ERROR"  # Test didn't fail in red phase (bad!)
        else:
            result = "ERROR"

        # Build generator_data with model attribution
        generator_data = {
            "test_code": test_code,
            "implementation_code": implementation_code,
        }

        # Add retrieved bullets (for reliability analysis)
        if retrieved_bullet_ids is not None:
            generator_data["retrieved_bullet_ids"] = retrieved_bullet_ids

        # Add model attribution if provided
        if actual_model is not None:
            generator_data["actual_model"] = actual_model
        if requested_model is not None:
            generator_data["requested_model"] = requested_model
        if provider is not None:
            generator_data["provider"] = provider
        if latency_ms is not None:
            generator_data["latency_ms"] = latency_ms
        if tokens_used is not None:
            generator_data["tokens_used"] = tokens_used
        if cost_usd is not None:
            generator_data["cost_usd"] = cost_usd

        return self.log_experiment(
            experiment_id=experiment_id,
            task_data={
                "type": "tdd_cycle",
                "cycle_number": cycle_number,
                "requirement": requirement,
                "test_name": test_name,
                "playbook_id": playbook_id,
            },
            generator_data=generator_data,
            environment_data={
                "red_phase": {
                    "passed": red_passed,
                    "output": red_output,
                },
                "green_phase": {
                    "passed": green_passed,
                    "output": green_output,
                },
            },
            result=result,
            reflector_data={
                "red_failed_correctly": not red_passed,
                "green_succeeded": green_passed,
                "proper_tdd_cycle": green_passed and not red_passed,
                "retry_count": retry_count,
                "human_intervention": human_intervention,
                # Failure analysis (populated when cycle fails)
                "failure_category": failure_category,
                "failure_root_cause": failure_root_cause,
                "failure_lesson": failure_lesson,
            },
            curator_data={
                "bullets_learned": learned_bullets,
                "bullet_count": len(learned_bullets),
                # If there's a lesson, it should become a playbook bullet
                "tdd_lesson": failure_lesson,
            },
            playbook_updated=len(learned_bullets) > 0,
        )

    def log_ml_experiment(
        self,
        experiment_id: str,
        experiment_name: str,
        hyperparameters: dict[str, Any],
        metrics: dict[str, float],
        decisions: list[dict[str, Any]],
        patterns_learned: list[dict[str, Any]],
        mlflow_run_id: str | None = None,
        success: bool = True,
    ) -> ExperimentLogModel:
        """
        Log an ML experiment (specialized wrapper for ML experiments).

        Args:
            experiment_id: Unique experiment identifier
            experiment_name: Human-readable experiment name
            hyperparameters: Model hyperparameters
            metrics: Evaluation metrics (accuracy, loss, etc.)
            decisions: Decisions made during experiment
            patterns_learned: Patterns learned from experiment
            mlflow_run_id: MLflow run ID (optional)
            success: Whether experiment succeeded

        Returns:
            Created experiment log
        """
        return self.log_experiment(
            experiment_id=experiment_id,
            task_data={
                "type": "ml_experiment",
                "experiment_name": experiment_name,
                "mlflow_run_id": mlflow_run_id,
            },
            generator_data={
                "hyperparameters": hyperparameters,
            },
            environment_data={
                "metrics": metrics,
                "success": success,
            },
            result="SUCCESS" if success else "FAILED",
            reflector_data={
                "decisions": decisions,
            },
            curator_data={
                "patterns_learned": patterns_learned,
                "pattern_count": len(patterns_learned),
            },
            playbook_updated=len(patterns_learned) > 0,
        )

    def get_recent_experiments(
        self,
        limit: int = 10,
        result_filter: str | None = None,
        experiment_type: str | None = None,
    ) -> list[ExperimentLogModel]:
        """
        Get recent experiments from the database.

        Args:
            limit: Maximum number of experiments to return
            result_filter: Filter by result (SUCCESS/FAILED/etc)
            experiment_type: Filter by type (tdd_cycle/ml_experiment)

        Returns:
            List of experiment logs
        """
        from sqlalchemy import desc

        with self.repo.get_session() as session:
            query = session.query(ExperimentLogModel)

            if result_filter:
                query = query.filter(ExperimentLogModel.result == result_filter)

            if experiment_type:
                query = query.filter(
                    ExperimentLogModel.task_data["type"].astext == experiment_type
                )

            query = query.order_by(desc(ExperimentLogModel.timestamp))
            query = query.limit(limit)

            return query.all()

    def get_experiment_stats(self) -> dict[str, Any]:
        """
        Get statistics about logged experiments.

        Returns:
            Dictionary with experiment statistics
        """
        from sqlalchemy import func, text

        with self.repo.get_session() as session:
            # Total experiments
            total = session.query(func.count(ExperimentLogModel.id)).scalar()

            # By result
            by_result = session.query(
                ExperimentLogModel.result,
                func.count(ExperimentLogModel.id)
            ).group_by(ExperimentLogModel.result).all()

            # By type
            by_type = session.execute(
                text("""
                    SELECT task_data->>'type' as type, COUNT(*)
                    FROM experiment_logs
                    WHERE task_data->>'type' IS NOT NULL
                    GROUP BY task_data->>'type'
                """)
            ).fetchall()

            # Playbook updates
            playbook_updates = session.query(
                func.count(ExperimentLogModel.id)
            ).filter(ExperimentLogModel.playbook_updated == True).scalar()

            return {
                "total_experiments": total,
                "by_result": dict(by_result),
                "by_type": dict(by_type),
                "playbook_updates": playbook_updates,
                "update_rate": playbook_updates / total if total > 0 else 0.0,
            }

    def get_tdd_lessons(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        Retrieve TDD lessons learned from failed cycles.

        These lessons can be injected into future TDD prompts to avoid
        repeating the same mistakes.

        Args:
            limit: Maximum number of lessons to retrieve

        Returns:
            List of lesson dictionaries with category, root_cause, and lesson
        """
        from sqlalchemy import desc, text

        lessons = []

        with self.repo.get_session() as session:
            # Query failed TDD cycles that have failure analysis
            results = session.execute(
                text("""
                    SELECT
                        task_data->>'test_name' as test_name,
                        reflector_data->>'failure_category' as category,
                        reflector_data->>'failure_root_cause' as root_cause,
                        reflector_data->>'failure_lesson' as lesson,
                        reflector_data->>'retry_count' as retry_count,
                        reflector_data->>'human_intervention' as human_intervention,
                        timestamp
                    FROM experiment_logs
                    WHERE task_data->>'type' = 'tdd_cycle'
                      AND result IN ('FAILED', 'ERROR')
                      AND reflector_data->>'failure_lesson' IS NOT NULL
                    ORDER BY timestamp DESC
                    LIMIT :limit
                """),
                {"limit": limit}
            ).fetchall()

            for row in results:
                lessons.append({
                    "test_name": row[0],
                    "category": row[1],
                    "root_cause": row[2],
                    "lesson": row[3],
                    "retry_count": row[4],
                    "human_intervention": row[5] == "true",
                    "timestamp": row[6],
                })

        logger.info(f"Retrieved {len(lessons)} TDD lessons")
        return lessons

    def get_tdd_anti_patterns(self) -> list[str]:
        """
        Get a list of TDD anti-patterns to avoid, derived from lessons.

        Returns:
            List of anti-pattern descriptions for prompt injection
        """
        lessons = self.get_tdd_lessons(limit=50)

        # Deduplicate and extract unique lessons
        unique_lessons = set()
        for lesson in lessons:
            if lesson.get("lesson"):
                unique_lessons.add(lesson["lesson"])

        return list(unique_lessons)

    def get_tdd_cycle_records(
        self,
        playbook_id: str | None = None,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return TDD cycle records as plain dicts for reliability analysis.

        Each record contains: timestamp, result, retry_count, playbook_id,
        retrieved_bullet_ids, and learned_bullet_count.
        """
        from sqlalchemy import desc

        with self.repo.get_session() as session:
            query = session.query(ExperimentLogModel).filter(
                ExperimentLogModel.task_data["type"].astext == "tdd_cycle"
            )
            if playbook_id:
                query = query.filter(
                    ExperimentLogModel.task_data["playbook_id"].astext == playbook_id
                )
            if since:
                query = query.filter(ExperimentLogModel.timestamp >= since)
            query = query.order_by(desc(ExperimentLogModel.timestamp))
            if limit:
                query = query.limit(limit)

            records = []
            for row in query.all():
                reflector = row.reflector_data or {}
                generator = row.generator_data or {}
                curator = row.curator_data or {}
                records.append({
                    "timestamp": row.timestamp,
                    "result": row.result,
                    "retry_count": reflector.get("retry_count", 0),
                    "playbook_id": (row.task_data or {}).get("playbook_id"),
                    "retrieved_bullet_ids": generator.get("retrieved_bullet_ids", []),
                    "learned_bullet_count": curator.get("bullet_count", 0),
                })
            return records
