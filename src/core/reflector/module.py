"""
Reflector Module - Analyze generator performance and extract insights.
Based on PRD Section 2.2.2: Reflector Module
"""
import json
import logging
from typing import Any

from src.config.settings import settings
from src.storage.schemas import (
    BulletFeedback,
    EnvironmentFeedback,
    GeneratorOutput,
    ReflectorOutput,
    TaskInput,
)
from src.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


class Reflector:
    """
    Reflector Module - analyzes task outcomes and extracts learning insights.

    Features (PRD Section 2.2.2):
    - Analyze generator performance
    - Extract error patterns and root causes
    - Tag bullets as helpful/harmful/neutral
    - Generate key insights and correct approaches
    - Support multiple feedback types (ground truth, execution, tests)
    - Iterative refinement (up to N rounds)
    - Quality scoring of insights
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        max_refinement_rounds: int | None = None,
        enable_iterative: bool | None = None,
    ) -> None:
        """
        Initialize Reflector.

        Args:
            llm_client: LLM client (default: new client with settings)
            max_refinement_rounds: Maximum refinement iterations (default from settings)
            enable_iterative: Enable iterative refinement (default from settings)
        """
        self.llm_client = llm_client or LLMClient()
        self.max_refinement_rounds = (
            max_refinement_rounds
            if max_refinement_rounds is not None
            else settings.max_refinement_rounds
        )
        self.enable_iterative = (
            enable_iterative
            if enable_iterative is not None
            else settings.enable_iterative_reflection
        )

    def reflect(
        self,
        task: TaskInput,
        generator_output: GeneratorOutput,
        environment_feedback: EnvironmentFeedback,
    ) -> ReflectorOutput:
        """
        Analyze task execution and extract insights.

        Args:
            task: Original task input
            generator_output: Generator's trajectory and solution
            environment_feedback: Execution results and feedback

        Returns:
            Reflector output with analysis and bullet tags
        """
        logger.info(f"Reflecting on task {task.id} (result: {environment_feedback.result})")

        # Determine if refinement is needed
        iterations = 1
        current_analysis = None

        for iteration in range(self.max_refinement_rounds):
            analysis = self._analyze_execution(
                task=task,
                generator_output=generator_output,
                environment_feedback=environment_feedback,
                previous_analysis=current_analysis,
                iteration=iteration + 1,
            )

            current_analysis = analysis

            # If high quality or iterative disabled, stop
            if not self.enable_iterative or analysis["quality_score"] >= 0.8:
                iterations = iteration + 1
                break

            logger.debug(
                f"Refining analysis (iteration {iteration + 1}, "
                f"quality={analysis['quality_score']:.2f})"
            )

        # Extract bullet feedback
        bullet_tags = self._tag_bullets(
            bullets_used=generator_output.bullets_used,
            bullet_feedback=generator_output.bullet_feedback,
            environment_result=environment_feedback.result,
            analysis=current_analysis,
        )

        # Build output
        output = ReflectorOutput(
            error_identification=current_analysis.get("error_identification"),
            root_cause=current_analysis.get("root_cause"),
            correct_approach=current_analysis.get("correct_approach"),
            key_insight=current_analysis.get("key_insight"),
            bullet_tags=bullet_tags,
            iterations=iterations,
            quality_score=current_analysis.get("quality_score", 0.0),
        )

        logger.info(
            f"Completed reflection on task {task.id} after {iterations} iteration(s) "
            f"(quality={output.quality_score:.2f})"
        )

        return output

    def _analyze_execution(
        self,
        task: TaskInput,
        generator_output: GeneratorOutput,
        environment_feedback: EnvironmentFeedback,
        previous_analysis: dict[str, Any] | None,
        iteration: int,
    ) -> dict[str, Any]:
        """
        Perform one round of analysis.

        Args:
            task: Original task
            generator_output: Generator output
            environment_feedback: Environment feedback
            previous_analysis: Previous analysis (for refinement)
            iteration: Current iteration number

        Returns:
            Analysis dictionary
        """
        # Build analysis prompt
        prompt = self._build_analysis_prompt(
            task=task,
            generator_output=generator_output,
            environment_feedback=environment_feedback,
            previous_analysis=previous_analysis,
            iteration=iteration,
        )

        system_prompt = """You are an expert at analyzing AI system performance and extracting learning insights.

Your role is to:
1. Identify what went wrong (or right) in the task execution
2. Determine the root cause of errors
3. Suggest the correct approach
4. Extract key insights for future tasks

Be specific, actionable, and focus on patterns that can be generalized."""

        # Generate analysis
        try:
            llm_response = self.llm_client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.3,  # Lower temperature for analytical tasks
            )

            content = llm_response["content"]

            # Parse analysis
            analysis = self._parse_analysis(content)

            # Calculate quality score
            analysis["quality_score"] = self._score_analysis_quality(
                analysis,
                environment_feedback,
            )

        except Exception as e:
            logger.error(f"Analysis failed for task {task.id}: {e}")
            # Return minimal analysis
            analysis = {
                "error_identification": "Analysis failed",
                "root_cause": str(e),
                "correct_approach": None,
                "key_insight": None,
                "quality_score": 0.0,
            }

        return analysis

    def _build_analysis_prompt(
        self,
        task: TaskInput,
        generator_output: GeneratorOutput,
        environment_feedback: EnvironmentFeedback,
        previous_analysis: dict[str, Any] | None,
        iteration: int,
    ) -> str:
        """Build prompt for reflection analysis."""
        prompt = f"""# Task Analysis Request

