"""CLI helper for adding knowledge with audit trail.

This module provides functions for the 'ace learn' CLI command:
- learn_with_audit: Add a single piece of knowledge
- learn_from_file: Batch import from markdown files

The audit events include full content for human visibility in the
audit dashboard.
"""
from pathlib import Path

from src.audit.local_client import LocalAuditClient
from src.audit.schemas import AuditEventType
from src.playbook.manager import PlaybookManager
from src.playbook.markdown_importer import MarkdownImporter
from src.storage.schemas import Bullet, BulletCreate


def learn_with_audit(
    manager: PlaybookManager,
    playbook_id: str,
    content: str,
    section: str,
    tags: list[str],
    audit_client: LocalAuditClient,
    actor_id: str = "cli-user",
) -> Bullet:
    """Add knowledge to playbook with audit trail.

    This is the primary function for CLI-based knowledge addition.
    It wraps PlaybookManager.add_bullet and emits an audit event.

    Args:
        manager: PlaybookManager instance
        playbook_id: Target playbook ID
        content: Knowledge content to add
        section: Playbook section (e.g., 'strategies_and_hard_rules')
        tags: Tags for categorization
        audit_client: Audit client for event emission
        actor_id: Human actor identifier (default: 'cli-user')

    Returns:
        Created Bullet instance
    """
    # Create bullet via manager
    bullet_data = BulletCreate(
        content=content,
        section=section,
        tags=tags,
        created_by_model=None,  # Human-created
        model_provider=None,
        license_type=None,
    )

    bullet = manager.add_bullet(playbook_id, bullet_data)

    # Emit audit event with full content for human visibility
    audit_client.emit_simple(
        event_type=AuditEventType.KNOWLEDGE_ADDED,
        actor_id=actor_id,
        actor_type="human",
        payload={
            "bullet_id": bullet.id,
            "content": content,
            "section": section,
            "tags": tags,
            "source": "cli",
            "playbook_id": playbook_id,
        },
        playbook_id=playbook_id,
    )

    return bullet


def learn_from_file(
    manager: PlaybookManager,
    playbook_id: str,
    file_path: Path | str,
    bullet_type: str = "pattern",
    tags: list[str] | None = None,
    audit_client: LocalAuditClient | None = None,
    actor_id: str = "cli-user",
) -> list[Bullet]:
    """Batch import knowledge from a markdown file.

    Parses the markdown file and creates bullets from each ## section.
    Supports YAML frontmatter for tags and type metadata.

    Args:
        manager: PlaybookManager instance
        playbook_id: Target playbook ID
        file_path: Path to markdown file
        bullet_type: Default bullet type (decision, pattern, snippet, etc.)
        tags: Additional tags to apply to all bullets
        audit_client: Optional audit client for event emission
        actor_id: Human actor identifier

    Returns:
        List of created Bullet instances
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Parse markdown file
    importer = MarkdownImporter()
    parsed_bullets = importer.parse_file(path)

    created_bullets = []
    additional_tags = tags or []

    for parsed in parsed_bullets:
        # Merge tags from file and CLI
        bullet_tags = list(set(parsed.get('tags', []) + additional_tags))

        # Use type from frontmatter if set, otherwise use CLI argument
        section = parsed.get('type', bullet_type)

        # Build content with title
        content = f"**{parsed['title']}**\n\n{parsed['content']}"

        # Create bullet
        bullet_data = BulletCreate(
            content=content,
            section=section,
            tags=bullet_tags,
            created_by_model=None,  # Human-created (imported from file)
            model_provider=None,
            license_type=None,
        )

        bullet = manager.add_bullet(playbook_id, bullet_data)
        created_bullets.append(bullet)

        # Emit audit event if client provided
        if audit_client:
            audit_client.emit_simple(
                event_type=AuditEventType.KNOWLEDGE_ADDED,
                actor_id=actor_id,
                actor_type="human",
                payload={
                    "bullet_id": bullet.id,
                    "content": content,
                    "section": section,
                    "tags": bullet_tags,
                    "source": "file_import",
                    "source_file": str(path),
                    "playbook_id": playbook_id,
                },
                playbook_id=playbook_id,
            )

    return created_bullets
