"""
Context scoring functions for CGR³.

Each function scores how well a bullet matches the request context
along a specific dimension (temporal, team, tech stack, project).
"""

import logging
from datetime import UTC, datetime

from src.retrieval.schemas import ContextGap, RetrievalContext
from src.storage.schemas import Bullet

logger = logging.getLogger(__name__)


class ContextScorer:
    """
    Scores bullets against request context across multiple dimensions.

    Each dimension contributes a score (0.0-1.0) and optionally a context gap
    that explains why the score is low.
    """

    # Default weights for each dimension
    DEFAULT_WEIGHTS = {
        "temporal": 0.25,
        "team": 0.25,
        "tech_stack": 0.30,
        "project": 0.20,
    }

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        temporal_decay_days: int = 365,
    ):
        """
        Initialize the context scorer.

        Args:
            weights: Custom weights for each dimension (must sum to ~1.0)
            temporal_decay_days: Days after which temporal score starts decaying
        """
        self.weights = weights or self.DEFAULT_WEIGHTS
        self.temporal_decay_days = temporal_decay_days

    def score(
        self,
        bullet: Bullet,
        context: RetrievalContext,
    ) -> tuple[float, list[ContextGap]]:
        """
        Score a bullet against the request context.

        Args:
            bullet: The bullet to score
            context: The request context

        Returns:
            (combined_score, list_of_context_gaps)
        """
        scores = {}
        gaps = []

        # Score each dimension
        score, gap = self.score_temporal(bullet, context)
        scores["temporal"] = score
        if gap:
            gaps.append(gap)

        score, gap = self.score_team(bullet, context)
        scores["team"] = score
        if gap:
            gaps.append(gap)

        score, gap = self.score_tech_stack(bullet, context)
        scores["tech_stack"] = score
        if gap:
            gaps.append(gap)

        score, gap = self.score_project(bullet, context)
        scores["project"] = score
        if gap:
            gaps.append(gap)

        # Compute weighted combination
        combined = sum(
            scores[dim] * self.weights.get(dim, 0.0)
            for dim in scores
        )

        return combined, gaps

    def score_temporal(
        self,
        bullet: Bullet,
        context: RetrievalContext,
    ) -> tuple[float, ContextGap | None]:
        """
        Score temporal validity.

        Checks:
        - Is the pattern within its valid_from/valid_until window?
        - How old is the pattern? (temporal decay)
        - Does temporal_confidence indicate reliability?
        """
        now = context.query_timestamp or datetime.now(UTC)

        # Check validity window
        if bullet.valid_from and bullet.valid_from > now:
            return 0.0, ContextGap(
                dimension="temporal",
                description=f"Pattern not yet valid (starts {bullet.valid_from.date()})",
                severity=1.0,
            )

        if bullet.valid_until and bullet.valid_until < now:
            return 0.0, ContextGap(
                dimension="temporal",
                description=f"Pattern expired ({bullet.valid_until.date()})",
                severity=1.0,
            )

        # Calculate age-based decay
        age_days = (now - bullet.created_at).days if bullet.created_at else 0

        if age_days > self.temporal_decay_days * 2:
            # Very old pattern
            age_score = 0.3
            gap = ContextGap(
                dimension="temporal",
                description=f"Pattern is {age_days} days old",
                severity=0.5,
            )
        elif age_days > self.temporal_decay_days:
            # Moderately old
            age_score = 0.6
            gap = ContextGap(
                dimension="temporal",
                description=f"Pattern is {age_days} days old",
                severity=0.3,
            )
        else:
            # Recent
            age_score = 1.0
            gap = None

        # Factor in bullet's temporal_confidence
        bullet_confidence = getattr(bullet, 'temporal_confidence', 1.0) or 1.0

        final_score = age_score * bullet_confidence
        return final_score, gap

    def score_team(
        self,
        bullet: Bullet,
        context: RetrievalContext,
    ) -> tuple[float, ContextGap | None]:
        """
        Score team locality.

        Patterns from the same team get higher scores.
        """
        if not context.team_id:
            # No team context provided - neutral score
            return 0.5, None

        bullet_team = getattr(bullet, 'team_id', None)

        if not bullet_team:
            # Bullet has no team - could be global/shared
            return 0.5, None

        if bullet_team == context.team_id:
            # Same team - full score
            return 1.0, None

        # Different team
        return 0.3, ContextGap(
            dimension="team",
            description=f"Pattern from team '{bullet_team}', you're in '{context.team_id}'",
            severity=0.4,
        )

    def score_tech_stack(
        self,
        bullet: Bullet,
        context: RetrievalContext,
    ) -> tuple[float, ContextGap | None]:
        """
        Score tech stack compatibility.

        Compares bullet's tech_context against request's tech_stack.
        """
        if not context.tech_stack:
            return 0.5, ContextGap(
                dimension="tech_stack",
                description="Tech stack unknown - can't verify compatibility",
                severity=0.2,
            )

        bullet_tech = getattr(bullet, 'tech_context', None)

        if not bullet_tech:
            # Bullet has no tech requirements - might be generic
            # Check tags as fallback
            tech_tags = set(context.tech_stack.keys())
            bullet_tags = set(bullet.tags) if bullet.tags else set()

            if tech_tags & bullet_tags:
                return 0.7, None  # Some overlap in tags
            return 0.5, None  # No info

        # Compare tech requirements
        matches = 0
        mismatches = []

        for tech, version in bullet_tech.items():
            if tech in context.tech_stack:
                # TODO: Proper version comparison (semver)
                if self._version_compatible(context.tech_stack[tech], version):
                    matches += 1
                else:
                    mismatches.append(f"{tech}: need {version}, have {context.tech_stack[tech]}")
            else:
                mismatches.append(f"{tech}: required but not in your stack")

        if not bullet_tech:
            return 0.5, None

        score = matches / len(bullet_tech) if bullet_tech else 0.5

        if mismatches:
            return score, ContextGap(
                dimension="tech_stack",
                description="; ".join(mismatches[:2]),  # Limit to 2
                severity=1.0 - score,
            )

        return score, None

    def _version_compatible(self, have: str, need: str) -> bool:
        """
        Check if 'have' version satisfies 'need' requirement.

        Simple implementation - just checks prefix match for now.
        TODO: Proper semver comparison.
        """
        # Handle comparison operators
        if need.startswith(">="):
            need_version = need[2:]
            return have >= need_version
        elif need.startswith(">"):
            need_version = need[1:]
            return have > need_version
        elif need.startswith("<="):
            need_version = need[2:]
            return have <= need_version
        elif need.startswith("<"):
            need_version = need[1:]
            return have < need_version
        elif need.startswith("=="):
            need_version = need[2:]
            return have == need_version
        else:
            # Exact or prefix match
            return have.startswith(need.split(".")[0])

    def score_project(
        self,
        bullet: Bullet,
        context: RetrievalContext,
    ) -> tuple[float, ContextGap | None]:
        """
        Score project relevance.

        Patterns used in the same project get higher scores.
        """
        if not context.project_id:
            return 0.5, None

        bullet_projects = getattr(bullet, 'project_ids', None)

        if not bullet_projects:
            return 0.5, None

        if context.project_id in bullet_projects:
            # Same project - full score
            return 1.0, None

        # Different project - check if domains overlap
        bullet_domains = getattr(bullet, 'applicable_domains', None)
        if bullet_domains and context.domain and context.domain in bullet_domains:
            return 0.7, None  # Same domain

        return 0.4, ContextGap(
            dimension="project",
            description="Pattern from different project",
            severity=0.3,
        )

    def score_domain(
        self,
        bullet: Bullet,
        context: RetrievalContext,
    ) -> tuple[float, ContextGap | None]:
        """
        Score domain relevance.

        Patterns with matching domain get higher scores.
        """
        if not context.domain:
            return 0.5, None

        bullet_domains = getattr(bullet, 'applicable_domains', None)

        if not bullet_domains:
            # Check tags as fallback
            if bullet.tags and context.domain in bullet.tags:
                return 0.8, None
            return 0.5, None

        if context.domain in bullet_domains:
            return 1.0, None

        return 0.3, ContextGap(
            dimension="domain",
            description=f"Pattern for domains {bullet_domains}, you're in '{context.domain}'",
            severity=0.4,
        )