## Task
Query: {task.query}
Type: {task.type}
Difficulty: {task.difficulty}

## Generator Output
Reasoning: {generator_output.trajectory}

Solution: {generator_output.solution}

Bullets Used: {len(generator_output.bullets_used)} bullets

## Execution Result
Result: {environment_feedback.result}
"""

        # Add expected vs actual if available
        if environment_feedback.expected:
            prompt += f"\nExpected: {environment_feedback.expected}"
        if environment_feedback.actual:
            prompt += f"\nActual: {environment_feedback.actual}"

        # Add feedback/error messages
        if environment_feedback.feedback:
            prompt += f"\n\nFeedback/Error:\n{environment_feedback.feedback}"

        # Add test report if available
        if environment_feedback.test_report:
            prompt += f"\n\nTest Report:\n{json.dumps(environment_feedback.test_report, indent=2)}"

        # Add previous analysis for refinement
        if previous_analysis and iteration > 1:
            prompt += f"\n\n## Previous Analysis (Iteration {iteration - 1})"
            prompt += f"\nError: {previous_analysis.get('error_identification')}"
            prompt += f"\nRoot Cause: {previous_analysis.get('root_cause')}"
            prompt += "\n\nPlease refine the analysis above with more specific insights."

        # Request structured output
        prompt += """

## Please provide your analysis in the following format:

### Error Identification
[What went wrong? Be specific about the mistake or issue]

### Root Cause
[Why did this error occur? What was the underlying cause?]

### Correct Approach
[What should have been done instead? Provide actionable guidance]

### Key Insight
[What is the key learning or pattern that can be applied to future tasks?]

Be specific, actionable, and focus on patterns that can be generalized to similar tasks.
"""

        return prompt

    def _parse_analysis(self, content: str) -> dict[str, Any]:
        """
        Parse LLM analysis into structured format.

        Args:
            content: Raw LLM response

        Returns:
            Parsed analysis dictionary
        """
        analysis = {
            "error_identification": None,
            "root_cause": None,
            "correct_approach": None,
            "key_insight": None,
        }

        # Parse markdown sections
        lines = content.split("\n")
        current_section = None
        current_text = []

        section_map = {
            "error identification": "error_identification",
            "root cause": "root_cause",
            "correct approach": "correct_approach",
            "key insight": "key_insight",
        }

        for line in lines:
            # Check for section headers
            line_lower = line.strip().lower()
            matched_section = None

            for key, value in section_map.items():
                if line_lower.startswith("###") and key in line_lower:
                    matched_section = value
                    break
                elif line_lower.startswith("**") and key in line_lower:
                    matched_section = value
                    break

            if matched_section:
                # Save previous section
                if current_section and current_text:
                    analysis[current_section] = "\n".join(current_text).strip()

                # Start new section
                current_section = matched_section
                current_text = []
                continue

            # Add content to current section
            if current_section and line.strip():
                # Skip markdown artifacts
                if not line.strip().startswith("#") and not line.strip().startswith("**"):
                    current_text.append(line.strip())

        # Save last section
        if current_section and current_text:
            analysis[current_section] = "\n".join(current_text).strip()

        return analysis

    def _score_analysis_quality(
        self,
        analysis: dict[str, Any],
        environment_feedback: EnvironmentFeedback,
    ) -> float:
        """
        Score the quality of analysis.

        Args:
            analysis: Parsed analysis
            environment_feedback: Environment feedback

        Returns:
            Quality score (0-1)
        """
        score = 0.0
        max_score = 4.0

        # Check completeness
        if analysis.get("error_identification"):
            score += 1.0
        if analysis.get("root_cause"):
            score += 1.0
        if analysis.get("correct_approach"):
            score += 1.0
        if analysis.get("key_insight"):
            score += 1.0

        # Bonus for specificity (longer, more detailed responses)
        total_length = sum(
            len(str(v)) for v in analysis.values() if v
        )

        if total_length > 200:
            score += 0.2
        if total_length > 500:
            score += 0.2

        # Normalize to 0-1
        return min(score / max_score, 1.0)

    def _tag_bullets(
        self,
        bullets_used: list[str],
        bullet_feedback: dict[str, str],
        environment_result: str,
        analysis: dict[str, Any],
    ) -> list[BulletFeedback]:
        """
        Tag bullets based on task outcome.

        Args:
            bullets_used: List of bullet IDs used
            bullet_feedback: Initial feedback from generator
            environment_result: Task result (SUCCESS/FAILED/etc)
            analysis: Reflection analysis

        Returns:
            List of bullet feedback tags
        """
        bullet_tags = []

        # Simple heuristic: if task succeeded, mark bullets as helpful
        # If task failed, mark as harmful (can be refined with more sophisticated logic)
        if environment_result == "SUCCESS":
            default_tag = "helpful"
        elif environment_result == "FAILED":
            default_tag = "harmful"
        else:
            default_tag = "neutral"

        for bullet_id in bullets_used:
            # Use generator's initial feedback if available
            tag = bullet_feedback.get(bullet_id, default_tag)

            bullet_tags.append(
                BulletFeedback(
                    bullet_id=bullet_id,
                    tag=tag,  # type: ignore
                )
            )

        # TODO: Enhance with LLM-based bullet attribution
        # Analyze which bullets were actually helpful vs misleading

        return bullet_tags

    def get_statistics(self) -> dict[str, Any]:
        """
        Get reflector statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "provider": self.llm_client.provider,
            "model": self.llm_client.model,
            "max_refinement_rounds": self.max_refinement_rounds,
            "enable_iterative": self.enable_iterative,
        }
