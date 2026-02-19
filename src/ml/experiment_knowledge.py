"""ML Experiment Knowledge Schema - extends ACE playbook structure for ML experimentation."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ExperimentDecision:
    """Captures a decision made during ML experimentation."""

    decision_id: str
    timestamp: datetime
    question: str  # "Which optimizer to use?"
    decision: str  # "Adam with lr=0.001"
    rationale: str  # "AdamW showed instability in early experiments"

    # Optional fields with defaults
    alternatives_considered: list[str] = field(default_factory=list)  # ["SGD", "AdamW", "RMSprop"]
    context: dict[str, Any] = field(default_factory=dict)  # {"previous_run_id": "abc123"}

    # Provenance
    human_contributor: str | None = None
    ai_models: list[dict[str, str]] = field(default_factory=list)
    conversation_id: str | None = None

    # Outcome tracking
    outcome: str | None = None  # "successful" | "failed" | "inconclusive"
    learned_insight: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp.isoformat(),
            "question": self.question,
            "decision": self.decision,
            "rationale": self.rationale,
            "alternatives_considered": self.alternatives_considered,
            "context": self.context,
            "human_contributor": self.human_contributor,
            "ai_models": self.ai_models,
            "conversation_id": self.conversation_id,
            "outcome": self.outcome,
            "learned_insight": self.learned_insight,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ExperimentDecision':
        """Load from dictionary."""
        data = data.copy()
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


@dataclass
class ExperimentPattern:
    """Cross-experiment pattern learned from multiple runs."""

    pattern_id: str
    pattern_name: str  # "Learning rate warmup for large batches"
    description: str

    # Evidence
    observed_in_experiments: list[str]  # List of MLflow run_ids
    success_rate: float  # 0.0 to 1.0

    # Application guidance
    when_to_apply: str  # "When batch_size > 256 and using Adam optimizer"
    implementation: str  # Code snippet or configuration

    # Provenance
    discovered_date: datetime

    # Optional fields with defaults
    avg_improvement: float | None = None  # Metric improvement when pattern applied
    antipatterns: list[str] = field(default_factory=list)
    experiments_count: int = 1
    domain_tags: list[str] = field(default_factory=list)

    # Quality signals
    usefulness_score: float = 0.0
    times_applied: int = 0
    times_successful: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "pattern_id": self.pattern_id,
            "pattern_name": self.pattern_name,
            "description": self.description,
            "observed_in_experiments": self.observed_in_experiments,
            "success_rate": self.success_rate,
            "avg_improvement": self.avg_improvement,
            "when_to_apply": self.when_to_apply,
            "implementation": self.implementation,
            "antipatterns": self.antipatterns,
            "discovered_date": self.discovered_date.isoformat(),
            "experiments_count": self.experiments_count,
            "domain_tags": self.domain_tags,
            "usefulness_score": self.usefulness_score,
            "times_applied": self.times_applied,
            "times_successful": self.times_successful,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ExperimentPattern':
        """Load from dictionary."""
        data = data.copy()
        data['discovered_date'] = datetime.fromisoformat(data['discovered_date'])
        return cls(**data)


@dataclass
class MLExperimentKnowledge:
    """Knowledge base for ML experiments - integrates with MLflow run tracking."""

    experiment_name: str
    mlflow_experiment_id: str | None = None

    # Decision trail
    decisions: list[ExperimentDecision] = field(default_factory=list)

    # Learned patterns
    patterns: list[ExperimentPattern] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def add_decision(self, decision: ExperimentDecision) -> None:
        """Add a decision to the knowledge base."""
        self.decisions.append(decision)
        self.updated_at = datetime.now()

    def add_pattern(self, pattern: ExperimentPattern) -> None:
        """Add a learned pattern to the knowledge base."""
        self.patterns.append(pattern)
        self.updated_at = datetime.now()

    def get_decisions_for_run(self, mlflow_run_id: str) -> list[ExperimentDecision]:
        """Get all decisions associated with a specific MLflow run."""
        return [
            d for d in self.decisions
            if d.context.get("mlflow_run_id") == mlflow_run_id
        ]

    def get_patterns_by_domain(self, domain: str) -> list[ExperimentPattern]:
        """Get patterns relevant to a specific domain."""
        return [
            p for p in self.patterns
            if domain in p.domain_tags
        ]

    def get_successful_patterns(
        self, min_success_rate: float = 0.7, min_experiments: int = 1
    ) -> list[ExperimentPattern]:
        """Get patterns with high success rate."""
        return [
            p for p in self.patterns
            if p.success_rate >= min_success_rate and p.experiments_count >= min_experiments
        ]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "experiment_name": self.experiment_name,
            "mlflow_experiment_id": self.mlflow_experiment_id,
            "decisions": [d.to_dict() for d in self.decisions],
            "patterns": [p.to_dict() for p in self.patterns],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'MLExperimentKnowledge':
        """Load from dictionary."""
        data = data.copy()
        data['decisions'] = [ExperimentDecision.from_dict(d) for d in data.get('decisions', [])]
        data['patterns'] = [ExperimentPattern.from_dict(p) for p in data.get('patterns', [])]
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        return cls(**data)

    def save(self, filepath: Path) -> None:
        """Save knowledge base to JSON file."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath: Path) -> 'MLExperimentKnowledge':
        """Load knowledge base from JSON file."""
        with open(filepath) as f:
            data = json.load(f)
        return cls.from_dict(data)
