"""
Demo: Extract Gherkin from Existing Code

This demonstrates reverse-engineering Gherkin scenarios from existing Python code and tests.
The extracted Gherkin can then be used for:
- Safe refactoring
- Cross-language migration (Python → Go)
- Documentation generation
- Legacy system understanding
"""

import sys
from pathlib import Path
import logging

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from agents.gherkin_extraction_agent import GherkinExtractionAgent

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def create_sample_code():
    """Create sample OAuth code to extract from."""

    sample_dir = Path(__file__).parent / "examples" / "oauth_legacy"
    sample_dir.mkdir(parents=True, exist_ok=True)

    # Create sample OAuth implementation
    oauth_code = '''"""
Legacy OAuth Client Implementation

This is an existing codebase that we want to refactor or migrate to another language.
"""

from urllib.parse import urlencode
from typing import Optional


class OAuthClient:
    """OAuth 2.0 client for authorization code flow."""

    def __init__(self, client_id: str, client_secret: str, auth_url: str):
        """
        Initialize OAuth client.

        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret
            auth_url: Authorization server URL
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.auth_url = auth_url

    def generate_authorization_url(
        self,
        redirect_uri: str,
        scope: str,
        state: Optional[str] = None
    ) -> str:
        """
        Generate OAuth authorization URL.

        Args:
            redirect_uri: Callback URL for your application
            scope: Requested permissions
            state: CSRF protection token

        Returns:
            Authorization URL for user to visit
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "response_type": "code"
        }

        if state:
            params["state"] = state

        return f"{self.auth_url}?{urlencode(params)}"

    def exchange_code_for_token(
        self,
        authorization_code: str,
        redirect_uri: str
    ) -> dict:
        """
        Exchange authorization code for access token.

        Args:
            authorization_code: Code received from authorization
            redirect_uri: Same redirect URI used in authorization

        Returns:
            Token response with access_token, token_type, expires_in
        """
        # Simplified: In reality would make HTTP request
        return {
            "access_token": "mock_access_token",
            "token_type": "Bearer",
            "expires_in": 3600
        }
'''

    oauth_file = sample_dir / "oauth.py"
    oauth_file.write_text(oauth_code)

    # Create sample tests
    test_code = '''"""
Tests for OAuth Client

These existing tests capture the behavior we want to preserve.
"""

import pytest
from oauth import OAuthClient


class TestOAuthClient:
    """Test suite for OAuth client."""

    def test_create_oauth_client(self):
        """Test OAuth client can be created with credentials."""
        client = OAuthClient(
            client_id="test_client_id",
            client_secret="test_secret",
            auth_url="https://auth.example.com/oauth"
        )

        assert client.client_id == "test_client_id"
        assert client.client_secret == "test_secret"
        assert client.auth_url == "https://auth.example.com/oauth"

    def test_generate_authorization_url_with_required_params(self):
        """Test generating authorization URL with required parameters."""
        client = OAuthClient(
            client_id="app_123",
            client_secret="secret",
            auth_url="https://auth.example.com/oauth"
        )

        url = client.generate_authorization_url(
            redirect_uri="https://myapp.com/callback",
            scope="read write"
        )

        assert url.startswith("https://auth.example.com/oauth?")
        assert "client_id=app_123" in url
        assert "redirect_uri=https%3A%2F%2Fmyapp.com%2Fcallback" in url
        assert "scope=read+write" in url
        assert "response_type=code" in url

    def test_generate_authorization_url_with_state(self):
        """Test generating authorization URL with CSRF state parameter."""
        client = OAuthClient(
            client_id="app_123",
            client_secret="secret",
            auth_url="https://auth.example.com/oauth"
        )

        url = client.generate_authorization_url(
            redirect_uri="https://myapp.com/callback",
            scope="read",
            state="random_csrf_token"
        )

        assert "state=random_csrf_token" in url

    def test_exchange_code_for_token(self):
        """Test exchanging authorization code for access token."""
        client = OAuthClient(
            client_id="app_123",
            client_secret="secret",
            auth_url="https://auth.example.com/oauth"
        )

        token_response = client.exchange_code_for_token(
            authorization_code="auth_code_xyz",
            redirect_uri="https://myapp.com/callback"
        )

        assert token_response["access_token"] is not None
        assert token_response["token_type"] == "Bearer"
        assert token_response["expires_in"] > 0
'''

    test_file = sample_dir / "test_oauth.py"
    test_file.write_text(test_code)

    logger.info(f"Created sample code in: {sample_dir}")
    return oauth_file, test_file


