"""
PostgreSQL Adapter for Playbook Manager.

Provides the same interface as PlaybookManager but uses PostgreSQL with pgvector
for storage and retrieval instead of file-based JSON storage.
"""
import logging
from datetime import datetime

from src.config.settings import settings
from src.storage.repository import PlaybookRepository
from src.storage.schemas import (
    Bullet,
    BulletCreate,
    Playbook,
    PlaybookCreate,
    PlaybookMetadata,
)
from src.utils.embedding import get_embedding_service
from src.utils.id_generator import generate_playbook_id

logger = logging.getLogger(__name__)


class PostgresPlaybookAdapter:
    """
    PostgreSQL-backed playbook manager that maintains compatibility
    with the existing PlaybookManager interface.

    Uses PostgreSQL with pgvector for:
    - Persistent storage (no in-memory dict needed)
    - Vector similarity search
    - Automatic embedding generation
    """

    def __init__(self, storage_path: str | None = None) -> None:
        """
        Initialize PostgreSQL adapter.

        Args:
            storage_path: Ignored (kept for interface compatibility)
        """
        self.token_budget_per_section = settings.token_budget_per_section
        self.enable_redundancy_checking = settings.enable_redundancy_checking
        self.dedup_threshold = settings.deduplication_similarity_threshold

        # PostgreSQL repository
        self.repo = PlaybookRepository()
        self.embedder = get_embedding_service()

        # Bullet counter for ID generation
        self._bullet_counter: int = 0

        logger.info("PostgresPlaybookAdapter initialized with PostgreSQL backend")

    def create_playbook(self, create_data: PlaybookCreate) -> Playbook:
        """
        Create a new empty playbook in PostgreSQL.

        Args:
            create_data: Playbook creation parameters

        Returns:
            Newly created playbook
        """
        playbook_id = generate_playbook_id()
        now = datetime.utcnow()

        # Create playbook in PostgreSQL
        playbook_model = self.repo.get_or_create_playbook(
            playbook_id=playbook_id,
            version="0.1.0",
            domain=create_data.domain,
            base_model=create_data.base_model,
        )

        # Convert to Playbook schema
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

        logger.info(f"Created playbook {playbook_id} for domain '{create_data.domain}' in PostgreSQL")

        return playbook

    def get_playbook(self, playbook_id: str) -> Playbook | None:
        """
        Retrieve a playbook from PostgreSQL.

        Args:
            playbook_id: Unique playbook identifier

        Returns:
            Playbook if found, None otherwise
        """
        playbook_model = self.repo.get_playbook(playbook_id)
        if not playbook_model:
            return None

        # Get all bullets for this playbook
        bullets = self.repo.get_bullets_by_playbook(playbook_id)

        # Organize bullets by section
        sections = {
            "strategies_and_hard_rules": [],
            "code_snippets": [],
            "troubleshooting": [],
            "domain_knowledge": [],
        }

        for bullet_model in bullets:
            bullet = Bullet(
                id=bullet_model.bullet_id,
                content=bullet_model.content,
                section=bullet_model.section,
                tags=bullet_model.tags or [],
                helpful_count=bullet_model.helpful_count,
                harmful_count=bullet_model.harmful_count,
                created_at=bullet_model.created_at,
                last_used=bullet_model.last_used,
                embedding=bullet_model.embedding,
                created_by_model=playbook_model.base_model,
                model_provider="unknown",  # Not stored in DB currently
                license_type="unknown",  # Not stored in DB currently
            )

            # Add to appropriate section
            if bullet.section in sections:
                sections[bullet.section].append(bullet)

        metadata = PlaybookMetadata(
            domain=playbook_model.domain,
            base_model=playbook_model.base_model,
            total_tokens=playbook_model.total_tokens,
            total_bullets=playbook_model.total_bullets,
        )

        playbook = Playbook(
            playbook_id=playbook_model.playbook_id,
            version=playbook_model.version,
            metadata=metadata,
            sections=sections,
            created_at=playbook_model.created_at,
            updated_at=playbook_model.updated_at,
        )

        return playbook

    def add_bullet(
        self,
        playbook_id: str,
        bullet_data: BulletCreate,
        auto_save: bool = True,
    ) -> Bullet:
        """
        Add a new bullet to a playbook in PostgreSQL.

        Args:
            playbook_id: Target playbook ID
            bullet_data: Bullet content and metadata
            auto_save: Ignored (PostgreSQL always persists)

        Returns:
            Created bullet with ID and metadata

        Raises:
            ValueError: If playbook not found or section invalid
        """
        # Verify playbook exists
        playbook_model = self.repo.get_playbook(playbook_id)
        if not playbook_model:
            raise ValueError(f"Playbook {playbook_id} not found")

        # Validate section
        valid_sections = [
            "strategies_and_hard_rules",
            "code_snippets",
            "troubleshooting",
            "domain_knowledge",
        ]
        if bullet_data.section not in valid_sections:
            raise ValueError(f"Invalid section: {bullet_data.section}")

        # Generate unique bullet ID with timestamp to avoid collisions
        import time
        timestamp_ms = int(time.time() * 1000)
        self._bullet_counter += 1
        bullet_id = f"ctx-{timestamp_ms}-{self._bullet_counter:05d}"

        # Add bullet to PostgreSQL (automatically generates embedding)
        bullet_dict = {
            "bullet_id": bullet_id,
            "content": bullet_data.content,
            "section": bullet_data.section,
            "tags": bullet_data.tags or [],
            "helpful_count": 0,
            "harmful_count": 0,
        }

        self.repo.bulk_add_bullets(
            playbook_id=playbook_id,
            bullets=[bullet_dict],
        )

        # Retrieve the bullet to get the embedding
        bullet_model = self.repo.get_bullet(bullet_id)

        # Create bullet response
        now = datetime.utcnow()
        bullet = Bullet(
            id=bullet_id,
            content=bullet_data.content,
            section=bullet_data.section,
            tags=bullet_data.tags or [],
            helpful_count=0,
            harmful_count=0,
            created_at=now,
            last_used=None,
            embedding=bullet_model.embedding if bullet_model else [],
            created_by_model=playbook_model.base_model,
            model_provider=bullet_data.model_provider or "unknown",
            license_type=bullet_data.license_type or "unknown",
        )

        logger.info(f"Added bullet {bullet_id} to playbook {playbook_id} in PostgreSQL")

        return bullet

    def get_all_bullets(self, playbook_id: str) -> list[Bullet]:
        """
        Get all bullets from a playbook.

        Args:
            playbook_id: Playbook identifier

        Returns:
            List of all bullets in the playbook
        """
        playbook = self.get_playbook(playbook_id)
        if not playbook:
            return []

        # Flatten all sections
        all_bullets = []
        for section_bullets in playbook.sections.values():
            all_bullets.extend(section_bullets)

        return all_bullets

    def semantic_search(
        self,
        query: str,
        playbook_id: str | None = None,
        top_k: int = 5,
        similarity_threshold: float = 0.3,
    ) -> list[tuple[Bullet, float]]:
        """
        Search for relevant bullets using semantic similarity.

        Args:
            query: Search query
            playbook_id: Optional playbook to search within
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score

        Returns:
            List of (bullet, similarity_score) tuples
        """
        # Generate query embedding
        query_emb = self.embedder.embed_text(query)

        # Search PostgreSQL
        results = self.repo.similarity_search(
            query_embedding=query_emb,
            playbook_id=playbook_id,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
        )

        # Convert to Bullet schema
        bullet_results = []
        for bullet_model, score in results:
            # Get playbook for metadata
            playbook_model = self.repo.get_playbook_by_bullet(bullet_model.bullet_id)

            bullet = Bullet(
                id=bullet_model.bullet_id,
                content=bullet_model.content,
                section=bullet_model.section,
                tags=bullet_model.tags or [],
                helpful_count=bullet_model.helpful_count,
                harmful_count=bullet_model.harmful_count,
                created_at=bullet_model.created_at,
                last_used=bullet_model.last_used,
                embedding=bullet_model.embedding,
                created_by_model=playbook_model.base_model if playbook_model else "unknown",
                model_provider="unknown",
                license_type="unknown",
            )
            bullet_results.append((bullet, score))

        return bullet_results

    def list_playbooks(self) -> list[str]:
        """
        List all playbook IDs in PostgreSQL.

        Returns:
            List of playbook IDs
        """
        stats = self.repo.get_stats()
        # Note: The repository doesn't have a list method yet,
        # so we'll need to add one or query directly
        from sqlalchemy import select

        from src.storage.models import PlaybookModel

        with self.repo.get_session() as session:
            result = session.execute(select(PlaybookModel.playbook_id))
            return [row[0] for row in result.fetchall()]
