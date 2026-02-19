"""
Embedding Service - Generate embeddings for playbook bullets.
Uses local sentence-transformers model (no API calls required).
"""
import logging

import numpy as np
from sentence_transformers import SentenceTransformer

from src.config.settings import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Local embedding generation using sentence-transformers.

    Features:
    - Local model (no API calls)
    - Batch processing
    - CPU/GPU support
    - Fast inference (~100ms for small batches)
    - Free and offline
    """

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
    ) -> None:
        """
        Initialize embedding service.

        Args:
            model_name: Model name (default from settings)
            device: Device to use: 'cpu', 'cuda', 'mps' (default from settings)
        """
        self.model_name = model_name or settings.embedding_model
        self.device = device or settings.embedding_device

        logger.info(f"Loading embedding model: {self.model_name} on {self.device}")

        try:
            self.model = SentenceTransformer(self.model_name, device=self.device)
            logger.info("✓ Embedding model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise

    def embed_text(self, text: str) -> list[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding")
            return []

        try:
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return []

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts (batch processing).

        More efficient than calling embed_text() multiple times.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # Filter out empty strings
        valid_texts = [t for t in texts if t and t.strip()]

        if not valid_texts:
            logger.warning("All texts were empty")
            return [[] for _ in texts]

        try:
            batch_size = settings.embedding_batch_size
            embeddings = self.model.encode(
                valid_texts,
                batch_size=batch_size,
                convert_to_numpy=True,
                show_progress_bar=len(valid_texts) > 10,
            )

            logger.debug(f"Generated {len(embeddings)} embeddings")
            return [emb.tolist() for emb in embeddings]

        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}")
            return [[] for _ in texts]

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by this model.

        Returns:
            Embedding dimension (e.g., 384 for all-MiniLM-L6-v2)
        """
        return self.model.get_sentence_embedding_dimension()

    @staticmethod
    def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        """
        Calculate cosine similarity between two embedding vectors.

        Args:
            vec1: First embedding vector
            vec2: Second embedding vector

        Returns:
            Cosine similarity score (0-1)
        """
        if not vec1 or not vec2:
            return 0.0

        v1 = np.array(vec1)
        v2 = np.array(vec2)

        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(np.dot(v1, v2) / (norm1 * norm2))


# Global singleton instance (lazy-loaded)
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """
    Get or create global embedding service instance.

    Returns:
        EmbeddingService singleton
    """
    global _embedding_service

    if _embedding_service is None:
        _embedding_service = EmbeddingService()

    return _embedding_service
