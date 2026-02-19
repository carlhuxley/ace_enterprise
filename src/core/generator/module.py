"""
Generator Module - Execute tasks using playbook context.
Based on PRD Section 2.2.1: Generator Module
"""
import logging
import time
from typing import Any

from src.config.settings import settings
from src.playbook.manager import PlaybookManager
from src.playbook.retrieval import BulletRetriever
from src.storage.schemas import Bullet, GeneratorOutput, TaskInput
from src.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


class Generator:
    """
    Generator Module - executes tasks using playbook-guided LLM.

    Features (PRD Section 2.2.1):
    - Execute queries using current playbook context
    - Retrieve relevant bullets for task
    - Generate reasoning trajectory
    - Track bullet usage and feedback
    - Monitor token usage and latency
    - Graceful degradation if playbook unavailable
    """

    def __init__(
        self,
        playbook_manager: PlaybookManager,
        llm_client: LLMClient | None = None,
        retriever: BulletRetriever | None = None,
    ) -> None:
        """
        Initialize Generator.

        Args:
            playbook_manager: Playbook manager instance
            llm_client: LLM client (default: new client with settings)
            retriever: Bullet retriever (default: new retriever)
        """
        self.playbook_manager = playbook_manager
        self.llm_client = llm_client or LLMClient()
        self.retriever = retriever or BulletRetriever()

    def execute(
        self,
        task: TaskInput,
        playbook_id: str,
        query_embedding: list[float] | None = None,
    ) -> GeneratorOutput:
        """
        Execute a task using playbook-guided generation.

        Args:
            task: Task input with query and context
            playbook_id: Playbook to use
            query_embedding: Pre-computed query embedding (optional)

        Returns:
            Generator output with trajectory, solution, and metadata

        Raises:
            ValueError: If playbook not found
        """
        start_time = time.time()

        # Get playbook
        playbook = self.playbook_manager.get_playbook(playbook_id)
        if not playbook:
            raise ValueError(f"Playbook {playbook_id} not found")

        logger.info(f"Executing task {task.id} with playbook {playbook_id}")

        # Retrieve relevant bullets based on retrieval mode
        if settings.retrieval_mode == "cross_model_hybrid":
            # Cross-model retrieval: use primary + domain playbooks
            primary_bullets = self.playbook_manager.get_all_bullets(playbook_id)
            secondary_bullets = self.playbook_manager.get_cross_model_bullets(
                primary_playbook_id=playbook_id,
                include_primary=False,
            )

            retrieved_with_source = self.retriever.retrieve_cross_model(
                query=task.query,
                primary_bullets=primary_bullets,
                secondary_bullets_by_playbook=secondary_bullets,
                primary_playbook_id=playbook_id,
                query_embedding=query_embedding,
                secondary_weight=settings.cross_model_weight,
            )

            # Extract bullets and track sources
            retrieved_bullets = [(bullet, score) for bullet, score, _ in retrieved_with_source]
            bullets_used = [bullet.id for bullet, _ in retrieved_bullets]

            # Log source distribution
            primary_count = sum(1 for _, _, src in retrieved_with_source if src == playbook_id)
            secondary_count = len(retrieved_with_source) - primary_count
            logger.debug(
                f"Cross-model retrieval for task {task.id}: "
                f"{len(retrieved_bullets)} bullets ({primary_count} primary, {secondary_count} from other models)"
            )

        else:
            # Model-specific retrieval: use only this playbook
            all_bullets = self.playbook_manager.get_all_bullets(playbook_id)
            retrieved_bullets = self.retriever.retrieve(
                query=task.query,
                bullets=all_bullets,
                query_embedding=query_embedding,
            )

            bullets_used = [bullet.id for bullet, _ in retrieved_bullets]

            logger.debug(
                f"Model-specific retrieval for task {task.id}: "
                f"{len(retrieved_bullets)} bullets from {playbook_id}"
            )

        # Build prompt with playbook context
        prompt = self._build_prompt(
            task=task,
            retrieved_bullets=[b for b, _ in retrieved_bullets],
        )

        system_prompt = self._build_system_prompt(task, playbook)

        # Generate response
        try:
            llm_response = self.llm_client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.7,
            )

            content = llm_response["content"]
            tokens_used = llm_response["tokens_used"]

        except Exception as e:
            logger.error(f"LLM generation failed for task {task.id}: {e}")
            # Graceful degradation - return error as solution
            content = f"Error: LLM generation failed: {str(e)}"
            tokens_used = 0

        latency_ms = int((time.time() - start_time) * 1000)

        # Parse trajectory and solution
        trajectory, solution = self._parse_response(content)

        # Request feedback on bullets (will be provided later by user/environment)
        bullet_feedback = dict.fromkeys(bullets_used, "neutral")

        output = GeneratorOutput(
            trajectory=trajectory,
            solution=solution,
            bullets_used=bullets_used,
            bullet_feedback=bullet_feedback,
            latency_ms=latency_ms,
            tokens_used=tokens_used,
        )

        logger.info(
            f"Completed task {task.id} in {latency_ms}ms "
            f"(used {len(bullets_used)} bullets, {tokens_used} tokens)"
        )

        return output

    def _build_prompt(
        self,
        task: TaskInput,
        retrieved_bullets: list[Bullet],
    ) -> str:
        """
        Build prompt with playbook bullets.

        Args:
            task: Task input
            retrieved_bullets: Relevant bullets

        Returns:
            Formatted prompt string
        """
        # Organize bullets by section
        sections: dict[str, list[Bullet]] = {}
        for bullet in retrieved_bullets:
            if bullet.section not in sections:
                sections[bullet.section] = []
            sections[bullet.section].append(bullet)

        # Build playbook context
        playbook_context = ""
        if sections:
            playbook_context = "\n# Relevant Playbook Context\n\n"

            section_names = {
                "strategies_and_hard_rules": "Strategies and Hard Rules",
                "code_snippets": "Code Snippets",
                "troubleshooting": "Troubleshooting",
                "domain_knowledge": "Domain Knowledge",
            }

            for section_key, bullets in sections.items():
                section_name = section_names.get(section_key, section_key)
                playbook_context += f"## {section_name}\n\n"

                for bullet in bullets:
                    playbook_context += f"- {bullet.content}\n"

                playbook_context += "\n"

        # Build main prompt
        prompt = f"""Task: {task.query}

{playbook_context}

Please provide:
1. **Reasoning**: Your step-by-step thought process
2. **Solution**: Your final answer or action

Format your response as:

## Reasoning
[Your reasoning steps here]

## Solution
[Your final solution here]
"""

        # Add any additional context
        if task.context:
            prompt += f"\n\nAdditional Context:\n{task.context}\n"

        return prompt

    def _build_system_prompt(
        self,
        task: TaskInput,
        playbook: Any,
    ) -> str:
        """
        Build system prompt for LLM.

        Args:
            task: Task input
            playbook: Playbook metadata

        Returns:
            System prompt string
        """
        system_prompt = f"""You are an AI assistant specialized in {playbook.metadata.domain}.

Your task is to help solve problems by:
1. Carefully analyzing the task
2. Using the provided playbook context (strategies, code snippets, troubleshooting tips)
3. Reasoning step-by-step through the problem
4. Providing a clear, actionable solution

The playbook contains learned knowledge from previous successful executions.
Pay close attention to strategies and hard rules - they represent important patterns.

Be thorough in your reasoning and precise in your solution."""

        return system_prompt

    def _parse_response(self, content: str) -> tuple[str, str]:
        """
        Parse LLM response into trajectory and solution.

        Args:
            content: Raw LLM response

        Returns:
            Tuple of (trajectory, solution)
        """
        # Try to extract sections
        trajectory = ""
        solution = ""

        # Look for ## Reasoning and ## Solution markers
        lines = content.split("\n")
        current_section = None

        for line in lines:
            if line.strip().startswith("## Reasoning"):
                current_section = "reasoning"
                continue
            elif line.strip().startswith("## Solution"):
                current_section = "solution"
                continue

            if current_section == "reasoning":
                trajectory += line + "\n"
            elif current_section == "solution":
                solution += line + "\n"

        # If parsing failed, use full content as solution
        if not solution.strip():
            solution = content
            trajectory = "No explicit reasoning provided"

        return trajectory.strip(), solution.strip()

    def update_bullet_feedback(
        self,
        playbook_id: str,
        bullet_feedback: dict[str, str],
    ) -> None:
        """
        Update bullet feedback based on task outcome.

        Should be called after task execution with actual feedback.

        Args:
            playbook_id: Playbook ID
            bullet_feedback: Map of bullet_id -> feedback ("helpful"/"harmful"/"neutral")
        """
        for bullet_id, feedback in bullet_feedback.items():
            try:
                self.playbook_manager.update_bullet_feedback(
                    playbook_id=playbook_id,
                    bullet_id=bullet_id,
                    feedback=feedback,
                )
            except ValueError as e:
                logger.warning(f"Failed to update feedback for bullet {bullet_id}: {e}")

    def get_statistics(self) -> dict[str, Any]:
        """
        Get generator statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "provider": self.llm_client.provider,
            "model": self.llm_client.model,
            "retriever_top_k": self.retriever.top_k,
            "retriever_threshold": self.retriever.similarity_threshold,
        }
