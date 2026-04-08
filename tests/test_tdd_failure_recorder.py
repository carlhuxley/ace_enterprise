"""Tests for TDDFailureRecorder - self-healing TDD automation."""
import json
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from src.agents.tdd_failure_recorder import (
    TDDFailureRecorder,
    FailureContext,
    InterventionRecord,
)


class TestTDDFailureRecorder:
    """Tests for TDDFailureRecorder class."""

    def test_can_be_created(self):
        """TDDFailureRecorder can be instantiated."""
        recorder = TDDFailureRecorder()
        assert recorder is not None
        assert recorder.failed_cycles == 0

    def test_can_be_created_with_dependencies(self):
        """TDDFailureRecorder accepts optional dependencies."""
        mock_logger = Mock()
        mock_manager = Mock()
        
        recorder = TDDFailureRecorder(
            experiment_logger=mock_logger,
            playbook_manager=mock_manager,
            playbook_id="test-playbook",
        )
        
        assert recorder.experiment_logger == mock_logger
        assert recorder.playbook_manager == mock_manager
        assert recorder.playbook_id == "test-playbook"


class TestRecordFailure:
    """Tests for record_failure method."""

    def test_increments_failed_cycles(self):
        """record_failure increments the failed_cycles counter."""
        recorder = TDDFailureRecorder()
        context = FailureContext(
            feature_requirement="Test feature",
            cycle_number=1,
            error_message="Test error",
        )
        
        recorder.record_failure(context)
        assert recorder.failed_cycles == 1
        
        recorder.record_failure(context)
        assert recorder.failed_cycles == 2

    def test_logs_to_experiment_logger(self):
        """record_failure calls ExperimentLogger with correct params."""
        mock_logger = Mock()
        recorder = TDDFailureRecorder(experiment_logger=mock_logger)
        
        context = FailureContext(
            feature_requirement="Build markdown importer",
            cycle_number=3,
            error_message="ImportError: cannot import",
            error_type="ImportError",
            model="gemini-2.0-flash",
            provider="openrouter",
        )
        
        recorder.record_failure(context)
        
        mock_logger.log_experiment.assert_called_once()
        call_kwargs = mock_logger.log_experiment.call_args.kwargs
        
        assert call_kwargs["result"] == "FAILED"
        assert call_kwargs["task_data"]["description"] == "Build markdown importer"
        assert call_kwargs["curator_data"]["manual_intervention_required"] is True

    def test_creates_beads_issue(self, tmp_path):
        """record_failure creates a bug issue in beads."""
        beads_file = tmp_path / "issues.jsonl"
        beads_file.write_text("")
        
        recorder = TDDFailureRecorder(beads_path=beads_file)
        
        context = FailureContext(
            feature_requirement="Test feature",
            cycle_number=1,
            error_message="Something failed",
            error_type="RuntimeError",
        )
        
        recorder.record_failure(context, suggested_fix="Fix the thing")
        
        content = beads_file.read_text()
        assert "RuntimeError" in content
        assert "Test feature" in content
        assert "Fix the thing" in content

    def test_adds_playbook_bullet(self):
        """record_failure adds troubleshooting bullet to playbook."""
        mock_manager = Mock()
        recorder = TDDFailureRecorder(
            playbook_manager=mock_manager,
            playbook_id="test-pb",
        )
        
        context = FailureContext(
            feature_requirement="Test feature",
            cycle_number=1,
            error_message="Error details",
            error_type="ValueError",
        )
        
        recorder.record_failure(context)
        
        mock_manager.add_bullet.assert_called_once()
        call_args = mock_manager.add_bullet.call_args
        assert call_args[0][0] == "test-pb"  # playbook_id
        bullet = call_args[0][1]
        assert "ValueError" in bullet.content
        assert "troubleshooting" == bullet.section


class TestRecordIntervention:
    """Tests for record_intervention method."""

    def test_records_intervention_source(self, tmp_path):
        """record_intervention stores the intervention source."""
        beads_file = tmp_path / "issues.jsonl"
        
        # Create initial issue
        issue = {
            "id": "test-issue",
            "related_experiment": "tdd-fail-20260408-120000",
            "status": "open",
        }
        beads_file.write_text(json.dumps(issue))
        
        recorder = TDDFailureRecorder(beads_path=beads_file)
        
        intervention = InterventionRecord(
            source="ai_assistant",
            steps_taken=["Fixed imports", "Rewrote tests"],
            tests_written=5,
        )
        
        recorder.record_intervention("tdd-fail-20260408-120000", intervention)
        
        content = beads_file.read_text()
        data = json.loads(content)
        assert data["intervention_source"] == "ai_assistant"
        assert "Fixed imports" in data["intervention_steps"]


class TestInterventionRate:
    """Tests for intervention rate calculation."""

    def test_returns_zero_without_logger(self):
        """calculate_intervention_rate returns 0 without logger."""
        recorder = TDDFailureRecorder()
        rate = recorder.calculate_intervention_rate()
        assert rate == 0.0

    def test_reset_failed_cycles(self):
        """reset_failed_cycles sets counter to zero."""
        recorder = TDDFailureRecorder()
        recorder.failed_cycles = 5
        recorder.reset_failed_cycles()
        assert recorder.failed_cycles == 0


class TestFailureContext:
    """Tests for FailureContext dataclass."""

    def test_required_fields(self):
        """FailureContext requires essential fields."""
        context = FailureContext(
            feature_requirement="Build X",
            cycle_number=1,
            error_message="Error",
        )
        
        assert context.feature_requirement == "Build X"
        assert context.cycle_number == 1
        assert context.error_message == "Error"
        assert context.error_type == "RuntimeError"  # default

    def test_optional_fields(self):
        """FailureContext accepts optional fields."""
        context = FailureContext(
            feature_requirement="Build X",
            cycle_number=1,
            error_message="Error",
            explicit_class_name="MyClass",
            explicit_file_path="src/myclass.py",
        )
        
        assert context.explicit_class_name == "MyClass"
        assert context.explicit_file_path == "src/myclass.py"


class TestInterventionRecord:
    """Tests for InterventionRecord dataclass."""

    def test_intervention_sources(self):
        """InterventionRecord accepts valid sources."""
        for source in ["human", "ai_assistant", "self_healed"]:
            record = InterventionRecord(source=source)
            assert record.source == source

    def test_default_values(self):
        """InterventionRecord has sensible defaults."""
        record = InterventionRecord(source="human")
        
        assert record.steps_taken == []
        assert record.files_modified == []
        assert record.tests_written == 0
        assert record.tests_passing == 0
