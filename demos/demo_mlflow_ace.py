#!/usr/bin/env python3
"""
Demo: MLflow + ACE Integration for ML Experimentation Knowledge Capture

This demo shows how ACE integrates with MLflow to capture not just execution metrics,
but the decision-making context, rationale, and learned patterns across experiments.

MLflow tracks: Parameters, metrics, artifacts, code versions
ACE captures: Decisions, rationale, rejected alternatives, cross-experiment patterns

Together: Complete institutional memory of ML experimentation
"""

import logging
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ml.experiment_knowledge import MLExperimentKnowledge, ExperimentDecision, ExperimentPattern
from src.ml.mlflow_callback import ACEMLflowCallback
from src.ml.query_interface import MLflowKnowledgeQuery

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def simulate_experiment_with_ace():
    """Simulate ML experiments with ACE knowledge capture."""

    print("\n" + "="*80)
    print("MLflow + ACE Integration Demo")
    print("="*80)

    try:
        import mlflow
        import numpy as np
        from sklearn.datasets import make_classification
        from sklearn.model_selection import train_test_split
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score, f1_score
    except ImportError as e:
        print(f"\n❌ Missing required package: {e}")
        print("Install with: pip install mlflow scikit-learn numpy")
        return 1

    # Configuration
    experiment_name = "image_classification_demo"
    knowledge_dir = Path.home() / ".ace" / "ml_experiments"
    human_contributor = "data_scientist@company.com"

    print(f"\n📁 Experiment: {experiment_name}")
    print(f"📁 Knowledge directory: {knowledge_dir}")

    # Generate synthetic dataset
    print("\n🔬 Generating synthetic dataset...")
    X, y = make_classification(
        n_samples=1000,
        n_features=20,
        n_informative=15,
        n_redundant=5,
        random_state=42
    )
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # Set MLflow tracking URI
    mlflow_dir = Path.home() / ".ace" / "mlruns"
    mlflow_dir.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(f"file://{mlflow_dir}")

    print(f"📁 MLflow tracking: {mlflow_dir}")

    # Set MLflow experiment (must be done before starting runs)
    mlflow.set_experiment(experiment_name)
    print(f"🔬 MLflow experiment: {experiment_name}")

    # =========================================================================
    # Experiment 1: Baseline with default hyperparameters
    # =========================================================================
    print("\n" + "="*80)
    print("Experiment 1: Baseline (default hyperparameters)")
    print("="*80)

    # Initialize ACE callback
    ace_callback = ACEMLflowCallback(
        experiment_name=experiment_name,
        knowledge_dir=knowledge_dir,
        human_contributor=human_contributor
    )

    with mlflow.start_run(run_name="baseline") as run:
        print(f"\n▶️  MLflow run ID: {run.info.run_id}")

        # Log decision: Using default hyperparameters
        print("\n💡 Logging decision: Hyperparameter choice")
        ace_callback.log_decision(
            question="Which hyperparameters to use for baseline?",
            decision="Use scikit-learn defaults (n_estimators=100, max_depth=None)",
            rationale="Establish baseline performance before optimization",
            alternatives_considered=[
                "Grid search from start",
                "Transfer hyperparams from similar project",
                "Random search"
            ],
            ai_models=[
                {"provider": "anthropic", "model": "claude-sonnet-3.5", "license": "proprietary"}
            ]
        )

        # Train model
        print("🏋️  Training model...")
        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)

        # Evaluate
        y_pred = model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred)

        # Log to MLflow
        mlflow.log_param("n_estimators", 100)
        mlflow.log_param("max_depth", "None")
        mlflow.log_param("random_state", 42)
        mlflow.log_metric("accuracy", accuracy)
        mlflow.log_metric("f1_score", f1)

        print(f"📊 Accuracy: {accuracy:.4f}")
        print(f"📊 F1 Score: {f1:.4f}")

        # Update decision outcome
        decision_id = ace_callback.knowledge.decisions[-1].decision_id
        ace_callback.update_decision_outcome(
            decision_id=decision_id,
            outcome="successful",
            learned_insight=f"Baseline achieves {accuracy:.4f} accuracy, good starting point for optimization"
        )

        run1_id = run.info.run_id

    # =========================================================================
    # Experiment 2: Increase tree depth based on baseline observation
    # =========================================================================
    print("\n" + "="*80)
    print("Experiment 2: Increase max_depth (based on baseline)")
    print("="*80)

    with mlflow.start_run(run_name="deeper_trees") as run:
        print(f"\n▶️  MLflow run ID: {run.info.run_id}")

        # Log decision: Increase max_depth
        print("\n💡 Logging decision: Tree depth adjustment")
        ace_callback.log_decision(
            question="Should we limit tree depth?",
            decision="Set max_depth=20 to allow more complex patterns",
            rationale="Baseline with unlimited depth may be overfitting. Want to find sweet spot.",
            alternatives_considered=[
                "Keep max_depth=None (unlimited)",
                "Try max_depth=10 (conservative)",
                "Grid search multiple depths"
            ],
            context={"previous_run_id": run1_id, "baseline_accuracy": accuracy},
            ai_models=[
                {"provider": "anthropic", "model": "claude-sonnet-3.5", "license": "proprietary"}
            ]
        )

        # Train model
        print("🏋️  Training model...")
        model = RandomForestClassifier(n_estimators=100, max_depth=20, random_state=42)
        model.fit(X_train, y_train)

        # Evaluate
        y_pred = model.predict(X_test)
        accuracy_2 = accuracy_score(y_test, y_pred)
        f1_2 = f1_score(y_test, y_pred)

        # Log to MLflow
        mlflow.log_param("n_estimators", 100)
        mlflow.log_param("max_depth", 20)
        mlflow.log_param("random_state", 42)
        mlflow.log_metric("accuracy", accuracy_2)
        mlflow.log_metric("f1_score", f1_2)

        print(f"📊 Accuracy: {accuracy_2:.4f} (Δ {accuracy_2 - accuracy:+.4f})")
        print(f"📊 F1 Score: {f1_2:.4f} (Δ {f1_2 - f1:+.4f})")

        # Update decision outcome
        decision_id = ace_callback.knowledge.decisions[-1].decision_id
        if accuracy_2 > accuracy:
            ace_callback.update_decision_outcome(
                decision_id=decision_id,
                outcome="successful",
                learned_insight=f"Limiting depth improved accuracy by {accuracy_2 - accuracy:.4f}"
            )
        else:
            ace_callback.update_decision_outcome(
                decision_id=decision_id,
                outcome="failed",
                learned_insight=f"Limiting depth decreased accuracy by {accuracy_2 - accuracy:.4f}"
            )

        run2_id = run.info.run_id

    # =========================================================================
    # Experiment 3: Increase number of trees
    # =========================================================================
    print("\n" + "="*80)
    print("Experiment 3: More trees (n_estimators=200)")
    print("="*80)

    with mlflow.start_run(run_name="more_trees") as run:
        print(f"\n▶️  MLflow run ID: {run.info.run_id}")

        # Log decision: More trees
        print("\n💡 Logging decision: Number of trees")
        ace_callback.log_decision(
            question="How many trees should we use?",
            decision="Increase to n_estimators=200",
            rationale="More trees generally improve performance with diminishing returns. Want to test if worth the compute cost.",
            alternatives_considered=[
                "Keep n_estimators=100",
                "Try n_estimators=500 (expensive)",
                "Use early stopping"
            ],
            context={"previous_run_id": run2_id},
            ai_models=[
                {"provider": "anthropic", "model": "claude-sonnet-3.5", "license": "proprietary"}
            ]
        )

        # Train model
        print("🏋️  Training model...")
        model = RandomForestClassifier(n_estimators=200, max_depth=20, random_state=42)
        model.fit(X_train, y_train)

        # Evaluate
        y_pred = model.predict(X_test)
        accuracy_3 = accuracy_score(y_test, y_pred)
        f1_3 = f1_score(y_test, y_pred)

        # Log to MLflow
        mlflow.log_param("n_estimators", 200)
        mlflow.log_param("max_depth", 20)
        mlflow.log_param("random_state", 42)
        mlflow.log_metric("accuracy", accuracy_3)
        mlflow.log_metric("f1_score", f1_3)

        print(f"📊 Accuracy: {accuracy_3:.4f} (Δ {accuracy_3 - accuracy_2:+.4f})")
        print(f"📊 F1 Score: {f1_3:.4f} (Δ {f1_3 - f1_2:+.4f})")

        # Update decision outcome
        decision_id = ace_callback.knowledge.decisions[-1].decision_id
        improvement = accuracy_3 - accuracy_2
        if improvement > 0.01:  # Meaningful improvement
            ace_callback.update_decision_outcome(
                decision_id=decision_id,
                outcome="successful",
                learned_insight=f"Doubling trees improved accuracy by {improvement:.4f} - worth the compute cost"
            )
        else:
            ace_callback.update_decision_outcome(
                decision_id=decision_id,
                outcome="inconclusive",
                learned_insight=f"Marginal improvement ({improvement:.4f}) - may not justify 2x compute cost"
            )

        run3_id = run.info.run_id

    # =========================================================================
    # Log a learned pattern from the experiments
    # =========================================================================
    print("\n" + "="*80)
    print("Extracting Learned Pattern")
    print("="*80)

    print("\n🔍 Analyzing experiments to extract pattern...")
    ace_callback.log_pattern(
        pattern_name="Limited tree depth improves Random Forest generalization",
        description="For Random Forest classifiers on medium-sized datasets, limiting max_depth prevents overfitting and improves test accuracy",
        when_to_apply="When using Random Forest on datasets with < 10K samples and unlimited depth shows signs of overfitting",
        implementation="Set max_depth between 10-30 depending on feature complexity. Start with max_depth=20 as reasonable default.",
        observed_in_runs=[run1_id, run2_id, run3_id],
        success_rate=0.67,  # 2/3 runs showed improvement
        domain_tags=["random_forest", "classification", "overfitting_prevention"],
        antipatterns=[
            "Don't use max_depth < 5 unless dataset is very simple",
            "Don't set max_depth too high on small datasets (< 1K samples)"
        ],
        avg_improvement=0.02  # Average accuracy improvement
    )
    print("✅ Pattern logged!")

    # =========================================================================
    # Query the combined MLflow + ACE knowledge base
    # =========================================================================
    print("\n" + "="*80)
    print("Querying MLflow + ACE Knowledge Base")
    print("="*80)

    query = MLflowKnowledgeQuery(
        experiment_name=experiment_name,
        knowledge_dir=knowledge_dir,
        mlflow_tracking_uri=f"file://{mlflow_dir}"
    )

    # Get all enriched runs
    print("\n📊 All runs with knowledge context:")
    enriched_runs = query.get_enriched_runs()
    for run in enriched_runs:
        print(f"\n  Run: {run.run_id[:8]}... ({run.tags.get('mlflow.runName', 'unnamed')})")
        print(f"    Accuracy: {run.metrics.get('accuracy', 'N/A'):.4f}")
        print(f"    Decisions: {run.decision_count}")
        print(f"    Failed decisions: {run.has_failed_decisions}")

    # Find runs by decision
    print("\n🔍 Runs where we decided on tree depth:")
    depth_runs = query.find_runs_by_decision(question="tree depth")
    for run in depth_runs:
        for decision in run.decisions:
            if "depth" in decision.question.lower():
                print(f"\n  Run: {run.run_id[:8]}...")
                print(f"    Question: {decision.question}")
                print(f"    Decision: {decision.decision}")
                print(f"    Outcome: {decision.outcome}")

    # Get decision history
    print("\n📜 Full decision history:")
    decisions = query.get_decision_history()
    for i, dec in enumerate(decisions, 1):
        print(f"\n  {i}. {dec.question}")
        print(f"     → {dec.decision}")
        print(f"     Rationale: {dec.rationale}")
        if dec.outcome:
            print(f"     Outcome: {dec.outcome}")
        if dec.learned_insight:
            print(f"     Learned: {dec.learned_insight}")

    # Compare runs
    print("\n🔬 Comparing baseline vs best run:")
    comparison = query.compare_runs(run1_id, run3_id)
    print(f"\n  Parameter differences:")
    for param, diff in comparison["param_differences"].items():
        print(f"    {param}: {diff['run1']} → {diff['run2']}")

    print(f"\n  Metric differences:")
    for metric, diff in comparison["metric_differences"].items():
        print(f"    {metric}: {diff['run1']:.4f} → {diff['run2']:.4f} "
              f"({diff['diff']:+.4f}, {diff['pct_change']:+.2f}%)")

    print(f"\n  Decision differences:")
    for question, diff in comparison["decision_differences"].items():
        print(f"    {question}")
        print(f"      Run 1: {diff['run1']}")
        print(f"      Run 2: {diff['run2']}")

    # Get recommendations for new experiment
    print("\n💡 Recommendations for new experiment with similar parameters:")
    recommendations = query.get_recommendations_for_params(
        params={"n_estimators": 100, "max_depth": 20},
        domain_tags=["random_forest"],
        min_success_rate=0.5
    )
    for pattern, reason in recommendations:
        print(f"\n  📌 {pattern.pattern_name}")
        print(f"     Reason: {reason}")
        print(f"     Success rate: {pattern.success_rate:.2f}")
        print(f"     When to apply: {pattern.when_to_apply}")
        print(f"     Implementation: {pattern.implementation}")

    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "="*80)
    print("Demo Summary")
    print("="*80)

    print(f"""
✅ Successfully demonstrated MLflow + ACE integration!

What we captured:
- 📊 3 MLflow runs with parameters and metrics
- 💡 3 decisions with full rationale and alternatives
- 📈 1 cross-experiment pattern
- 🔍 Complete decision-outcome trail

What's in MLflow:
- Parameters (n_estimators, max_depth, etc.)
- Metrics (accuracy, f1_score)
- Run metadata and tags

What's in ACE:
- Why each decision was made
- What alternatives were considered
- Outcome of each decision (successful/failed)
- Learned insights from outcomes
- Cross-experiment patterns with success rates

Combined Value:
- Can query "show me runs where we tried increasing tree depth"
- Can see "what did we learn from failed decisions"
- Can get "recommendations based on what worked before"
- Can trace "why did we make this decision" months later

Knowledge stored at:
- MLflow: {mlflow_dir}
- ACE: {knowledge_dir / experiment_name}.json

Try running MLflow UI:
  cd {mlflow_dir.parent}
  mlflow ui

Or query the knowledge base:
  python -c "from src.ml import MLflowKnowledgeQuery; \\
             q = MLflowKnowledgeQuery('{experiment_name}'); \\
             print(q.get_decision_history())"
""")

    return 0


if __name__ == "__main__":
    sys.exit(simulate_experiment_with_ace())