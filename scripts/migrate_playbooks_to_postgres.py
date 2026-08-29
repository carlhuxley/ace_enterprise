"""
Migrate existing JSON playbooks to PostgreSQL with embeddings.

Reads playbooks from data/playbooks/ and data/playbooks_untracked/,
generates embeddings for all bullets, and stores them in PostgreSQL.
"""

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent / "src"))

from storage.repository import PlaybookRepository
from utils.embedding import get_embedding_service

print("\n" + "="*80)
print("MIGRATING PLAYBOOKS TO POSTGRESQL")
print("="*80)

# Connect to PostgreSQL
print("\n1. Connecting to PostgreSQL...")
try:
    repo = PlaybookRepository()
    print("   ✓ Connected to PostgreSQL")
except Exception as e:
    print(f"   ✗ Connection failed: {e}")
    print("\n   Start PostgreSQL: nix-shell --run start-postgres")
    sys.exit(1)

# Initialize embedding service
print("\n2. Initializing embedding service...")
embedder = get_embedding_service()
print("   ✓ Embedding service ready")

# Find all playbook files
print("\n3. Scanning for playbook files...")
playbook_dirs = [
    Path("data/playbooks"),
    # Uncomment to include untracked playbooks:
    # Path("data/playbooks_untracked"),
]

playbook_files = []
for dir_path in playbook_dirs:
    if dir_path.exists():
        playbook_files.extend(sorted(dir_path.glob("pb_*.json")))

print(f"   ✓ Found {len(playbook_files)} playbook files")

# Track statistics
stats = {
    "total_playbooks": 0,
    "total_bullets": 0,
    "skipped_playbooks": 0,
    "errors": []
}

# Process each playbook
print("\n4. Migrating playbooks...")
for idx, playbook_path in enumerate(playbook_files, 1):
    playbook_id = playbook_path.stem  # e.g., "pb_20251129_860"

    print(f"\n   [{idx}/{len(playbook_files)}] Processing {playbook_id}...")

    try:
        # Load playbook JSON
        with open(playbook_path, 'r') as f:
            playbook_data = json.load(f)

        # Check if playbook is essentially empty (some are just metadata)
        total_bullets = playbook_data.get("metadata", {}).get("total_bullets", 0)
        if total_bullets == 0:
            print(f"       ⊘ Skipping (empty playbook)")
            stats["skipped_playbooks"] += 1
            continue

        # Extract metadata
        metadata = playbook_data.get("metadata", {})
        version = playbook_data.get("version", "0.1.0")
        domain = metadata.get("domain", "unknown")
        base_model = metadata.get("base_model", "unknown")

        # Create or update playbook in PostgreSQL
        playbook = repo.get_or_create_playbook(
            playbook_id=playbook_id,
            version=version,
            domain=domain,
            base_model=base_model
        )

        # Collect all bullets from all sections
        all_bullets = []
        sections = playbook_data.get("sections", {})

        for section_name, bullets in sections.items():
            if not bullets:  # Skip empty sections
                continue

            for bullet in bullets:
                # Use the existing bullet ID
                bullet_id = bullet.get("id", f"{playbook_id}_{len(all_bullets)}")

                all_bullets.append({
                    "bullet_id": bullet_id,
                    "content": bullet.get("content", ""),
                    "section": section_name,
                    "tags": bullet.get("tags", []),
                    "helpful_count": bullet.get("helpful_count", 0),
                    "harmful_count": bullet.get("harmful_count", 0),
                })

        if not all_bullets:
            print(f"       ⊘ Skipping (no bullets found)")
            stats["skipped_playbooks"] += 1
            continue

        # Store bullets in bulk (automatically generates embeddings)
        try:
            count = repo.bulk_add_bullets(
                playbook_id=playbook_id,
                bullets=all_bullets
            )
            print(f"       ✓ Stored {count} bullets with embeddings")
            stats["total_playbooks"] += 1
            stats["total_bullets"] += count
        except Exception as e:
            # If we get a duplicate key error, the playbook was already migrated
            if "duplicate key" in str(e).lower():
                print(f"       ⊘ Already exists (skipping)")
                stats["skipped_playbooks"] += 1
            else:
                print(f"       ✗ Error storing bullets: {e}")
                stats["errors"].append(f"{playbook_id}: {e}")

    except Exception as e:
        print(f"       ✗ Error processing: {e}")
        stats["errors"].append(f"{playbook_id}: {e}")
        continue

# Display final statistics
print("\n" + "="*80)
print("MIGRATION COMPLETE")
print("="*80)

db_stats = repo.get_stats()

print("\n📊 Migration Summary:")
print(f"   • Processed {len(playbook_files)} playbook files")
print(f"   • Migrated {stats['total_playbooks']} playbooks")
print(f"   • Stored {stats['total_bullets']} bullets with embeddings")
print(f"   • Skipped {stats['skipped_playbooks']} (empty or duplicates)")
if stats["errors"]:
    print(f"   • Errors: {len(stats['errors'])}")

print("\n📊 Database Statistics:")
print(f"   • Total playbooks: {db_stats['total_playbooks']}")
print(f"   • Total bullets: {db_stats['total_bullets']}")
print(f"   • Bullets with embeddings: {db_stats['bullets_with_embeddings']}")
print(f"   • Embedding coverage: {db_stats['embedding_coverage']:.1%}")

if stats["errors"]:
    print("\n⚠️  Errors encountered:")
    for error in stats["errors"][:10]:  # Show first 10 errors
        print(f"   • {error}")
    if len(stats["errors"]) > 10:
        print(f"   ... and {len(stats["errors"]) - 10} more")

print()
