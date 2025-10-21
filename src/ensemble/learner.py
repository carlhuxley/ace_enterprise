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
    ):
        """
        Initialize ensemble learner.

        Args:
            models: List of (provider, model_name) or (provider, model_name, base_url) tuples
            playbook_id: Shared playbook for all models
            voting_strategy: Voting strategy (default: majority)
            similarity_threshold: Threshold for clustering similar bullets
        """
        self.models = models
        self.playbook_id = playbook_id
        self.playbook_manager = PlaybookManager()
        self.voting_system = VotingSystem(voting_strategy)
        self.consensus_builder = ConsensusBuilder(similarity_threshold)

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

    def _get_model_vote(
        self,
        bullet: ConsensusBullet,
        model_id: str,
        llm_client: LLMClient,
    ) -> Vote:
        """
        Get a single model's vote on a bullet.

        Args:
            bullet: Bullet to vote on
            model_id: Voting model ID
            llm_client: LLM client for this model

        Returns:
            Vote object
        """
        # For MVP, use simple heuristic voting
        # In Phase 2, we'll add LLM-based reasoning

        # If this model proposed the bullet, approve with high confidence
        if bullet.proposed_by == model_id or bullet.proposed_by.startswith("consensus"):
            return Vote(
                model_id=model_id,
                vote=VoteType.APPROVE,
                reasoning="I proposed this bullet or it's a consensus from similar proposals",
                confidence=0.9,
            )

        # Otherwise, approve with medium confidence (consensus by default)
        # In Phase 2, we'll actually ask the LLM to evaluate
        return Vote(
            model_id=model_id,
            vote=VoteType.APPROVE,
            reasoning="Looks reasonable based on task context",
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
