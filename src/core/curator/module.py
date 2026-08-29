"""
Curator Module - Synthesize insights into playbook updates.
Based on PRD Section 2.2.3: Curator Module
"""
import logging
from typing import Any

from src.config.settings import settings
from src.playbook.manager import PlaybookManager
from src.storage.schemas import CuratorOutput, DeltaBullet, Playbook, ReflectorOutput
from src.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


class Curator:
    """
    Curator Module - synthesizes reflector insights into actionable playbook updates.

    Features (PRD Section 2.2.3):
    - Synthesize insights into playbook bullets
    - Avoid redundancy checking
    - Respect token budgets
    - Section-based organization
    - Actionable, specific content
    - No hallucinated attributions
    """

    def __init__(
        self,
        playbook_manager: PlaybookManager,
        llm_client: LLMClient | None = None,
        token_budget_per_section: int | None = None,
        enable_redundancy_checking: bool | None = None,
    ) -> None:
        """
        Initialize Curator.

        Args:
            playbook_manager: Playbook manager instance
            llm_client: LLM client (default: new client with settings)
            token_budget_per_section: Token budget (default from settings)
            enable_redundancy_checking: Enable redundancy check (default from settings)
        """
        self.playbook_manager = playbook_manager
        self.llm_client = llm_client or LLMClient()
        self.token_budget_per_section = (
            token_budget_per_section
            if token_budget_per_section is not None
            else settings.token_budget_per_section
        )
        self.enable_redundancy_checking = (
            enable_redundancy_checking
            if enable_redundancy_checking is not None
            else settings.enable_redundancy_checking
        )

    def curate(
        self,
        reflector_output: ReflectorOutput,
        playbook_id: str,
        task_context: dict[str, Any] | None = None,
    ) -> CuratorOutput:
        """
        Synthesize reflector insights into playbook updates.

        Args:
            reflector_output: Analysis from reflector
            playbook_id: Target playbook ID
            task_context: Additional task context (optional)

        Returns:
            Curator output with delta bullets and reasoning
        """
        logger.info(f"Curating insights for playbook {playbook_id}")

        # Get current playbook for context
        playbook = self.playbook_manager.get_playbook(playbook_id)
        if not playbook:
            raise ValueError(f"Playbook {playbook_id} not found")

        # Get playbook statistics for token budget checking
        stats = self.playbook_manager.get_statistics(playbook_id)

        # Generate delta bullets from insights
        delta_bullets, reasoning = self._synthesize_bullets(
            reflector_output=reflector_output,
            playbook=playbook,
            playbook_stats=stats,
            task_context=task_context,
        )

        output = CuratorOutput(
            delta_bullets=delta_bullets,
            reasoning=reasoning,
        )

        logger.info(
            f"Curated {len(delta_bullets)} delta bullets for playbook {playbook_id}"
        )

        return output

    def _synthesize_bullets(
        self,
        reflector_output: ReflectorOutput,
        playbook: Playbook,
        playbook_stats: dict[str, Any],
        task_context: dict[str, Any] | None,
    ) -> tuple[list[DeltaBullet], str]:
        """
        Synthesize insights into actionable bullets.

        Args:
            reflector_output: Reflector analysis
            playbook: Current playbook
            playbook_stats: Playbook statistics
            task_context: Additional context

        Returns:
            Tuple of (delta_bullets, reasoning)
        """
        # Build synthesis prompt
        prompt = self._build_synthesis_prompt(
            reflector_output=reflector_output,
            playbook=playbook,
            playbook_stats=playbook_stats,
            task_context=task_context,
        )

        system_prompt = """You are an expert at synthesizing learning insights into actionable knowledge.

Your role is to:
1. Extract key learnings from analysis
2. Create specific, actionable bullets
3. Organize bullets by appropriate section
4. Ensure content is concrete and generalizable
5. Avoid redundancy with existing playbook content

Generate bullets that will genuinely help prevent similar mistakes in the future."""

        # Generate synthesis
        try:
            llm_response = self.llm_client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.5,  # Moderate temperature for creative synthesis
            )

            content = llm_response["content"]

            # Parse bullets and reasoning
            delta_bullets, reasoning = self._parse_synthesis(content, task_context)

        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            # Return empty results
            delta_bullets = []
            reasoning = f"Synthesis failed: {str(e)}"

        return delta_bullets, reasoning

    def _build_synthesis_prompt(
        self,
        reflector_output: ReflectorOutput,
        playbook: Playbook,
        playbook_stats: dict[str, Any],
        task_context: dict[str, Any] | None,
    ) -> str:
        """Build prompt for bullet synthesis."""
        prompt = f"""# Playbook Update Request

## Current Playbook Context
Domain: {playbook.metadata.domain}
Total Bullets: {playbook.metadata.total_bullets}
Version: {playbook.version}

## Section Statistics
"""

        for section, section_stats in playbook_stats.get("sections", {}).items():
            prompt += f"\n### {section}"
            prompt += f"\n- Bullets: {section_stats['bullet_count']}"
            prompt += f"\n- Helpful Ratio: {section_stats['helpful_ratio']:.2f}"

        prompt += "\n\n## Analysis from Reflector\n"

        if reflector_output.error_identification:
            prompt += f"\n**Error Identified:**\n{reflector_output.error_identification}\n"

        if reflector_output.root_cause:
            prompt += f"\n**Root Cause:**\n{reflector_output.root_cause}\n"

        if reflector_output.correct_approach:
            prompt += f"\n**Correct Approach:**\n{reflector_output.correct_approach}\n"

        if reflector_output.key_insight:
            prompt += f"\n**Key Insight:**\n{reflector_output.key_insight}\n"

        if reflector_output.code_invariant:
            prompt += (
                f"\n**Code Invariant (embed this exact expression verbatim, "
                f"in backticks, in the bullet you write from it -- do not "
                f"paraphrase it into prose):**\n`{reflector_output.code_invariant}`\n"
            )

        # Available sections
        prompt += """

## Available Sections

You can add bullets to these sections:

1. **strategies_and_hard_rules** - High-level strategies, rules, and principles
2. **code_snippets** - Concrete code examples and patterns
3. **troubleshooting** - Solutions to specific problems
4. **domain_knowledge** - Domain-specific facts and context

## Task

Based on the analysis above, generate new bullets that will help prevent similar errors in the future.

For each bullet:
1. Choose the appropriate section
2. Write specific, actionable content
3. Focus on what to DO, not just what went wrong
4. Make it generalizable to similar situations
5. If a Code Invariant was provided above, include that exact expression
   verbatim (in backticks) in the bullet -- a bullet that only restates the
   idea in prose ("check the sign of the divisor") without the precise
   expression ("`math.copysign(1.0, x) < 0`") is not specific enough

Format your response as:

### Reasoning
[Explain your thought process for creating these bullets]

### Delta Bullets

#### Section: [section_name]
- [Bullet content 1]
- [Bullet content 2]

#### Section: [another_section_name]
- [Bullet content 3]

**Important:**
- Be specific and actionable
- Avoid vague or generic advice
- Focus on preventable patterns
- Don't create bullets for one-time issues
- Maximum 3-5 bullets per synthesis
"""

        return prompt

    def _parse_synthesis(
        self, content: str, task_context: dict[str, Any] | None = None,
    ) -> tuple[list[DeltaBullet], str]:
        """
        Parse LLM synthesis into delta bullets and reasoning.

        Args:
            content: Raw LLM response
            task_context: Caller-supplied context (team_id, project_ids,
                applicable_domains, tech_context, tags) stamped onto every
                bullet verbatim -- these are provenance/scoping facts the
                caller actually knows, not something to ask the LLM to
                invent. `tags` is for fine-grained topic scoping narrower
                than `applicable_domains` (e.g. BulletRetriever's
                required_tags/excluded_tags, or benchmarks/runner.py using
                it to stop bullets from one unrelated task under a shared
                domain diluting another task's retry prompt).

        Returns:
            Tuple of (delta_bullets, reasoning)
        """
        task_context = task_context or {}
        delta_bullets: list[DeltaBullet] = []
        reasoning = ""

        lines = content.split("\n")
        current_section = None
        parsing_reasoning = False
        parsing_bullets = False
        reasoning_lines = []

        # A bullet's content can span multiple lines when the model
        # introduces a fenced code block after a colon (e.g. "Here's a
        # corrected implementation:\n```python\n...\n```"). Only the intro
        # line matched "-"/"*" below, so the fence that followed it was
        # silently dropped -- found via forensic analysis of a real
        # benchmark run: a curated bullet promised "a corrected
        # implementation" the playbook never actually contained. Accumulate
        # the open bullet's lines here and finalize (join + append) it only
        # once a new bullet, a new section, or end-of-input is reached.
        current_bullet_lines: list[str] | None = None
        in_code_fence = False

        def finalize_bullet() -> None:
            if current_bullet_lines is None or current_section is None:
                return
            bullet_content = "\n".join(current_bullet_lines).strip()
            if not bullet_content:
                return
            delta_bullets.append(DeltaBullet(
                section=current_section,
                content=bullet_content,
                tags=list(task_context.get("tags") or []),
                team_id=task_context.get("team_id"),
                project_ids=task_context.get("project_ids"),
                applicable_domains=task_context.get("applicable_domains"),
                tech_context=task_context.get("tech_context"),
            ))

        for line in lines:
            line_stripped = line.strip()

            # Check for Reasoning section
            if "### Reasoning" in line or "## Reasoning" in line:
                finalize_bullet()
                current_bullet_lines = None
                parsing_reasoning = True
                parsing_bullets = False
                continue

            # Check for Delta Bullets section
            if "### Delta Bullets" in line or "## Delta Bullets" in line:
                finalize_bullet()
                current_bullet_lines = None
                parsing_reasoning = False
                parsing_bullets = True
                continue

            # Parse reasoning
            if parsing_reasoning and line_stripped:
                reasoning_lines.append(line_stripped)
                continue

            # Parse bullets
            if parsing_bullets:
                # Check for section header
                if line_stripped.startswith("#### Section:") or line_stripped.startswith("**Section:"):
                    finalize_bullet()
                    current_bullet_lines = None
                    in_code_fence = False
                    # Extract section name
                    section_text = line_stripped.split(":", 1)[1].strip()
                    # Remove markdown artifacts
                    section_text = section_text.replace("**", "").replace("`", "").strip()
                    current_section = section_text
                    continue

                # Fenced code block delimiter -- toggle state and keep the
                # fence marker itself as part of the open bullet so its
                # content still renders as a valid code block.
                if line_stripped.startswith("```"):
                    in_code_fence = not in_code_fence
                    if current_bullet_lines is not None:
                        current_bullet_lines.append(line.rstrip())
                    continue

                # Inside a fence, every line belongs to the bullet that
                # opened it -- checked before the "-"/"*" bullet-start test
                # below so a code line that happens to start with those
                # characters (a unary-minus expression, a markdown list
                # inside a docstring) isn't mistaken for a new top-level
                # bullet.
                if in_code_fence:
                    if current_bullet_lines is not None:
                        current_bullet_lines.append(line.rstrip())
                    continue

                # Check for bullet
                if line_stripped.startswith("-") or line_stripped.startswith("*"):
                    finalize_bullet()
                    current_bullet_lines = [line_stripped[1:].strip()]
                    continue

                # Any other line outside a fence (blank lines, stray prose
                # between bullets) is ignored, same as before this fix --
                # only fenced code blocks that follow a bullet are now
                # preserved instead of silently dropped.

        finalize_bullet()

        # Combine reasoning
        reasoning = "\n".join(reasoning_lines).strip()
        if not reasoning:
            reasoning = "Synthesized bullets from reflector analysis"

        logger.debug(f"Parsed {len(delta_bullets)} delta bullets from synthesis")

        return delta_bullets, reasoning

    def apply_updates(
        self,
        playbook_id: str,
        curator_output: CuratorOutput,
    ) -> list[str]:
        """
        Apply curator's delta bullets to playbook.

        Args:
            playbook_id: Target playbook ID
            curator_output: Curator output with delta bullets

        Returns:
            List of added bullet IDs
        """
        logger.info(f"Applying {len(curator_output.delta_bullets)} delta bullets to playbook {playbook_id}")

        # Apply delta using playbook manager
        added_bullets = self.playbook_manager.apply_delta(
            playbook_id=playbook_id,
            delta_bullets=curator_output.delta_bullets,
        )

        added_ids = [bullet.id for bullet in added_bullets]

        logger.info(
            f"Successfully added {len(added_ids)}/{len(curator_output.delta_bullets)} bullets "
            f"to playbook {playbook_id}"
        )

        return added_ids

    def get_statistics(self) -> dict[str, Any]:
        """
        Get curator statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "provider": self.llm_client.provider,
            "model": self.llm_client.model,
            "token_budget_per_section": self.token_budget_per_section,
            "enable_redundancy_checking": self.enable_redundancy_checking,
        }
