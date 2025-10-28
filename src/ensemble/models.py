"""
Data models for ensemble learning system.

Defines the core data structures for multi-model consensus building:
- ConsensusBullet: Bullet with voting metadata
- Vote: Individual model vote with reasoning
- VoteResults: Aggregated voting results
- EnsembleResult: Complete ensemble learning outcome
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class VoteType(str, Enum):
    """Types of votes a model can cast."""
    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


class BulletSection(str, Enum):
    """Playbook sections for organizing bullets."""
    STRATEGIES = "strategies_and_hard_rules"
    CODE_SNIPPETS = "code_snippets"
    TROUBLESHOOTING = "troubleshooting_tips"
    DOMAIN = "domain_knowledge"


@dataclass
class Vote:
    """A single model's vote on a proposed bullet."""

    model_id: str  # Which model cast this vote
    vote: VoteType  # approve/reject/abstain
    reasoning: str  # Why did the model vote this way?
    confidence: float  # 0.0-1.0, how confident is the model?
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Validate vote data."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0.0-1.0, got {self.confidence}")


@dataclass
class ConsensusBullet:
    """A proposed bullet with voting metadata."""

    # Bullet content
    content: str
    section: BulletSection

    # Proposing model
    proposed_by: str  # model_id of proposer
    proposal_reasoning: str  # Why did the model propose this?

    # Optional fields with defaults
    tags: list[str] = field(default_factory=list)

    # Voting results
    votes: list[Vote] = field(default_factory=list)

    # Consensus metadata
    approved: Optional[bool] = None  # None = pending, True/False = decided
    approval_strategy: Optional[str] = None  # Which strategy approved it?
    deliberation_rounds: int = 0  # How many discussion rounds?

    # Similarity clustering
    similar_bullets: list[str] = field(default_factory=list)  # IDs of similar proposals
    cluster_id: Optional[str] = None  # Which cluster does this belong to?

    # Timestamps
    proposed_at: datetime = field(default_factory=datetime.now)
    decided_at: Optional[datetime] = None

    @property
    def vote_counts(self) -> dict[VoteType, int]:
        """Count votes by type."""
        counts = {VoteType.APPROVE: 0, VoteType.REJECT: 0, VoteType.ABSTAIN: 0}
        for vote in self.votes:
            counts[vote.vote] += 1
        return counts

    @property
    def approval_rate(self) -> float:
        """Calculate percentage of approvals (excluding abstentions)."""
        counts = self.vote_counts
        total_votes = counts[VoteType.APPROVE] + counts[VoteType.REJECT]
        if total_votes == 0:
            return 0.0
        return counts[VoteType.APPROVE] / total_votes

    @property
    def avg_confidence(self) -> float:
        """Average confidence across all votes."""
        if not self.votes:
            return 0.0
        return sum(v.confidence for v in self.votes) / len(self.votes)

    def add_vote(self, vote: Vote, allow_update: bool = False) -> None:
        """
        Add a vote from a model.

        Args:
            vote: Vote to add
            allow_update: If True, allows updating an existing vote (for deliberation)
        """
        # Check if this model already voted
        existing_idx = None
        for i, v in enumerate(self.votes):
            if v.model_id == vote.model_id:
                existing_idx = i
                break

        if existing_idx is not None:
            if allow_update:
                # Replace existing vote (deliberation round)
                self.votes[existing_idx] = vote
            else:
                raise ValueError(f"Model {vote.model_id} already voted on this bullet")
        else:
            self.votes.append(vote)

    def get_vote(self, model_id: str) -> Optional[Vote]:
        """Get a specific model's vote on this bullet."""
        for vote in self.votes:
            if vote.model_id == model_id:
                return vote
        return None

    def is_contested(self, threshold_low: float = 0.4, threshold_high: float = 0.6) -> bool:
        """
        Check if this bullet is contested (approval rate in middle range).

        Args:
            threshold_low: Lower bound for contested range (default 40%)
            threshold_high: Upper bound for contested range (default 60%)

        Returns:
            True if approval rate is between thresholds
        """
        if len(self.votes) < 2:
            return False  # Need at least 2 votes to be contested

        approval = self.approval_rate
        return threshold_low <= approval <= threshold_high


