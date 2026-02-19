"""
PostgreSQL Repository with pgvector for Semantic Search

Provides database operations for playbooks and bullets with
vector similarity search capabilities.
"""

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import settings
from src.storage.models import Base, BulletModel, PlaybookModel
from src.utils.embedding import get_embedding_service

logger = logging.getLogger(__name__)


class PlaybookRepository:
    """
    PostgreSQL repository for playbooks and bullets with pgvector integration.

    Features:
    - Full CRUD operations
    - Vector similarity search using pgvector
    - Batch operations
    - Transaction support
    """

    def __init__(self, database_url: str | None = None):
        """
        Initialize repository with database connection.

        Args:
            database_url: PostgreSQL connection string (default from settings)
        """
        if database_url is None:
            # Convert async URL to sync (asyncpg → psycopg2)
            db_url = str(settings.database_url).replace('asyncpg', 'psycopg2')
        else:
            db_url = database_url

        self.database_url = db_url
        self.engine = create_engine(
            self.database_url,
            echo=getattr(settings, 'sql_echo', False),
            pool_pre_ping=True  # Verify connections before using
        )
        self.SessionLocal = sessionmaker(bind=self.engine)

        logger.info("PostgreSQL repository initialized")

    def create_tables(self):
        """Create all tables (use migrations instead in production)."""
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created")

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    # ========================================================================
    # Playbook Operations
    # ========================================================================

    def create_playbook(
        self,
        playbook_id: str,
        version: str,
        domain: str,
        base_model: str
    ) -> PlaybookModel:
        """Create a new playbook."""
        with self.get_session() as session:
            playbook = PlaybookModel(
                playbook_id=playbook_id,
                version=version,
                domain=domain,
                base_model=base_model
            )
            session.add(playbook)
            session.commit()
            session.refresh(playbook)
            logger.info(f"Created playbook: {playbook_id}")
            return playbook

    def get_playbook(self, playbook_id: str) -> PlaybookModel | None:
        """Get playbook by ID."""
        with self.get_session() as session:
            return session.query(PlaybookModel).filter(
                PlaybookModel.playbook_id == playbook_id
            ).first()

    def get_or_create_playbook(
        self,
        playbook_id: str,
        version: str,
        domain: str,
        base_model: str
    ) -> PlaybookModel:
        """Get existing playbook or create if not exists."""
        playbook = self.get_playbook(playbook_id)
        if playbook:
            return playbook
        return self.create_playbook(playbook_id, version, domain, base_model)

    # ========================================================================
    # Bullet Operations
    # ========================================================================

    def add_bullet(
        self,
        playbook_id: str,
        bullet_id: str,
        content: str,
        section: str,
        tags: list[str],
        embedding: list[float] | None = None
    ) -> BulletModel:
        """Add a bullet to a playbook."""
        with self.get_session() as session:
            # Get playbook internal ID
            playbook = session.query(PlaybookModel).filter(
                PlaybookModel.playbook_id == playbook_id
            ).first()

            if not playbook:
                raise ValueError(f"Playbook not found: {playbook_id}")

            # Generate embedding if not provided
            if embedding is None and content:
                embedder = get_embedding_service()
                embedding = embedder.embed_text(content)

            bullet = BulletModel(
                bullet_id=bullet_id,
                playbook_id=playbook.id,
                content=content,
                section=section,
                tags=tags,
                embedding=embedding
            )

            session.add(bullet)
            session.commit()
            session.refresh(bullet)

            # Update playbook bullet count
            playbook.total_bullets = session.query(BulletModel).filter(
                BulletModel.playbook_id == playbook.id
            ).count()
            session.commit()

            logger.debug(f"Added bullet {bullet_id} to playbook {playbook_id}")
            return bullet

    def get_bullets(
        self,
        playbook_id: str,
        section: str | None = None,
        tags: list[str] | None = None
    ) -> list[BulletModel]:
        """Get bullets from a playbook."""
        with self.get_session() as session:
            # Get playbook internal ID
            playbook = session.query(PlaybookModel).filter(
                PlaybookModel.playbook_id == playbook_id
            ).first()

            if not playbook:
                return []

            query = session.query(BulletModel).filter(
                BulletModel.playbook_id == playbook.id
            )

            # Filter by section
            if section:
                query = query.filter(BulletModel.section == section)

            # Filter by tags (any match)
            if tags:
                query = query.filter(
                    BulletModel.tags.op('&&')(tags)  # JSONB overlap operator
                )

            return query.all()

    def get_bullet(self, bullet_id: str) -> BulletModel | None:
        """Get a single bullet by ID."""
        with self.get_session() as session:
            return session.query(BulletModel).filter(
                BulletModel.bullet_id == bullet_id
            ).first()

    def get_bullets_by_playbook(self, playbook_id: str) -> list[BulletModel]:
        """Get all bullets from a playbook (alias for get_bullets without filters)."""
        return self.get_bullets(playbook_id)

    def get_playbook_by_bullet(self, bullet_id: str) -> PlaybookModel | None:
        """Get the playbook that owns a bullet."""
        with self.get_session() as session:
            bullet = session.query(BulletModel).filter(
                BulletModel.bullet_id == bullet_id
            ).first()

            if not bullet:
                return None

            return session.query(PlaybookModel).filter(
                PlaybookModel.id == bullet.playbook_id
            ).first()

    # ========================================================================
    # Pgvector Similarity Search
    # ========================================================================

    def similarity_search(
        self,
        query_embedding: list[float],
        playbook_id: str | None = None,
        section: str | None = None,
        top_k: int = 10,
        similarity_threshold: float = 0.0,
        distance_metric: str = "cosine"
    ) -> list[tuple[BulletModel, float]]:
        """
        Semantic similarity search using pgvector.

        Args:
            query_embedding: Query vector (384 dimensions)
            playbook_id: Filter by playbook (optional)
            section: Filter by section (optional)
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score (0-1)
            distance_metric: "cosine", "l2", or "ip" (inner product)

        Returns:
            List of (bullet, similarity_score) tuples, sorted by relevance
        """
        with self.get_session() as session:
            # Choose distance operator based on metric
            distance_ops = {
                "cosine": "<=>",  # Cosine distance (lower = more similar)
                "l2": "<->",      # L2 distance (Euclidean)
                "ip": "<#>"       # Inner product (negative = higher similarity)
            }

            if distance_metric not in distance_ops:
                raise ValueError(f"Invalid distance metric: {distance_metric}")

            op = distance_ops[distance_metric]

            # Build query
            query = session.query(
                BulletModel,
                # Convert distance to similarity (1 - distance for cosine/l2)
                text(f"1 - (embedding {op} :query_emb) as similarity")
            ).filter(
                BulletModel.embedding.isnot(None)
            )

            # Filter by playbook
            if playbook_id:
                playbook = session.query(PlaybookModel).filter(
                    PlaybookModel.playbook_id == playbook_id
                ).first()
                if playbook:
                    query = query.filter(BulletModel.playbook_id == playbook.id)

            # Filter by section
            if section:
                query = query.filter(BulletModel.section == section)

            # Order by similarity (using vector distance)
            query = query.order_by(
                text(f"embedding {op} :query_emb")
            ).params(query_emb=str(query_embedding))

            # Limit results
            query = query.limit(top_k)

            # Execute query
            results = query.all()

            # Filter by threshold and convert to tuples
            filtered_results = [
                (bullet, float(similarity))
                for bullet, similarity in results
                if float(similarity) >= similarity_threshold
            ]

            logger.debug(
                f"Similarity search found {len(filtered_results)} results "
                f"(threshold: {similarity_threshold})"
            )

            return filtered_results

    def similarity_search_multi_playbook(
        self,
        query_embedding: list[float],
        domain: str,
        top_k: int = 10,
        similarity_threshold: float = 0.5
    ) -> list[tuple[BulletModel, float, str]]:
        """
        Search across all playbooks in a domain.

        Returns:
            List of (bullet, similarity, playbook_id) tuples
        """
        with self.get_session() as session:
            query = session.query(
                BulletModel,
                text("1 - (bullets.embedding <=> :query_emb) as similarity"),
                PlaybookModel.playbook_id
            ).join(
                PlaybookModel,
                BulletModel.playbook_id == PlaybookModel.id
            ).filter(
                PlaybookModel.domain == domain,
                BulletModel.embedding.isnot(None)
            ).order_by(
                text("bullets.embedding <=> :query_emb")
            ).params(
                query_emb=str(query_embedding)
            ).limit(top_k)

            results = query.all()

            filtered = [
                (bullet, float(sim), pb_id)
                for bullet, sim, pb_id in results
                if float(sim) >= similarity_threshold
            ]

            return filtered

    # ========================================================================
    # Bulk Operations
    # ========================================================================

    def bulk_add_bullets(
        self,
        playbook_id: str,
        bullets: list[dict]
    ) -> int:
        """
        Add multiple bullets in a single transaction.

        Args:
            playbook_id: Target playbook ID
            bullets: List of bullet dicts with keys: bullet_id, content, section, tags, embedding

        Returns:
            Number of bullets added
        """
        with self.get_session() as session:
            # Get playbook
            playbook = session.query(PlaybookModel).filter(
                PlaybookModel.playbook_id == playbook_id
            ).first()

            if not playbook:
                raise ValueError(f"Playbook not found: {playbook_id}")

            # Generate embeddings for bullets without them
            embedder = get_embedding_service()
            for bullet_data in bullets:
                if not bullet_data.get('embedding') and bullet_data.get('content'):
                    bullet_data['embedding'] = embedder.embed_text(bullet_data['content'])

            # Create bullet models
            bullet_models = [
                BulletModel(
                    bullet_id=b['bullet_id'],
                    playbook_id=playbook.id,
                    content=b['content'],
                    section=b['section'],
                    tags=b.get('tags', []),
                    embedding=b.get('embedding')
                )
                for b in bullets
            ]

            # Bulk insert
            session.bulk_save_objects(bullet_models)
            session.commit()

            # Update playbook count
            playbook.total_bullets = session.query(BulletModel).filter(
                BulletModel.playbook_id == playbook.id
            ).count()
            session.commit()

            logger.info(f"Bulk added {len(bullets)} bullets to {playbook_id}")
            return len(bullets)

    # ========================================================================
    # Statistics
    # ========================================================================

    def get_stats(self) -> dict:
        """Get repository statistics."""
        with self.get_session() as session:
            playbook_count = session.query(PlaybookModel).count()
            bullet_count = session.query(BulletModel).count()
            bullets_with_embeddings = session.query(BulletModel).filter(
                BulletModel.embedding.isnot(None)
            ).count()

            return {
                "total_playbooks": playbook_count,
                "total_bullets": bullet_count,
                "bullets_with_embeddings": bullets_with_embeddings,
                "embedding_coverage": bullets_with_embeddings / bullet_count if bullet_count > 0 else 0
            }


# Global singleton
_repository: PlaybookRepository | None = None


def get_repository() -> PlaybookRepository:
    """Get or create global repository instance."""
    global _repository
    if _repository is None:
        _repository = PlaybookRepository()
    return _repository
