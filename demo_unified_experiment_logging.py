"""
Demo: Unified Experiment Logging for TDD and ML

Shows how both TDD cycles and ML experiments are logged to the same
PostgreSQL experiment_logs table with consistent structure.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.storage.experiment_logger import ExperimentLogger
from src.playbook.postgres_adapter import PostgresPlaybookAdapter
from src.storage.schemas import PlaybookCreate

print("\n" + "="*80)
print("UNIFIED EXPERIMENT LOGGING DEMO")
print("="*80)

# Initialize
print("\n1. Initializing components...")
adapter = PostgresPlaybookAdapter()

# Create playbooks for both TDD and ML
tdd_playbook = adapter.create_playbook(
    PlaybookCreate(
        domain="tdd_logging_demo",
        base_model="claude-sonnet-4.5"
    )
)

ml_playbook = adapter.create_playbook(
    PlaybookCreate(
        domain="ml_logging_demo",
        base_model="claude-sonnet-4.5"
    )
)

print(f"   ✓ Created TDD playbook: {tdd_playbook.playbook_id}")
print(f"   ✓ Created ML playbook: {ml_playbook.playbook_id}")

# Initialize logger
logger = ExperimentLogger(playbook_version="1.0.0")

# ============================================================================
# Demo 1: Log TDD Cycle
# ============================================================================

print("\n" + "="*80)
print("DEMO 1: TDD CYCLE LOGGING")
print("="*80)

print("\nLogging a TDD cycle...")
tdd_experiment = logger.log_tdd_cycle(
    cycle_number=1,
    requirement="Implement user authentication",
    test_name="test_user_can_login",
    test_code="""
def test_user_can_login():
    auth = AuthService()
    result = auth.login("user@example.com", "password123")
    assert result.success == True
    assert result.token is not None
""",
    implementation_code="""
class AuthService:
    def login(self, email: str, password: str) -> AuthResult:
        # Minimal implementation to pass test
        if email and password:
            return AuthResult(success=True, token="abc123")
        return AuthResult(success=False, token=None)
""",
    red_passed=False,  # Test failed in RED phase (good!)
    green_passed=True,  # Test passed in GREEN phase (good!)
    red_output="FAILED: 1 test failed",
    green_output="PASSED: 1 test passed",
    learned_bullets=[
        {
            "content": "Always validate email format in authentication",
            "section": "strategies_and_hard_rules",
            "tags": ["auth", "validation"]
        }
    ],
    playbook_id=tdd_playbook.playbook_id,
)

print(f"   ✓ Logged TDD cycle: {tdd_experiment.experiment_id}")
print(f"   Result: {tdd_experiment.result}")
print(f"   Playbook updated: {tdd_experiment.playbook_updated}")

# ============================================================================
# Demo 2: Log ML Experiment
# ============================================================================

print("\n" + "="*80)
print("DEMO 2: ML EXPERIMENT LOGGING")
print("="*80)

print("\nLogging an ML experiment...")
ml_experiment = logger.log_ml_experiment(
    experiment_id="ml_sentiment_classifier_001",
    experiment_name="Sentiment Classification",
    hyperparameters={
        "model": "bert-base-uncased",
        "learning_rate": 2e-5,
        "batch_size": 16,
        "epochs": 3,
        "optimizer": "AdamW"
    },
    metrics={
        "accuracy": 0.94,
        "f1_score": 0.93,
        "val_loss": 0.12
    },
    decisions=[
        {
            "question": "Which pre-trained model to use?",
            "decision": "BERT base uncased",
            "rationale": "Good balance of performance and inference speed"
        }
    ],
    patterns_learned=[
        {
            "pattern_name": "BERT fine-tuning for sentiment",
            "description": "BERT with lr=2e-5 works well for sentiment classification",
            "when_to_apply": "When classifying sentiment on social media text",
            "success_rate": 0.94
        }
    ],
    mlflow_run_id="abc123def456",
    success=True,
)

print(f"   ✓ Logged ML experiment: {ml_experiment.experiment_id}")
print(f"   Result: {ml_experiment.result}")
print(f"   Playbook updated: {ml_experiment.playbook_updated}")

# ============================================================================
# Demo 3: Query Experiments
# ============================================================================

print("\n" + "="*80)
print("DEMO 3: QUERY EXPERIMENTS")
print("="*80)

print("\n📊 Recent experiments:")
recent = logger.get_recent_experiments(limit=10)
for exp in recent[:5]:
    exp_type = exp.task_data.get("type", "unknown")
    print(f"   • {exp.experiment_id} ({exp_type}): {exp.result}")

print("\n📊 Experiment statistics:")
stats = logger.get_experiment_stats()
print(f"   Total experiments: {stats['total_experiments']}")
print(f"   By result: {stats['by_result']}")
print(f"   By type: {stats['by_type']}")
print(f"   Playbook updates: {stats['playbook_updates']}")
print(f"   Update rate: {stats['update_rate']:.1%}")

# ============================================================================
# Demo 4: Show Unified Structure
# ============================================================================

print("\n" + "="*80)
print("DEMO 4: UNIFIED EXPERIMENT STRUCTURE")
print("="*80)

print("\nTDD Experiment Structure:")
print(f"   Task: {tdd_experiment.task_data}")
print(f"   Generator: test_code + implementation_code")
print(f"   Environment: red_phase + green_phase outputs")
print(f"   Reflector: {tdd_experiment.reflector_data}")
print(f"   Curator: {tdd_experiment.curator_data}")

print("\nML Experiment Structure:")
print(f"   Task: {ml_experiment.task_data}")
print(f"   Generator: {ml_experiment.generator_data}")
print(f"   Environment: {ml_experiment.environment_data}")
print(f"   Reflector: {ml_experiment.reflector_data}")
print(f"   Curator: {ml_experiment.curator_data}")

# ============================================================================
# Summary
# ============================================================================

print("\n" + "="*80)
print("✅ UNIFIED LOGGING DEMO COMPLETE")
print("="*80)

print("""
🎯 What We Demonstrated:

1. **TDD Cycle Logging**
   - Logged test-code-refactor cycle
   - Captured RED and GREEN phase results
   - Stored learned patterns

2. **ML Experiment Logging**
   - Logged hyperparameters and metrics
   - Captured decisions and rationale
   - Stored successful patterns

3. **Unified Structure**
   - Both use same PostgreSQL table (experiment_logs)
   - Both follow ACE architecture (Task→Generator→Environment→Reflector→Curator)
   - Both enable institutional knowledge capture

4. **Query & Analytics**
   - Search experiments by type, result, date
   - Track learning rate (% of experiments that update playbook)
   - Analyze patterns across TDD and ML domains

🚀 Next Steps:
   1. Hook into AutonomousTDDAgent for automatic TDD logging
   2. Use PostgresACEMLflowCallback in your ML training scripts
   3. Build dashboards to visualize learning over time
   4. Cross-pollinate knowledge between TDD and ML domains
""")

print()
