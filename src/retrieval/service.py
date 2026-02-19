"""
Institutional Knowledge Service.

Central service for knowledge retrieval that any code generation consumer can use.
This is the main entry point for CGR³ functionality.
"""

import logging

from src.retrieval.cgr3_retriever import ContextGraphRetriever
from src.retrieval.schemas import (
    KnowledgeResponse,
    RetrievalContext,
)
from src.storage.schemas import Bullet

logger = logging.getLogger(__name__)


class InstitutionalKnowledgeService:
    """
    Central knowledge retrieval service for all code generation activities.

    Used by:
    - TDD Agent: Test patterns, implementation patterns
    - Code Gen (Claude Code, IDE plugins): "How we do things here"
    - ML Training: Hyperparameter decisions, architecture choices
    - PR Review: Pattern compliance checking

    The service provides:
    - Context-aware retrieval (CGR³)
    - Guidance on which patterns to apply vs. ask about
    - Integration with playbook storage

    Usage:
        service = InstitutionalKnowledgeService(playbook_manager)

        response = service.get_guidance(
            query="handle database connection timeout",
            context=RetrievalContext(
                team_id="backend",
                tech_stack={"python": "3.11", "database": "postgresql"},
            ),
        )

        # Patterns safe to apply
        for rb in response.apply:
            print(f"Apply: {rb.bullet.content}")

        # Patterns needing clarification
        for question in response.questions:
            print(f"Clarify: {question}")
    """

    def __init__(
        self,
        playbook_manager=None,
        retriever: ContextGraphRetriever | None = None,
        default_playbook_id: str | None = None,
    ):
        """
        Initialize the knowledge service.

        Args:
            playbook_manager: PlaybookManager for accessing bullets
            retriever: CGR³ retriever (default: creates new one)
            default_playbook_id: Default playbook to query
        """
        self.playbook_manager = playbook_manager
        self.retriever = retriever or ContextGraphRetriever()
        self.default_playbook_id = default_playbook_id

    def get_guidance(
        self,
        query: str,
        context: RetrievalContext | None = None,
        playbook_id: str | None = None,
        domain: str | None = None,
        top_k: int = 10,
        include_cross_playbook: bool = True,
    ) -> KnowledgeResponse:
        """
        Get institutional knowledge guidance for a query.

        This is the main entry point for consumers.

        Args:
            query: What knowledge are you looking for?
            context: Request context (team, project, tech stack, etc.)
            playbook_id: Specific playbook to query (default: project's playbook)
            domain: Filter by domain (e.g., "tdd", "ml", "architecture")
            top_k: Maximum results to return
            include_cross_playbook: Whether to include patterns from other playbooks

        Returns:
            KnowledgeResponse with categorized patterns and clarifying questions
        """
        # Get bullets to search
        bullets = self._get_bullets(
            playbook_id=playbook_id or self.default_playbook_id,
            domain=domain,
            include_cross_playbook=include_cross_playbook,
        )

        if not bullets:
            logger.warning(f"No bullets found for query: {query}")
            return KnowledgeResponse(query=query, context=context)

        # Run CGR³ retrieval
        return self.retriever.retrieve(
            query=query,
            bullets=bullets,
            context=context,
            top_k=top_k,
        )

    def get_guidance_for_tdd(
        self,
        test_name: str,
        implementation_context: str,
        context: RetrievalContext | None = None,
    ) -> KnowledgeResponse:
        """
        Get guidance specifically for TDD cycles.

        Args:
            test_name: Name of the test being written
            implementation_context: What's being implemented
            context: Request context

        Returns:
            KnowledgeResponse with TDD-relevant patterns
        """
        query = f"writing test {test_name}: {implementation_context}"

        # Ensure context has TDD domain
        if context is None:
            context = RetrievalContext(domain="tdd")
        elif not context.domain:
            context.domain = "tdd"

        return self.get_guidance(query, context, domain="tdd")

    def get_guidance_for_implementation(
        self,
        feature_description: str,
        context: RetrievalContext | None = None,
    ) -> KnowledgeResponse:
        """
        Get guidance for implementing a feature.

        Args:
            feature_description: What feature is being implemented
            context: Request context

        Returns:
            KnowledgeResponse with implementation patterns
        """
        return self.get_guidance(
            query=f"implementing: {feature_description}",
            context=context,
        )

    def get_anti_patterns(
        self,
        context_description: str,
        context: RetrievalContext | None = None,
    ) -> KnowledgeResponse:
        """
        Get anti-patterns to avoid.

        Args:
            context_description: What you're working on
            context: Request context

        Returns:
            KnowledgeResponse with anti-patterns
        """
        return self.get_guidance(
            query=f"anti-patterns avoid {context_description}",
            context=context,
            domain="anti-patterns",
        )

    def _get_bullets(
        self,
        playbook_id: str | None,
        domain: str | None,
        include_cross_playbook: bool,
    ) -> list[Bullet]:
        """
        Get bullets from playbook(s).

        Args:
            playbook_id: Primary playbook ID
            domain: Filter by domain
            include_cross_playbook: Include other playbooks

        Returns:
            List of bullets to search
        """
        if self.playbook_manager is None:
            logger.warning("No playbook manager configured")
            return []

        bullets = []

        # Get primary playbook
        if playbook_id:
            playbook = self.playbook_manager.get_playbook(playbook_id)
            if playbook:
                for section_bullets in playbook.sections.values():
                    bullets.extend(section_bullets)

        # Get cross-playbook bullets if requested
        if include_cross_playbook and hasattr(self.playbook_manager, '_playbooks'):
            for pb_id, pb in self.playbook_manager._playbooks.items():
                if pb_id == playbook_id:
                    continue  # Skip primary
                for section_bullets in pb.sections.values():
                    bullets.extend(section_bullets)

        # Filter by domain if specified
        if domain:
            bullets = [
                b for b in bullets
                if domain in (b.tags or []) or
                   domain in (getattr(b, 'applicable_domains', None) or [])
            ]

        return bullets

    def format_guidance(
        self,
        response: KnowledgeResponse,
        include_ask_first: bool = False,
    ) -> str:
        """
        Format guidance response as text for injection into prompts.

        Args:
            response: KnowledgeResponse from get_guidance
            include_ask_first: Whether to include uncertain patterns

        Returns:
            Formatted text suitable for prompt injection
        """
        if not response.has_results:
            return "No relevant patterns found."

        lines = []

        if response.apply:
            lines.append("**Confirmed patterns (safe to apply):**")
            for rb in response.apply:
                lines.append(f"- {rb.bullet.content}")
            lines.append("")

        if include_ask_first and response.ask_first:
            lines.append("**Patterns that may apply (verify context):**")
            for rb in response.ask_first:
                gaps = ", ".join(g.description for g in rb.context_gaps)
                lines.append(f"- {rb.bullet.content}")
                lines.append(f"  *Note: {gaps}*")
            lines.append("")

        return "\n".join(lines)


# Module-level service instance
_service_instance: InstitutionalKnowledgeService | None = None


def get_knowledge_service(
    playbook_manager=None,
    force_new: bool = False,
) -> InstitutionalKnowledgeService:
    """
    Get the knowledge service singleton.

    Args:
        playbook_manager: PlaybookManager to use (only for first call)
        force_new: Force creation of new instance

    Returns:
        InstitutionalKnowledgeService instance
    """
    global _service_instance

    if _service_instance is None or force_new:
        _service_instance = InstitutionalKnowledgeService(
            playbook_manager=playbook_manager,
        )

    return _service_instance
