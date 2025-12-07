"""
Gherkin Extraction + PostgreSQL Demo

Demonstrates the full workflow:
1. Extract Gherkin scenarios from existing code
2. Extract patterns as knowledge bullets
3. Store in PostgreSQL with pgvector embeddings
4. Search for similar patterns using semantic similarity

This is the integration point between reverse engineering and institutional knowledge.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from storage.repository import PlaybookRepository
from utils.embedding import get_embedding_service
from agents.gherkin_extraction_agent import GherkinExtractionAgent, ExtractionResult

print("\n" + "="*80)
print("GHERKIN EXTRACTION → POSTGRESQL STORAGE DEMO")
print("="*80)

# ============================================================================
# Step 1: Extract Gherkin from existing code
# ============================================================================

print("\n1. Extracting Gherkin from existing code...")

# Use the ML experiment knowledge code as example
code_path = Path("src/ml_experiment_knowledge")
test_path = Path("tests/test_experiment_knowledge.py")

if not code_path.exists() or not test_path.exists():
    print(f"   ⚠ Example code not found. Using OAuth example instead...")
    # Create simple OAuth example for demo
    code_path = Path("temp_oauth_example.py")
    test_path = Path("temp_oauth_test.py")

    code_path.write_text("""
class OAuthProvider:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.tokens = {}

    def generate_authorization_url(self, redirect_uri: str) -> str:
        return f"https://oauth.provider.com/authorize?client_id={self.client_id}&redirect_uri={redirect_uri}"

    def exchange_code_for_token(self, code: str) -> dict:
        token = f"access_token_{code}"
        self.tokens[code] = token
        return {"access_token": token, "token_type": "Bearer"}
""")

    test_path.write_text("""
import pytest
from temp_oauth_example import OAuthProvider

def test_generate_authorization_url():
    provider = OAuthProvider("client_123", "secret_456")
    url = provider.generate_authorization_url("http://localhost/callback")
    assert "client_id=client_123" in url
    assert "redirect_uri=http://localhost/callback" in url

def test_exchange_code_for_token():
    provider = OAuthProvider("client_123", "secret_456")
    result = provider.exchange_code_for_token("auth_code_789")
    assert result["access_token"] == "access_token_auth_code_789"
    assert result["token_type"] == "Bearer"
""")

# Extract Gherkin
extractor = GherkinExtractionAgent()
extraction_result: ExtractionResult = extractor.extract_from_codebase(
    code_path=code_path,
    test_path=test_path
)

print(f"   ✓ Extracted {len(extraction_result.feature.scenarios)} scenarios")
print(f"   Confidence: {extraction_result.confidence_score:.0%}")

# ============================================================================
# Step 2: Convert Gherkin scenarios to knowledge bullets
# ============================================================================

print("\n2. Converting scenarios to knowledge patterns...")

def scenario_to_bullets(scenario, domain: str, section: str) -> list[dict]:
    """Convert a Gherkin scenario into knowledge bullets."""
    bullets = []

    # Create a safe scenario identifier
    scenario_id = scenario.name.lower().replace(' ', '_')

    # Pattern 1: Given steps (setup patterns)
    for idx, given in enumerate(scenario.given_steps):
        bullets.append({
            "bullet_id": f"pattern_{domain}_{section}_{scenario_id}_given_{idx}",
            "content": f"Setup pattern: {given}",
            "section": f"{section}/setup",
            "tags": ["gherkin_extracted", domain, "setup", "given"]
        })

    # Pattern 2: When steps (action patterns)
    for idx, when in enumerate(scenario.when_steps):
        bullets.append({
            "bullet_id": f"pattern_{domain}_{section}_{scenario_id}_when_{idx}",
            "content": f"Action pattern: {when}",
            "section": f"{section}/actions",
            "tags": ["gherkin_extracted", domain, "action", "when"]
        })

    # Pattern 3: Then steps (verification patterns)
    for idx, then in enumerate(scenario.then_steps):
        bullets.append({
            "bullet_id": f"pattern_{domain}_{section}_{scenario_id}_then_{idx}",
            "content": f"Verification pattern: {then}",
            "section": f"{section}/verification",
            "tags": ["gherkin_extracted", domain, "verification", "then"]
        })

    # Pattern 4: Full scenario as integrated pattern
    full_pattern = f"""
Scenario: {scenario.name}

Given:
{chr(10).join('  - ' + g for g in scenario.given_steps)}

When:
{chr(10).join('  - ' + w for w in scenario.when_steps)}

