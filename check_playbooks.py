#!/usr/bin/env python3
"""
Check TDD Playbooks

See what knowledge the TDD Agent has accumulated.
"""
import sys
sys.path.insert(0, "/home/ch_dev/ace_enterprise")

from src.playbook.manager import PlaybookManager

print("=" * 80)
print("  TDD PLAYBOOK INSPECTION")
print("=" * 80)

manager = PlaybookManager()

# Check in-memory playbooks
if not manager._playbooks:
    print("\n❌ No playbooks in memory (they weren't persisted)")
    print("   Note: Current implementation uses in-memory storage only")
    print("   Playbooks are lost when process ends")
else:
    print(f"\n✓ Found {len(manager._playbooks)} playbook(s) in memory\n")

    for pb_id, playbook in manager._playbooks.items():
        print(f"📚 Playbook: {pb_id}")
        print(f"   Domain: {playbook.metadata.domain}")
        print(f"   Version: {playbook.version}")
        print(f"   Total Bullets: {playbook.metadata.total_bullets}")

        if playbook.metadata.total_bullets > 0:
            print(f"\n   Knowledge accumulated:")

            for section_name, bullets in playbook.sections.items():
                if bullets:
                    print(f"\n   [{section_name}]")
                    for bullet in bullets:
                        print(f"      • {bullet.id}: {bullet.content[:80]}...")
                        if bullet.tags:
                            print(f"        Tags: {', '.join(bullet.tags)}")
                        print(f"        Helpful: {bullet.helpful_count}, Harmful: {bullet.harmful_count}")
        else:
            print("   (Empty playbook - no learning occurred)")

        print()

print("=" * 80)
print("  IMPLICATIONS")
print("=" * 80)
print("""
Current Status:
- Playbooks are stored in MEMORY only
- They are lost when the Python process ends
- Each demo run creates a new playbook

To persist learning across sessions, we need to:
1. Add database storage (SQLite/Postgres)
2. Or add JSON file persistence
3. Load previous playbooks when starting

This is why our demo agents showed 0 bullets learned -
they worked, but the knowledge wasn't persisted!
""")
