"""
Voting system for ensemble learning.

Implements multiple voting strategies:
- Majority: >50% approval
- Supermajority: ≥66.7% approval
- Weighted: Models vote with earned weights based on accuracy
- Unanimous: 100% approval required
"""
import logging
from abc import ABC, abstractmethod
from typing import Protocol

from src.ensemble.models import (
    ConsensusBullet,
    ModelPerformance,
    Vote,
    VoteType,
)

logger = logging.getLogger(__name__)


class VotingStrategy(ABC):
    """Base class for voting strategies."""

    @abstractmethod
    def decide(
        self,
        bullet: ConsensusBullet,
        model_performance: dict[str, ModelPerformance] | None = None,
    ) -> bool:
        """
        Decide if bullet should be approved based on votes.

        Args:
            bullet: The bullet with votes to decide on
            model_performance: Optional performance data for weighted voting

        Returns:
            True if approved, False if rejected
        """
        pass

    @abstractmethod
    def name(self) -> str:
        """Name of the strategy."""
        pass


class MajorityVoting(VotingStrategy):
    """Simple majority: >50% approval wins."""

    def decide(
        self,
        bullet: ConsensusBullet,
        model_performance: dict[str, ModelPerformance] | None = None,
    ) -> bool:
        """Approve if >50% of votes are APPROVE."""
        counts = bullet.vote_counts
        total_votes = counts[VoteType.APPROVE] + counts[VoteType.REJECT]

        if total_votes == 0:
            return False  # No votes = reject

        approval_rate = counts[VoteType.APPROVE] / total_votes
        return approval_rate > 0.5

    def name(self) -> str:
        return "majority"


class SupermajorityVoting(VotingStrategy):
    """Supermajority: ≥66.7% (2/3) approval required."""

    def __init__(self, threshold: float = 0.667):
        """
        Args:
            threshold: Approval threshold (default 2/3)
        """
        self.threshold = threshold

    def decide(
        self,
        bullet: ConsensusBullet,
        model_performance: dict[str, ModelPerformance] | None = None,
    ) -> bool:
        """Approve if ≥threshold of votes are APPROVE."""
        counts = bullet.vote_counts
        total_votes = counts[VoteType.APPROVE] + counts[VoteType.REJECT]

        if total_votes == 0:
            return False

        approval_rate = counts[VoteType.APPROVE] / total_votes
        return approval_rate >= self.threshold

    def name(self) -> str:
        return f"supermajority_{int(self.threshold * 100)}"


class WeightedVoting(VotingStrategy):
    """Weighted voting: Models vote with weight based on their accuracy."""

    def __init__(self, threshold: float = 0.5):
        """
        Args:
            threshold: Weighted approval threshold (default 0.5)
        """
        self.threshold = threshold

    def decide(
        self,
        bullet: ConsensusBullet,
        model_performance: dict[str, ModelPerformance] | None = None,
    ) -> bool:
        """Approve if weighted approval ≥ threshold."""
        if not model_performance:
            # Fallback to simple majority if no performance data
            logger.warning("No performance data for weighted voting, using majority")
            return MajorityVoting().decide(bullet)

        weighted_approval = 0.0
        weighted_rejection = 0.0

        for vote in bullet.votes:
            perf = model_performance.get(vote.model_id)
            if not perf:
                weight = 1.0  # Default weight for unknown models
            else:
                weight = perf.voting_weight

            if vote.vote == VoteType.APPROVE:
                weighted_approval += weight
            elif vote.vote == VoteType.REJECT:
                weighted_rejection += weight

        total_weight = weighted_approval + weighted_rejection
        if total_weight == 0:
            return False

        approval_rate = weighted_approval / total_weight
        return approval_rate >= self.threshold

    def name(self) -> str:
        return "weighted"


class UnanimousVoting(VotingStrategy):
    """Unanimous: 100% approval required (no rejections)."""

    def decide(
        self,
        bullet: ConsensusBullet,
        model_performance: dict[str, ModelPerformance] | None = None,
    ) -> bool:
        """Approve only if ALL votes are APPROVE (no REJECT votes)."""
        counts = bullet.vote_counts

        # Must have at least one vote
        if counts[VoteType.APPROVE] == 0:
            return False

        # No rejections allowed
        return counts[VoteType.REJECT] == 0

    def name(self) -> str:
        return "unanimous"


