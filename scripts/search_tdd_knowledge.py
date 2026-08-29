"""
Search and display TDD-specific knowledge from the database.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from storage.repository import PlaybookRepository
from utils.embedding import get_embedding_service
from sqlalchemy import text

print("\n" + "="*80)
print("TDD KNOWLEDGE IN DATABASE")
print("="*80)

repo = PlaybookRepository()
embedder = get_embedding_service()

# Get TDD content breakdown
print("\n📊 TDD Content Distribution:")
with repo.get_session() as session:
    results = session.execute(
        text("""
            SELECT
                section,
                COUNT(*) as count
            FROM bullets
            WHERE content ILIKE '%TDD%' OR tags::text ILIKE '%tdd%'
            GROUP BY section
            ORDER BY count DESC
        """)
    ).fetchall()

    print("\n   Section                          Count")
    print("   " + "-"*50)
    total = 0
    for section, count in results:
        print(f"   {section:30} {count:6}")
        total += count
    print("   " + "-"*50)
    print(f"   {'TOTAL':30} {total:6}")

# Semantic search for TDD topics
print("\n" + "="*80)
print("🔍 TDD SEMANTIC SEARCH EXAMPLES")
print("="*80)

queries = [
    "What are TDD anti-patterns to avoid?",
    "How to implement red-green-refactor cycle?",
    "TDD best practices for test organization",
    "Handling test redundancy in TDD",
    "When to write integration tests vs unit tests",
]

for query in queries:
    print(f"\n📍 {query}")

    query_emb = embedder.embed_text(query)
    results = repo.similarity_search(
        query_embedding=query_emb,
        playbook_id=None,
        top_k=3,
        similarity_threshold=0.35
    )

    if results:
        for bullet, similarity in results[:2]:  # Show top 2
            content = bullet.content.replace('\n', ' ')[:150]
            print(f"   [{similarity:.3f}] {content}...")
    else:
        print("   (No high-confidence matches)")

# Show some example TDD anti-patterns
print("\n" + "="*80)
print("📚 SAMPLE TDD ANTI-PATTERNS FROM DATABASE")
print("="*80)

with repo.get_session() as session:
    results = session.execute(
        text("""
            SELECT content, section
            FROM bullets
            WHERE content ILIKE '%ANTI-PATTERN%' AND content ILIKE '%TDD%'
            LIMIT 5
        """)
    ).fetchall()

    for idx, (content, section) in enumerate(results, 1):
        print(f"\n{idx}. [{section}]")
        # Extract just the title
        lines = content.split('\n')
        title = lines[0] if lines else content[:100]
        print(f"   {title}")

print("\n" + "="*80)
print("💡 TIP: Query your TDD knowledge with:")
print("="*80)
print("""
from storage.repository import PlaybookRepository
from utils.embedding import get_embedding_service

repo = PlaybookRepository()
embedder = get_embedding_service()

query_emb = embedder.embed_text("your TDD question")
results = repo.similarity_search(query_emb, top_k=5)

for bullet, score in results:
    print(f"[{score:.3f}] {bullet.content}")
""")
print()
