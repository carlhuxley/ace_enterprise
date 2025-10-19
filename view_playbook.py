#!/usr/bin/env python3
"""
View Playbook - Display playbook contents in a readable format
"""
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, "/home/ch_dev/ace_enterprise")

from src.playbook.manager import PlaybookManager
from src.storage.schemas import PlaybookCreate
from src.utils.llm_client import LLMClient


def view_playbook(playbook_id: str = None):
    """View a playbook's contents."""
    manager = PlaybookManager()

    if not playbook_id:
        # List all playbooks
        if not manager._playbooks:
            print("No playbooks found in memory.")
            print("\nNote: Playbooks are currently stored in memory and cleared when the script exits.")
            print("To persist playbooks, they need to be saved to a database or file.")
            return

        print("Available Playbooks:")
        print("=" * 70)
        for pb_id, playbook in manager._playbooks.items():
            print(f"\nID: {pb_id}")
            print(f"Domain: {playbook.metadata.domain}")
            print(f"Version: {playbook.version}")
            print(f"Bullets: {playbook.metadata.total_bullets}")
            print(f"Created: {playbook.created_at}")
        return

    # Get specific playbook
    playbook = manager.get_playbook(playbook_id)
    if not playbook:
        print(f"Playbook '{playbook_id}' not found.")
        return

    print("=" * 70)
    print(f"  PLAYBOOK: {playbook.playbook_id}")
    print("=" * 70)
    print(f"\nDomain: {playbook.metadata.domain}")
    print(f"Version: {playbook.version}")
    print(f"Base Model: {playbook.metadata.base_model}")
    print(f"Total Bullets: {playbook.metadata.total_bullets}")
    print(f"Created: {playbook.created_at}")
    print(f"Updated: {playbook.updated_at}")

    # Display bullets by section
    for section_name, bullets in playbook.sections.items():
        if bullets:
            print(f"\n{'=' * 70}")
            print(f"  SECTION: {section_name.upper()}")
            print(f"{'=' * 70}")

            for i, bullet in enumerate(bullets, 1):
                print(f"\n[{i}] ID: {bullet.id}")
                print(f"    Tags: {', '.join(bullet.tags)}")
                print(f"    Helpful: {bullet.helpful_count} | Harmful: {bullet.harmful_count}")
                if bullet.last_used:
                    print(f"    Last Used: {bullet.last_used}")
                print(f"\n    Content:")
                # Indent content for readability
                for line in bullet.content.split('\n'):
                    print(f"    {line}")

    # Display statistics
    print(f"\n{'=' * 70}")
    print("  STATISTICS")
    print(f"{'=' * 70}")

    stats = manager.get_statistics(playbook_id)
    for section_name, section_stats in stats['sections'].items():
        if section_stats['bullet_count'] > 0:
            print(f"\n{section_name}:")
            print(f"  Bullets: {section_stats['bullet_count']}")
            print(f"  Helpful: {section_stats['helpful_count']}")
            print(f"  Harmful: {section_stats['harmful_count']}")
            print(f"  Helpful Ratio: {section_stats['helpful_ratio']:.2%}")


def export_playbook_json(playbook_id: str, output_file: str):
    """Export playbook to JSON file."""
    manager = PlaybookManager()
    playbook = manager.get_playbook(playbook_id)

    if not playbook:
        print(f"Playbook '{playbook_id}' not found.")
        return

    # Convert to dict for JSON serialization
    data = {
        "playbook_id": playbook.playbook_id,
        "version": playbook.version,
        "metadata": {
            "domain": playbook.metadata.domain,
            "base_model": playbook.metadata.base_model,
            "total_bullets": playbook.metadata.total_bullets,
            "total_tokens": playbook.metadata.total_tokens,
        },
        "sections": {},
        "created_at": playbook.created_at.isoformat(),
        "updated_at": playbook.updated_at.isoformat(),
    }

    for section_name, bullets in playbook.sections.items():
        data["sections"][section_name] = [
            {
                "id": b.id,
                "content": b.content,
                "tags": b.tags,
                "helpful_count": b.helpful_count,
                "harmful_count": b.harmful_count,
                "created_at": b.created_at.isoformat(),
                "last_used": b.last_used.isoformat() if b.last_used else None,
            }
            for b in bullets
        ]

    # Write to file
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Playbook exported to: {output_file}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "list":
            view_playbook()
        elif command == "view" and len(sys.argv) > 2:
            view_playbook(sys.argv[2])
        elif command == "export" and len(sys.argv) > 3:
            export_playbook_json(sys.argv[2], sys.argv[3])
        else:
            print("Usage:")
            print("  python view_playbook.py list")
            print("  python view_playbook.py view <playbook_id>")
            print("  python view_playbook.py export <playbook_id> <output_file.json>")
    else:
        print("⚠️  Playbooks are stored in memory during demo execution.")
        print("\nTo view playbooks, you need to integrate this script into the demo.")
        print("\nUsage:")
        print("  python view_playbook.py list")
        print("  python view_playbook.py view <playbook_id>")
        print("  python view_playbook.py export <playbook_id> <output_file.json>")
