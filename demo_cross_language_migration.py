"""
Demo: Cross-Language Migration (Python → Go)

This demonstrates the complete workflow:
1. Extract Gherkin from existing Python code
2. Generate Go step definitions from Gherkin
3. Implement in Go (scaffolded, ready for implementation)
4. Both Python and Go pass same Gherkin specs = behavior preserved
"""

import sys
from pathlib import Path
import logging

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from agents.gherkin_extraction_agent import GherkinExtractionAgent
from agents.go_step_generator import GoStepGenerator

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def demonstrate_cross_language_migration():
    """Demonstrate Python → Go migration."""

    print("\n" + "="*80)
    print("DEMO: Cross-Language Migration (Python → Go)")
    print("="*80)

    # Step 1: Extract Gherkin from Python
    print("\n" + "="*80)
    print("STEP 1: Extract Gherkin from Existing Python Code")
    print("="*80)

    python_code = Path("examples/oauth_legacy/oauth.py")
    python_tests = Path("examples/oauth_legacy/test_oauth.py")

    if not python_code.exists():
        print(f"\n⚠️  Sample Python code not found. Run demo_gherkin_extraction.py first.")
        return

    print(f"\n📂 Source:")
    print(f"   Python code: {python_code}")
    print(f"   Python tests: {python_tests}")

    print(f"\n🔍 Extracting Gherkin...")
    agent = GherkinExtractionAgent()
    result = agent.extract_from_codebase(
        code_path=python_code,
        test_path=python_tests,
        feature_name="OAuth Authentication"
    )

    gherkin_dir = Path("extracted_gherkin")
    feature_file = gherkin_dir / "oauth.feature"

    print(f"   ✓ Extracted {len(result.feature.scenarios)} scenarios")
    print(f"   ✓ Confidence: {result.confidence_score:.0%}")
    print(f"   ✓ Saved to: {feature_file}")

    # Step 2: Generate Go step definitions
    print("\n" + "="*80)
    print("STEP 2: Generate Go Step Definitions")
    print("="*80)

    go_output_dir = Path("go_oauth_implementation")
    go_steps_dir = go_output_dir / "steps"

    print(f"\n📝 Generating Go code...")
    go_generator = GoStepGenerator(package_name="steps")

    # Generate step definitions
    steps_file = go_generator.generate_from_feature_file(
        feature_path=feature_file,
        output_dir=go_steps_dir
    )
    print(f"   ✓ Step definitions: {steps_file}")

    # Generate test runner
    test_file = go_generator.generate_test_runner(
        output_dir=go_steps_dir,
        feature_name="oauth"
    )
    print(f"   ✓ Test runner: {test_file}")

    # Generate go.mod
    mod_file = go_generator.generate_go_mod(
        output_dir=go_output_dir,
        module_name="oauth-go"
    )
    print(f"   ✓ go.mod: {mod_file}")

    # Generate README
    readme_file = go_generator.generate_readme(
        output_dir=go_output_dir,
        feature_name="oauth"
    )
    print(f"   ✓ README: {readme_file}")

    # Copy feature file
    go_features_dir = go_output_dir / "features"
    go_features_dir.mkdir(parents=True, exist_ok=True)
    go_feature_file = go_features_dir / "oauth.feature"

    import shutil
    shutil.copy(feature_file, go_feature_file)
    print(f"   ✓ Feature file: {go_feature_file}")

    # Show generated Go code
    print("\n" + "="*80)
    print("GENERATED GO STEP DEFINITIONS (Sample)")
    print("="*80)

    with open(steps_file, 'r') as f:
        go_code_lines = f.readlines()
        # Show first 40 lines
        print("".join(go_code_lines[:40]))
        print("... (truncated)")

    # Show next steps
    print("\n" + "="*80)
    print("NEXT STEPS: Implement in Go")
    print("="*80)

    print(f"""
1. Navigate to Go implementation:
   cd {go_output_dir}

2. Install dependencies:
   go mod download

3. Implement step functions:
   Edit steps/oauth_steps.go

   Example implementation for one step:

   func (ctx *OauthContext) aOAuthClientWith(...) error {{
       ctx.client = &OAuthClient{{
           ClientID:     clientID,
           ClientSecret: clientSecret,
           AuthURL:      authURL,
       }}
       return nil
   }}

4. Run tests:
   go test -v

5. Verify behavior matches Python:

   # Both should pass same Gherkin

   Python:
   cd {python_code.parent}
   behave ../../{feature_file}

   Go:
   cd {go_output_dir}
   go test -v

   ✓ If both pass = behavior preserved across languages!
""")

    print("\n" + "="*80)
    print("CROSS-LANGUAGE MIGRATION BENEFITS")
    print("="*80)

    print("""
✅ BEHAVIOR PRESERVATION
   - Gherkin specs define exact behavior
   - Both implementations verified against same tests
   - No guesswork about what code should do

✅ SAFE MIGRATION
   - Incremental: Migrate one feature at a time
   - Testable: Verify each step
   - Reversible: Can always fall back to Python

✅ POLYGLOT SYSTEMS
   - Microservices in different languages
   - All share same behavioral specs
   - Consistent behavior guaranteed

✅ PERFORMANCE OPTIMIZATION
   - Reimplement bottlenecks in Go/Rust
   - Same behavior, better performance
   - Measured improvement, not guessed

✅ TEAM COLLABORATION
   - Backend (Go) and Frontend (TS) share specs
   - QA validates across all services
   - Business can read/verify Gherkin
    """)

    print("\n" + "="*80)
    print("FILES CREATED")
    print("="*80)

    print(f"""
Python (Original):
  {python_code}
  {python_tests}

Gherkin (Language-Agnostic):
  {feature_file}
  {gherkin_dir}/steps/oauth_steps.py

Go (New Implementation):
  {go_feature_file}
  {steps_file}
  {test_file}
  {mod_file}
  {readme_file}
    """)

    print("\n✅ Cross-language migration demo complete!")
    print("\nThe Gherkin specs are now the source of truth.")
    print("Implement in any language, verify against same specs.")


if __name__ == "__main__":
    demonstrate_cross_language_migration()
