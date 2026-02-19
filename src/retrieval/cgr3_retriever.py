"""
CGR³ Context Graph Retriever.

Implements the Retrieve → Rank → Reason pipeline for context-aware
knowledge retrieval.
"""

import logging
import time

from src.playbook.retrieval import BulletRetriever
from src.retrieval.context_scorer import ContextScorer
from src.retrieval.schemas import (
    ContextGap,
    KnowledgeResponse,
    RankedBullet,
    ReasoningVerdict,
    RetrievalContext,
)
from src.storage.schemas import Bullet

logger = logging.getLogger(__name__)


class ContextGraphRetriever:
    """
    CGR³: Context Graph Retrieve-Rank-Reason.

    Extends semantic retrieval with context-aware ranking and
    sufficiency reasoning.

    The pipeline:
    1. RETRIEVE: Get candidates by semantic similarity (existing BulletRetriever)
    2. RANK: Re-rank by context match (team, project, tech stack, temporal)
    3. REASON: Determine if context is sufficient to apply each pattern

    Usage:
        retriever = ContextGraphRetriever(base_retriever)
        response = retriever.retrieve(
            query="handle auth timeout",
            bullets=bullets,
            context=RetrievalContext(
                team_id="payments",
                tech_stack={"python": "3.11", "framework": "fastapi"},
            )
        )

        for rb in response.apply:
            # These patterns are safe to use
            print(rb.bullet.content)

        for rb in response.ask_first:
            # These need clarification
            print(f"Pattern may apply, but: {rb.context_gaps}")
    """

    def __init__(
        self,
        base_retriever: BulletRetriever | None = None,
        context_scorer: ContextScorer | None = None,
        context_weight: float = 0.4,
        min_context_score: float = 0.3,
        skip_threshold: float = 0.15,
        max_gaps_for_apply: int = 0,
        max_gaps_for_ask: int = 2,
    ):
        """
        Initialize the CGR³ retriever.

        Args:
            base_retriever: Underlying semantic retriever (default: new BulletRetriever)
            context_scorer: Context scoring engine (default: new ContextScorer)
            context_weight: How much context affects ranking (0.0-1.0)
            min_context_score: Below this, verdict = ASK_FIRST
            skip_threshold: Below this, verdict = SKIP
            max_gaps_for_apply: Max context gaps for APPLY verdict
            max_gaps_for_ask: Max context gaps for ASK_FIRST (more = SKIP)
        """
        self.base_retriever = base_retriever or BulletRetriever()
        self.context_scorer = context_scorer or ContextScorer()
        self.context_weight = context_weight
        self.min_context_score = min_context_score
        self.skip_threshold = skip_threshold
        self.max_gaps_for_apply = max_gaps_for_apply
        self.max_gaps_for_ask = max_gaps_for_ask

    def retrieve(
        self,
        query: str,
        bullets: list[Bullet],
        context: RetrievalContext | None = None,
        query_embedding: list[float] | None = None,
        top_k: int | None = None,
    ) -> KnowledgeResponse:
        """
        Execute the CGR³ pipeline.

        Args:
            query: Query text
            bullets: Candidate bullets to search
            context: Request context for ranking/reasoning
            query_embedding: Pre-computed query embedding (optional)
            top_k: Override number of results (optional)

        Returns:
            KnowledgeResponse with categorized results
        """
        start_time = time.time()

        # Default context if not provided
        if context is None:
            context = RetrievalContext()

        # ===== RETRIEVE =====
        # Use existing retriever for semantic candidates
        candidates = self.base_retriever.retrieve(
            query=query,
            bullets=bullets,
            query_embedding=query_embedding,
        )

        if not candidates:
            return KnowledgeResponse(
                query=query,
                context=context,
                total_candidates=0,
                retrieval_time_ms=(time.time() - start_time) * 1000,
            )

        # ===== RANK =====
        ranked_bullets = []

        for bullet, semantic_score in candidates:
            # Calculate context match
            context_score, context_gaps = self.context_scorer.score(bullet, context)

            # Combine scores
            combined_score = (
                semantic_score * (1 - self.context_weight) +
                context_score * self.context_weight
            )

            # ===== REASON =====
            verdict, reasoning = self._determine_verdict(
                context_score=context_score,
                context_gaps=context_gaps,
            )

            ranked_bullets.append(RankedBullet(
                bullet=bullet,
                semantic_score=semantic_score,
                context_score=context_score,
                combined_score=combined_score,
                context_gaps=context_gaps,
                verdict=verdict,
                reasoning=reasoning,
            ))

        # Sort by combined score
        ranked_bullets.sort(key=lambda x: x.combined_score, reverse=True)

        # Apply top_k if specified
        if top_k:
            ranked_bullets = ranked_bullets[:top_k]

        # Categorize by verdict
        apply_bullets = [rb for rb in ranked_bullets if rb.verdict == ReasoningVerdict.APPLY]
        ask_first_bullets = [rb for rb in ranked_bullets if rb.verdict == ReasoningVerdict.ASK_FIRST]
        # SKIP bullets are excluded from response

        elapsed_ms = (time.time() - start_time) * 1000

        logger.info(
            f"CGR³ retrieval: {len(candidates)} candidates → "
            f"{len(apply_bullets)} apply, {len(ask_first_bullets)} ask_first, "
            f"{len(ranked_bullets) - len(apply_bullets) - len(ask_first_bullets)} skip "
            f"({elapsed_ms:.1f}ms)"
        )

        return KnowledgeResponse(
            apply=apply_bullets,
            ask_first=ask_first_bullets,
            total_candidates=len(candidates),
            query=query,
            context=context,
            retrieval_time_ms=elapsed_ms,
        )

    def _determine_verdict(
        self,
        context_score: float,
        context_gaps: list[ContextGap],
    ) -> tuple[ReasoningVerdict, str]:
        """
        Reason about whether to apply a pattern.

        This is the key CGR³ innovation: don't just retrieve,
        decide if retrieval is actionable.

        Args:
            context_score: Combined context match score
            context_gaps: List of context gaps/mismatches

        Returns:
            (verdict, reasoning_explanation)
        """
        # Count significant gaps (severity > 0.3)
        significant_gaps = [g for g in context_gaps if g.severity > 0.3]
        num_gaps = len(significant_gaps)

        # Decision logic
        if context_score < self.skip_threshold:
            return (
                ReasoningVerdict.SKIP,
                f"Context score too low ({context_score:.2f} < {self.skip_threshold})"
            )

        if context_score < self.min_context_score:
            gap_summary = "; ".join(g.description for g in significant_gaps[:2])
            return (
                ReasoningVerdict.ASK_FIRST,
                f"Context uncertain: {gap_summary}"
            )

        if num_gaps > self.max_gaps_for_ask:
            return (
                ReasoningVerdict.SKIP,
                f"Too many context gaps ({num_gaps})"
            )

        if num_gaps > self.max_gaps_for_apply:
            gap_summary = "; ".join(g.description for g in significant_gaps[:2])
            return (
                ReasoningVerdict.ASK_FIRST,
                f"Some context gaps: {gap_summary}"
            )

        return (
            ReasoningVerdict.APPLY,
            "Context matches well"
        )

    def retrieve_with_lineage(
        self,
        query: str,
        bullets: list[Bullet],
        context: RetrievalContext | None = None,
        include_superseded: bool = False,
    ) -> KnowledgeResponse:
        """
        Retrieve with lineage-aware filtering.

        Excludes patterns that have been superseded by newer patterns,
        unless explicitly requested.

        Args:
            query: Query text
            bullets: Candidate bullets
            context: Request context
            include_superseded: Whether to include superseded patterns

        Returns:
            KnowledgeResponse with lineage-filtered results
        """
        # TODO: Implement lineage filtering using BulletLineageModel
        # For now, delegate to regular retrieve
        return self.retrieve(query, bullets, context)

    def explain_verdict(self, ranked_bullet: RankedBullet) -> str:
        """
        Generate a human-readable explanation of why a verdict was reached.

        Args:
            ranked_bullet: The ranked bullet to explain

        Returns:
            Explanation string
        """
        rb = ranked_bullet
        lines = [
            f"Pattern: {rb.bullet.content[:60]}...",
            f"Semantic score: {rb.semantic_score:.2f}",
            f"Context score: {rb.context_score:.2f}",
            f"Combined score: {rb.combined_score:.2f}",
            f"Verdict: {rb.verdict.value.upper()}",
        ]

        if rb.context_gaps:
            lines.append("Context gaps:")
            for gap in rb.context_gaps:
                lines.append(f"  - [{gap.dimension}] {gap.description} (severity: {gap.severity:.1f})")

        if rb.reasoning:
            lines.append(f"Reasoning: {rb.reasoning}")

        return "\n".join(lines)
