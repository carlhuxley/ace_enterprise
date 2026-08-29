#!/usr/bin/env python3
"""
Generate Embeddings for Existing Playbook Bullets

This script processes all existing playbooks and generates embeddings
for bullets that don't have them yet.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from src.playbook.manager import PlaybookManager
from src.utils.embedding import get_embedding_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def generate_embeddings_for_playbooks():
    """Generate embeddings for all bullets in all playbooks."""

    print("\n" + "=" * 70)
    print("  EMBEDDING GENERATION")
    print("=" * 70)

    # Initialize
    pm = PlaybookManager()
    embedding_service = get_embedding_service()

    print(f"\n✓ Loaded embedding model: {embedding_service.model_name}")
    print(f"  Device: {embedding_service.device}")
    print(f"  Embedding dimension: {embedding_service.get_embedding_dimension()}")

    # Get all playbooks
    playbooks = pm._playbooks
    if not playbooks:
        print("\n⚠️  No playbooks found!")
        return

    print(f"\n📚 Found {len(playbooks)} playbook(s)")

    # Process each playbook
    total_bullets = 0
    total_embedded = 0
    total_skipped = 0

    for playbook_id, playbook in playbooks.items():
        print(f"\n{'─' * 70}")
        print(f"Processing: {playbook_id}")
        print(f"  Domain: {playbook.metadata.domain}")
        print(f"  Model: {playbook.metadata.base_model}")
        print(f"  Total bullets: {playbook.metadata.total_bullets}")

        # Collect bullets without embeddings
        bullets_to_embed = []
        bullet_texts = []

        for section_name, bullets in playbook.sections.items():
            for bullet in bullets:
                total_bullets += 1
                if bullet.embedding is None or len(bullet.embedding) == 0:
                    bullets_to_embed.append(bullet)
                    bullet_texts.append(bullet.content)
                else:
                    total_skipped += 1

        if not bullets_to_embed:
            print(f"  ✓ All bullets already have embeddings")
            continue

        print(f"  Generating embeddings for {len(bullets_to_embed)} bullet(s)...")

        # Batch generate embeddings
        try:
            embeddings = embedding_service.embed_batch(bullet_texts)

            # Assign embeddings to bullets
            for bullet, embedding in zip(bullets_to_embed, embeddings):
                bullet.embedding = embedding
                total_embedded += 1

            print(f"  ✓ Generated {len(embeddings)} embeddings")

            # Save playbook with new embeddings
            pm._save_playbook(playbook_id)
            print(f"  ✓ Saved playbook with embeddings")

        except Exception as e:
            print(f"  ❌ Error: {e}")
            logger.error(f"Failed to generate embeddings for {playbook_id}: {e}")

    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"\nTotal bullets processed: {total_bullets}")
    print(f"  Embeddings generated: {total_embedded}")
    print(f"  Already had embeddings: {total_skipped}")

    if total_embedded > 0:
        print(f"\n✅ Successfully generated {total_embedded} new embeddings!")
        print(f"   All playbooks now have semantic search enabled.")
    else:
        print(f"\n✓ All bullets already had embeddings.")


if __name__ == "__main__":
    try:
        generate_embeddings_for_playbooks()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
