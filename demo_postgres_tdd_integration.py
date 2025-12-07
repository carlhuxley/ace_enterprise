"""
Demo: PostgreSQL Integration with TDD Agent

Shows how to use PostgreSQL-backed playbooks with the autonomous TDD agent.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.playbook.postgres_adapter import PostgresPlaybookAdapter
from src.playbook.postgres_retriever import PostgresBulletRetriever
from src.storage.schemas import PlaybookCreate

print("\n" + "="*80)
print("POSTGRESQL + TDD AGENT INTEGRATION DEMO")
print("="*80)

# Step 1: Initialize PostgreSQL adapter
print("\n1. Initializing PostgreSQL playbook system...")
adapter = PostgresPlaybookAdapter()
print("   ✓ PostgreSQL adapter ready")

# Step 2: Check available playbooks
print("\n2. Checking available playbooks...")
playbook_ids = adapter.list_playbooks()
print(f"   ✓ Found {len(playbook_ids)} playbooks in PostgreSQL")

# Show some playbooks by domain
from sqlalchemy import text
with adapter.repo.get_session() as session:
    results = session.execute(
        text("""
            SELECT domain, COUNT(*) as count
            FROM playbooks
            GROUP BY domain
            ORDER BY count DESC
        """)
    ).fetchall()

    print("\n   Playbooks by domain:")
    for domain, count in results:
        print(f"     - {domain}: {count} playbooks")

# Step 3: Initialize retriever
print("\n3. Initializing PostgreSQL bullet retriever...")
retriever = PostgresBulletRetriever(
    playbook_adapter=adapter,
    top_k=5,
    similarity_threshold=0.3
)
print("   ✓ Retriever ready")

# Step 4: Test retrieval for TDD-related queries
print("\n4. Testing TDD knowledge retrieval...")

tdd_queries = [
    "How to write failing tests in red phase?",
    "Best practices for test-driven development",
    "Avoiding test redundancy",
]

for query in tdd_queries:
    print(f"\n   Query: \"{query}\"")

    # Retrieve relevant bullets
    results = retriever.retrieve(
        query=query,
        playbook_id=None,  # Search all playbooks
        top_k=3,
    )

    if results:
        print(f"   Found {len(results)} relevant bullets:")
        for bullet, score in results:
            content_preview = bullet.content[:80].replace('\n', ' ')
            print(f"     [{score:.3f}] {content_preview}...")
    else:
        print("   No results found")

# Step 5: Show how to integrate with existing agents
print("\n" + "="*80)
print("INTEGRATION WITH ACE AGENTS")
print("="*80)

print("""
To integrate PostgreSQL with your autonomous TDD agent:

1. Update agent initialization:
   ```python
   from src.playbook.postgres_adapter import PostgresPlaybookAdapter
   from src.playbook.postgres_retriever import PostgresBulletRetriever

   # Replace file-based PlaybookManager with PostgreSQL adapter
   adapter = PostgresPlaybookAdapter()
   retriever = PostgresBulletRetriever(adapter)

   # Use in TDD agent
   agent = AutonomousTDDAgent(
       ensemble_learner=ensemble,
       test_reviewer=reviewer,
       project_root=Path("."),
       test_dir=Path("tests"),
       src_dir=Path("src"),
   )

   # Override the bullet retriever
   agent.bullet_retriever = retriever
   agent.playbook_manager = adapter
   ```

2. The agent will now:
   - Query PostgreSQL for relevant TDD knowledge
   - Use pgvector for semantic search (fast!)
   - Store new learnings in PostgreSQL
   - No need to load all playbooks into memory

3. Benefits:
   - Semantic search across ALL your playbooks
   - Faster retrieval (database indexing)
   - Persistent storage with embeddings
   - No file I/O overhead
""")

# Step 6: Show how to create a new TDD playbook
print("\n" + "="*80)
print("CREATING NEW TDD PLAYBOOK (Optional)")
print("="*80)

print("""
To create a new playbook for a TDD session:

```python
# Create playbook
playbook = adapter.create_playbook(
    PlaybookCreate(
        domain="user_authentication_tdd",
        base_model="claude-sonnet-4.5"
    )
)

# Add bullets during TDD cycles
from src.storage.schemas import BulletCreate

adapter.add_bullet(
    playbook_id=playbook.playbook_id,
    bullet_data=BulletCreate(
        content="Always test authentication failure cases first",
        section="strategies_and_hard_rules",
        tags=["tdd", "authentication", "security"],
    )
)
```
""")

print("\n✅ Demo complete! PostgreSQL integration is ready for TDD workflows.")
print()
