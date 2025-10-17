"""
Playbook Manager - Core playbook operations.
Based on PRD Section 4: Core Features
"""
import logging
from datetime import datetime
from typing import Any

from src.config.settings import settings
from src.storage.schemas import (
    Bullet,
    BulletCreate,
    DeltaBullet,
    Playbook,
    PlaybookCreate,
    PlaybookMetadata,
)
from src.utils.id_generator import generate_bullet_id, generate_playbook_id

logger = logging.getLogger(__name__)


class PlaybookManager:
    """
    Manages playbook operations: creation, updates, merging, and retrieval.

    Features (PRD Section 4.1-4.3):
    - Incremental delta updates
    - Semantic de-duplication
    - Fine-grained retrieval
    - Token budget management
    """

    def __init__(self) -> None:
        self.token_budget_per_section = settings.token_budget_per_section
        self.enable_redundancy_checking = settings.enable_redundancy_checking
        self.dedup_threshold = settings.deduplication_similarity_threshold

        # In-memory playbook storage (will be replaced with database)
        self._playbooks: dict[str, Playbook] = {}
        self._bullet_counter: int = 0

    def create_playbook(self, create_data: PlaybookCreate) -> Playbook:
        """
        Create a new empty playbook.

        Args:
            create_data: Playbook creation parameters

        Returns:
            Newly created playbook
        """
        playbook_id = generate_playbook_id()
        now = datetime.utcnow()

        metadata = PlaybookMetadata(
            domain=create_data.domain,
            base_model=create_data.base_model,
            total_tokens=0,
            total_bullets=0,
        )

        playbook = Playbook(
            playbook_id=playbook_id,
            version="0.1.0",
            metadata=metadata,
            sections={
                "strategies_and_hard_rules": [],
                "code_snippets": [],
                "troubleshooting": [],
                "domain_knowledge": [],
            },
            created_at=now,
            updated_at=now,
        )

        self._playbooks[playbook_id] = playbook
        logger.info(f"Created playbook {playbook_id} for domain '{create_data.domain}'")

        return playbook

    def get_playbook(self, playbook_id: str) -> Playbook | None:
        """
        Retrieve a playbook by ID.

        Args:
            playbook_id: Unique playbook identifier

        Returns:
            Playbook if found, None otherwise
        """
        return self._playbooks.get(playbook_id)

    def add_bullet(
        self,
        playbook_id: str,
        bullet_data: BulletCreate,
    ) -> Bullet:
        """
        Add a new bullet to a playbook.

        Args:
            playbook_id: Target playbook ID
            bullet_data: Bullet content and metadata

        Returns:
            Created bullet with ID and metadata

        Raises:
            ValueError: If playbook not found or section invalid
        """
        playbook = self.get_playbook(playbook_id)
        if not playbook:
            raise ValueError(f"Playbook {playbook_id} not found")

        if bullet_data.section not in playbook.sections:
            raise ValueError(f"Invalid section: {bullet_data.section}")

        # Generate unique bullet ID
        self._bullet_counter += 1
        bullet_id = generate_bullet_id(self._bullet_counter)

        # Create bullet
        now = datetime.utcnow()
        bullet = Bullet(
            id=bullet_id,
            content=bullet_data.content,
            section=bullet_data.section,
            tags=bullet_data.tags,
            helpful_count=0,
            harmful_count=0,
            created_at=now,
            last_used=None,
            embedding=None,  # Will be generated later
        )

        # Add to playbook
        playbook.sections[bullet_data.section].append(bullet)
        playbook.metadata.total_bullets += 1
        playbook.updated_at = now

        # Update version (increment patch)
        self._increment_version(playbook)

        logger.info(f"Added bullet {bullet_id} to playbook {playbook_id} section '{bullet_data.section}'")

        return bullet

    def apply_delta(
        self,
        playbook_id: str,
        delta_bullets: list[DeltaBullet],
    ) -> list[Bullet]:
        """
        Apply delta updates to playbook (PRD Section 4.1).

        Incremental update mechanism that adds new bullets without
        full rewrite. Optionally checks for redundancy.

        Args:
            playbook_id: Target playbook ID
            delta_bullets: List of new bullets to add

        Returns:
            List of added bullets

        Raises:
            ValueError: If playbook not found
        """
        playbook = self.get_playbook(playbook_id)
        if not playbook:
            raise ValueError(f"Playbook {playbook_id} not found")

        added_bullets: list[Bullet] = []

        for delta in delta_bullets:
            # Check redundancy if enabled
            if self.enable_redundancy_checking:
                if self._is_redundant(playbook, delta):
                    logger.debug(
                        f"Skipping redundant bullet in section '{delta.section}': {delta.content[:50]}..."
                    )
                    continue

            # Check token budget
            if not self._check_token_budget(playbook, delta.section):
                logger.warning(
                    f"Token budget exceeded for section '{delta.section}', skipping bullet"
                )
                continue

            # Add bullet
            bullet_create = BulletCreate(
                content=delta.content,
                section=delta.section,
                tags=delta.tags,
            )
            bullet = self.add_bullet(playbook_id, bullet_create)
            added_bullets.append(bullet)

        logger.info(
            f"Applied delta to playbook {playbook_id}: {len(added_bullets)}/{len(delta_bullets)} bullets added"
        )

        return added_bullets

    def update_bullet_feedback(
        self,
        playbook_id: str,
        bullet_id: str,
        feedback: str,
    ) -> None:
        """
        Update bullet helpful/harmful counts based on feedback.

        Args:
            playbook_id: Playbook ID
            bullet_id: Bullet ID
            feedback: One of "helpful", "harmful", "neutral"

        Raises:
            ValueError: If playbook or bullet not found, or invalid feedback
        """
        playbook = self.get_playbook(playbook_id)
        if not playbook:
            raise ValueError(f"Playbook {playbook_id} not found")

        # Find bullet
        bullet = self._find_bullet(playbook, bullet_id)
        if not bullet:
            raise ValueError(f"Bullet {bullet_id} not found in playbook {playbook_id}")

        # Update counts
        if feedback == "helpful":
            bullet.helpful_count += 1
        elif feedback == "harmful":
            bullet.harmful_count += 1
        elif feedback == "neutral":
            pass  # No change
        else:
            raise ValueError(f"Invalid feedback: {feedback}")

        # Update last used timestamp
        bullet.last_used = datetime.utcnow()
        playbook.updated_at = datetime.utcnow()

        logger.debug(f"Updated feedback for bullet {bullet_id}: {feedback}")

    def get_section_bullets(
        self,
        playbook_id: str,
        section: str,
    ) -> list[Bullet]:
        """
        Get all bullets in a specific section.

        Args:
            playbook_id: Playbook ID
            section: Section name

        Returns:
            List of bullets in section

        Raises:
            ValueError: If playbook not found or invalid section
        """
        playbook = self.get_playbook(playbook_id)
        if not playbook:
            raise ValueError(f"Playbook {playbook_id} not found")

        if section not in playbook.sections:
            raise ValueError(f"Invalid section: {section}")

        return playbook.sections[section]

    def get_all_bullets(self, playbook_id: str) -> list[Bullet]:
        """
        Get all bullets across all sections.

        Args:
            playbook_id: Playbook ID

        Returns:
            List of all bullets

        Raises:
            ValueError: If playbook not found
        """
        playbook = self.get_playbook(playbook_id)
        if not playbook:
            raise ValueError(f"Playbook {playbook_id} not found")

        all_bullets = []
        for bullets in playbook.sections.values():
            all_bullets.extend(bullets)

        return all_bullets

    def remove_bullet(
        self,
        playbook_id: str,
        bullet_id: str,
    ) -> bool:
        """
        Remove a bullet from playbook.

        Args:
            playbook_id: Playbook ID
            bullet_id: Bullet ID to remove

        Returns:
            True if removed, False if not found

        Raises:
            ValueError: If playbook not found
        """
        playbook = self.get_playbook(playbook_id)
        if not playbook:
            raise ValueError(f"Playbook {playbook_id} not found")

        # Search all sections
        for section_name, bullets in playbook.sections.items():
            for i, bullet in enumerate(bullets):
                if bullet.id == bullet_id:
                    bullets.pop(i)
                    playbook.metadata.total_bullets -= 1
                    playbook.updated_at = datetime.utcnow()
                    self._increment_version(playbook)
                    logger.info(f"Removed bullet {bullet_id} from playbook {playbook_id}")
                    return True

        return False

    # ============================================================================
    # Private Helper Methods
    # ============================================================================

    def _find_bullet(self, playbook: Playbook, bullet_id: str) -> Bullet | None:
        """Find a bullet by ID across all sections."""
        for bullets in playbook.sections.values():
            for bullet in bullets:
                if bullet.id == bullet_id:
                    return bullet
        return None

    def _is_redundant(self, playbook: Playbook, delta: DeltaBullet) -> bool:
        """
        Check if delta bullet is redundant with existing bullets.

        For now, uses simple string matching. Will be enhanced with
        semantic similarity once embeddings are integrated.
        """
        section_bullets = playbook.sections.get(delta.section, [])

        # Simple exact match check
        for bullet in section_bullets:
            if bullet.content.strip().lower() == delta.content.strip().lower():
                return True

        # TODO: Implement semantic similarity check using embeddings
        # if bullet.embedding and delta_embedding:
        #     similarity = cosine_similarity(bullet.embedding, delta_embedding)
        #     if similarity > self.dedup_threshold:
        #         return True

        return False

    def _check_token_budget(self, playbook: Playbook, section: str) -> bool:
        """
        Check if section is within token budget.

        Simplified version - assumes average 4 chars per token.
        Will be enhanced with proper tokenization.
        """
        section_bullets = playbook.sections.get(section, [])

        # Estimate tokens (rough approximation)
        total_chars = sum(len(bullet.content) for bullet in section_bullets)
        estimated_tokens = total_chars // 4

        return estimated_tokens < self.token_budget_per_section

    def _increment_version(self, playbook: Playbook) -> None:
        """Increment playbook version (semantic versioning)."""
        parts = playbook.version.split(".")
        patch = int(parts[2]) + 1
        playbook.version = f"{parts[0]}.{parts[1]}.{patch}"

    def get_statistics(self, playbook_id: str) -> dict[str, Any]:
        """
        Get playbook statistics.

        Args:
            playbook_id: Playbook ID

        Returns:
            Dictionary with statistics

        Raises:
            ValueError: If playbook not found
        """
        playbook = self.get_playbook(playbook_id)
        if not playbook:
            raise ValueError(f"Playbook {playbook_id} not found")

        stats = {
            "playbook_id": playbook.playbook_id,
            "version": playbook.version,
            "domain": playbook.metadata.domain,
            "total_bullets": playbook.metadata.total_bullets,
            "sections": {},
        }

        for section_name, bullets in playbook.sections.items():
            helpful = sum(b.helpful_count for b in bullets)
            harmful = sum(b.harmful_count for b in bullets)
            total_feedback = helpful + harmful

            stats["sections"][section_name] = {
                "bullet_count": len(bullets),
                "helpful_count": helpful,
                "harmful_count": harmful,
                "helpful_ratio": helpful / total_feedback if total_feedback > 0 else 0.0,
            }

        return stats
