"""
SQLAlchemy database models for ACE Enterprise.
Based on PRD Section 3: Data Architecture

Note: These models will be used when PostgreSQL is available.
For now, they serve as the data model specification.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, mapped_column, relationship

# pgvector integration for semantic search
from pgvector.sqlalchemy import Vector

Base = declarative_base()


# ============================================================================
# Playbook Models
# ============================================================================


class PlaybookModel(Base):
    """
    Playbook table - stores playbook metadata and configuration.
    Bullets are stored separately for better querying and updates.
    """

    __tablename__ = "playbooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    playbook_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    domain: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    base_model: Mapped[str] = mapped_column(String(100), nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_bullets: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    bullets: Mapped[list["BulletModel"]] = relationship(
        "BulletModel", back_populates="playbook", cascade="all, delete-orphan"
    )
    checkpoints: Mapped[list["CheckpointModel"]] = relationship(
        "CheckpointModel", back_populates="playbook"
    )

    __table_args__ = (Index("ix_playbooks_domain_version", "domain", "version"),)


class BulletModel(Base):
    """
    Bullet table - individual knowledge units within a playbook.
    """

    __tablename__ = "bullets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bullet_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    playbook_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    helpful_count: Mapped[int] = mapped_column(Integer, default=0)
    harmful_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_used: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Vector embedding for semantic search using pgvector
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)

    # Relationships
    playbook: Mapped["PlaybookModel"] = relationship("PlaybookModel", back_populates="bullets")

    __table_args__ = (
        Index("ix_bullets_playbook_section", "playbook_id", "section"),
        Index("ix_bullets_helpful_count", "helpful_count"),
    )


# ============================================================================
# Experiment Log Models
# ============================================================================


class ExperimentLogModel(Base):
    """
    Experiment log table - comprehensive audit trail of all learning activities.
    """

    __tablename__ = "experiment_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    playbook_version: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Task information
    task_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    # Generator output
    generator_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    # Environment feedback
    environment_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result: Mapped[str] = mapped_column(
        Enum("SUCCESS", "FAILED", "TIMEOUT", "ERROR", name="task_result"),
        nullable=False,
        index=True,
    )

    # Reflector output (optional - may be null for some experiments)
    reflector_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Curator output (optional)
    curator_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Outcome
    playbook_updated: Mapped[bool] = mapped_column(Boolean, default=False)
    performance_delta: Mapped[float] = mapped_column(Float, default=0.0)
    checkpoint_created: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("ix_experiment_logs_timestamp_result", "timestamp", "result"),
        Index("ix_experiment_logs_playbook_version", "playbook_version"),
    )


# ============================================================================
# Checkpoint Models
# ============================================================================


class CheckpointModel(Base):
    """
    Checkpoint table - versioned snapshots of playbooks with metrics.
    """

    __tablename__ = "checkpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    playbook_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False
    )
    playbook_version: Mapped[str] = mapped_column(String(20), nullable=False)

    # Full playbook snapshot (JSONB for efficient querying)
    playbook_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Metrics at checkpoint time
    accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    avg_helpful_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    tasks_processed: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_latency_ms: Mapped[float] = mapped_column(Float, nullable=False)

    # Trigger information
    trigger: Mapped[str] = mapped_column(
        Enum(
            "scheduled",
            "performance_peak",
            "manual",
            "pre_deployment",
            "pre_risky_update",
            name="checkpoint_trigger",
        ),
        nullable=False,
        index=True,
    )

    retention_policy: Mapped[str] = mapped_column(
        Enum("keep_indefinitely", "standard", name="retention_policy"),
        default="standard",
        nullable=False,
    )

    # Additional metadata (renamed from 'metadata' to avoid SQLAlchemy conflict)
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Relationships
    playbook: Mapped["PlaybookModel"] = relationship("PlaybookModel", back_populates="checkpoints")

    __table_args__ = (
        Index("ix_checkpoints_playbook_timestamp", "playbook_id", "timestamp"),
        Index("ix_checkpoints_accuracy", "accuracy"),
    )


# ============================================================================
# Performance Metrics Models
# ============================================================================


class PerformanceMetricModel(Base):
    """
    Performance metrics table - time-series data for monitoring.
    """

    __tablename__ = "performance_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    playbook_version: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Metrics
    task_success_rate: Mapped[float] = mapped_column(Float, nullable=False)
    avg_helpful_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    playbook_size_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    playbook_size_bullets: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_adaptation_latency_ms: Mapped[float] = mapped_column(Float, nullable=False)

    # Aggregated data
    error_frequency: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    bullet_utilization: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)

    __table_args__ = (Index("ix_performance_metrics_timestamp", "timestamp"),)


# ============================================================================
# Regression Alert Models
# ============================================================================


class RegressionAlertModel(Base):
    """
    Regression alerts table - tracks detected performance regressions.
    """

    __tablename__ = "regression_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    playbook_version: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Regression details
    recent_avg: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_avg: Mapped[float] = mapped_column(Float, nullable=False)
    delta: Mapped[float] = mapped_column(Float, nullable=False)
    p_value: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    recommended_action: Mapped[str] = mapped_column(
        Enum("rollback", "investigate", "ignore", name="regression_action"),
        nullable=False,
    )

    # Resolution tracking
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution_action: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Additional details
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    __table_args__ = (Index("ix_regression_alerts_resolved", "resolved", "detected_at"),)


# ============================================================================
# Rollback History Models
# ============================================================================


class RollbackHistoryModel(Base):
    """
    Rollback history table - audit trail of all rollback operations.
    """

    __tablename__ = "rollback_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rollback_timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    # Rollback details
    checkpoint_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    from_version: Mapped[str] = mapped_column(String(20), nullable=False)
    to_version: Mapped[str] = mapped_column(String(20), nullable=False)

    reason: Mapped[str] = mapped_column(Text, nullable=False)
    triggered_by: Mapped[str] = mapped_column(
        Enum("automatic", "manual", name="rollback_trigger"), nullable=False
    )

    # Result
    status: Mapped[str] = mapped_column(
        Enum("success", "failed", name="rollback_status"), nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Additional metadata (renamed from 'metadata' to avoid SQLAlchemy conflict)
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
