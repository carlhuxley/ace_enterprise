#!/usr/bin/env python3
"""
Test Embedding Quality

Tests semantic search retrieval quality with embeddings.
"""
import sys
sys.path.insert(0, "/home/ch_dev/ace_enterprise")

from src.config.settings import settings
from src.playbook.manager import PlaybookManager
from src.playbook.retrieval import BulletRetriever
from src.utils.embedding import get_embedding_service


def test_retrieval_quality():
    """Test retrieval with embeddings."""

    print("\n" + "=" * 70)
    print("  EMBEDDING-BASED RETRIEVAL TEST")
    print("=" * 70)

    # Initialize
    pm = PlaybookManager()
    retriever = BulletRetriever()
    embedding_service = get_embedding_service()

    print(f"\n✓ Loaded {len(pm._playbooks)} playbook(s)")
    print(f"✓ Embedding dimension: {embedding_service.get_embedding_dimension()}")
    print(f"✓ Retrieval top-k: {retriever.top_k}")
    print(f"✓ Similarity threshold: {retriever.similarity_threshold}")

    # Get TDD playbooks
    tdd_playbooks = pm.get_playbooks_by_domain("tdd_python")
    if not tdd_playbooks:
        print("\n❌ No TDD playbooks found!")
        return

    print(f"\n📚 Found {len(tdd_playbooks)} TDD playbook(s)")
    for pb in tdd_playbooks:
        print(f"  - {pb.playbook_id} ({pb.metadata.base_model}, {pb.metadata.total_bullets} bullets)")

    # Test queries related to TDD content
    test_queries = [
        "How do I write tests with pytest?",
        "How do I check if a test fails?",
        "What are best practices for test-driven development?",
        "How do I structure test files?",
        "How do I use fixtures in testing?",
    ]

    for query in test_queries:
        print("\n" + "-" * 70)
        print(f"Query: {query}")
        print("-" * 70)

        # Generate query embedding
        query_embedding = embedding_service.embed_text(query)

        # Get all bullets from TDD playbooks
        all_bullets = []
        for pb in tdd_playbooks:
            all_bullets.extend(pm.get_all_bullets(pb.playbook_id))

        print(f"Searching {len(all_bullets)} bullets...")

        # Retrieve
        results = retriever.retrieve(
            query=query,
            bullets=all_bullets,
            query_embedding=query_embedding,
        )

        print(f"\n✓ Retrieved {len(results)} bullet(s)")

        if results:
            print("\nTop 3 matches:")
            for i, (bullet, score) in enumerate(results[:3], 1):
                print(f"\n  {i}. Score: {score:.3f}")
                print(f"     Section: {bullet.section}")
                print(f"     Content: {bullet.content[:100]}...")
                print(f"     Helpful: {bullet.helpful_count}, Harmful: {bullet.harmful_count}")
        else:
            print("  No bullets matched (scores below threshold)")

    # Test cross-model retrieval
    print("\n" + "=" * 70)
    print("  CROSS-MODEL RETRIEVAL TEST")
    print("=" * 70)

    primary_pb = tdd_playbooks[0]
    query = "How do I write tests?"
    query_embedding = embedding_service.embed_text(query)

    print(f"\nPrimary playbook: {primary_pb.playbook_id}")
    print(f"Query: {query}")

    # Model-specific
    primary_bullets = pm.get_all_bullets(primary_pb.playbook_id)
    results_specific = retriever.retrieve(
        query=query,
        bullets=primary_bullets,
        query_embedding=query_embedding,
    )

    print(f"\nModel-Specific: {len(results_specific)} bullets")

    # Cross-model
    secondary_bullets = pm.get_cross_model_bullets(
        primary_playbook_id=primary_pb.playbook_id,
        include_primary=False,
    )

    results_cross = retriever.retrieve_cross_model(
        query=query,
        primary_bullets=primary_bullets,
        secondary_bullets_by_playbook=secondary_bullets,
        query_embedding=query_embedding,
        secondary_weight=settings.cross_model_weight,
    )

    print(f"Cross-Model: {len(results_cross)} bullets")

    if len(results_cross) > len(results_specific):
        print(f"\n✓ Cross-model found {len(results_cross) - len(results_specific)} additional bullets!")
    else:
        print(f"\n  No additional bullets from cross-model retrieval")

    print("\n" + "=" * 70)
    print("  TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        test_retrieval_quality()
    except KeyboardInterrupt:
        print("\n\nTest interrupted")
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