Then:
{chr(10).join('  - ' + t for t in scenario.then_steps)}
""".strip()

    bullets.append({
        "bullet_id": f"pattern_{domain}_{section}_scenario_{scenario.name.lower().replace(' ', '_')}",
        "content": full_pattern,
        "section": f"{section}/scenarios",
        "tags": ["gherkin_extracted", domain, "scenario", "integrated_pattern"]
    })

    return bullets

# Convert all scenarios
all_bullets = []
for scenario in extraction_result.feature.scenarios:
    bullets = scenario_to_bullets(
        scenario,
        domain="authentication",  # Infer domain from feature
        section="oauth"
    )
    all_bullets.extend(bullets)

print(f"   ✓ Generated {len(all_bullets)} knowledge bullets")

# ============================================================================
# Step 3: Store in PostgreSQL with embeddings
# ============================================================================

print("\n3. Connecting to PostgreSQL...")

try:
    repo = PlaybookRepository()
    print("   ✓ Connected to PostgreSQL")
except Exception as e:
    print(f"   ✗ Connection failed: {e}")
    print("\n   Start PostgreSQL: docker-compose up -d postgres")
    print("   Run migration: python migrations/run_migration.py")
    sys.exit(1)

print("\n4. Creating playbook for extracted patterns...")

playbook = repo.get_or_create_playbook(
    playbook_id="gherkin_extracted_patterns",
    version="1.0.0",
    domain="authentication",
    base_model="extracted_from_code"
)

print(f"   ✓ Playbook: {playbook.playbook_id}")

print("\n5. Storing patterns with embeddings...")

try:
    # Store all bullets in bulk (automatically generates embeddings)
    count = repo.bulk_add_bullets(
        playbook_id="gherkin_extracted_patterns",
        bullets=all_bullets
    )
    print(f"   ✓ Stored {count} patterns with embeddings")
except Exception as e:
    print(f"   ✗ Error storing patterns: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================================
# Step 6: Semantic search for similar patterns
# ============================================================================

print("\n6. Testing semantic pattern search...")

embedder = get_embedding_service()

# Search queries
queries = [
    "How to handle OAuth authorization URLs?",
    "Exchanging authorization codes for tokens",
    "Validating OAuth responses"
]

for query in queries:
    print(f"\n   Query: \"{query}\"")

    # Generate query embedding
    query_emb = embedder.embed_text(query)

    # Search for similar patterns
    results = repo.similarity_search(
        query_embedding=query_emb,
        playbook_id="gherkin_extracted_patterns",
        top_k=3,
        similarity_threshold=0.3  # Lower threshold to see more results
    )

    if results:
        print(f"   Found {len(results)} similar patterns:")
        for bullet, similarity in results:
            # Truncate long content
            content_preview = bullet.content[:80].replace('\n', ' ')
            print(f"     [{similarity:.3f}] {content_preview}...")
    else:
        print("   No patterns found above threshold")

# ============================================================================
# Step 7: Show repository statistics
# ============================================================================

print("\n7. Repository statistics...")

stats = repo.get_stats()
print(f"   Total playbooks: {stats['total_playbooks']}")
print(f"   Total patterns: {stats['total_bullets']}")
print(f"   Patterns with embeddings: {stats['bullets_with_embeddings']}")
print(f"   Embedding coverage: {stats['embedding_coverage']:.1%}")

# ============================================================================
# Summary
# ============================================================================

print("\n" + "="*80)
print("✅ GHERKIN → POSTGRESQL INTEGRATION COMPLETE")
print("="*80)

print("\n📊 Summary:")
print(f"   • Extracted {len(extraction_result.feature.scenarios)} Gherkin scenarios from code")
print(f"   • Generated {len(all_bullets)} knowledge patterns")
print(f"   • Stored in PostgreSQL with vector embeddings")
print(f"   • Enabled semantic search across patterns")

print("\n🎯 Key Benefits:")
print("   1. Reverse engineer existing code into reusable patterns")
print("   2. Store patterns with semantic embeddings")
print("   3. Search patterns by similarity, not just keywords")
print("   4. Build institutional knowledge from legacy systems")
print("   5. Enable cross-language pattern reuse")

print("\n📚 Next Steps:")
print("   1. Extract patterns from more codebases")
print("   2. Build pattern library across projects")
print("   3. Use patterns for code generation")
print("   4. Cross-language migration workflows")

# Cleanup temp files if created
if code_path.name.startswith("temp_"):
    code_path.unlink()
    test_path.unlink()
    print("\n   (Cleaned up temporary example files)")

print()
