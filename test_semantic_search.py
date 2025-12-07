"""
Test semantic search across all migrated playbooks.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from storage.repository import PlaybookRepository
from utils.embedding import get_embedding_service

print("\n" + "="*80)
print("TESTING SEMANTIC SEARCH ACROSS PLAYBOOKS")
print("="*80)

# Connect
repo = PlaybookRepository()
embedder = get_embedding_service()

# Test queries
queries = [
    "How should I handle test redundancy in TDD?",
    "What are best practices for OAuth authentication?",
    "Role-based access control permission checking",
    "Handling logging in unit tests",
]

print("\n📚 Searching across all playbooks...")

for query in queries:
    print(f"\n🔍 Query: \"{query}\"")

    # Generate query embedding
    query_emb = embedder.embed_text(query)

    # Search across ALL playbooks (don't specify playbook_id)
    results = repo.similarity_search(
        query_embedding=query_emb,
        playbook_id=None,  # Search all playbooks
        top_k=5,
        similarity_threshold=0.3
    )

    if results:
        print(f"   Found {len(results)} relevant patterns:")
        for bullet, similarity in results:
            # Get playbook info
            content_preview = bullet.content[:120].replace('\n', ' ')
            print(f"     [{similarity:.3f}] {content_preview}...")
    else:
        print("   No patterns found above threshold")

# Show distribution by domain
print("\n" + "="*80)
print("📊 PLAYBOOK DISTRIBUTION BY DOMAIN")
print("="*80)

from sqlalchemy import text, func
from storage.models import PlaybookModel, BulletModel

with repo.get_session() as session:
    # Get domain distribution
    results = session.execute(
        text("""
            SELECT domain, COUNT(DISTINCT playbooks.id) as playbook_count, COUNT(bullets.id) as bullet_count
            FROM playbooks
            LEFT JOIN bullets ON playbooks.id = bullets.playbook_id
            GROUP BY domain
            ORDER BY bullet_count DESC
        """)
    ).fetchall()

    print("\n   Domain                              Playbooks  Bullets")
    print("   " + "-"*60)
    for domain, playbook_count, bullet_count in results:
        print(f"   {domain:36} {playbook_count:6}    {bullet_count:6}")

print()
