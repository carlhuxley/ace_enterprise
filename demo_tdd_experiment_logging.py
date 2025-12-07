#!/usr/bin/env python3
"""
Demo: TDD Cycle Experiment Logging

Shows how TDD cycles are automatically logged to experiment_logs table.
This simulates what happens when AutonomousTDDAgent runs.
"""
from src.storage.experiment_logger import ExperimentLogger
from src.playbook.postgres_adapter import PostgresPlaybookAdapter
from src.storage.schemas import PlaybookCreate

print("\n" + "="*80)
print("TDD CYCLE EXPERIMENT LOGGING DEMO")
print("="*80)

# Initialize
print("\n1. Initializing components...")
adapter = PostgresPlaybookAdapter()
logger = ExperimentLogger(playbook_version="1.0.0")

# Create a test playbook
print("\n2. Creating test playbook...")
playbook = adapter.create_playbook(
    PlaybookCreate(
        domain="tdd_demo",
        base_model="qwen2.5-coder:7b"
    )
)
print(f"   ✓ Created playbook: {playbook.playbook_id}")

# Simulate TDD Cycle 1: Calculator creation
print("\n" + "="*80)
print("SIMULATING TDD CYCLE 1: Create Calculator")
print("="*80)

print("\n📝 RED Phase: Write failing test...")
test_code_1 = """
def test_calculator_can_be_created():
    calc = Calculator()
    assert calc is not None
"""
print("   ✓ Test written")

print("\n🔴 Running test... FAILED (expected - no Calculator class)")
red_passed = False

print("\n💻 GREEN Phase: Write minimal implementation...")
impl_code_1 = """
class Calculator:
    pass
"""
print("   ✓ Implementation written")

print("\n🟢 Running test... PASSED!")
green_passed = True

print("\n📊 Logging cycle to experiment_logs...")
experiment = logger.log_tdd_cycle(
    cycle_number=1,
    requirement="Calculator that can be instantiated",
    test_name="test_calculator_can_be_created",
    test_code=test_code_1,
    implementation_code=impl_code_1,
    red_passed=red_passed,
    green_passed=green_passed,
    red_output="FAILED: NameError: name 'Calculator' is not defined",
    green_output="PASSED: 1 test passed",
    learned_bullets=[
        {
            "content": "Start TDD with simplest test: can object be created?",
            "section": "strategies_and_hard_rules",
            "tags": ["tdd", "testing", "basics"]
        }
    ],
    playbook_id=playbook.playbook_id
)
print(f"   ✓ Logged cycle 1: {experiment.experiment_id}")
print(f"   Result: {experiment.result}")
print(f"   Playbook updated: {experiment.playbook_updated}")

# Simulate TDD Cycle 2: Add method
print("\n" + "="*80)
print("SIMULATING TDD CYCLE 2: Add 'add' method")
print("="*80)

print("\n📝 RED Phase: Write failing test...")
test_code_2 = """
def test_calculator_has_add_method():
    calc = Calculator()
    result = calc.add(2, 3)
    assert result == 5
"""
print("   ✓ Test written")

print("\n🔴 Running test... FAILED (expected - no add method)")
red_passed = False

print("\n💻 GREEN Phase: Write minimal implementation...")
impl_code_2 = """
class Calculator:
    def add(self, a, b):
        return a + b
"""
print("   ✓ Implementation written")

print("\n🟢 Running test... PASSED!")
green_passed = True

print("\n📊 Logging cycle to experiment_logs...")
experiment = logger.log_tdd_cycle(
    cycle_number=2,
    requirement="Calculator can add two numbers",
    test_name="test_calculator_has_add_method",
    test_code=test_code_2,
    implementation_code=impl_code_2,
    red_passed=red_passed,
    green_passed=green_passed,
    red_output="FAILED: AttributeError: 'Calculator' object has no attribute 'add'",
    green_output="PASSED: 2 tests passed",
    learned_bullets=[
        {
            "content": "After testing creation, test the first behavior/method",
            "section": "strategies_and_hard_rules",
            "tags": ["tdd", "progression"]
        }
    ],
    playbook_id=playbook.playbook_id
)
print(f"   ✓ Logged cycle 2: {experiment.experiment_id}")
print(f"   Result: {experiment.result}")
print(f"   Playbook updated: {experiment.playbook_updated}")

# Query experiments
print("\n" + "="*80)
print("QUERYING LOGGED EXPERIMENTS")
print("="*80)

print("\n📊 Recent TDD cycles:")
recent = logger.get_recent_experiments(limit=10)
for exp in recent[:5]:
    exp_type = exp.task_data.get("type", "unknown")
    cycle_num = exp.task_data.get("cycle_number", "?")
    test_name = exp.task_data.get("test_name", "unknown")
    print(f"   • Cycle {cycle_num}: {test_name} - {exp.result}")

print("\n📊 Experiment statistics:")
stats = logger.get_experiment_stats()
print(f"   Total experiments: {stats['total_experiments']}")
print(f"   By result: {stats['by_result']}")
print(f"   By type: {stats['by_type']}")
print(f"   Playbook updates: {stats['playbook_updates']}")
print(f"   Update rate: {stats['update_rate']:.1%}")

# Summary
print("\n" + "="*80)
print("✅ DEMO COMPLETE")
print("="*80)

print("""
🎯 What We Demonstrated:

1. **Automatic TDD Cycle Logging**
   - Each cycle logged with full context
   - RED and GREEN phase results captured
   - Test code and implementation stored

2. **ACE Architecture Mapping**
   - Task: TDD cycle requirement
   - Generator: Test code + implementation code
   - Environment: RED and GREEN test outputs
   - Reflector: Analysis of what worked
   - Curator: Learned patterns added to playbook

3. **Queryable History**
   - Search experiments by type, result, date
   - Track success rates and learning velocity
   - Analyze patterns across all TDD cycles

🚀 In Real TDD Workflow:
   When AutonomousTDDAgent runs, EVERY cycle is logged this way automatically!
   No manual intervention needed - just build features and learning happens.
""")

print()
