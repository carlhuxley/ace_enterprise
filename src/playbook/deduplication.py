"""
Semantic Deduplication for Playbook Bullets.
Based on PRD Section 4.2: Semantic De-duplication
"""
import logging
from typing import Optional

import numpy as np

from src.config.settings import settings
from src.storage.schemas import Bullet

logger = logging.getLogger(__name__)


class BulletDeduplicator:
    """
    Handles semantic deduplication of bullets using embedding similarity.

    Features (PRD Section 4.2):
    - Vector embeddings for all bullets
    - Cosine similarity threshold (default 0.85)
    - Preserve highest helpful/harmful ratio
    - Batch processing support
    """

    def __init__(
        self,
        similarity_threshold: Optional[float] = None,
    ) -> None:
        """
        Initialize deduplicator.

        Args:
            similarity_threshold: Cosine similarity threshold for duplicates
                                 (default from settings)
        """
        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else settings.deduplication_similarity_threshold
        )

    def is_duplicate(
        self,
        bullet1: Bullet,
        bullet2: Bullet,
    ) -> bool:
        """
        Check if two bullets are duplicates based on semantic similarity.

        Args:
            bullet1: First bullet
            bullet2: Second bullet

        Returns:
            True if bullets are considered duplicates
        """
        # If either bullet doesn't have embeddings, fall back to exact match
        if bullet1.embedding is None or bullet2.embedding is None:
            return self._exact_match(bullet1.content, bullet2.content)

        # Calculate cosine similarity
        similarity = self._cosine_similarity(
            bullet1.embedding,
            bullet2.embedding,
        )

        is_dup = similarity >= self.similarity_threshold

        if is_dup:
            logger.debug(
                f"Duplicate detected (similarity={similarity:.3f}): "
                f"'{bullet1.content[:50]}...' == '{bullet2.content[:50]}...'"
            )

        return is_dup

    def find_duplicates(
        self,
        bullets: list[Bullet],
    ) -> list[tuple[int, int, float]]:
        """
        Find all duplicate pairs in a list of bullets.

        Args:
            bullets: List of bullets to check

        Returns:
            List of (index1, index2, similarity) tuples for duplicates
        """
        duplicates = []

        for i in range(len(bullets)):
            for j in range(i + 1, len(bullets)):
                if self.is_duplicate(bullets[i], bullets[j]):
                    # Calculate similarity score
                    if bullets[i].embedding and bullets[j].embedding:
                        similarity = self._cosine_similarity(
                            bullets[i].embedding,
                            bullets[j].embedding,
                        )
                    else:
                        similarity = 1.0  # Exact match

                    duplicates.append((i, j, similarity))

        logger.info(f"Found {len(duplicates)} duplicate pairs in {len(bullets)} bullets")
        return duplicates

    def deduplicate(
        self,
        bullets: list[Bullet],
        preserve_strategy: str = "highest_ratio",
    ) -> list[Bullet]:
        """
        Remove duplicate bullets from a list.

        Args:
            bullets: List of bullets to deduplicate
            preserve_strategy: Strategy for choosing which duplicate to keep
                             - "highest_ratio": Keep bullet with best helpful/harmful ratio
                             - "most_recent": Keep most recently created
                             - "most_used": Keep most frequently used

        Returns:
            Deduplicated list of bullets
        """
        if not bullets:
            return []

        # Find all duplicates
        duplicates = self.find_duplicates(bullets)

        # Track indices to remove
        to_remove = set()

        # Process each duplicate pair
        for i, j, similarity in duplicates:
            # Skip if already marked for removal
            if i in to_remove or j in to_remove:
                continue

            # Decide which to keep
            keep_i = self._should_keep_first(
                bullets[i],
                bullets[j],
                preserve_strategy,
            )

            # Mark for removal
            to_remove.add(j if keep_i else i)

        # Filter out duplicates
        deduplicated = [b for i, b in enumerate(bullets) if i not in to_remove]

        logger.info(
            f"Deduplicated {len(bullets)} bullets to {len(deduplicated)} "
            f"(removed {len(to_remove)})"
        )

        return deduplicated

    def _should_keep_first(
        self,
        bullet1: Bullet,
        bullet2: Bullet,
        strategy: str,
    ) -> bool:
        """
        Decide which bullet to keep based on strategy.

        Args:
            bullet1: First bullet
            bullet2: Second bullet
            strategy: Preservation strategy

        Returns:
            True if should keep bullet1, False for bullet2
        """
        if strategy == "highest_ratio":
            ratio1 = self._helpful_ratio(bullet1)
            ratio2 = self._helpful_ratio(bullet2)
            return ratio1 >= ratio2

        elif strategy == "most_recent":
            return bullet1.created_at >= bullet2.created_at

        elif strategy == "most_used":
            count1 = bullet1.helpful_count + bullet1.harmful_count
            count2 = bullet2.helpful_count + bullet2.harmful_count
            return count1 >= count2

        else:
            logger.warning(f"Unknown strategy '{strategy}', using highest_ratio")
            return self._should_keep_first(bullet1, bullet2, "highest_ratio")

    @staticmethod
    def _helpful_ratio(bullet: Bullet) -> float:
        """Calculate helpful/(helpful+harmful) ratio."""
        total = bullet.helpful_count + bullet.harmful_count
        if total == 0:
            return 0.5  # Neutral for bullets with no feedback
        return bullet.helpful_count / total

    @staticmethod
    def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        """
        Calculate cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity (0-1)
        """
        v1 = np.array(vec1)
        v2 = np.array(vec2)

        # Handle zero vectors
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(np.dot(v1, v2) / (norm1 * norm2))

    @staticmethod
    def _exact_match(content1: str, content2: str) -> bool:
        """Check if two content strings are exact matches (case-insensitive)."""
        return content1.strip().lower() == content2.strip().lower()

    def get_duplicate_groups(
        self,
        bullets: list[Bullet],
    ) -> list[list[int]]:
        """
        Group bullets into duplicate clusters.

        Args:
            bullets: List of bullets

        Returns:
            List of groups, where each group is a list of bullet indices
        """
        duplicates = self.find_duplicates(bullets)

        # Build adjacency list
        groups: dict[int, set[int]] = {}

        for i, j, _ in duplicates:
            if i not in groups:
                groups[i] = {i}
            if j not in groups:
                groups[j] = {j}

            # Merge groups
            groups[i].add(j)
            groups[j].add(i)
            groups[i] |= groups[j]
            groups[j] = groups[i]

        # Extract unique groups
        seen = set()
        unique_groups = []

        for group in groups.values():
            group_tuple = tuple(sorted(group))
            if group_tuple not in seen:
                seen.add(group_tuple)
                unique_groups.append(list(group))

        logger.info(f"Found {len(unique_groups)} duplicate groups")
        return unique_groups
