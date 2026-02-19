"""
Playbook Manager - Core playbook operations.
Based on PRD Section 4: Core Features
"""
import json
import logging
from datetime import datetime
from pathlib import Path
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
from src.utils.embedding import get_embedding_service
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

    def __init__(self, storage_path: str | None = None) -> None:
        self.token_budget_per_section = settings.token_budget_per_section
        self.enable_redundancy_checking = settings.enable_redundancy_checking
        self.dedup_threshold = settings.deduplication_similarity_threshold

        # In-memory playbook storage
        self._playbooks: dict[str, Playbook] = {}
        self._bullet_counter: int = 0

        # File-based persistence
        self.storage_path = Path(storage_path) if storage_path else Path("data/playbooks")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Load existing playbooks from disk
        self._load_all_playbooks()

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

        # Auto-save to disk
        self._save_playbook(playbook_id)

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
        auto_save: bool = True,
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

        # Generate embedding for bullet content
        embedding = None
        try:
            embedding_service = get_embedding_service()
            embedding = embedding_service.embed_text(bullet_data.content)
            logger.debug(f"Generated embedding for bullet {bullet_id}")
        except Exception as e:
            logger.warning(f"Failed to generate embedding for bullet {bullet_id}: {e}")

        # Create bullet with model provenance
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
            embedding=embedding,
            created_by_model=bullet_data.created_by_model,
            model_provider=bullet_data.model_provider,
            license_type=bullet_data.license_type,
        )

        # Add to playbook
        playbook.sections[bullet_data.section].append(bullet)
        playbook.metadata.total_bullets += 1
        playbook.updated_at = now

        # Update version (increment patch)
        self._increment_version(playbook)

        logger.info(f"Added bullet {bullet_id} to playbook {playbook_id} section '{bullet_data.section}'")

        # Auto-save to disk (unless disabled for batch operations)
        if auto_save:
            self._save_playbook(playbook_id)

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

            # Add bullet (disable auto-save for batch operation)
            bullet_create = BulletCreate(
                content=delta.content,
                section=delta.section,
                tags=delta.tags,
            )
            bullet = self.add_bullet(playbook_id, bullet_create, auto_save=False)
            added_bullets.append(bullet)

        logger.info(
            f"Applied delta to playbook {playbook_id}: {len(added_bullets)}/{len(delta_bullets)} bullets added"
        )

        # Auto-save to disk if any bullets were added
        if added_bullets:
            self._save_playbook(playbook_id)

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

        # Auto-save to disk
        self._save_playbook(playbook_id)

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

    def get_playbooks_by_domain(self, domain: str) -> list[Playbook]:
        """
        Get all playbooks for a specific domain.

        Args:
            domain: Domain name

        Returns:
            List of playbooks matching the domain
        """
        return [
            playbook
            for playbook in self._playbooks.values()
            if playbook.metadata.domain == domain
        ]

    def get_cross_model_bullets(
        self,
        primary_playbook_id: str,
        include_primary: bool = True,
    ) -> dict[str, list[Bullet]]:
        """
        Get bullets from all playbooks in the same domain as the primary playbook.

        Args:
            primary_playbook_id: Primary playbook ID
            include_primary: Whether to include bullets from primary playbook

        Returns:
            Dictionary mapping playbook_id to list of bullets
        """
        primary_playbook = self.get_playbook(primary_playbook_id)
        if not primary_playbook:
            raise ValueError(f"Playbook {primary_playbook_id} not found")

        domain = primary_playbook.metadata.domain
        domain_playbooks = self.get_playbooks_by_domain(domain)

        result = {}
        for playbook in domain_playbooks:
            # Skip primary playbook if requested
            if not include_primary and playbook.playbook_id == primary_playbook_id:
                continue

            # Get all bullets from this playbook
            bullets = []
            for section_bullets in playbook.sections.values():
                bullets.extend(section_bullets)

            if bullets:
                result[playbook.playbook_id] = bullets

        return result

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

                    # Auto-save to disk
                    self._save_playbook(playbook_id)

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

    # ============================================================================
    # Persistence Methods
    # ============================================================================

    def _save_playbook(self, playbook_id: str) -> None:
        """
        Save a playbook to disk as JSON.

        Args:
            playbook_id: Playbook ID to save
        """
        playbook = self.get_playbook(playbook_id)
        if not playbook:
            logger.warning(f"Cannot save playbook {playbook_id}: not found")
            return

        file_path = self.storage_path / f"{playbook_id}.json"

        # Convert playbook to dict
        data = {
            "playbook_id": playbook.playbook_id,
            "version": playbook.version,
            "metadata": {
                "domain": playbook.metadata.domain,
                "base_model": playbook.metadata.base_model,
                "total_tokens": playbook.metadata.total_tokens,
                "total_bullets": playbook.metadata.total_bullets,
            },
            "sections": {},
            "created_at": playbook.created_at.isoformat(),
            "updated_at": playbook.updated_at.isoformat(),
        }

        # Convert bullets to dicts
        for section_name, bullets in playbook.sections.items():
            data["sections"][section_name] = [
                {
                    "id": b.id,
                    "content": b.content,
                    "section": b.section,
                    "tags": b.tags,
                    "helpful_count": b.helpful_count,
                    "harmful_count": b.harmful_count,
                    "created_at": b.created_at.isoformat(),
                    "last_used": b.last_used.isoformat() if b.last_used else None,
                    "embedding": b.embedding,
                    "created_by_model": b.created_by_model,
                    "model_provider": b.model_provider,
                    "license_type": b.license_type,
                }
                for b in bullets
            ]

        # Write to file
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)

        logger.debug(f"Saved playbook {playbook_id} to {file_path}")

    def _load_playbook(self, file_path: Path) -> Playbook | None:
        """
        Load a playbook from disk.

        Args:
            file_path: Path to JSON file

        Returns:
            Loaded playbook or None if loading failed
        """
        try:
            with open(file_path) as f:
                data = json.load(f)

            # Recreate metadata
            metadata = PlaybookMetadata(
                domain=data["metadata"]["domain"],
                base_model=data["metadata"]["base_model"],
                total_tokens=data["metadata"]["total_tokens"],
                total_bullets=data["metadata"]["total_bullets"],
            )

            # Recreate bullets
            sections = {}
            for section_name, bullets_data in data["sections"].items():
                bullets = []
                for b_data in bullets_data:
                    bullet = Bullet(
                        id=b_data["id"],
                        content=b_data["content"],
                        section=b_data["section"],
                        tags=b_data["tags"],
                        helpful_count=b_data["helpful_count"],
                        harmful_count=b_data["harmful_count"],
                        created_at=datetime.fromisoformat(b_data["created_at"]),
                        last_used=datetime.fromisoformat(b_data["last_used"]) if b_data["last_used"] else None,
                        embedding=b_data.get("embedding"),
                    )
                    bullets.append(bullet)

                    # Update bullet counter
                    if bullet.id.startswith("ctx-"):
                        try:
                            num = int(bullet.id.split("-")[1])
                            self._bullet_counter = max(self._bullet_counter, num)
                        except (IndexError, ValueError):
                            pass

                sections[section_name] = bullets

            # Recreate playbook
            playbook = Playbook(
                playbook_id=data["playbook_id"],
                version=data["version"],
                metadata=metadata,
                sections=sections,
                created_at=datetime.fromisoformat(data["created_at"]),
                updated_at=datetime.fromisoformat(data["updated_at"]),
            )

            logger.debug(f"Loaded playbook {playbook.playbook_id} from {file_path}")
            return playbook

        except Exception as e:
            logger.error(f"Failed to load playbook from {file_path}: {e}")
            return None

    def _load_all_playbooks(self) -> None:
        """Load all playbooks from storage directory."""
        if not self.storage_path.exists():
            logger.debug(f"Storage path {self.storage_path} does not exist, skipping load")
            return

        json_files = list(self.storage_path.glob("pb_*.json"))
        logger.info(f"Loading {len(json_files)} playbook(s) from {self.storage_path}")

        for file_path in json_files:
            playbook = self._load_playbook(file_path)
            if playbook:
                self._playbooks[playbook.playbook_id] = playbook
                logger.info(f"Loaded playbook {playbook.playbook_id} ({playbook.metadata.total_bullets} bullets)")

    def save_all_playbooks(self) -> None:
        """Save all playbooks to disk."""
        for playbook_id in self._playbooks:
            self._save_playbook(playbook_id)
        logger.info(f"Saved {len(self._playbooks)} playbook(s)")

    def delete_playbook(self, playbook_id: str) -> bool:
        """
        Delete a playbook from memory and disk.

        Args:
            playbook_id: Playbook ID to delete

        Returns:
            True if deleted, False if not found
        """
        # Remove from memory
        if playbook_id in self._playbooks:
            del self._playbooks[playbook_id]

            # Remove file
            file_path = self.storage_path / f"{playbook_id}.json"
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted playbook {playbook_id}")
                return True

        return False
