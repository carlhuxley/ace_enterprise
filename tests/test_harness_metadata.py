"""Tests for harness metadata in ExperimentLogger (ace_enterprise-8mz)."""
import tempfile
from pathlib import Path

import pytest

from src.storage.experiment_logger import ExperimentLogger
from src.storage.repository import PlaybookRepository


SAMPLE_METADATA = {
    "source_hash": "a" * 64,
    "verification_status": "CLEAN_PASS",
    "environment": "podman 5.0.0",
    "tdd_stage": "GREEN",
    "timestamp": "2026-05-16T12:00:00Z",
    "bandit_severity_counts": {"high": 0, "medium": 0, "low": 1},
    "audit_logs": "1 passed in 0.01s",
}


def make_logger(tmp_path: Path) -> ExperimentLogger:
    db_url = f"sqlite:///{tmp_path}/test.db"
    repo = PlaybookRepository(database_url=db_url)
    return ExperimentLogger(playbook_version="1.0.0", repository=repo)


def log_cycle(logger: ExperimentLogger, harness_metadata=None) -> str:
    """Log a minimal TDD cycle and return its experiment_id."""
    logger.log_tdd_cycle(
        cycle_number=1,
        requirement="add two numbers",
        test_name="test_add",
        test_code="def test_add(): assert add(1,2)==3",
        implementation_code="def add(a,b): return a+b",
        red_passed=False,
        green_passed=True,
        red_output="FAILED",
        green_output="1 passed",
        learned_bullets=[],
        playbook_id="pb-001",
        harness_metadata=harness_metadata,
    )
    return "tdd_pb-001_cycle_1"


# ---------------------------------------------------------------------------
# Behavior 1: harness_metadata stored under environment_data["harness"]
# ---------------------------------------------------------------------------

def test_harness_metadata_persisted_in_environment_data(tmp_path):
    from src.storage.models import ExperimentLogModel

    logger = make_logger(tmp_path)
    experiment_id = log_cycle(logger, harness_metadata=SAMPLE_METADATA)

    repo = logger.repo
    with repo.get_session() as session:
        row = session.query(ExperimentLogModel).filter_by(
            experiment_id=experiment_id
        ).one()
        harness = row.environment_data.get("harness")

    assert harness is not None
    assert harness["verification_status"] == "CLEAN_PASS"
    assert harness["source_hash"] == "a" * 64


# ---------------------------------------------------------------------------
# Behavior 2: existing callers without harness_metadata are unaffected
# ---------------------------------------------------------------------------

def test_log_tdd_cycle_without_harness_metadata_unaffected(tmp_path):
    from src.storage.models import ExperimentLogModel

    logger = make_logger(tmp_path)
    experiment_id = log_cycle(logger, harness_metadata=None)

    with logger.repo.get_session() as session:
        row = session.query(ExperimentLogModel).filter_by(
            experiment_id=experiment_id
        ).one()
        env = row.environment_data

    assert "harness" not in env
    assert "red_phase" in env
    assert "green_phase" in env


# ---------------------------------------------------------------------------
# Behavior 3: all 7 PRD fields survive the DB round-trip
# ---------------------------------------------------------------------------

def test_all_seven_harness_fields_survive_round_trip(tmp_path):
    from src.storage.models import ExperimentLogModel

    logger = make_logger(tmp_path)
    log_cycle(logger, harness_metadata=SAMPLE_METADATA)

    with logger.repo.get_session() as session:
        row = session.query(ExperimentLogModel).first()
        harness = row.environment_data["harness"]

    assert harness["source_hash"] == SAMPLE_METADATA["source_hash"]
    assert harness["verification_status"] == SAMPLE_METADATA["verification_status"]
    assert harness["environment"] == SAMPLE_METADATA["environment"]
    assert harness["tdd_stage"] == SAMPLE_METADATA["tdd_stage"]
    assert harness["timestamp"] == SAMPLE_METADATA["timestamp"]
    assert harness["bandit_severity_counts"] == SAMPLE_METADATA["bandit_severity_counts"]
    assert harness["audit_logs"] == SAMPLE_METADATA["audit_logs"]


# ---------------------------------------------------------------------------
# Behavior 4: verification_status accepts the four defined enum strings
# ---------------------------------------------------------------------------

def test_verification_status_values_are_stored_correctly(tmp_path):
    from src.storage.models import ExperimentLogModel

    statuses = ["CLEAN_PASS", "BANDIT_FAIL", "HASH_MISMATCH", "TEST_FAIL"]
    logger = make_logger(tmp_path)

    for i, status in enumerate(statuses):
        meta = {**SAMPLE_METADATA, "verification_status": status}
        logger.log_tdd_cycle(
            cycle_number=i + 1,
            requirement="req",
            test_name="test_x",
            test_code="",
            implementation_code="",
            red_passed=False,
            green_passed=True,
            red_output="",
            green_output="",
            learned_bullets=[],
            playbook_id=f"pb-{i}",
            harness_metadata=meta,
        )

    with logger.repo.get_session() as session:
        rows = session.query(ExperimentLogModel).all()
        stored = [r.environment_data["harness"]["verification_status"] for r in rows]

    assert stored == statuses
