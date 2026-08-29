"""Human feedback loop for calibrating automated evaluation scores.

Bead: ace_enterprise-e98

Humans rate evaluation outputs on a 1-5 scale.  FeedbackCollector stores
those ratings, blends them with automated scores, and exposes drift metrics
so callers can detect when automated scoring diverges from human judgement.
"""

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

# Expertise weights applied when blending feedback from different provider roles.
ROLE_WEIGHTS: dict[str, float] = {
    "developer": 1.0,
    "reviewer": 1.5,
    "expert": 2.0,
    "manager": 0.5,
}

# Feedback weight grows with sample count, capped at this fraction of the
# blended score so a single data point cannot dominate.
MAX_FEEDBACK_WEIGHT = 0.5
FEEDBACK_WEIGHT_RAMP = 10  # full weight reached at this many feedbacks

# Exponential recency decay: weight halves every RECENCY_HALF_LIFE_DAYS days.
RECENCY_HALF_LIFE_DAYS = 30


@dataclass
class HumanFeedback:
    """A single human quality rating for an evaluated output."""

    evaluation_id: str
    rating: int              # 1-5
    provider_id: str
    provider_role: str       # developer | reviewer | expert | manager | ...
    comment: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class FeedbackCollector:
    """Stores human ratings and derives blended / drift scores.

    All scores are on a 0-100 scale internally.  Human ratings (1-5) are
    mapped to 0-100 via  (rating - 1) / 4 * 100  before any calculation.
    """

    def __init__(self) -> None:
        self._store: dict[str, list[HumanFeedback]] = {}

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def submit(
        self,
        evaluation_id: str,
        rating: int,
        provider_id: str,
        provider_role: str,
        comment: str | None = None,
        timestamp: datetime | None = None,
    ) -> HumanFeedback:
        """Record a human rating for an evaluation result.

        Raises:
            ValueError: if rating is not in [1, 5].
        """
        if rating < 1 or rating > 5:
            raise ValueError(f"rating must be 1-5, got {rating}")

        fb = HumanFeedback(
            evaluation_id=evaluation_id,
            rating=rating,
            provider_id=provider_id,
            provider_role=provider_role,
            comment=comment,
            timestamp=timestamp or datetime.now(UTC),
        )
        self._store.setdefault(evaluation_id, []).append(fb)
        return fb

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_feedback(self, evaluation_id: str) -> list[HumanFeedback]:
        """Return all feedback for a specific evaluation, oldest first."""
        return list(self._store.get(evaluation_id, []))

    def get_all_feedback(self) -> list[HumanFeedback]:
        """Return all stored feedback across all evaluations."""
        return [fb for fbs in self._store.values() for fb in fbs]

    def has_feedback(self, evaluation_id: str) -> bool:
        return bool(self._store.get(evaluation_id))

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def blended_score(
        self,
        automated_score: float,
        evaluation_id: str,
        now: datetime | None = None,
    ) -> float:
        """Blend automated score with human feedback for evaluation_id.

        When no feedback exists the automated_score is returned unchanged.
        As feedback accumulates the human signal gains up to MAX_FEEDBACK_WEIGHT
        of the blended score.  Individual ratings are weighted by provider role
        and recency.

        Args:
            automated_score: 0-100 automated quality score.
            evaluation_id:   opaque identifier matching HumanFeedback.evaluation_id.
            now:             reference time for recency decay (defaults to UTC now).

        Returns:
            Blended score in [0, 100].
        """
        feedbacks = self.get_feedback(evaluation_id)
        if not feedbacks:
            return automated_score

        now = now or datetime.now(UTC)
        weighted_sum = 0.0
        total_weight = 0.0

        for fb in feedbacks:
            role_w = ROLE_WEIGHTS.get(fb.provider_role, 1.0)
            age_days = max(0.0, (now - fb.timestamp).total_seconds() / 86400)
            recency_w = math.exp(-age_days * math.log(2) / RECENCY_HALF_LIFE_DAYS)
            w = role_w * recency_w
            human_score = (fb.rating - 1) / 4 * 100
            weighted_sum += w * human_score
            total_weight += w

        if total_weight == 0:
            return automated_score

        avg_human = weighted_sum / total_weight
        # Feedback weight scales with effective evidence mass (decayed-weighted sum),
        # so stale feedback naturally carries less influence than fresh feedback.
        feedback_weight = min(MAX_FEEDBACK_WEIGHT, total_weight / FEEDBACK_WEIGHT_RAMP * MAX_FEEDBACK_WEIGHT)
        blended = (1.0 - feedback_weight) * automated_score + feedback_weight * avg_human
        return max(0.0, min(100.0, blended))

    def aggregated_rating(self, evaluation_id: str) -> float | None:
        """Simple unweighted mean of 1-5 ratings, or None if no feedback."""
        feedbacks = self.get_feedback(evaluation_id)
        if not feedbacks:
            return None
        return sum(fb.rating for fb in feedbacks) / len(feedbacks)

    # ------------------------------------------------------------------
    # Drift detection
    # ------------------------------------------------------------------

    def detect_drift(
        self,
        automated_score: float,
        evaluation_id: str,
        now: datetime | None = None,
    ) -> float:
        """Return (weighted_human_score_0_100 - automated_score).

        Positive = humans rate it higher than automation.
        Negative = humans rate it lower.
        Zero     = no feedback or perfect agreement.
        """
        feedbacks = self.get_feedback(evaluation_id)
        if not feedbacks:
            return 0.0

        now = now or datetime.now(UTC)
        weighted_sum = 0.0
        total_weight = 0.0

        for fb in feedbacks:
            role_w = ROLE_WEIGHTS.get(fb.provider_role, 1.0)
            age_days = max(0.0, (now - fb.timestamp).total_seconds() / 86400)
            recency_w = math.exp(-age_days * math.log(2) / RECENCY_HALF_LIFE_DAYS)
            w = role_w * recency_w
            weighted_sum += w * (fb.rating - 1) / 4 * 100
            total_weight += w

        if total_weight == 0:
            return 0.0

        return (weighted_sum / total_weight) - automated_score

    def drift_report(
        self,
        automated_scores: dict[str, float],
        now: datetime | None = None,
    ) -> dict[str, float]:
        """Compute drift for every evaluation_id that has both feedback and
        an automated_score entry.

        Args:
            automated_scores: mapping of evaluation_id → 0-100 score.

        Returns:
            Dict of evaluation_id → drift value.
        """
        return {
            eid: self.detect_drift(automated_scores[eid], eid, now)
            for eid in automated_scores
            if self.has_feedback(eid)
        }