class EscalatingVoting(VotingStrategy):
    """
    Escalating thresholds: Start strict, loosen over time.

    Useful for time-boxed deliberation where we need to force a decision.
    """

    def __init__(
        self,
        initial_threshold: float = 0.75,
        final_threshold: float = 0.5,
        max_rounds: int = 3,
    ):
        """
        Args:
            initial_threshold: Starting threshold (strict)
            final_threshold: Final threshold (lenient)
            max_rounds: Number of deliberation rounds before reaching final threshold
        """
        self.initial_threshold = initial_threshold
        self.final_threshold = final_threshold
        self.max_rounds = max_rounds

    def decide(
        self,
        bullet: ConsensusBullet,
        model_performance: dict[str, ModelPerformance] | None = None,
    ) -> bool:
        """Approve based on escalating threshold."""
        # Calculate current threshold based on deliberation rounds
        if bullet.deliberation_rounds >= self.max_rounds:
            threshold = self.final_threshold
        else:
            # Linear interpolation between thresholds
            progress = bullet.deliberation_rounds / self.max_rounds
            threshold = self.initial_threshold - (
                self.initial_threshold - self.final_threshold
            ) * progress

        counts = bullet.vote_counts
        total_votes = counts[VoteType.APPROVE] + counts[VoteType.REJECT]

        if total_votes == 0:
            return False

        approval_rate = counts[VoteType.APPROVE] / total_votes
        approved = approval_rate >= threshold

        logger.debug(
            f"Escalating vote: round {bullet.deliberation_rounds}, "
            f"threshold {threshold:.1%}, approval {approval_rate:.1%} -> {approved}"
        )

        return approved

    def name(self) -> str:
        return "escalating"


class VotingSystem:
    """
    Main voting system that can apply different strategies.
    """

    def __init__(self, strategy: VotingStrategy | None = None):
        """
        Args:
            strategy: Voting strategy to use (default: majority)
        """
        self.strategy = strategy or MajorityVoting()

    def vote_on_bullets(
        self,
        bullets: list[ConsensusBullet],
        model_performance: dict[str, ModelPerformance] | None = None,
    ) -> tuple[list[ConsensusBullet], list[ConsensusBullet]]:
        """
        Apply voting strategy to all bullets.

        Args:
            bullets: List of bullets to vote on
            model_performance: Optional model performance data

        Returns:
            Tuple of (approved_bullets, rejected_bullets)
        """
        approved = []
        rejected = []

        for bullet in bullets:
            if not bullet.votes:
                logger.warning(f"Bullet has no votes, rejecting: {bullet.content[:50]}")
                bullet.approved = False
                bullet.approval_strategy = "no_votes"
                rejected.append(bullet)
                continue

            # Apply voting strategy
            is_approved = self.strategy.decide(bullet, model_performance)

            bullet.approved = is_approved
            bullet.approval_strategy = self.strategy.name()

            if is_approved:
                approved.append(bullet)
            else:
                rejected.append(bullet)

        logger.info(
            f"Voting complete: {len(approved)} approved, {len(rejected)} rejected "
            f"(strategy: {self.strategy.name()})"
        )

        return approved, rejected

    def get_contested_bullets(
        self,
        bullets: list[ConsensusBullet],
        min_approval: float = 0.4,
        max_approval: float = 0.6,
    ) -> list[ConsensusBullet]:
        """
        Find bullets with close votes (indicating disagreement).

        Args:
            bullets: Bullets to analyze
            min_approval: Minimum approval rate for "contested"
            max_approval: Maximum approval rate for "contested"

        Returns:
            List of bullets with approval rates between min and max
        """
        contested = []

        for bullet in bullets:
            rate = bullet.approval_rate
            if min_approval <= rate <= max_approval:
                contested.append(bullet)

        logger.info(
            f"Found {len(contested)} contested bullets "
            f"({min_approval:.0%}-{max_approval:.0%} approval)"
        )

        return contested

    def analyze_disagreement(
        self, bullets: list[ConsensusBullet]
    ) -> dict[str, float]:
        """
        Analyze voting patterns for disagreement metrics.

        Returns:
            Dict with disagreement statistics
        """
        if not bullets:
            return {}

        unanimous_count = 0
        highly_contested_count = 0
        approval_rates = []

        for bullet in bullets:
            rate = bullet.approval_rate
            approval_rates.append(rate)

            # Unanimous = 0% or 100%
            if rate == 0.0 or rate == 1.0:
                unanimous_count += 1

            # Highly contested = 40-60%
            if 0.4 <= rate <= 0.6:
                highly_contested_count += 1

        return {
            "total_bullets": len(bullets),
            "unanimous": unanimous_count,
            "highly_contested": highly_contested_count,
            "avg_approval_rate": sum(approval_rates) / len(approval_rates),
            "min_approval_rate": min(approval_rates),
            "max_approval_rate": max(approval_rates),
        }
