"""
Tests for ML Experiment Knowledge System

These tests capture the actual business behavior of the ML knowledge system,
enabling high-quality Gherkin extraction.
"""

import pytest
from datetime import datetime
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ml.experiment_knowledge import (
    ExperimentDecision,
    ExperimentPattern,
    MLExperimentKnowledge
)


class TestExperimentDecision:
    """Test experiment decision tracking."""

    def test_create_decision_with_required_fields(self):
        """Test creating a decision with required fields."""
        decision = ExperimentDecision(
            decision_id="dec_001",
            timestamp=datetime(2025, 12, 6, 10, 30),
            question="Which optimizer to use?",
            decision="Adam with lr=0.001",
            rationale="SGD was unstable in pilot runs"
        )

        assert decision.decision_id == "dec_001"
        assert decision.question == "Which optimizer to use?"
        assert decision.decision == "Adam with lr=0.001"
        assert decision.rationale == "SGD was unstable in pilot runs"

    def test_create_decision_with_alternatives(self):
        """Test creating a decision with alternatives considered."""
        decision = ExperimentDecision(
            decision_id="dec_002",
            timestamp=datetime.now(),
            question="Which batch size?",
            decision="128",
            rationale="Good balance of speed and stability",
            alternatives_considered=["64", "256", "512"]
        )

        assert decision.alternatives_considered == ["64", "256", "512"]
        assert len(decision.alternatives_considered) == 3

    def test_decision_with_outcome_tracking(self):
        """Test tracking decision outcomes."""
        decision = ExperimentDecision(
            decision_id="dec_003",
            timestamp=datetime.now(),
            question="Use dropout?",
            decision="Yes, 0.5 rate",
            rationale="Prevent overfitting",
            outcome="successful",
            learned_insight="Dropout improved validation accuracy by 3%"
        )

        assert decision.outcome == "successful"
        assert decision.learned_insight == "Dropout improved validation accuracy by 3%"

    def test_decision_serialization_to_dict(self):
        """Test converting decision to dictionary."""
        decision = ExperimentDecision(
            decision_id="dec_004",
            timestamp=datetime(2025, 12, 6, 10, 30),
            question="Test question",
            decision="Test decision",
            rationale="Test rationale"
        )

        decision_dict = decision.to_dict()

        assert decision_dict["decision_id"] == "dec_004"
        assert decision_dict["question"] == "Test question"
        assert decision_dict["decision"] == "Test decision"
        assert "timestamp" in decision_dict

    def test_decision_deserialization_from_dict(self):
        """Test creating decision from dictionary."""
        decision_data = {
            "decision_id": "dec_005",
            "timestamp": "2025-12-06T10:30:00",
            "question": "Original question",
            "decision": "Original decision",
            "rationale": "Original rationale",
            "alternatives_considered": ["alt1", "alt2"]
        }

        decision = ExperimentDecision.from_dict(decision_data)

        assert decision.decision_id == "dec_005"
        assert decision.question == "Original question"
        assert decision.alternatives_considered == ["alt1", "alt2"]


class TestExperimentPattern:
    """Test experiment pattern learning."""

    def test_create_pattern_with_success_metrics(self):
        """Test creating a pattern with success rate and improvement."""
        pattern = ExperimentPattern(
            pattern_id="pat_001",
            pattern_name="Learning rate warmup",
            description="Gradually increase LR for first epoch",
            observed_in_experiments=["run_123", "run_456", "run_789"],
            success_rate=0.85,
            avg_improvement=0.03,
            when_to_apply="When batch_size > 256",
            implementation="Use lr_scheduler.LinearLR(start_factor=0.1)",
            discovered_date=datetime(2025, 12, 1)
        )

        assert pattern.pattern_name == "Learning rate warmup"
        assert pattern.success_rate == 0.85
        assert pattern.avg_improvement == 0.03
        assert len(pattern.observed_in_experiments) == 3

    def test_pattern_with_domain_tags(self):
        """Test pattern categorization with domain tags."""
        pattern = ExperimentPattern(
            pattern_id="pat_002",
            pattern_name="Differential privacy for HIPAA",
            description="Add noise to protect patient data",
            observed_in_experiments=["healthcare_01"],
            success_rate=1.0,
            when_to_apply="When handling healthcare data",
            implementation="Use opacus library",
            domain_tags=["healthcare", "privacy", "compliance"],
            discovered_date=datetime.now()
        )

        assert "healthcare" in pattern.domain_tags
        assert "privacy" in pattern.domain_tags
        assert "compliance" in pattern.domain_tags

    def test_pattern_with_antipatterns(self):
        """Test pattern with antipatterns to avoid."""
        pattern = ExperimentPattern(
            pattern_id="pat_003",
            pattern_name="Batch normalization",
            description="Normalize activations",
            observed_in_experiments=["exp_01"],
            success_rate=0.9,
            when_to_apply="Deep networks",
            implementation="Add BatchNorm2d layers",
            antipatterns=[
                "Don't use with very small batches (< 4)",
                "Don't combine with dropout in same layer"
            ],
            discovered_date=datetime.now()
        )

        assert len(pattern.antipatterns) == 2
        assert "Don't use with very small batches" in pattern.antipatterns[0]