def demonstrate_extraction():
    """Demonstrate Gherkin extraction."""

    print("\n" + "="*80)
    print("DEMO: Extract Gherkin from Existing Python Code")
    print("="*80)

    # Create sample code
    print("\n📁 Step 1: Creating sample OAuth implementation and tests...")
    code_file, test_file = create_sample_code()
    print(f"   ✓ Code: {code_file}")
    print(f"   ✓ Tests: {test_file}")

    # Initialize extraction agent
    print("\n🤖 Step 2: Initializing Gherkin Extraction Agent...")
    agent = GherkinExtractionAgent()
    print("   ✓ Agent ready")

    # Extract Gherkin
    print("\n🔍 Step 3: Analyzing code and tests...")
    result = agent.extract_from_codebase(
        code_path=code_file,
        test_path=test_file,
        feature_name="OAuth Authentication"
    )

    print(f"   ✓ Found {len(result.code_analysis.classes)} classes")
    print(f"   ✓ Found {len(result.test_analysis.scenarios)} test scenarios")
    print(f"   ✓ Generated {len(result.feature.scenarios)} Gherkin scenarios")
    print(f"   ✓ Confidence score: {result.confidence_score:.2%}")

    if result.warnings:
        print("\n⚠️  Warnings:")
        for warning in result.warnings:
            print(f"   - {warning}")

    # Write Gherkin feature file
    print("\n📝 Step 4: Writing Gherkin feature file...")
    output_dir = Path(__file__).parent / "extracted_gherkin"
    feature_file = output_dir / "oauth.feature"
    agent.write_gherkin_file(result.feature, feature_file)
    print(f"   ✓ Written to: {feature_file}")

    # Write step definitions
    print("\n📝 Step 5: Writing step definitions...")
    steps_dir = output_dir / "steps"
    steps_file = steps_dir / "oauth_steps.py"
    agent.write_step_definitions(
        result.step_definitions,
        result.code_analysis,
        steps_file
    )
    print(f"   ✓ Written to: {steps_file}")

    # Display extracted Gherkin
    print("\n" + "="*80)
    print("EXTRACTED GHERKIN FEATURE")
    print("="*80)
    with open(feature_file, 'r') as f:
        print(f.read())

    # Show what can be done next
    print("\n" + "="*80)
    print("WHAT YOU CAN DO NOW")
    print("="*80)
    print("""
1. VALIDATE THE GHERKIN
   Run the extracted Gherkin against the original Python code:

   cd examples/oauth_legacy
   behave ../../extracted_gherkin/oauth.feature

   ✓ Should pass 100% (proves Gherkin captures actual behavior)

2. SAFE REFACTORING
   Use the Gherkin as specification and rebuild with TDD agent:

   python demo_oauth_tdd.py --gherkin extracted_gherkin/oauth.feature

   ✓ Clean implementation, same behavior

3. CROSS-LANGUAGE MIGRATION
   Implement in Go:

   # Generate Go step definitions
   python generate_steps_go.py extracted_gherkin/oauth.feature

   # Implement in Go
   cd go_implementation
   cucumber features/oauth.feature

   ✓ Both Python and Go pass same Gherkin = behavior preserved

4. DOCUMENTATION
   The Gherkin serves as executable, business-readable documentation:

   - Product team can read and verify behavior
   - New developers understand what system does
   - QA can validate across all implementations
    """)

    print("\n" + "="*80)
    print("ANALYSIS DETAILS")
    print("="*80)

    print(f"\nCode Structure:")
    for cls in result.code_analysis.classes:
        print(f"  Class: {cls.name}")
        for method in cls.methods:
            params = ", ".join(p[0] for p in method.parameters)
            print(f"    - {method.name}({params}) -> {method.return_type}")

    print(f"\nTest Scenarios Analyzed:")
    for scenario in result.test_analysis.scenarios:
        print(f"  {scenario.test_name}")
        print(f"    Setup: {len(scenario.setup_actions)} actions")
        print(f"    Action: {scenario.action or 'None'}")
        print(f"    Assertions: {len(scenario.assertions)}")

    print(f"\nGenerated Gherkin Scenarios:")
    for scenario in result.feature.scenarios:
        print(f"  {scenario.name}")
        print(f"    Given: {len(scenario.given_steps)} steps")
        print(f"    When: {len(scenario.when_steps)} steps")
        print(f"    Then: {len(scenario.then_steps)} steps")

    print("\n✅ Demo complete!")
    print(f"\nExtracted files:")
    print(f"  - {feature_file}")
    print(f"  - {steps_file}")


if __name__ == "__main__":
    demonstrate_extraction()
