"""
Playbook Q&A System - Answer coding questions using learned knowledge.

Provides a simple interface to query playbooks and get answers backed by
learned patterns. Supports single-model and ensemble consensus answers.
"""
import logging
from dataclasses import dataclass, field

from src.playbook.manager import PlaybookManager
from src.playbook.retrieval import BulletRetriever
from src.storage.schemas import Bullet
from src.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class QAAnswer:
    """Answer to a coding question with playbook context."""

    question: str
    answer: str
    confidence: float  # 0.0-1.0 based on playbook coverage
    sources: list[Bullet] = field(default_factory=list)  # Playbook bullets used
    model_id: str | None = None  # Which model answered (if single model)
    consensus: dict | None = None  # If ensemble: {model: answer, votes: ...}
    playbook_coverage: float = 0.0  # How much playbook knowledge was available


class PlaybookQA:
    """
    Q&A system that answers coding questions using playbook knowledge.

    Features:
    - Searches playbooks for relevant bullets
    - Generates answers informed by learned patterns
    - Shows which playbook knowledge was used
    - Supports ensemble consensus (multiple models)
    """

    def __init__(
        self,
        playbook_manager: PlaybookManager,
        default_model: tuple[str, str] | None = None,
    ):
        """
        Initialize Q&A system.

        Args:
            playbook_manager: Manager for accessing playbooks
            default_model: (provider, model_name) for single-model Q&A
        """
        self.playbook_manager = playbook_manager
        self.retriever = BulletRetriever()

        # Default to local Ollama if not specified
        self.default_model = default_model or ("ollama", "qwen2.5-coder:1.5b")

        logger.info(
            f"Initialized PlaybookQA with default model: "
            f"{self.default_model[0]}/{self.default_model[1]}"
        )

    def ask(
        self,
        question: str,
        domain: str | None = None,
        top_k: int = 5,
    ) -> QAAnswer:
        """
        Ask a coding question and get answer with playbook context.

        Args:
            question: Coding question to answer
            domain: Optional domain to filter playbooks (e.g., "python_development")
            top_k: Number of relevant bullets to retrieve

        Returns:
            QAAnswer with response and source bullets
        """
        logger.info(f"Q&A query: {question[:50]}...")

        # Get all bullets from relevant playbooks
        bullets = self._get_relevant_bullets(domain)

        if not bullets:
            logger.warning(f"No bullets found for domain: {domain}")
            return self._answer_without_playbook(question)

        # Retrieve most relevant bullets for this question
        relevant_scored = self.retriever.retrieve(
            query=question,
            bullets=bullets,
        )

        # Extract just the bullets (discard scores)
        relevant_bullets = [bullet for bullet, score in relevant_scored]

        logger.info(f"Retrieved {len(relevant_bullets)} relevant bullets")

        # Calculate confidence based on playbook coverage
        confidence = self._calculate_confidence(relevant_bullets)

        # Generate answer using playbook context
        answer_text = self._generate_answer(question, relevant_bullets)

        return QAAnswer(
            question=question,
            answer=answer_text,
            confidence=confidence,
            sources=relevant_bullets,
            model_id=f"{self.default_model[0]}/{self.default_model[1]}",
            playbook_coverage=len(relevant_bullets) / max(top_k, 1),
        )

    def ask_ensemble(
        self,
        question: str,
        models: list[tuple[str, str]],
        domain: str | None = None,
        top_k: int = 5,
    ) -> QAAnswer:
        """
        Ask multiple models and return consensus answer.

        Args:
            question: Coding question to answer
            models: List of (provider, model_name) tuples
            domain: Optional domain to filter playbooks
            top_k: Number of relevant bullets to retrieve

        Returns:
            QAAnswer with consensus response
        """
        logger.info(f"Ensemble Q&A query with {len(models)} models: {question[:50]}...")

        # Get relevant bullets (same for all models)
        bullets = self._get_relevant_bullets(domain)
        relevant_bullets = []

        if bullets:
            relevant_scored = self.retriever.retrieve(
                query=question,
                bullets=bullets,
            )
            # Extract just the bullets (discard scores)
            relevant_bullets = [bullet for bullet, score in relevant_scored]
            logger.info(f"Retrieved {len(relevant_bullets)} relevant bullets")

        # Get answers from all models
        model_answers = {}
        for provider, model_name in models:
            model_id = f"{provider}/{model_name}"
            try:
                answer = self._generate_answer_with_model(
                    question, relevant_bullets, provider, model_name
                )
                model_answers[model_id] = answer
                logger.info(f"Got answer from {model_id}")
            except Exception as e:
                logger.warning(f"Failed to get answer from {model_id}: {e}")

        if not model_answers:
            logger.error("All models failed to answer")
            return self._answer_without_playbook(question)

        # Select best answer (for now, use longest answer as proxy for detail)
        # TODO: Could use LLM voting here to select best answer
        best_model = max(model_answers.keys(), key=lambda m: len(model_answers[m]))
        best_answer = model_answers[best_model]

        confidence = self._calculate_confidence(relevant_bullets)

        return QAAnswer(
            question=question,
            answer=best_answer,
            confidence=confidence,
            sources=relevant_bullets,
            consensus={
                "models": list(model_answers.keys()),
                "answers": model_answers,
                "selected": best_model,
                "agreement": self._calculate_agreement(model_answers),
            },
            playbook_coverage=len(relevant_bullets) / max(top_k, 1),
        )

    def _get_relevant_bullets(self, domain: str | None = None) -> list[Bullet]:
        """Get all bullets from playbooks (optionally filtered by domain)."""
        all_bullets = []

        for playbook_id, playbook in self.playbook_manager._playbooks.items():
            # Filter by domain if specified
            if domain and playbook.metadata.domain != domain:
                continue

            # Get all bullets from this playbook
            for section_bullets in playbook.sections.values():
                all_bullets.extend(section_bullets)

        logger.debug(f"Found {len(all_bullets)} total bullets")
        return all_bullets

    def _generate_answer(self, question: str, bullets: list[Bullet]) -> str:
        """Generate answer using playbook context."""
        return self._generate_answer_with_model(
            question, bullets, self.default_model[0], self.default_model[1]
        )

    def _generate_answer_with_model(
        self,
        question: str,
        bullets: list[Bullet],
        provider: str,
        model_name: str,
    ) -> str:
        """Generate answer using specific model and playbook context."""
        # Create LLM client
        llm_client = LLMClient(provider=provider, model=model_name)

        # Build context from bullets
        context = self._format_bullets_as_context(bullets)

        # Create prompt
        if context:
            prompt = f"""Answer this coding question using the provided knowledge from our playbook.

**Question:** {question}

**Relevant Knowledge from Playbook:**
{context}

**Instructions:**
- Use the playbook knowledge to inform your answer
- If the playbook has specific patterns, reference them
- If the playbook doesn't cover this, use your general knowledge
- Be concise but thorough
- Include code examples if relevant

Answer:"""
        else:
            prompt = f"""Answer this coding question:

**Question:** {question}

**Instructions:**
- Be concise but thorough
- Include code examples if relevant

Answer:"""

        # Generate answer
        try:
            response = llm_client.generate(
                prompt=prompt,
                system_prompt="You are a helpful coding assistant with access to team playbook knowledge.",
                max_tokens=1000,
                temperature=0.3,  # Lower temperature for more consistent answers
            )
            return response["content"]
        except Exception as e:
            logger.error(f"Failed to generate answer: {e}")
            return f"Error generating answer: {e}"

    def _format_bullets_as_context(self, bullets: list[Bullet]) -> str:
        """Format bullets as context for LLM."""
        if not bullets:
            return ""

        lines = []
        for i, bullet in enumerate(bullets, 1):
            # Include helpful count as indicator of reliability
            reliability = (
                f" (👍 {bullet.helpful_count})"
                if bullet.helpful_count > 0
                else ""
            )
            lines.append(f"{i}. {bullet.content}{reliability}")

        return "\n".join(lines)

    def _calculate_confidence(self, bullets: list[Bullet]) -> float:
        """
        Calculate confidence based on playbook coverage.

        Higher confidence when:
        - More relevant bullets found
        - Bullets have high helpful counts
        - Bullets have high similarity scores
        """
        if not bullets:
            return 0.3  # Low confidence without playbook

        # Base confidence from number of bullets
        base = min(len(bullets) / 5.0, 1.0)  # Max at 5 bullets

        # Boost from helpful counts
        avg_helpful = sum(b.helpful_count for b in bullets) / len(bullets)
        helpful_boost = min(avg_helpful / 10.0, 0.2)  # Up to 0.2 boost

        return min(base + helpful_boost, 0.95)  # Cap at 0.95

    def _calculate_agreement(self, answers: dict[str, str]) -> float:
        """
        Calculate agreement between model answers.

        Simple heuristic: Longer common prefix = higher agreement
        """
        if len(answers) < 2:
            return 1.0

        # Get all answer texts
        texts = list(answers.values())

        # Calculate pairwise similarity (simple: length of common prefix)
        total_similarity = 0
        pairs = 0

        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                # Simple similarity: how many chars match at start
                common = 0
                for c1, c2 in zip(texts[i], texts[j]):
                    if c1.lower() == c2.lower():
                        common += 1
                    else:
                        break

                similarity = common / max(len(texts[i]), len(texts[j]))
                total_similarity += similarity
                pairs += 1

        return total_similarity / pairs if pairs > 0 else 0.0

    def _answer_without_playbook(self, question: str) -> QAAnswer:
        """Fallback when no playbook knowledge available."""
        llm_client = LLMClient(
            provider=self.default_model[0],
            model=self.default_model[1],
        )

        try:
            response = llm_client.generate(
                prompt=f"Answer this coding question concisely:\n\n{question}",
                system_prompt="You are a helpful coding assistant.",
                max_tokens=1000,
                temperature=0.3,
            )
            answer_text = response["content"]
        except Exception as e:
            answer_text = f"Error: {e}"

        return QAAnswer(
            question=question,
            answer=answer_text,
            confidence=0.3,  # Low confidence without playbook
            sources=[],
            model_id=f"{self.default_model[0]}/{self.default_model[1]}",
            playbook_coverage=0.0,
        )
