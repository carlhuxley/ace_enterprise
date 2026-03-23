"""
Playbook Maintenance Functions.

Provides maintenance operations for playbook health:
- Confidence decay for stale bullets
- Pruning of low-confidence patterns
"""

import logging
from datetime import datetime, timedelta

from src.playbook.manager import PlaybookManager

logger = logging.getLogger(__name__)


async def decay_stale_bullets(
    playbook_manager: PlaybookManager,
    playbook_id: str,
    stale_days: int = 90,
    decay_factor: float = 0.1,
) -> int:
    """
    Reduce confidence of bullets that haven't been used recently.

    Stale bullets (not used in `stale_days`) have their confidence reduced,
    which eventually moves them below the retrieval threshold. This helps
    ensure that the most relevant, actively-used patterns are surfaced.

    Args:
        playbook_manager: PlaybookManager instance
        playbook_id: ID of the playbook to process
        stale_days: Number of days before a bullet is considered stale
        decay_factor: Amount to reduce confidence (0.0-1.0)

    Returns:
        Number of bullets affected
    """
    playbook = playbook_manager.get_playbook(playbook_id)
    if not playbook:
        logger.warning(f"Playbook {playbook_id} not found for maintenance")
        return 0

    cutoff = datetime.utcnow() - timedelta(days=stale_days)
    affected = 0

    for section_bullets in playbook.sections.values():
        for bullet in section_bullets:
            # Get last_used, default to created_at if never used
            last_active = bullet.last_used or bullet.created_at

            if last_active < cutoff:
                # Get current confidence
                current_confidence = getattr(bullet, 'confidence_score', 0.5)

                # Apply decay
                new_confidence = max(0.0, current_confidence - decay_factor)

                if new_confidence != current_confidence:
                    bullet.confidence_score = new_confidence
                    affected += 1

                    logger.debug(
                        f"Decayed bullet {bullet.id}: "
                        f"{current_confidence:.2f} -> {new_confidence:.2f}"
                    )

    if affected > 0:
        playbook_manager._save_playbook(playbook_id)
        logger.info(
            f"Confidence decay: {affected} stale bullets in {playbook_id} "
            f"(stale_days={stale_days}, decay_factor={decay_factor})"
        )

    return affected


async def prune_low_confidence_bullets(
    playbook_manager: PlaybookManager,
    playbook_id: str,
    min_confidence: float = 0.1,
    min_age_days: int = 30,
) -> int:
    """
    Remove bullets that have fallen below a minimum confidence threshold.

    Only affects bullets older than `min_age_days` to avoid pruning
    newly-created patterns that haven't had time to gather feedback.

    Args:
        playbook_manager: PlaybookManager instance
        playbook_id: ID of the playbook to process
        min_confidence: Minimum confidence to keep (default 0.1)
        min_age_days: Minimum age before a bullet can be pruned

    Returns:
        Number of bullets removed
    """
    playbook = playbook_manager.get_playbook(playbook_id)
    if not playbook:
        logger.warning(f"Playbook {playbook_id} not found for pruning")
        return 0

    cutoff = datetime.utcnow() - timedelta(days=min_age_days)
    removed = 0

    for section_name, section_bullets in playbook.sections.items():
        bullets_to_keep = []

        for bullet in section_bullets:
            confidence = getattr(bullet, 'confidence_score', 0.5)

            # Only prune if below threshold AND old enough
            if confidence < min_confidence and bullet.created_at < cutoff:
                logger.info(
                    f"Pruning low-confidence bullet {bullet.id} "
                    f"(confidence={confidence:.2f}, section={section_name})"
                )
                removed += 1
            else:
                bullets_to_keep.append(bullet)

        playbook.sections[section_name] = bullets_to_keep

    if removed > 0:
        playbook.metadata.total_bullets -= removed
        playbook_manager._save_playbook(playbook_id)
        logger.info(
            f"Pruned {removed} low-confidence bullets from {playbook_id}"
        )

    return removed


async def run_maintenance(
    playbook_manager: PlaybookManager,
    playbook_id: str | None = None,
    decay_stale_days: int = 90,
    decay_factor: float = 0.1,
    prune_threshold: float = 0.1,
    prune_min_age_days: int = 30,
) -> dict:
    """
    Run full maintenance cycle on playbook(s).

    Args:
        playbook_manager: PlaybookManager instance
        playbook_id: Specific playbook to maintain (None = all playbooks)
        decay_stale_days: Days before considering a bullet stale
        decay_factor: Amount to decay stale bullet confidence
        prune_threshold: Minimum confidence to keep
        prune_min_age_days: Minimum age before pruning allowed

    Returns:
        Dictionary with maintenance statistics
    """
    stats = {
        "playbooks_processed": 0,
        "bullets_decayed": 0,
        "bullets_pruned": 0,
    }

    # Get playbooks to process
    if playbook_id:
        playbook_ids = [playbook_id]
    else:
        playbook_ids = list(playbook_manager._playbooks.keys())

    for pb_id in playbook_ids:
        # Run confidence decay
        decayed = await decay_stale_bullets(
            playbook_manager=playbook_manager,
            playbook_id=pb_id,
            stale_days=decay_stale_days,
            decay_factor=decay_factor,
        )
        stats["bullets_decayed"] += decayed

        # Run pruning
        pruned = await prune_low_confidence_bullets(
            playbook_manager=playbook_manager,
            playbook_id=pb_id,
            min_confidence=prune_threshold,
            min_age_days=prune_min_age_days,
        )
        stats["bullets_pruned"] += pruned

        stats["playbooks_processed"] += 1

    logger.info(
        f"Maintenance complete: {stats['playbooks_processed']} playbooks, "
        f"{stats['bullets_decayed']} decayed, {stats['bullets_pruned']} pruned"
    )

    return stats
