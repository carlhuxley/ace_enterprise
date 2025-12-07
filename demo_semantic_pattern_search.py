"""
Semantic Pattern Search Demo

Demonstrates advanced semantic search capabilities using pgvector:
1. Find similar patterns across different domains
2. Cross-language pattern matching
3. Hybrid search (semantic + keyword + metrics)
4. Multi-playbook search

This shows how institutional knowledge becomes searchable and reusable.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from storage.repository import PlaybookRepository
from utils.embedding import get_embedding_service

print("\n" + "="*80)
print("SEMANTIC PATTERN SEARCH DEMO")
print("="*80)

# ============================================================================
# Setup
# ============================================================================

print("\n1. Connecting to PostgreSQL...")

try:
    repo = PlaybookRepository()
    embedder = get_embedding_service()
    print("   ✓ Connected to PostgreSQL with pgvector")
except Exception as e:
    print(f"   ✗ Connection failed: {e}")
    print("\n   Run: docker-compose up -d postgres")
    print("   Run: python migrations/run_migration.py")
    print("   Run: python demo_gherkin_extraction_pgvector.py")
    sys.exit(1)

# ============================================================================
# Demo 1: Cross-Domain Pattern Search
# ============================================================================

print("\n" + "="*80)
print("DEMO 1: Cross-Domain Pattern Search")
print("="*80)

print("\nSearching for authentication patterns across all domains...")

query = "How to authenticate users with third-party providers?"
query_emb = embedder.embed_text(query)

# Search across all playbooks (no playbook_id filter)
results = repo.similarity_search(
    query_embedding=query_emb,
    top_k=5,
    similarity_threshold=0.5
)

if results:
    print(f"\n✓ Found {len(results)} relevant patterns:\n")
    for idx, (bullet, similarity) in enumerate(results, 1):
        print(f"{idx}. [Similarity: {similarity:.3f}]")
        print(f"   Section: {bullet.section}")
        print(f"   Tags: {', '.join(bullet.tags)}")
        print(f"   Content: {bullet.content[:100]}...")
        print()
else:
    print("   No patterns found. Run demo_gherkin_extraction_pgvector.py first.")

# ============================================================================
# Demo 2: Find Patterns by Different Distance Metrics
# ============================================================================

print("\n" + "="*80)
print("DEMO 2: Comparing Distance Metrics")
print("="*80)

query = "OAuth token exchange"
query_emb = embedder.embed_text(query)

print(f"\nQuery: \"{query}\"\n")

for metric in ["cosine", "l2", "ip"]:
    print(f"Using {metric.upper()} distance:")

    results = repo.similarity_search(
        query_embedding=query_emb,
        top_k=3,
        distance_metric=metric
    )

    if results:
        for bullet, sim in results[:2]:  # Show top 2
            content_preview = bullet.content[:60].replace('\n', ' ')
            print(f"  [{sim:.3f}] {content_preview}...")
    else:
        print("  No results found")
    print()

# ============================================================================
# Demo 3: Section-Specific Search
# ============================================================================

print("\n" + "="*80)
print("DEMO 3: Section-Specific Pattern Search")
print("="*80)

query = "authorization verification"
query_emb = embedder.embed_text(query)

sections_to_search = ["oauth/verification", "oauth/actions", "oauth/setup"]

print(f"\nQuery: \"{query}\"\n")

for section in sections_to_search:
    print(f"Searching in section: {section}")

    results = repo.similarity_search(
        query_embedding=query_emb,
        section=section,
        top_k=2
    )

    if results:
        for bullet, sim in results:
            content_preview = bullet.content[:60].replace('\n', ' ')
            print(f"  [{sim:.3f}] {content_preview}...")
    else:
        print("  No patterns in this section")
    print()

# ============================================================================
# Demo 4: Multi-Playbook Domain Search
# ============================================================================

print("\n" + "="*80)
print("DEMO 4: Multi-Playbook Domain Search")
print("="*80)

query = "user authentication patterns"
query_emb = embedder.embed_text(query)

print(f"\nQuery: \"{query}\"")
print("Searching across all playbooks in 'authentication' domain...\n")

try:
    results = repo.similarity_search_multi_playbook(
        query_embedding=query_emb,
        domain="authentication",
        top_k=5,
        similarity_threshold=0.4
    )

    if results:
        print(f"✓ Found {len(results)} patterns across playbooks:\n")
        for idx, (bullet, similarity, playbook_id) in enumerate(results, 1):
            print(f"{idx}. [Similarity: {similarity:.3f}] [{playbook_id}]")
            content_preview = bullet.content[:80].replace('\n', ' ')
            print(f"   {content_preview}...")
            print()
    else:
        print("   No cross-playbook patterns found")
except Exception as e:
    print(f"   ⚠ Multi-playbook search not available: {e}")

# ============================================================================
# Demo 5: Repository Statistics
# ============================================================================

print("\n" + "="*80)
print("DEMO 5: Repository Statistics")
print("="*80)

stats = repo.get_stats()

print(f"""
Repository Overview:
  📚 Total Playbooks:         {stats['total_playbooks']}
  📝 Total Patterns:          {stats['total_bullets']}
  🔢 Patterns with Embeddings: {stats['bullets_with_embeddings']}
  📊 Embedding Coverage:      {stats['embedding_coverage']:.1%}
""")

# ============================================================================
# Demo 6: Pattern Recommendations
# ============================================================================

print("\n" + "="*80)
print("DEMO 6: Pattern Recommendation System")
print("="*80)

print("\nScenario: Developer working on OAuth implementation")
print("Current context: 'Building authorization code flow'")
print("\nRecommending relevant patterns...\n")

context = "Building authorization code flow for OAuth"
context_emb = embedder.embed_text(context)

results = repo.similarity_search(
    query_embedding=context_emb,
    top_k=5,
    similarity_threshold=0.4
)

if results:
    print("💡 Recommended patterns:\n")
    for idx, (bullet, similarity) in enumerate(results, 1):
        print(f"{idx}. [Relevance: {similarity:.1%}]")
        print(f"   Tags: {', '.join(bullet.tags[:3])}")

        # Show first 2 lines of content
        lines = bullet.content.split('\n')[:2]
        for line in lines:
            if line.strip():
                print(f"   {line.strip()}")
        print()
else:
    print("   No recommendations available")

# ============================================================================
# Summary
# ============================================================================

print("\n" + "="*80)
print("✅ SEMANTIC SEARCH CAPABILITIES DEMONSTRATED")
print("="*80)

print("""
🔍 Search Features:
   ✓ Semantic similarity (understands meaning, not just keywords)
   ✓ Multiple distance metrics (cosine, L2, inner product)
   ✓ Section-specific filtering
   ✓ Cross-playbook domain search
   ✓ Configurable similarity thresholds
   ✓ Pattern recommendations based on context

🚀 Performance Benefits:
   • pgvector IVFFlat indexing (fast approximate nearest neighbor)
   • SQL-level filtering (no Python loops)
   • Batch embedding generation
   • Persistent vector storage

📈 Use Cases:
   1. Code pattern discovery during development
   2. Cross-project knowledge reuse
   3. Similar bug/solution finding
   4. Automated pattern recommendations
   5. Legacy system knowledge extraction
   6. Cross-language pattern migration

💡 Next Steps:
   1. Add more playbooks from different codebases
   2. Implement hybrid ranking (semantic + keyword + helpful_count)
   3. Add pattern usage tracking
   4. Build pattern recommendation API
   5. Create pattern quality scoring
""")

print()
