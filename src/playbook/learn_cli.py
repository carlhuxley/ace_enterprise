"""CLI helper for adding knowledge with audit trail.

This module provides the learn_with_audit function used by the 'ace learn'
CLI command. It adds knowledge to a playbook and emits an audit event.

The audit event includes full content for human visibility in the
audit dashboard.
"""

from src.audit.local_client import LocalAuditClient
from src.audit.schemas import AuditEventType
from src.playbook.manager import PlaybookManager
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
