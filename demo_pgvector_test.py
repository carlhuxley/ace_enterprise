"""
Quick test of pgvector setup

Tests:
1. Database connection
2. pgvector extension enabled
3. Vector similarity search works
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from storage.repository import PlaybookRepository
from utils.embedding import get_embedding_service

print("\n" + "="*80)
print("PGVECTOR SETUP TEST")
print("="*80)

print("\n1. Testing database connection...")
try:
    repo = PlaybookRepository()
    print("   ✓ Connected to PostgreSQL")
except Exception as e:
    print(f"   ✗ Connection failed: {e}")
    print("\n   Run PostgreSQL first: docker-compose up -d postgres")
    sys.exit(1)

print("\n2. Testing pgvector extension...")
try:
    from sqlalchemy import text
    with repo.get_session() as session:
        result = session.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
        version = result.scalar()
        if version:
            print(f"   ✓ pgvector enabled (version: {version})")
        else:
            print("   ✗ pgvector not enabled")
            print("   Run: python migrations/run_migration.py")
            sys.exit(1)
except Exception as e:
    print(f"   ✗ Error: {e}")
    sys.exit(1)

print("\n3. Creating test playbook...")
try:
    playbook = repo.get_or_create_playbook(
        playbook_id="test_pgvector",
        version="1.0.0",
        domain="testing",
        base_model="gpt-4"
    )
    print(f"   ✓ Playbook created: {playbook.playbook_id}")
except Exception as e:
    print(f"   ✗ Error: {e}")
    sys.exit(1)

print("\n4. Testing embedding generation...")
try:
    embedder = get_embedding_service()
    test_text = "OAuth authentication with authorization code flow"
    embedding = embedder.embed_text(test_text)
    print(f"   ✓ Generated {len(embedding)}-dimensional embedding")
except Exception as e:
    print(f"   ✗ Error: {e}")
    sys.exit(1)

print("\n5. Adding test bullets with embeddings...")
test_bullets = [
    {
        "bullet_id": "test_001",
        "content": "OAuth uses authorization code flow for third-party access",
        "section": "authentication",
        "tags": ["oauth", "security"],
    },
    {
        "bullet_id": "test_002",
        "content": "JWT tokens provide stateless authentication",
        "section": "authentication",
        "tags": ["jwt", "security"],
    },
    {
        "bullet_id": "test_003",
        "content": "RBAC controls user permissions based on roles",
        "section": "authorization",
        "tags": ["rbac", "security"],
    },
]

try:
    count = repo.bulk_add_bullets("test_pgvector", test_bullets)
    print(f"   ✓ Added {count} bullets with embeddings")
except Exception as e:
    print(f"   ✗ Error: {e}")
    sys.exit(1)

print("\n6. Testing pgvector similarity search...")
try:
    # Search for authentication-related bullets
    query = "How does OAuth authentication work?"
    query_emb = embedder.embed_text(query)

    results = repo.similarity_search(
        query_embedding=query_emb,
        playbook_id="test_pgvector",
        top_k=3
    )

    print(f"   ✓ Found {len(results)} similar bullets")
    print(f"\n   Query: \"{query}\"")
    print("   Results:")
    for bullet, similarity in results:
        print(f"     [{similarity:.3f}] {bullet.content[:60]}...")

except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n7. Repository statistics...")
try:
    stats = repo.get_stats()
    print(f"   Total playbooks: {stats['total_playbooks']}")
    print(f"   Total bullets: {stats['total_bullets']}")
    print(f"   Bullets with embeddings: {stats['bullets_with_embeddings']}")
    print(f"   Embedding coverage: {stats['embedding_coverage']:.1%}")
except Exception as e:
    print(f"   ✗ Error: {e}")

print("\n" + "="*80)
print("✅ PGVECTOR SETUP TEST PASSED")
print("="*80)
print("\nNext steps:")
print("1. Run: python demo_gherkin_extraction_pgvector.py")
print("2. Extract patterns and store in PostgreSQL")
print("3. Use semantic search to find similar patterns")
