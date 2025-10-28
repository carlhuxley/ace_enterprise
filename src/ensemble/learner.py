"""
Ensemble Learner - Orchestrate multiple models learning in parallel.

Coordinates:
1. Parallel task execution across multiple LLM models
2. Cross-voting on proposed bullets
3. Consensus building and deduplication
4. Performance tracking and weighted voting
"""
import concurrent.futures
import logging
from datetime import datetime
from typing import Optional

from src.config.settings import settings
from src.core.curator.module import Curator
from src.core.generator.module import Generator
from src.core.reflector.module import Reflector
from src.ensemble.consensus import ConsensusBuilder
from src.ensemble.models import (
    BulletSection,
    ConsensusBullet,
    EnsembleResult,
    ModelPerformance,
    Vote,
    VoteResults,
    VoteType,
)
from src.ensemble.voting import VotingStrategy, VotingSystem
from src.playbook.manager import PlaybookManager
from src.storage.schemas import (
    BulletCreate,
    EnvironmentFeedback,
    TaskInput,
)
from src.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


class EnsembleLearner:
    """
    Ensemble learning system for ACE.

    Enables multiple LLM models to learn collaboratively:
    - Each model executes task independently
    - Models propose bullets from their analysis
    - Cross-voting on all proposals
    - Consensus-based bullet selection
    """

    def __init__(
        self,
        models: list[tuple[str, str] | tuple[str, str, str]],  # [(provider, model_name[, base_url]), ...]
        playbook_id: str,
        voting_strategy: Optional[VotingStrategy] = None,
        similarity_threshold: float = 0.85,
        enable_deliberation: bool = True,
        deliberation_threshold_low: float = 0.4,
        deliberation_threshold_high: float = 0.6,
        max_deliberation_rounds: int = 2,
    ):
        """
        Initialize ensemble learner.

        Args:
            models: List of (provider, model_name) or (provider, model_name, base_url) tuples
            playbook_id: Shared playbook for all models
            voting_strategy: Voting strategy (default: majority)
            similarity_threshold: Threshold for clustering similar bullets
            enable_deliberation: Enable deliberative discussion for contested bullets
            deliberation_threshold_low: Lower approval rate for contested bullets (default: 40%)
            deliberation_threshold_high: Upper approval rate for contested bullets (default: 60%)
            max_deliberation_rounds: Maximum discussion rounds per bullet (default: 2)
        """
        self.models = models
        self.playbook_id = playbook_id
        self.playbook_manager = PlaybookManager()
        self.voting_system = VotingSystem(voting_strategy)
        self.consensus_builder = ConsensusBuilder(similarity_threshold)

        # Deliberation settings
        self.enable_deliberation = enable_deliberation
        self.deliberation_threshold_low = deliberation_threshold_low
        self.deliberation_threshold_high = deliberation_threshold_high
        self.max_deliberation_rounds = max_deliberation_rounds

        # Track model performance
        self.model_performance: dict[str, ModelPerformance] = {}
        for model_tuple in models:
            provider, model = model_tuple[0], model_tuple[1]
            model_id = f"{provider}/{model}"
            self.model_performance[model_id] = ModelPerformance(model_id=model_id)

        logger.info(
            f"Initialized ensemble with {len(models)} models: "
            f"{', '.join(f'{m[0]}/{m[1]}' for m in models)}"
        )

    def learn_from_task(
        self,
        task: TaskInput,
        environment_feedback: EnvironmentFeedback,
        parallel: bool = True,
    ) -> EnsembleResult:
        """
        Execute full ensemble learning cycle.

        Args:
            task: Task to learn from
            environment_feedback: Execution result
            parallel: Run models in parallel (default: True)

        Returns:
            EnsembleResult with consensus bullets and performance metrics
        """
        started_at = datetime.now()

        logger.info(
            f"Starting ensemble learning for task {task.id} "
            f"({len(self.models)} models, parallel={parallel})"
        )

        # Step 1: Parallel execution across models
        model_proposals = self._execute_models(task, environment_feedback, parallel)

        # Step 2: Collect all proposed bullets
        all_proposals = []
        for model_id, proposals in model_proposals.items():
            all_proposals.extend(proposals)
            logger.info(f"  {model_id}: {len(proposals)} proposals")

        logger.info(f"📊 Collected {len(all_proposals)} total bullet proposals")

        # Step 3: Cluster similar bullets
        logger.info("🔍 Clustering similar bullets...")
        consensus_bullets = self.consensus_builder.build_consensus(all_proposals)

        logger.info(
            f"✓ After deduplication: {len(consensus_bullets)} unique bullets"
        )

        # Step 4: Cross-voting
        logger.info("🗳️  Conducting cross-voting...")
        self._conduct_cross_voting(consensus_bullets, model_proposals)
        logger.info("✓ Cross-voting complete")

        # Step 4.5: Deliberative discussion for contested bullets
        if self.enable_deliberation:
            logger.info("💬 Checking for contested bullets requiring deliberation...")
            contested_count = self._conduct_deliberation(consensus_bullets, model_proposals)
            if contested_count > 0:
                logger.info(f"✓ Deliberation complete: {contested_count} bullets discussed")
            else:
                logger.info("✓ No contested bullets found")

        # Step 5: Apply voting strategy to decide which bullets to keep
        logger.info("⚖️  Applying voting strategy...")
        approved, rejected = self.voting_system.vote_on_bullets(
            consensus_bullets, self.model_performance
        )
        logger.info(f"✓ Voting complete: {len(approved)} approved, {len(rejected)} rejected")

        # Step 6: Calculate metrics
        vote_results = self._calculate_vote_results(consensus_bullets)
        diversity_score = self.consensus_builder.calculate_diversity_score(all_proposals)
        consensus_strength = self.consensus_builder.calculate_consensus_strength(
            consensus_bullets
        )

        # Step 7: Update model performance
        self._update_model_performance(consensus_bullets)

        completed_at = datetime.now()

        result = EnsembleResult(
            task_description=task.query,
            models_used=[f"{m[0]}/{m[1]}" for m in self.models],
            voting_strategy=self.voting_system.strategy.name(),
            bullets=consensus_bullets,
            vote_results=vote_results,
            model_performance=self.model_performance.copy(),
            started_at=started_at,
            completed_at=completed_at,
            diversity_score=diversity_score,
            consensus_strength=consensus_strength,
        )

        logger.info(
            f"Ensemble learning complete: {len(approved)} bullets approved, "
            f"{len(rejected)} rejected in {result.duration_seconds:.1f}s"
        )

        return result

    def _execute_models(
        self,
        task: TaskInput,
        environment_feedback: EnvironmentFeedback,
        parallel: bool,
    ) -> dict[str, list[ConsensusBullet]]:
        """
        Execute task across all models and collect proposals.

        Args:
            task: Task to execute
            environment_feedback: Execution feedback
            parallel: Run in parallel

        Returns:
            Dict mapping model_id -> proposed bullets
        """
        if parallel:
            return self._execute_models_parallel(task, environment_feedback)
        else:
            return self._execute_models_sequential(task, environment_feedback)

    def _execute_models_parallel(
        self,
        task: TaskInput,
        environment_feedback: EnvironmentFeedback,
    ) -> dict[str, list[ConsensusBullet]]:
        """Execute models in parallel using ThreadPoolExecutor."""
        proposals = {}

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(self.models)
        ) as executor:
            # Submit all tasks
            future_to_model = {}
            for model_tuple in self.models:
                provider, model = model_tuple[0], model_tuple[1]
                base_url = model_tuple[2] if len(model_tuple) > 2 else None
                model_id = f"{provider}/{model}"

                future = executor.submit(
                    self._execute_single_model, provider, model, task, environment_feedback, base_url
                )
                future_to_model[future] = model_id

            # Collect results
            for future in concurrent.futures.as_completed(future_to_model):
                model_id = future_to_model[future]
                try:
                    model_proposals = future.result()
                    proposals[model_id] = model_proposals
                    logger.debug(
                        f"Model {model_id} proposed {len(model_proposals)} bullets"
                    )
                except Exception as e:
                    logger.error(f"Model {model_id} failed: {e}")
                    proposals[model_id] = []

        return proposals

    def _execute_models_sequential(
        self,
        task: TaskInput,
        environment_feedback: EnvironmentFeedback,
    ) -> dict[str, list[ConsensusBullet]]:
        """Execute models sequentially (for debugging)."""
        proposals = {}

        for i, model_tuple in enumerate(self.models, 1):
            provider, model = model_tuple[0], model_tuple[1]
            base_url = model_tuple[2] if len(model_tuple) > 2 else None
            model_id = f"{provider}/{model}"
            logger.info(f"[{i}/{len(self.models)}] Starting model: {model_id}")
            try:
                model_proposals = self._execute_single_model(
                    provider, model, task, environment_feedback, base_url
                )
                proposals[model_id] = model_proposals
                logger.info(f"[{i}/{len(self.models)}] ✓ {model_id} proposed {len(model_proposals)} bullets")
            except Exception as e:
                logger.error(f"[{i}/{len(self.models)}] ✗ {model_id} failed: {e}")
                proposals[model_id] = []

        return proposals

    def _execute_single_model(
        self,
        provider: str,
        model: str,
        task: TaskInput,
        environment_feedback: EnvironmentFeedback,
        base_url: Optional[str] = None,
    ) -> list[ConsensusBullet]:
        """
        Execute Generator -> Reflector -> Curator for a single model.

        Args:
            provider: LLM provider
            model: Model name
            task: Task to execute
            environment_feedback: Execution feedback
            base_url: Custom base URL for vLLM endpoints

        Returns:
            List of proposed bullets
        """
        model_id = f"{provider}/{model}"

        # Create model-specific LLM client
        llm_client = LLMClient(provider=provider, model=model, base_url=base_url)

        # Initialize ACE modules
        generator = Generator(
            playbook_manager=self.playbook_manager,
            llm_client=llm_client,
        )
        reflector = Reflector(llm_client=llm_client)
        curator = Curator(
            playbook_manager=self.playbook_manager,
            llm_client=llm_client,
        )

        # Run Generator
        logger.info(f"  → Running Generator for {model_id}...")
        generator_output = generator.execute(task, self.playbook_id)
        logger.info(f"  → Generator complete for {model_id}")

        # Run Reflector
        logger.info(f"  → Running Reflector for {model_id}...")
        reflector_output = reflector.reflect(task, generator_output, environment_feedback)
        logger.info(f"  → Reflector complete for {model_id}")

        # Run Curator
        logger.info(f"  → Running Curator for {model_id}...")
        curator_output = curator.curate(
            reflector_output=reflector_output,
            playbook_id=self.playbook_id,
            task_context=task.context if hasattr(task, 'context') else None,
        )
        logger.info(f"  → Curator complete for {model_id} ({len(curator_output.delta_bullets)} bullets)")

        # Convert curator bullets to ConsensusBullets
        consensus_bullets = []

        for bullet in curator_output.delta_bullets:
            # Map section names to BulletSection enum
            section_map = {
                "strategies_and_hard_rules": BulletSection.STRATEGIES,
                "code_snippets": BulletSection.CODE_SNIPPETS,
                "troubleshooting_tips": BulletSection.TROUBLESHOOTING,
                "domain_knowledge": BulletSection.DOMAIN,
            }

            section = section_map.get(
                bullet.section, BulletSection.STRATEGIES
            )

            consensus_bullet = ConsensusBullet(
                content=bullet.content,
                section=section,
                tags=bullet.tags,
                proposed_by=model_id,
                proposal_reasoning=f"Generated by {model_id} during ACE learning cycle. "
                f"Reasoning: {curator_output.reasoning[:100]}...",
            )

            consensus_bullets.append(consensus_bullet)

        logger.debug(f"Model {model_id} generated {len(consensus_bullets)} bullets")

        # Update performance tracking
        perf = self.model_performance[model_id]
        perf.proposals_made += len(consensus_bullets)

        return consensus_bullets

    def _conduct_cross_voting(
        self,
        bullets: list[ConsensusBullet],
        model_proposals: dict[str, list[ConsensusBullet]],
    ) -> None:
        """
        Have each model vote on all bullets (including their own).

        Args:
            bullets: All consensus bullets to vote on
            model_proposals: Original proposals by each model
        """
        logger.info(f"Starting cross-voting on {len(bullets)} bullets")

        for bullet in bullets:
            # Each model votes
            for model_id in model_proposals.keys():
                # Create LLM client for this model
                provider, model = model_id.split("/")

                # Find base_url if this is a vLLM model
                base_url = None
                for model_tuple in self.models:
                    if f"{model_tuple[0]}/{model_tuple[1]}" == model_id:
                        base_url = model_tuple[2] if len(model_tuple) > 2 else None
                        break

                llm_client = LLMClient(provider=provider, model=model, base_url=base_url)

                # Get vote from model
                vote = self._get_model_vote(bullet, model_id, llm_client)
                bullet.add_vote(vote)

                # Update performance
                perf = self.model_performance[model_id]
                perf.votes_cast += 1
                perf.avg_confidence = (
                    (perf.avg_confidence * (perf.votes_cast - 1) + vote.confidence)
                    / perf.votes_cast
                )

        logger.info(
            f"Cross-voting complete: {len(bullets)} bullets x {len(model_proposals)} models "
            f"= {len(bullets) * len(model_proposals)} total votes"
        )

    def _conduct_deliberation(
        self,
        bullets: list[ConsensusBullet],
        model_proposals: dict[str, list[ConsensusBullet]],
    ) -> int:
        """
        Conduct deliberative discussion for contested bullets.

        Identifies bullets with close votes (e.g., 40-60% approval) and has
        models discuss them, potentially revising their votes.

        Args:
            bullets: All consensus bullets to check
            model_proposals: Original proposals by each model

        Returns:
            Number of bullets that underwent deliberation
        """
        # Find contested bullets
        contested = [
            bullet for bullet in bullets
            if bullet.is_contested(
                self.deliberation_threshold_low,
                self.deliberation_threshold_high
            )
        ]

        if not contested:
            return 0

        logger.info(
            f"Found {len(contested)} contested bullets "
            f"(approval rate {self.deliberation_threshold_low:.0%}-{self.deliberation_threshold_high:.0%})"
        )

        # Conduct discussion rounds for each contested bullet
        for bullet in contested:
            logger.debug(
                f"Starting deliberation on bullet: {bullet.content[:50]}... "
                f"(current approval: {bullet.approval_rate:.0%})"
            )

            for round_num in range(1, self.max_deliberation_rounds + 1):
                logger.debug(f"  Deliberation round {round_num}/{self.max_deliberation_rounds}")

                # Have each model reconsider their vote
                votes_changed = 0
                for model_id in model_proposals.keys():
                    # Get model's current vote
                    current_vote = bullet.get_vote(model_id)
                    if not current_vote:
                        continue  # Skip if model hasn't voted

                    # Create LLM client for this model
                    provider, model = model_id.split("/")
                    base_url = None
                    for model_tuple in self.models:
                        if f"{model_tuple[0]}/{model_tuple[1]}" == model_id:
                            base_url = model_tuple[2] if len(model_tuple) > 2 else None
                            break

                    llm_client = LLMClient(provider=provider, model=model, base_url=base_url)

                    # Get updated vote after seeing others' reasoning
                    new_vote = self._get_deliberation_vote(
                        bullet, model_id, current_vote, llm_client
                    )

                    # Check if vote changed
                    if new_vote.vote != current_vote.vote:
                        votes_changed += 1
                        logger.debug(
                            f"    {model_id}: {current_vote.vote.value} → {new_vote.vote.value}"
                        )

                    # Update the vote
                    bullet.add_vote(new_vote, allow_update=True)

                # Update deliberation count
                bullet.deliberation_rounds += 1

                # Check if still contested after this round
                if not bullet.is_contested(
                    self.deliberation_threshold_low,
                    self.deliberation_threshold_high
                ):
                    logger.debug(
                        f"  Consensus reached after round {round_num} "
                        f"(final approval: {bullet.approval_rate:.0%})"
                    )
                    break

                # If no votes changed, stop deliberating
                if votes_changed == 0:
                    logger.debug(
                        f"  No votes changed in round {round_num}, ending deliberation"
                    )
                    break

        return len(contested)

    def _get_model_vote(
        self,
        bullet: ConsensusBullet,
        model_id: str,
        llm_client: LLMClient,
    ) -> Vote:
        """
        Get a single model's vote on a bullet using LLM-based evaluation.

        Args:
            bullet: Bullet to vote on
            model_id: Voting model ID
            llm_client: LLM client for this model

        Returns:
            Vote object with LLM reasoning
        """
        # Create voting prompt
        voting_prompt = self._create_voting_prompt(bullet, model_id)

        try:
            # Ask LLM to evaluate the bullet
            response = llm_client.generate(
                prompt=voting_prompt,
                system_prompt=(
                    "You are a code quality expert evaluating proposed knowledge bullets. "
                    "Analyze the bullet critically and provide honest assessment."
                ),
                max_tokens=300,
                temperature=0.3,  # Lower temperature for more consistent voting
            )

            # Parse LLM response
            vote_result = self._parse_vote_response(response["content"], model_id)

            logger.debug(
                f"Model {model_id} voted {vote_result.vote.value} on bullet "
                f"(confidence: {vote_result.confidence:.2f})"
            )

            return vote_result

        except Exception as e:
            # Fallback to heuristic voting on error
            logger.warning(
                f"LLM voting failed for model {model_id}, using fallback: {e}"
            )
            return self._fallback_heuristic_vote(bullet, model_id)

    def _create_voting_prompt(self, bullet: ConsensusBullet, voter_id: str) -> str:
        """
        Create a structured prompt for LLM-based voting.

        Args:
            bullet: Bullet to evaluate
            voter_id: ID of the voting model

        Returns:
            Formatted voting prompt
        """
        is_own_proposal = bullet.proposed_by == voter_id

        prompt = f"""# Evaluate This Knowledge Bullet

**Task Context**: We are building a shared knowledge base (playbook) to help solve coding tasks.

**Proposed Bullet**:
Section: {bullet.section.value}
Content: {bullet.content}
Proposed by: {"You (this model)" if is_own_proposal else f"Another model ({bullet.proposed_by})"}
Reasoning: {bullet.proposal_reasoning}

**Your Task**: Evaluate whether this bullet should be added to the shared playbook.

**Evaluation Criteria**:
1. **Accuracy**: Is the information correct and technically sound?
2. **Usefulness**: Will this help solve future tasks in this domain?
3. **Clarity**: Is it clear, specific, and actionable?
4. **Relevance**: Does it belong in the "{bullet.section.value}" section?
5. **Non-Redundancy**: Does it add unique value (not generic advice)?

**Response Format**:
VOTE: [APPROVE/REJECT/ABSTAIN]
CONFIDENCE: [0.0-1.0]
REASONING: [1-2 sentences explaining your vote]

**Example**:
VOTE: APPROVE
CONFIDENCE: 0.85
REASONING: This bullet provides specific, actionable guidance for email validation that will help prevent common bugs. The regex pattern is correct and the explanation is clear.

Now evaluate the bullet above:"""

        return prompt

    def _get_deliberation_vote(
        self,
        bullet: ConsensusBullet,
        model_id: str,
        current_vote: Vote,
        llm_client: LLMClient,
    ) -> Vote:
        """
        Get updated vote after model sees other models' reasoning.

        Args:
            bullet: Bullet being discussed
            model_id: Voting model ID
            current_vote: Model's current vote
            llm_client: LLM client for this model

        Returns:
            Updated Vote object (may be same as current or different)
        """
        # Create deliberation prompt showing all votes
        deliberation_prompt = self._create_deliberation_prompt(
            bullet, model_id, current_vote
        )

        try:
            # Ask LLM to reconsider vote
            response = llm_client.generate(
                prompt=deliberation_prompt,
                system_prompt=(
                    "You are a code quality expert participating in peer review. "
                    "You can change your vote based on others' arguments, but only if they're convincing."
                ),
                max_tokens=300,
                temperature=0.3,
            )

            # Parse updated vote
            new_vote = self._parse_vote_response(response["content"], model_id)
            return new_vote

        except Exception as e:
            logger.warning(
                f"Deliberation failed for {model_id}, keeping current vote: {e}"
            )
            # Return current vote unchanged on error
            return current_vote

    def _create_deliberation_prompt(
        self,
        bullet: ConsensusBullet,
        voter_id: str,
        current_vote: Vote,
    ) -> str:
        """
        Create deliberation prompt showing other models' votes and reasoning.

        Args:
            bullet: Bullet under discussion
            voter_id: ID of the voting model
            current_vote: Model's current vote

        Returns:
            Formatted deliberation prompt
        """
        # Build summary of all votes
        vote_summary = []
        for vote in bullet.votes:
            if vote.model_id == voter_id:
                continue  # Skip own vote

            vote_emoji = {"approve": "✅", "reject": "❌", "abstain": "⏸️"}.get(
                vote.vote.value, "?"
            )
            vote_summary.append(
                f"- **{vote.model_id}**: {vote_emoji} {vote.vote.value.upper()} "
                f"(confidence: {vote.confidence:.2f})\n"
                f"  Reasoning: {vote.reasoning}"
            )

        votes_text = "\n".join(vote_summary)

        current_vote_emoji = {"approve": "✅", "reject": "❌", "abstain": "⏸️"}.get(
            current_vote.vote.value, "?"
        )

        prompt = f"""# Deliberative Discussion: Reconsider Your Vote

**Contested Bullet** (close vote, {bullet.approval_rate:.0%} approval):
Section: {bullet.section.value}
Content: {bullet.content}
Proposed by: {bullet.proposed_by}

**Your Current Vote**:
{current_vote_emoji} {current_vote.vote.value.upper()} (confidence: {current_vote.confidence:.2f})
Your reasoning: {current_vote.reasoning}

**Other Models' Votes and Reasoning**:
{votes_text}

**Task**: After reading the other models' arguments, reconsider your vote.

**Guidelines**:
- If others raised valid points you didn't consider, you MAY change your vote
- If you still stand by your original assessment, keep your vote
- Don't change just to agree - only change if convinced by the arguments

**Response Format**:
VOTE: [APPROVE/REJECT/ABSTAIN]
CONFIDENCE: [0.0-1.0]
REASONING: [1-2 sentences explaining your decision, mention if you were convinced by others' arguments or why you're keeping your vote]

Your reconsidered vote:"""

        return prompt

    def _parse_vote_response(self, response: str, model_id: str) -> Vote:
        """
        Parse LLM voting response into Vote object.

        Args:
            response: LLM response text
            model_id: Voting model ID

        Returns:
            Parsed Vote object
        """
        import re

        # Extract vote type
        vote_match = re.search(r'VOTE:\s*(APPROVE|REJECT|ABSTAIN)', response, re.IGNORECASE)
        if vote_match:
            vote_str = vote_match.group(1).upper()
            vote_type = VoteType[vote_str]
        else:
            # Default to APPROVE if parsing fails
            logger.warning(f"Could not parse vote type from response, defaulting to APPROVE")
            vote_type = VoteType.APPROVE

        # Extract confidence
        conf_match = re.search(r'CONFIDENCE:\s*(0?\.\d+|1\.0|[01])', response, re.IGNORECASE)
        if conf_match:
            confidence = float(conf_match.group(1))
            confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
        else:
            # Default confidence based on vote type
            confidence = 0.7 if vote_type == VoteType.APPROVE else 0.6
            logger.warning(f"Could not parse confidence, using default: {confidence}")

        # Extract reasoning
        reasoning_match = re.search(r'REASONING:\s*(.+?)(?:\n\n|\Z)', response, re.IGNORECASE | re.DOTALL)
        if reasoning_match:
            reasoning = reasoning_match.group(1).strip()
        else:
            # Use full response as reasoning if format not followed
            reasoning = response.strip()[:200]  # Truncate if too long

        return Vote(
            model_id=model_id,
            vote=vote_type,
            reasoning=reasoning,
            confidence=confidence,
        )

    def _fallback_heuristic_vote(
        self,
        bullet: ConsensusBullet,
        model_id: str,
    ) -> Vote:
        """
        Fallback heuristic voting when LLM voting fails.

        This is the original MVP voting logic, kept as a safety net.

        Args:
            bullet: Bullet to vote on
            model_id: Voting model ID

        Returns:
            Vote object with heuristic reasoning
        """
        # If this model proposed the bullet, approve with high confidence
        if bullet.proposed_by == model_id or bullet.proposed_by.startswith("consensus"):
            return Vote(
                model_id=model_id,
                vote=VoteType.APPROVE,
                reasoning="I proposed this bullet or it's a consensus from similar proposals",
                confidence=0.9,
            )

        # Otherwise, approve with medium confidence (consensus by default)
        return Vote(
            model_id=model_id,
            vote=VoteType.APPROVE,
            reasoning="Looks reasonable based on task context (fallback heuristic)",
            confidence=0.7,
        )

    def _calculate_vote_results(
        self, bullets: list[ConsensusBullet]
    ) -> VoteResults:
        """Calculate aggregate voting results."""
        approved = sum(1 for b in bullets if b.approved is True)
        rejected = sum(1 for b in bullets if b.approved is False)
        pending = sum(1 for b in bullets if b.approved is None)

        # Breakdown by strategy
        strategy_counts = {
            "majority": 0,
            "supermajority": 0,
            "weighted": 0,
            "unanimous": 0,
        }

        for bullet in bullets:
            if bullet.approved and bullet.approval_strategy:
                for key in strategy_counts:
                    if key in bullet.approval_strategy:
                        strategy_counts[key] += 1
                        break

        # Quality metrics
        voted_bullets = [b for b in bullets if b.votes]
        avg_approval_rate = (
            sum(b.approval_rate for b in voted_bullets) / len(voted_bullets)
            if voted_bullets
            else 0.0
        )
        avg_confidence = (
            sum(b.avg_confidence for b in voted_bullets) / len(voted_bullets)
            if voted_bullets
            else 0.0
        )
        avg_deliberation = (
            sum(b.deliberation_rounds for b in bullets) / len(bullets)
            if bullets
            else 0.0
        )

        # Disagreement analysis
        highly_contested = sum(
            1 for b in bullets if 0.4 <= b.approval_rate <= 0.6
        )
        unanimous = sum(
            1 for b in bullets if b.approval_rate in (0.0, 1.0)
        )

        return VoteResults(
            total_bullets=len(bullets),
            approved=approved,
            rejected=rejected,
            pending=pending,
            majority_approved=strategy_counts["majority"],
            supermajority_approved=strategy_counts["supermajority"],
            weighted_approved=strategy_counts["weighted"],
            unanimous_approved=strategy_counts["unanimous"],
            avg_approval_rate=avg_approval_rate,
            avg_confidence=avg_confidence,
            avg_deliberation_rounds=avg_deliberation,
            highly_contested=highly_contested,
            unanimous_decisions=unanimous,
        )

    def _update_model_performance(
        self, bullets: list[ConsensusBullet]
    ) -> None:
        """Update model performance based on voting results."""
        for bullet in bullets:
            if bullet.approved is None:
                continue

            # Update proposer stats
            if bullet.proposed_by in self.model_performance:
                perf = self.model_performance[bullet.proposed_by]
                if bullet.approved:
                    perf.proposals_approved += 1
                else:
                    perf.proposals_rejected += 1

            # Update voter stats (did they agree with final decision?)
            for vote in bullet.votes:
                if vote.model_id not in self.model_performance:
                    continue

                perf = self.model_performance[vote.model_id]

                # Check if vote matched final decision
                vote_agreed = (
                    (vote.vote == VoteType.APPROVE and bullet.approved)
                    or (vote.vote == VoteType.REJECT and not bullet.approved)
                )

                if vote_agreed:
                    perf.votes_with_majority += 1

        # Calculate accuracy and update voting weights
        for model_id, perf in self.model_performance.items():
            if perf.votes_cast > 0:
                agreement_rate = perf.votes_with_majority / perf.votes_cast
                perf.accuracy_score = agreement_rate

                # Update voting weight based on accuracy
                # Weight ranges from 0.5 (50% agreement) to 1.5 (100% agreement)
                perf.voting_weight = 0.5 + agreement_rate

        logger.debug(
            "Updated model performance: "
            f"{', '.join(f'{m}: {p.accuracy_score:.2%}' for m, p in self.model_performance.items())}"
        )

    def add_approved_bullets_to_playbook(
        self, result: EnsembleResult
    ) -> int:
        """
        Add approved consensus bullets to the shared playbook.

        Args:
            result: Ensemble result with approved bullets

        Returns:
            Number of bullets added
        """
        added = 0

        for bullet in result.approved_bullets:
            # Convert back to BulletCreate format
            bullet_data = BulletCreate(
                content=bullet.content,
                section=bullet.section.value,
                tags=bullet.tags,
            )

            try:
                self.playbook_manager.add_bullet(self.playbook_id, bullet_data)
                added += 1
            except Exception as e:
                logger.warning(f"Failed to add bullet to playbook: {e}")

        logger.info(
            f"Added {added}/{len(result.approved_bullets)} approved bullets to playbook"
        )

        return added
