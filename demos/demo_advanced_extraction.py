"""
Advanced Demo: Extract Gherkin from ACE's Own Codebase

This demonstrates extraction from a real, production-ready codebase:
ACE Enterprise's ML Experiment Knowledge system.

This is more complex than the simple OAuth example, showing:
- Multiple classes with inheritance
- Complex data models
- Real-world business logic
- Production-quality code patterns
"""

import sys
from pathlib import Path
import logging

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agents.gherkin_extraction_agent import GherkinExtractionAgent

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def demonstrate_real_codebase_extraction():
    """Extract Gherkin from ACE's ML experiment knowledge system."""

    print("\n" + "="*80)
    print("ADVANCED DEMO: Extract Gherkin from Real Production Code")
    print("="*80)
    print("\nTarget: ACE Enterprise ML Experiment Knowledge System")
    print("- Production-ready code with complex business logic")
    print("- Multiple data models and classes")
    print("- Real-world patterns and edge cases")

    # Target files from ACE's own codebase
    code_file = Path("src/ml/experiment_knowledge.py")

    # Check if we have tests for this component
    # If not, we'll analyze just the code structure
    test_file = Path("tests/test_experiment_knowledge.py")

    if not code_file.exists():
        print(f"\n❌ Code file not found: {code_file}")
        print("This demo requires the ML integration to be present.")
        return

    print(f"\n📂 Analyzing:")
    print(f"   Code: {code_file}")
    if test_file.exists():
        print(f"   Tests: {test_file}")
    else:
        print(f"   Tests: Not found (will extract from code structure only)")

    # Initialize extraction agent
    print(f"\n🤖 Initializing Gherkin Extraction Agent...")
    agent = GherkinExtractionAgent()

    # Analyze the code
    print(f"\n🔍 Analyzing production code...")
    code_analysis = agent.code_analyzer.analyze(code_file)

    print(f"\n📊 Code Analysis Results:")
    print(f"   Classes found: {len(code_analysis.classes)}")
    for cls in code_analysis.classes:
        print(f"\n   Class: {cls.name}")
        if cls.docstring:
            doc_preview = cls.docstring.split('\n')[0][:60]
            print(f"      Docstring: {doc_preview}...")
        print(f"      Methods: {len(cls.methods)}")
        for method in cls.methods[:5]:  # Show first 5 methods
            params = ", ".join(p[0] for p in method.parameters if p[0] != 'self')
            print(f"        - {method.name}({params})")
        if len(cls.methods) > 5:
            print(f"        ... and {len(cls.methods) - 5} more")

    # Create a synthetic test scenario based on code structure
    print(f"\n📝 Generating Gherkin from code structure...")
    print(f"   (Note: In production, you'd have actual tests)")

    # For demo purposes, let's extract just the ExperimentDecision class
    decision_class = next((cls for cls in code_analysis.classes if 'Decision' in cls.name), None)

    if decision_class:
        print(f"\n✨ Focusing on: {decision_class.name}")

        # Generate high-level Gherkin based on class structure
        feature_name = "ML Experiment Decision Tracking"
        scenarios = []

        # Generate scenarios from methods
        for method in decision_class.methods:
            if not method.name.startswith('_'):  # Skip private methods
                scenario_name = agent._humanize_test_name(f"test_{method.name}")

                # Build a basic scenario
                given_steps = [f"an ML experiment with a decision to record"]
                when_steps = [f"I {agent._humanize_name(method.name)}"]
                then_steps = ["the decision should be properly recorded"]

                from agents.gherkin_extraction_agent import GherkinScenario
                scenarios.append(GherkinScenario(
                    name=scenario_name,
                    given_steps=given_steps,
                    when_steps=when_steps,
                    then_steps=then_steps
                ))

        print(f"   Generated {len(scenarios)} scenarios")

        # Write to file
        output_dir = Path("extracted_gherkin_advanced")
        feature_file = output_dir / "ml_experiment_knowledge.feature"
        output_dir.mkdir(parents=True, exist_ok=True)

        with open(feature_file, 'w') as f:
            f.write(f"Feature: {feature_name}\n")
            if decision_class.docstring:
                for line in decision_class.docstring.split('\n')[:3]:
                    f.write(f"  {line}\n")
            f.write("\n")

            for scenario in scenarios:
                f.write(f"  Scenario: {scenario.name}\n")
                for step in scenario.given_steps:
                    f.write(f"    Given {step}\n")
                for step in scenario.when_steps:
                    f.write(f"    When {step}\n")
                for step in scenario.then_steps:
                    f.write(f"    Then {step}\n")
                f.write("\n")

        print(f"\n✅ Generated Gherkin: {feature_file}")

    # Show insights about the codebase
    print(f"\n" + "="*80)
    print("INSIGHTS FROM PRODUCTION CODE")
    print("="*80)

    print(f"\n📈 Complexity Analysis:")
    total_methods = sum(len(cls.methods) for cls in code_analysis.classes)
    avg_methods = total_methods / len(code_analysis.classes) if code_analysis.classes else 0
    print(f"   Total classes: {len(code_analysis.classes)}")
    print(f"   Total methods: {total_methods}")
    print(f"   Average methods per class: {avg_methods:.1f}")

    documented_classes = sum(1 for cls in code_analysis.classes if cls.docstring)
    doc_ratio = documented_classes / len(code_analysis.classes) * 100 if code_analysis.classes else 0
    print(f"   Documentation coverage: {doc_ratio:.0f}%")

    # Identify patterns
    print(f"\n🔍 Patterns Identified:")
    dataclass_count = sum(1 for cls in code_analysis.classes if '@dataclass' in str(cls.docstring) or cls.name.endswith('Data') or cls.name.endswith('Result'))
    print(f"   Data models (dataclasses): ~{dataclass_count}")

    constructor_count = sum(1 for cls in code_analysis.classes for method in cls.methods if method.is_constructor)
    print(f"   Classes with constructors: {constructor_count}")

    type_hints = sum(1 for cls in code_analysis.classes for method in cls.methods for param in method.parameters if param[1])
    print(f"   Type-hinted parameters: {type_hints}")

    # Real-world extraction scenarios
    print(f"\n" + "="*80)
    print("REAL-WORLD EXTRACTION SCENARIOS")
    print("="*80)

    print(f"""
🎯 SCENARIO 1: Refactor ML Knowledge System
   Current: Python implementation
   Goal: Clean up technical debt, improve performance

   Workflow:
   1. Extract Gherkin from current code (what we just did)
   2. Use Gherkin as specification
   3. Rebuild with autonomous TDD agent
   4. Validate new implementation passes same specs
   5. Deploy with confidence

🎯 SCENARIO 2: Migrate to Go for Performance
   Current: Python ML knowledge tracking
   Goal: 10x faster for large-scale experiments

   Workflow:
   1. Extract Gherkin (business behavior)
   2. Generate Go step definitions
   3. Implement ML knowledge system in Go
   4. Both Python and Go pass same specs
   5. Gradually migrate production traffic

🎯 SCENARIO 3: Polyglot Microservices
   Services:
   - Python: Research experimentation
   - Go: Production inference

   All services share same Gherkin specs for:
   - Experiment tracking
   - Decision logging
   - Knowledge retrieval

   Result: Consistent behavior across languages

🎯 SCENARIO 4: Documentation & Onboarding
   Challenge: New team members struggle to understand ML tracking system

   Solution:
   1. Extract Gherkin (business-readable)
   2. New developers read scenarios
   3. Understand WHAT system does (not HOW)
   4. Can verify behavior with executable tests
    """)

    print(f"\n" + "="*80)
    print("COMPARISON: Simple vs Advanced Extraction")
    print("="*80)

    print(f"""
SIMPLE OAUTH EXAMPLE:
   - 1 class (OAuthClient)
   - 3 methods
   - 4 test scenarios
   - Straightforward logic
   - 100% confidence

ADVANCED ML KNOWLEDGE:
   - {len(code_analysis.classes)} classes
   - {total_methods} methods
   - Complex data models
   - Production patterns
   - Requires domain knowledge

Key Difference:
- Simple: Easy to extract, obvious scenarios
- Advanced: Needs understanding of business domain
- Advanced: Benefits MORE from extraction (complexity → clarity)
    """)

    print(f"\n" + "="*80)
    print("NEXT STEPS")
    print("="*80)

    print(f"""
1. CREATE TESTS for ML knowledge system
   - Write pytest tests capturing current behavior
   - Run extraction again with tests
   - Higher confidence, better scenarios

2. USE EXTRACTED GHERKIN
   - Refactor ML knowledge code with TDD agent
   - Or: Migrate to Go for performance
   - Or: Generate documentation

3. EXTRACT FROM OTHER ACE COMPONENTS
   - Playbook system (bullet_manager.py)
   - Autonomous TDD agent (autonomous_tdd_agent.py)
   - Build complete spec library

4. BUILD SPEC-DRIVEN DEVELOPMENT WORKFLOW
   Extract → Specify → Implement → Validate → Deploy
    """)

    print(f"\n✅ Advanced extraction demo complete!")
    print(f"\nGenerated file: {feature_file}")
    print("\nKey Insight: Real codebases benefit MORE from extraction")
    print("Complex logic → Clear specs = Safer refactoring & migration")


if __name__ == "__main__":
    demonstrate_real_codebase_extraction()