class TestMLExperimentKnowledge:
    """Test ML experiment knowledge management."""

    def test_create_empty_knowledge_base(self):
        """Test creating an empty knowledge base."""
        knowledge = MLExperimentKnowledge(experiment_name="test_experiment")

        assert knowledge.experiment_name == "test_experiment"
        assert len(knowledge.decisions) == 0
        assert len(knowledge.patterns) == 0

    def test_add_decision_to_knowledge_base(self):
        """Test adding a decision to the knowledge base."""
        knowledge = MLExperimentKnowledge(experiment_name="test_experiment")

        decision = ExperimentDecision(
            decision_id="dec_001",
            timestamp=datetime.now(),
            question="Which optimizer?",
            decision="Adam",
            rationale="Best for this problem"
        )

        knowledge.add_decision(decision)

        assert len(knowledge.decisions) == 1
        assert knowledge.decisions[0].decision_id == "dec_001"

    def test_add_multiple_decisions(self):
        """Test adding multiple decisions."""
        knowledge = MLExperimentKnowledge(experiment_name="test_experiment")

        for i in range(5):
            decision = ExperimentDecision(
                decision_id=f"dec_{i:03d}",
                timestamp=datetime.now(),
                question=f"Question {i}",
                decision=f"Decision {i}",
                rationale=f"Rationale {i}"
            )
            knowledge.add_decision(decision)

        assert len(knowledge.decisions) == 5

    def test_get_decisions_for_specific_run(self):
        """Test retrieving decisions for a specific MLflow run."""
        knowledge = MLExperimentKnowledge(
            experiment_name="test_experiment",
            mlflow_experiment_id="exp_123"
        )

        # Add decision for run_001
        decision1 = ExperimentDecision(
            decision_id="dec_001",
            timestamp=datetime.now(),
            question="Q1",
            decision="D1",
            rationale="R1",
            context={"mlflow_run_id": "run_001"}
        )

        # Add decision for run_002
        decision2 = ExperimentDecision(
            decision_id="dec_002",
            timestamp=datetime.now(),
            question="Q2",
            decision="D2",
            rationale="R2",
            context={"mlflow_run_id": "run_002"}
        )

        knowledge.add_decision(decision1)
        knowledge.add_decision(decision2)

        run_001_decisions = knowledge.get_decisions_for_run("run_001")

        assert len(run_001_decisions) == 1
        assert run_001_decisions[0].decision_id == "dec_001"

    def test_add_pattern_to_knowledge_base(self):
        """Test adding a learned pattern."""
        knowledge = MLExperimentKnowledge(experiment_name="test_experiment")

        pattern = ExperimentPattern(
            pattern_id="pat_001",
            pattern_name="Test pattern",
            description="Test description",
            observed_in_experiments=["run_001"],
            success_rate=0.8,
            when_to_apply="Test condition",
            implementation="Test implementation",
            discovered_date=datetime.now()
        )

        knowledge.add_pattern(pattern)

        assert len(knowledge.patterns) == 1
        assert knowledge.patterns[0].pattern_id == "pat_001"

    def test_get_patterns_by_domain(self):
        """Test filtering patterns by domain."""
        knowledge = MLExperimentKnowledge(experiment_name="test_experiment")

        # Add computer vision pattern
        cv_pattern = ExperimentPattern(
            pattern_id="pat_cv",
            pattern_name="Data augmentation",
            description="Augment training images",
            observed_in_experiments=["run_001"],
            success_rate=0.9,
            when_to_apply="Image classification",
            implementation="Use torchvision.transforms",
            domain_tags=["computer_vision", "image_classification"],
            discovered_date=datetime.now()
        )

        # Add NLP pattern
        nlp_pattern = ExperimentPattern(
            pattern_id="pat_nlp",
            pattern_name="Tokenization",
            description="Subword tokenization",
            observed_in_experiments=["run_002"],
            success_rate=0.85,
            when_to_apply="Text processing",
            implementation="Use transformers.AutoTokenizer",
            domain_tags=["nlp", "text_processing"],
            discovered_date=datetime.now()
        )

        knowledge.add_pattern(cv_pattern)
        knowledge.add_pattern(nlp_pattern)

        cv_patterns = knowledge.get_patterns_by_domain("computer_vision")

        assert len(cv_patterns) == 1
        assert cv_patterns[0].pattern_id == "pat_cv"

    def test_get_successful_patterns_above_threshold(self):
        """Test filtering patterns by success rate."""
        knowledge = MLExperimentKnowledge(experiment_name="test_experiment")

        # Add high success pattern
        high_success = ExperimentPattern(
            pattern_id="pat_high",
            pattern_name="High success pattern",
            description="Works great",
            observed_in_experiments=["run_001"],
            success_rate=0.95,
            when_to_apply="Always",
            implementation="Do this",
            discovered_date=datetime.now()
        )

        # Add low success pattern
        low_success = ExperimentPattern(
            pattern_id="pat_low",
            pattern_name="Low success pattern",
            description="Sometimes works",
            observed_in_experiments=["run_002"],
            success_rate=0.55,
            when_to_apply="Rarely",
            implementation="Try this",
            discovered_date=datetime.now()
        )

        knowledge.add_pattern(high_success)
        knowledge.add_pattern(low_success)

        successful_patterns = knowledge.get_successful_patterns(min_success_rate=0.8)

        assert len(successful_patterns) == 1
        assert successful_patterns[0].pattern_id == "pat_high"

    def test_save_and_load_knowledge_base(self, tmp_path):
        """Test persistence of knowledge base."""
        knowledge = MLExperimentKnowledge(experiment_name="test_experiment")

        # Add decision
        decision = ExperimentDecision(
            decision_id="dec_001",
            timestamp=datetime.now(),
            question="Test",
            decision="Test decision",
            rationale="Test rationale"
        )
        knowledge.add_decision(decision)

        # Save
        save_path = tmp_path / "knowledge.json"
        knowledge.save(save_path)

        # Load
        loaded_knowledge = MLExperimentKnowledge.load(save_path)

        assert loaded_knowledge.experiment_name == "test_experiment"
        assert len(loaded_knowledge.decisions) == 1
        assert loaded_knowledge.decisions[0].decision_id == "dec_001"
