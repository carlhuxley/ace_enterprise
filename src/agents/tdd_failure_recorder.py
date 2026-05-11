"""
TDD Failure Recorder - Self-healing automation for TDD agent.

Records failures, creates issues, and adds playbook bullets to enable
continuous improvement and reduce intervention rate.
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from src.storage.experiment_logger import ExperimentLogger
from src.playbook.manager import PlaybookManager
from src.storage.schemas import BulletCreate

logger = logging.getLogger(__name__)

InterventionSource = Literal["human", "ai_assistant", "self_healed"]


@dataclass
class FailureContext:
    """Context about a TDD failure for recording."""
    feature_requirement: str
    cycle_number: int
    error_message: str
    error_type: str = "RuntimeError"
    stack_trace: str = ""
    test_file: str = ""
    impl_file: str = ""
    explicit_class_name: str | None = None
    explicit_file_path: str | None = None
    model: str = "unknown"
    provider: str = "unknown"


@dataclass 
class InterventionRecord:
    """Record of intervention after TDD failure."""
    source: InterventionSource
    steps_taken: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    tests_written: int = 0
    tests_passing: int = 0


class TDDFailureRecorder:
    """
    Records TDD failures and interventions for self-improvement.
    
    Responsibilities:
    1. Log failed experiments to ExperimentLogger
    2. Create bug issues in .beads/issues.jsonl
    3. Add troubleshooting bullets to playbook
    4. Track intervention source and steps
    5. Calculate intervention_rate metric
    """
    
    def __init__(
        self,
        experiment_logger: ExperimentLogger | None = None,
        playbook_manager: PlaybookManager | None = None,
        playbook_id: str | None = None,
        beads_path: Path = Path(".beads/issues.jsonl"),
    ):
        self.experiment_logger = experiment_logger
        self.playbook_manager = playbook_manager
        self.playbook_id = playbook_id
        self.beads_path = beads_path
        self.failed_cycles = 0
    
    def record_failure(
        self,
        context: FailureContext,
        suggested_fix: str | None = None,
    ) -> str:
        """
        Record a TDD failure with full context.
        
        Args:
            context: Failure context details
            suggested_fix: LLM-suggested fix if available
            
        Returns:
            Experiment ID of the logged failure
        """
        self.failed_cycles += 1
        now = datetime.now(timezone.utc)
        experiment_id = f"tdd-fail-{now.strftime('%Y%m%d-%H%M%S%f')}"
        
        # 1. Log to ExperimentLogger
        if self.experiment_logger:
            self.experiment_logger.log_experiment(
                experiment_id=experiment_id,
                task_data={
                    "type": "build_feature",
                    "description": context.feature_requirement,
                    "cycle_number": context.cycle_number,
                },
                generator_data={
                    "model": context.model,
                    "provider": context.provider,
                    "explicit_class_name": context.explicit_class_name,
                    "explicit_file_path": context.explicit_file_path,
                },
                environment_data={
                    "test_file": context.test_file,
                    "impl_file": context.impl_file,
                },
                result="FAILED",
                reflector_data={
                    "error_type": context.error_type,
                    "error_message": context.error_message,
                    "stack_trace": context.stack_trace[:1000],  # Truncate
                },
                curator_data={
                    "manual_intervention_required": True,
                    "suggested_fix": suggested_fix,
                },
            )
            logger.info(f"📊 Logged failure experiment: {experiment_id}")
        
        # 2. Create beads issue
        issue_id = self._create_beads_issue(context, suggested_fix, experiment_id, now)
        logger.info(f"🐛 Created beads issue: {issue_id}")
        
        # 3. Add playbook bullet
        if self.playbook_manager and self.playbook_id:
            self._add_playbook_bullet(context)
            logger.info(f"📚 Added troubleshooting bullet to playbook")
        
        return experiment_id
    
    def record_intervention(
        self,
        experiment_id: str,
        intervention: InterventionRecord,
    ) -> None:
        """
        Record that intervention was required after a failure.
        
        Args:
            experiment_id: The failed experiment ID
            intervention: Details of the intervention
        """
        # Update beads with intervention record
        if self.beads_path.exists():
            lines = self.beads_path.read_text().strip().split('\n')
            updated = []
            for line in lines:
                if line:
                    issue = json.loads(line)
                    # Find related issue and update
                    if issue.get('related_experiment') == experiment_id:
                        issue['intervention_source'] = intervention.source
                        issue['intervention_steps'] = intervention.steps_taken
                        issue['updated_at'] = datetime.now(timezone.utc).isoformat()
                    updated.append(json.dumps(issue))
            self.beads_path.write_text('\n'.join(updated))
        
        logger.info(f"📝 Recorded intervention: {intervention.source}")
    
    def calculate_intervention_rate(self) -> float:
        """
        Calculate intervention rate from experiment logs.
        
        Returns:
            Rate as float between 0 and 1 (interventions / total builds)
        """
        if not self.experiment_logger:
            return 0.0
        
        # Query experiments from database
        # For now, return 0 - full implementation needs DB query
        return 0.0
    
    def reset_failed_cycles(self) -> None:
        """Reset the failed cycles counter."""
        self.failed_cycles = 0
    
    def _create_beads_issue(
        self,
        context: FailureContext,
        suggested_fix: str | None,
        experiment_id: str,
        now: datetime,
    ) -> str:
        """Create a bug issue in beads."""
        issue_id = f"ace_enterprise-bf{now.strftime('%Y%m%d%H%M%S%f')}"

        issue = {
            "id": issue_id,
            "title": f"TDD build failed: {context.error_type} in cycle {context.cycle_number}",
            "description": f"""**Feature:** {context.feature_requirement}

**Error:** {context.error_type}
```
{context.error_message}
```

**Files:**
- Test: {context.test_file}
- Impl: {context.impl_file}

**Suggested Fix:**
{suggested_fix or 'No suggestion available'}
""",
            "issue_type": "bug",
            "status": "open",
            "priority": 2,
            "created_at": now.isoformat(),
            "created_by": "TDDFailureRecorder",
            "labels": ["tdd", "auto-generated", context.error_type.lower()],
            "related_experiment": experiment_id,
        }
        
        # Append to beads file
        self.beads_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.beads_path, 'a') as f:
            f.write('\n' + json.dumps(issue))
        
        return issue_id
    
    def _add_playbook_bullet(self, context: FailureContext) -> None:
        """Add troubleshooting bullet to playbook."""
        bullet = BulletCreate(
            content=f"""**TDD Failure Pattern: {context.error_type}**

Error in cycle {context.cycle_number} of "{context.feature_requirement}":
```
{context.error_message[:500]}
```

Files involved: {context.test_file}, {context.impl_file}

Prevention: Check for similar patterns before generating code.""",
            section="troubleshooting",
            tags=["tdd", "auto-learned", context.error_type.lower()],
            created_by_model="TDDFailureRecorder",
        )
        
        try:
            self.playbook_manager.add_bullet(self.playbook_id, bullet)
        except Exception as e:
            logger.warning(f"Could not add playbook bullet: {e}")
