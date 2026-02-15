"""
CGR³ retrieval schemas.

Defines the data structures for context-aware knowledge retrieval.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from src.storage.schemas import Bullet


class ReasoningVerdict(str, Enum):
    """
    Verdict from the Reason phase of CGR³.

    Determines whether a retrieved pattern should be applied.
    """

    APPLY = "apply"
    """Sufficient context match - safe to use this pattern."""

    ASK_FIRST = "ask_first"
    """Missing context - clarify before applying."""

    SKIP = "skip"
    """Context mismatch - don't use this pattern."""


@dataclass
class RetrievalContext:
    """
    Context for the current retrieval request.

    Provides information about the requestor's environment to enable
    context-aware ranking and reasoning.
    """

    # Who is asking?
    team_id: Optional[str] = None
    user_id: Optional[str] = None

    # What project/codebase?
    project_id: Optional[str] = None
    project_path: Optional[str] = None

    # What tech stack?
    tech_stack: dict[str, str] = field(default_factory=dict)
    """e.g., {"python": "3.11", "framework": "fastapi", "testing": "pytest"}"""

    # When?
    query_timestamp: datetime = field(default_factory=datetime.utcnow)

    # What domain?
    domain: Optional[str] = None
    """e.g., "fintech", "healthcare", "ml-ops" """

    # Session context
    session_id: Optional[str] = None
    """Current conversation/session ID for continuity."""


@dataclass
class ContextGap:
    """Describes a gap in context that affects pattern applicability."""

    dimension: str
    """Which context dimension has the gap: 'temporal', 'team', 'tech_stack', 'project'"""

    description: str
    """Human-readable description of the gap."""

    severity: float
    """How much this gap affects confidence (0.0-1.0)."""


@dataclass
class RankedBullet:
    """
    A bullet with context-aware ranking from CGR³.

    Extends semantic similarity with context scoring and reasoning verdict.
    """

    bullet: Bullet
    """The retrieved bullet."""

    # Scores
    semantic_score: float
    """Score from semantic/embedding similarity (0.0-1.0)."""

    context_score: float
    """Score from context match (0.0-1.0)."""

    combined_score: float
    """Weighted combination of semantic and context scores."""

    # Context analysis
    context_gaps: list[ContextGap] = field(default_factory=list)
    """What context is missing or mismatched?"""

    # Reasoning verdict
    verdict: ReasoningVerdict = ReasoningVerdict.APPLY
    """Should this pattern be applied?"""

    # Explanation
    reasoning: Optional[str] = None
    """Why this verdict was reached."""


@dataclass
class KnowledgeResponse:
    """
    Response from the InstitutionalKnowledgeService.

    Provides categorized results based on CGR³ reasoning.
    """

    # Patterns safe to apply
    apply: list[RankedBullet] = field(default_factory=list)
    """Patterns with sufficient context match."""

    # Patterns that need clarification
    ask_first: list[RankedBullet] = field(default_factory=list)
    """Patterns with context gaps - ask before applying."""

    # Total candidates considered
    total_candidates: int = 0

    # Query metadata
    query: str = ""
    context: Optional[RetrievalContext] = None
    retrieval_time_ms: float = 0.0

    @property
    def has_results(self) -> bool:
        """Whether any applicable patterns were found."""
        return len(self.apply) > 0 or len(self.ask_first) > 0

    @property
    def questions(self) -> list[str]:
        """Generate clarifying questions for ASK_FIRST patterns."""
        questions = []
        for rb in self.ask_first:
            gaps = ", ".join(g.description for g in rb.context_gaps)
            preview = rb.bullet.content[:50] + "..." if len(rb.bullet.content) > 50 else rb.bullet.content
            questions.append(f"Pattern '{preview}' may apply, but: {gaps}")
        return questions
