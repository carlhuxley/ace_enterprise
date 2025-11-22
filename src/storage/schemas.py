"""
Pydantic schemas for data validation and API models.
Based on PRD Section 3: Data Architecture
"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ============================================================================
# Bullet Schemas (PRD Section 3.1)
# ============================================================================


class BulletBase(BaseModel):
    """Base schema for a playbook bullet"""

    content: str = Field(..., description="The actual content/text of the bullet")
    section: str = Field(
        ...,
        description="Section this bullet belongs to (strategies_and_hard_rules, code_snippets, troubleshooting, domain_knowledge)",
    )
    tags: list[str] = Field(default_factory=list, description="Optional tags for categorization")


class BulletCreate(BulletBase):
    """Schema for creating a new bullet"""

    # Model provenance (optional, for auditability)
    created_by_model: str | None = None
    model_provider: str | None = None
    license_type: str | None = None


class Bullet(BulletBase):
    """Complete bullet schema with metadata"""

    id: str = Field(..., description="Unique bullet ID (e.g., ctx-00001)")
    helpful_count: int = Field(default=0, description="Number of times marked as helpful")
    harmful_count: int = Field(default=0, description="Number of times marked as harmful")
    created_at: datetime
    last_used: datetime | None = None
    embedding: list[float] | None = Field(
        None, description="Vector embedding for semantic search"
    )

    # Model provenance fields (added 2025-11-21 for auditability and licensing)
    created_by_model: str | None = Field(
        None, description="Model that created this bullet (e.g., 'gpt-4o', 'qwen2.5-coder:14b')"
    )
    model_provider: str | None = Field(
        None, description="Model provider (e.g., 'openai', 'ollama', 'anthropic')"
    )
    license_type: str | None = Field(
        None, description="Model license (e.g., 'apache-2.0', 'mit', 'proprietary')"
    )

    class Config:
        from_attributes = True


class BulletFeedback(BaseModel):
    """Feedback on bullet usefulness from Generator"""

    bullet_id: str
    tag: Literal["helpful", "harmful", "neutral"]


# ============================================================================
# Playbook Schemas (PRD Section 3.1)
# ============================================================================


class PlaybookMetadata(BaseModel):
    """Playbook metadata"""

    domain: str = Field(..., description="Domain or use case (e.g., financial_analysis)")
    base_model: str = Field(..., description="LLM model used (e.g., qwen3-coder:30b)")
    total_tokens: int = Field(default=0, description="Total token count of playbook")
    total_bullets: int = Field(default=0, description="Total number of bullets")


class PlaybookSections(BaseModel):
    """Playbook organized by sections"""

    strategies_and_hard_rules: list[Bullet] = Field(default_factory=list)
    code_snippets: list[Bullet] = Field(default_factory=list)
    troubleshooting: list[Bullet] = Field(default_factory=list)
    domain_knowledge: list[Bullet] = Field(default_factory=list)


class PlaybookBase(BaseModel):
    """Base playbook schema"""

    metadata: PlaybookMetadata
    sections: dict[str, list[Bullet]] = Field(
        default_factory=dict, description="Bullets organized by section"
    )


class PlaybookCreate(BaseModel):
    """Schema for creating a new playbook"""

    domain: str
    base_model: str


class Playbook(PlaybookBase):
    """Complete playbook schema"""

    playbook_id: str = Field(..., description="Unique playbook ID (e.g., pb_20251016_001)")
    version: str = Field(..., description="Semantic version (e.g., 1.2.3)")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Task & Environment Schemas (PRD Section 3.2)
# ============================================================================


class TaskInput(BaseModel):
    """Task input from user"""

    id: str = Field(..., description="Unique task ID")
    query: str = Field(..., description="User query or task description")
    type: str = Field(default="agent_execution", description="Type of task")
    difficulty: Literal["easy", "normal", "hard"] = Field(default="normal")
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context")


class EnvironmentFeedback(BaseModel):
    """Feedback from task execution environment"""

    result: Literal["SUCCESS", "FAILED", "TIMEOUT", "ERROR"]
    expected: str | None = Field(None, description="Expected output (if available)")
    actual: str | None = Field(None, description="Actual output")
    feedback: str | None = Field(None, description="Error messages or test results")
    test_report: dict[str, Any] | None = Field(None, description="Detailed test report")


# ============================================================================
# Generator Schemas (PRD Section 3.2)
# ============================================================================


class GeneratorOutput(BaseModel):
    """Output from Generator module"""

    trajectory: str = Field(..., description="Reasoning steps taken")
    solution: str = Field(..., description="Final solution or action")
    bullets_used: list[str] = Field(default_factory=list, description="IDs of bullets used")
    bullet_feedback: dict[str, str] = Field(
        default_factory=dict, description="Feedback on each bullet (helpful/harmful/neutral)"
    )
    latency_ms: int = Field(..., description="Execution time in milliseconds")
    tokens_used: int = Field(..., description="Total tokens consumed")


# ============================================================================
# Reflector Schemas (PRD Section 3.2)
# ============================================================================


class ReflectorOutput(BaseModel):
    """Output from Reflector module"""

    error_identification: str | None = Field(
        None, description="What went wrong (if anything)"
    )
    root_cause: str | None = Field(None, description="Why it went wrong")
    correct_approach: str | None = Field(None, description="What should have been done")
    key_insight: str | None = Field(None, description="Key learning or pattern")
    bullet_tags: list[BulletFeedback] = Field(
        default_factory=list, description="Updated tags for bullets"
    )
    iterations: int = Field(default=1, description="Number of refinement iterations")
    quality_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Quality of insights (0-1)"
    )


# ============================================================================
# Curator Schemas (PRD Section 3.2)
# ============================================================================


class DeltaBullet(BaseModel):
    """A new bullet to add to playbook"""

    section: str = Field(..., description="Target section")
    content: str = Field(..., description="Bullet content")
    tags: list[str] = Field(default_factory=list)


class CuratorOutput(BaseModel):
    """Output from Curator module"""

    delta_bullets: list[DeltaBullet] = Field(
        default_factory=list, description="New bullets to add"
    )
    reasoning: str = Field(..., description="Why these bullets were created")


# ============================================================================
# Experiment Log Schemas (PRD Section 3.2)
# ============================================================================


class ExperimentOutcome(BaseModel):
    """Final outcome of an experiment"""

    playbook_updated: bool = Field(default=False)
    performance_delta: float = Field(
        default=0.0, description="Change in performance metric"
    )
    checkpoint_created: bool = Field(default=False)


class ExperimentLogBase(BaseModel):
    """Base experiment log schema"""

    playbook_version: str
    timestamp: datetime
    task: TaskInput
    generator: GeneratorOutput
    environment: EnvironmentFeedback
    reflector: ReflectorOutput | None = None
    curator: CuratorOutput | None = None
    outcome: ExperimentOutcome


class ExperimentLogCreate(BaseModel):
    """Schema for creating experiment log"""

    playbook_version: str
    task: TaskInput
    generator: GeneratorOutput
    environment: EnvironmentFeedback


class ExperimentLog(ExperimentLogBase):
    """Complete experiment log"""

    experiment_id: str = Field(..., description="Unique experiment ID (e.g., exp_20251016_12345)")

    class Config:
        from_attributes = True


# ============================================================================
# Checkpoint Schemas (PRD Section 3.3)
# ============================================================================


class CheckpointMetrics(BaseModel):
    """Performance metrics at checkpoint time"""

    accuracy: float = Field(..., ge=0.0, le=1.0)
    avg_helpful_ratio: float = Field(..., ge=0.0, le=1.0)
    tasks_processed: int = Field(..., ge=0)
    avg_latency_ms: float = Field(..., gt=0)


class CheckpointMetadata(BaseModel):
    """Additional checkpoint metadata"""

    epoch: int | None = None
    training_split: Literal["offline", "online", "hybrid"] | None = None
    git_commit: str | None = None
    notes: str | None = None


class CheckpointCreate(BaseModel):
    """Schema for creating a checkpoint"""

    playbook_id: str
    trigger: Literal["scheduled", "performance_peak", "manual", "pre_deployment", "pre_risky_update"]
    metrics: CheckpointMetrics
    metadata: CheckpointMetadata | None = None


class Checkpoint(BaseModel):
    """Complete checkpoint schema"""

    checkpoint_id: str = Field(..., description="Unique checkpoint ID (e.g., ckpt_20251016_003)")
    playbook_snapshot: Playbook = Field(..., description="Full playbook state at checkpoint")
    timestamp: datetime
    metrics: CheckpointMetrics
    trigger: Literal["scheduled", "performance_peak", "manual", "pre_deployment", "pre_risky_update"]
    retention_policy: Literal["keep_indefinitely", "standard"] = Field(default="standard")
    metadata: CheckpointMetadata | None = None

    class Config:
        from_attributes = True


# ============================================================================
# Rollback Schemas
# ============================================================================


class RollbackRequest(BaseModel):
    """Request to rollback to a checkpoint"""

    checkpoint_id: str
    reason: str
    confirmation_token: str = Field(..., description="Required confirmation for safety")


class RollbackResult(BaseModel):
    """Result of a rollback operation"""

    status: Literal["success", "failed"]
    playbook_version: str | None = None
    rollback_timestamp: datetime
    error_message: str | None = None


# ============================================================================
# Performance Monitoring Schemas
# ============================================================================


class PerformanceMetrics(BaseModel):
    """Real-time performance metrics"""

    task_success_rate: float = Field(..., ge=0.0, le=1.0, description="Rolling window success rate")
    avg_helpful_ratio: float = Field(..., ge=0.0, le=1.0)
    playbook_size_tokens: int
    playbook_size_bullets: int
    avg_adaptation_latency_ms: float
    error_frequency: dict[str, int] = Field(default_factory=dict)
    bullet_utilization: dict[str, int] = Field(
        default_factory=dict, description="Usage count per bullet"
    )


class RegressionAlert(BaseModel):
    """Alert for performance regression"""

    detected_at: datetime
    playbook_version: str
    recent_avg: float
    baseline_avg: float
    delta: float
    p_value: float
    confidence: float
    recommended_action: Literal["rollback", "investigate", "ignore"]
    details: dict[str, Any] = Field(default_factory=dict)