@dataclass
class VoteResults:
    """Aggregated results from voting on multiple bullets."""

    total_bullets: int
    approved: int
    rejected: int
    pending: int

    # Breakdown by strategy
    majority_approved: int = 0
    supermajority_approved: int = 0
    weighted_approved: int = 0
    unanimous_approved: int = 0

    # Quality metrics
    avg_approval_rate: float = 0.0
    avg_confidence: float = 0.0
    avg_deliberation_rounds: float = 0.0

    # Disagreement analysis
    highly_contested: int = 0  # Close votes (40-60% approval)
    unanimous_decisions: int = 0  # 100% agreement

    @property
    def approval_percentage(self) -> float:
        """Percentage of bullets approved."""
        if self.total_bullets == 0:
            return 0.0
        return (self.approved / self.total_bullets) * 100


@dataclass
class ModelPerformance:
    """Track individual model's performance in ensemble."""

    model_id: str

    # Proposal metrics
    proposals_made: int = 0
    proposals_approved: int = 0
    proposals_rejected: int = 0

    # Voting metrics
    votes_cast: int = 0
    votes_with_majority: int = 0  # How often did model agree with final decision?
    avg_confidence: float = 0.0

    # Quality indicators
    accuracy_score: float = 0.0  # Based on comparison with final consensus
    voting_weight: float = 1.0  # Weight for weighted voting (earned through accuracy)

    @property
    def proposal_success_rate(self) -> float:
        """Percentage of proposals that got approved."""
        if self.proposals_made == 0:
            return 0.0
        return (self.proposals_approved / self.proposals_made) * 100

    @property
    def agreement_rate(self) -> float:
        """How often model agrees with final consensus."""
        if self.votes_cast == 0:
            return 0.0
        return (self.votes_with_majority / self.votes_cast) * 100


@dataclass
class EnsembleResult:
    """Complete result from ensemble learning session."""

    # Input configuration
    task_description: str
    models_used: list[str]
    voting_strategy: str

    # Bullet results
    bullets: list[ConsensusBullet]
    vote_results: VoteResults

    # Model performance
    model_performance: dict[str, ModelPerformance]

    # Timing
    started_at: datetime
    completed_at: datetime

    # Quality metrics
    diversity_score: float = 0.0  # How different were the models' proposals?
    consensus_strength: float = 0.0  # How strong was the agreement?

    @property
    def duration_seconds(self) -> float:
        """Total time for ensemble learning."""
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def approved_bullets(self) -> list[ConsensusBullet]:
        """Get only the approved bullets."""
        return [b for b in self.bullets if b.approved is True]

    @property
    def rejected_bullets(self) -> list[ConsensusBullet]:
        """Get only the rejected bullets."""
        return [b for b in self.bullets if b.approved is False]

    @property
    def pending_bullets(self) -> list[ConsensusBullet]:
        """Get bullets still pending decision."""
        return [b for b in self.bullets if b.approved is None]

    def get_bullets_by_section(self, section: BulletSection) -> list[ConsensusBullet]:
        """Get approved bullets for a specific section."""
        return [b for b in self.approved_bullets if b.section == section]

    def summary(self) -> str:
        """Generate human-readable summary."""
        return f"""
Ensemble Learning Results
========================
Task: {self.task_description}
Models: {', '.join(self.models_used)}
Strategy: {self.voting_strategy}

Bullets:
  Total: {self.vote_results.total_bullets}
  Approved: {self.vote_results.approved} ({self.vote_results.approval_percentage:.1f}%)
  Rejected: {self.vote_results.rejected}
  Pending: {self.vote_results.pending}

Quality:
  Avg Approval Rate: {self.vote_results.avg_approval_rate:.1%}
  Avg Confidence: {self.vote_results.avg_confidence:.1%}
  Consensus Strength: {self.consensus_strength:.1%}
  Diversity Score: {self.diversity_score:.2f}

Timing:
  Duration: {self.duration_seconds:.1f}s
  Avg Deliberation Rounds: {self.vote_results.avg_deliberation_rounds:.1f}

Top Performer:
  {max(self.model_performance.items(), key=lambda x: x[1].accuracy_score)[0]}
        """.strip()
