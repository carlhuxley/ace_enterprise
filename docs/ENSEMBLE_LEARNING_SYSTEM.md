# ACE Ensemble Learning & Deliberative Committee System

**Status:** Concept / Future Enhancement
**Created:** 2025-10-18
**Priority:** High-value innovation for quality & learning speed

---

## 🎯 Executive Summary

Transform ACE from single-model learning into a **multi-model ensemble system** where:
- Multiple local LLMs learn simultaneously from the same task
- Models vote on each other's proposed bullets
- Time-boxed deliberation resolves disagreements
- Consensus filtering produces higher-quality playbooks
- Learning speed increases 3-5x while remaining FREE

**Key Innovation:** "Committee of AI Advisors" with forced consensus under deadline constraints.

---

## 🧠 Core Concepts

### **1. Ensemble Learning**
Run the same task through multiple models in parallel, each contributing unique perspectives:

```
Single Model Learning:
Task → qwen3 → 20 bullets (60% quality)

Ensemble Learning:
Task → qwen3      → 20 bullets
     → deepseek   → 18 bullets
     → codellama  → 22 bullets
     → mistral    → 19 bullets
     → phi-2      → 15 bullets
     ────────────────────────────
     Raw: 94 bullets
     After dedup: ~60 unique bullets
     After voting: ~40 high-quality bullets (85% quality)
```

**Why This Works:**
- ✅ **Diversity:** Different models have different strengths/biases
- ✅ **Error Cancellation:** Multiple models catch each other's mistakes
- ✅ **Consensus Quality:** Patterns agreed upon by 4-5 models are highly reliable
- ✅ **Still Free:** All local models (Ollama)

### **2. Deliberative Voting**
Models don't just generate independently - they **review and vote** on each other's proposals:

```
Round 1: PROPOSE
├─ Each model generates bullets from task
└─ Tag with source (proposed_by: "qwen3")

Round 2: VOTE
├─ Each model votes on ALL bullets (helpful/harmful/neutral)
├─ Provides reasoning for votes
└─ Creates vote matrix

Round 3: DELIBERATE (for contested bullets)
├─ Bullets with mixed votes discussed
├─ Models argue their positions
├─ Synthesis or forced decision
└─ Final vote

Result: Peer-reviewed, high-confidence bullets
```

### **3. Time-Boxed Constraints**
Prevent infinite deliberation with forcing functions:

```
Time Budget: 5 minutes per bullet
├─ 0-3 min: Vote + initial reasoning
├─ 3-4 min: Discussion (if needed)
├─ 4-5 min: Final decision required
└─ 5 min: FORCED DECISION or REJECT

Escalating Thresholds:
├─ Early (0-40%):   Require 80% agreement (4/5 models)
├─ Mid (40-70%):    Require 60% agreement (3/5 models)
├─ Late (70-90%):   Simple majority (3/5 models)
└─ Final (90-100%): DECIDE NOW or default to REJECT
```

---

## 🏗️ Architecture

### **System Overview**
```
┌─────────────────────────────────────────────────────┐
│           Task: Build Password Validator            │
└─────────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┬───────────┐
        ▼               ▼               ▼           ▼
   ┌────────┐      ┌────────┐     ┌────────┐  ┌────────┐
   │ Model  │      │ Model  │     │ Model  │  │ Model  │
   │   A    │      │   B    │     │   C    │  │   D    │
   └────────┘      └────────┘     └────────┘  └────────┘
        │               │               │           │
        ├─ Proposes ────┼───────────────┼───────────┤
        │  20 bullets   │  18 bullets   │ 22 bullets│ 15 bullets
        │               │               │           │
        └───────────────┴───────────────┴───────────┘
                        ▼
                ┌──────────────┐
                │ Vote Matrix  │
                │ (cross-vote) │
                └──────────────┘
                        ▼
                ┌──────────────┐
                │  Consensus   │
                │   Builder    │
                └──────────────┘
                        ▼
                ┌──────────────┐
                │ High-quality │
                │   Bullets    │
                │ (40 approved)│
                └──────────────┘
```

### **Key Components**

#### **1. Ensemble Learner**
```python
class EnsembleLearner:
    """Coordinates multiple models learning from same task."""

    def __init__(self, models: list[str]):
        self.models = models  # ["qwen3:1.7b", "deepseek-coder", ...]
        self.consensus_builder = ConsensusBuilder()
        self.voting_system = VotingSystem()

    def learn_from_task(
        self,
        task: TaskInput,
        playbook_id: str
    ) -> EnsembleResult:
        """
        1. Run task with all models in parallel
        2. Collect proposed bullets from each
        3. Cross-vote on all proposals
        4. Build consensus
        5. Return high-quality bullets
        """
        pass
```

#### **2. Voting System**
```python
class VotingSystem:
    """Manages cross-model voting on proposals."""

    def vote_on_proposals(
        self,
        proposals: dict[str, list[Bullet]]
    ) -> dict[str, VoteResults]:
        """
        Each model votes on ALL bullets (including own).

        Vote types:
        - helpful: Good pattern, should add
        - harmful: Bad pattern, should reject
        - neutral: Uncertain or context-dependent

        Returns vote matrix with reasoning.
        """
        pass

    def get_model_vote(
        self,
        voter: str,
        bullet: Bullet
    ) -> Vote:
        """
        Prompt voter model to review bullet.

        Includes:
        - Vote type (helpful/harmful/neutral)
        - Reasoning (1-2 sentences)
        - Confidence (0-1)
        """
        pass
```

#### **3. Consensus Builder**
```python
class ConsensusBuilder:
    """Builds consensus from multiple model votes."""

    def build_consensus(
        self,
        vote_results: dict[str, VoteResults]
    ) -> list[ConsensusBullet]:
        """
        Analyze votes to determine which bullets to accept.

        Strategies:
        - High consensus (4-5 models agree): Auto-approve
        - Medium consensus (3 models): Review/discuss
        - Low consensus (1-2 models): Reject or defer
        - Contradictions: Deliberate
        """
        pass

    def cluster_similar_bullets(
        self,
        all_bullets: list[Bullet]
    ) -> list[BulletCluster]:
        """
        Group semantically similar bullets.

        Uses embedding similarity to find:
        - Exact duplicates
        - Paraphrases (same idea, different wording)
        - Related concepts (merge or keep separate?)
        """
        pass
```

#### **4. Time-Boxed Deliberation**
```python
class DeliberativeCommittee:
    """Facilitates discussion with hard time limits."""

    def __init__(self):
        self.time_limits = {
            "per_bullet": 300,        # 5 min max per bullet
            "voting_round": 180,      # 3 min for all votes
            "discussion": 60,         # 1 min for discussion
        }
        self.decision_rules = EscalatingDecisionRules()

    def deliberate(
        self,
        contested_bullets: list[VoteResults],
        deadline: float
    ) -> list[Decision]:
        """
        Time-boxed discussion for contested bullets.

        Phases:
        1. Present disagreement
        2. Models argue positions (token-limited)
        3. Synthesize discussion
        4. Final vote or forced decision
        """
        pass

    def force_decision(
        self,
        bullet: Bullet,
        votes: VoteResults
    ) -> Decision:
        """
        When time runs out, force decision:

        - Conservative mode: Default to REJECT
        - Aggressive mode: Default to APPROVE
        - Use escalating thresholds
        """
        pass
```

---

## 📊 Data Structures

### **ConsensusBullet**
```python
class ConsensusBullet(Bullet):
    """Bullet with multi-model consensus metadata."""

    # Standard bullet fields
    id: str
    content: str
    section: str
    tags: list[str]
    embedding: list[float]

    # Consensus fields
    agreement_count: int              # How many models agreed
    source_models: list[str]          # Which models proposed/agreed
    confidence: float                 # agreement_count / total_models
    vote_breakdown: dict[str, str]    # model -> vote_type

    # Quality indicators
    is_unanimous: bool                # All models agreed
    is_contested: bool                # Mixed votes
    discussion_summary: Optional[str] # If deliberated

    def quality_score(self) -> float:
        """
        Calculate overall quality based on consensus.

        Factors:
        - Agreement count (more = better)
        - Unanimity bonus
        - Source model reputation
        """
        base_score = self.confidence

        if self.is_unanimous:
            base_score *= 1.2  # 20% bonus for unanimity

        return min(base_score, 1.0)
```

### **Vote**
```python
class Vote:
    """A single model's vote on a bullet."""

    voter: str                        # Model that voted
    type: Literal["helpful", "harmful", "neutral"]
    reasoning: str                    # 1-2 sentence explanation
    confidence: float                 # 0-1, how sure is the model
    timestamp: datetime
    tokens_used: int                  # Token budget tracking
```

### **VoteResults**
```python
class VoteResults:
    """Aggregated votes for a bullet."""

    bullet: Bullet
    votes: dict[str, Vote]            # model -> vote

    helpful_count: int
    harmful_count: int
    neutral_count: int

    def is_unanimous(self) -> bool:
        """All models voted the same way."""
        pass

    def is_contested(self) -> bool:
        """Significant disagreement (no clear majority)."""
        pass

    def majority_decision(self) -> Decision:
        """Simple majority wins."""
        pass

    def supermajority_decision(self, threshold: float = 0.66) -> Decision:
        """Require 2/3 agreement."""
        pass
```

### **EnsembleResult**
```python
class EnsembleResult:
    """Results from ensemble learning session."""

    # Approved bullets
    consensus_bullets: list[ConsensusBullet]

    # Raw data
    raw_bullets_by_model: dict[str, list[Bullet]]

    # Analysis
    agreement_matrix: AgreementMatrix
    total_proposed: int
    total_approved: int
    approval_rate: float

    # Time tracking
    time_elapsed: float
    bullets_per_second: float

    # Quality metrics
    avg_confidence: float
    unanimous_count: int
    contested_count: int
```

---

## 🎯 Voting Strategies

### **Strategy 1: Simple Majority**
```python
def simple_majority(votes: VoteResults) -> Decision:
    """
    Most votes wins.

    Use when: Fast decisions needed, trust all models equally
    """
    if votes.helpful_count > votes.harmful_count:
        return Decision.APPROVE
    else:
        return Decision.REJECT
```

### **Strategy 2: Supermajority**
```python
def supermajority(votes: VoteResults, threshold: float = 0.66) -> Decision:
    """
    Require 2/3+ agreement.

    Use when: Conservative, quality over quantity
    """
    total = len(votes.votes)

    if votes.helpful_count / total >= threshold:
        return Decision.APPROVE
    elif votes.harmful_count / total >= threshold:
        return Decision.REJECT
    else:
        return Decision.NEEDS_DISCUSSION
```

### **Strategy 3: Weighted Voting**
```python
def weighted_voting(
    votes: VoteResults,
    model_weights: dict[str, float]
) -> Decision:
    """
    Models with better track record have more voting power.

    Use when: Models have proven different accuracy levels
    """
    helpful_weight = sum(
        model_weights[model]
        for model, vote in votes.votes.items()
        if vote.type == "helpful"
    )

    harmful_weight = sum(
        model_weights[model]
        for model, vote in votes.votes.items()
        if vote.type == "harmful"
    )

    return Decision.APPROVE if helpful_weight > harmful_weight else Decision.REJECT
```

### **Strategy 4: Escalating Thresholds**
```python
def escalating_threshold(
    votes: VoteResults,
    time_progress: float  # 0.0 to 1.0
) -> Decision:
    """
    Required approval percentage decreases over time.

    Forces decision as deadline approaches.

    Use when: Time-boxed sessions, must make decisions
    """
    if time_progress < 0.3:
        threshold = 0.80  # Need 4/5 early on
    elif time_progress < 0.6:
        threshold = 0.60  # Need 3/5 mid-way
    else:
        threshold = 0.51  # Simple majority at end

    approval_rate = votes.helpful_count / len(votes.votes)

    return Decision.APPROVE if approval_rate >= threshold else Decision.REJECT
```

---

## ⏱️ Time-Boxing & Forcing Functions

### **Hard Time Limits**
```yaml
time_constraints:
  # Per-bullet limits
  proposal_generation: 30      # 30s per model to propose
  vote_per_bullet: 15          # 15s per vote
  discussion_per_bullet: 60    # 1 min to discuss if needed
  total_per_bullet: 300        # 5 min hard cap

  # Session limits
  total_session: 1800          # 30 min for ~100 bullets

  # Token limits (prevent verbose responses)
  vote_reasoning: 100          # 100 tokens max
  discussion_round: 150        # 150 tokens max
  final_argument: 200          # 200 tokens max
```

### **Escalating Pressure**
```python
class EscalatingPressure:
    """
    As deadline approaches, force faster decisions.

    Timeline (5 min per bullet):
    - 0-2 min: Normal voting, allow discussion
    - 2-4 min: Fast voting, limited discussion
    - 4-5 min: Binary decision only
    - 5 min: FORCED DECISION (reject if uncertain)
    """

    def get_current_mode(self, time_elapsed: float) -> str:
        if time_elapsed < 120:
            return "deliberative"
        elif time_elapsed < 240:
            return "expedited"
        elif time_elapsed < 300:
            return "binary"
        else:
            return "forced"
```

### **Conservative vs Aggressive Defaults**
```python
# Conservative (Production): Quality over quantity
class ConservativeMode:
    def timeout_decision(self) -> Decision:
        return Decision.REJECT  # When uncertain, reject

    def tie_breaker(self) -> Decision:
        return Decision.REJECT  # Ties go to reject

    def min_agreement(self) -> float:
        return 0.60  # Need 60% to approve

# Aggressive (Learning): Quantity now, filter later
class AggressiveMode:
    def timeout_decision(self) -> Decision:
        return Decision.APPROVE  # When uncertain, try it

    def tie_breaker(self) -> Decision:
        return Decision.APPROVE  # Ties go to approve

    def min_agreement(self) -> float:
        return 0.40  # Only need 40% to approve
```

---

## 📈 Expected Performance

### **Single Model Baseline**
```
Task: Password Validator
Model: qwen3:1.7b
Time: 5 minutes
Bullets: 20 proposed
Quality: ~60% useful
Cost: FREE
```

### **Ensemble (5 Models)**
```
Task: Password Validator
Models: qwen3, deepseek, codellama, mistral, phi-2
Time: 5 minutes (parallel!)
Bullets: 94 proposed
After voting: 40 approved
Quality: ~85% useful (consensus filtering!)
Cost: FREE (all local)

Breakdown:
- 25 bullets: Unanimous (5/5 models) → 95% quality
- 10 bullets: Strong agreement (4/5) → 85% quality
- 5 bullets: Majority (3/5) → 70% quality
- 54 bullets: Rejected (< 3/5 agreement)
```

### **ROI Analysis**
```
Single Model (100 tasks):
- Bullets learned: ~2000
- Quality: 60%
- Useful bullets: 1200
- Time: 500 minutes
- Cost: FREE

Ensemble (100 tasks):
- Bullets learned: ~4000 (after voting)
- Quality: 85%
- Useful bullets: 3400
- Time: 500 minutes (parallel!)
- Cost: FREE (all local)

Result: 3x more knowledge, 25% higher quality, same time!
```

---

## 🛠️ Implementation Roadmap

### **Phase 1: Basic Ensemble (Week 1)**
**Goal:** Multiple models propose, simple voting

**Tasks:**
- [ ] Parallel task execution across models
- [ ] Collect proposals from each model
- [ ] Implement simple majority voting
- [ ] Return consensus bullets

**Files:**
- `src/ensemble/learner.py` - EnsembleLearner class
- `src/ensemble/voting.py` - Basic voting logic
- `tests/test_ensemble.py` - Unit tests
- `scripts/ensemble_demo.py` - Demo script

**Deliverable:** Run task with 3-5 models, get consensus bullets

---

### **Phase 2: Cross-Voting (Week 2)**
**Goal:** Models vote on each other's proposals

**Tasks:**
- [ ] Implement cross-model voting
- [ ] Vote reasoning extraction
- [ ] Vote result aggregation
- [ ] Confidence scoring

**Files:**
- `src/ensemble/voting.py` - Enhanced with cross-voting
- `src/ensemble/consensus.py` - ConsensusBuilder
- `src/storage/schemas.py` - Vote, VoteResults classes

**Deliverable:** Vote matrix showing how models rated each bullet

---

### **Phase 3: Time-Boxed Deliberation (Week 3)**
**Goal:** Discussion with hard deadlines

**Tasks:**
- [ ] Time-boxed discussion rounds
- [ ] Escalating decision thresholds
- [ ] Forced decision mechanisms
- [ ] Token budget constraints

**Files:**
- `src/ensemble/deliberation.py` - DeliberativeCommittee
- `src/ensemble/constraints.py` - Time/token limits
- `config/ensemble_config.yaml` - Configuration

**Deliverable:** Committee that ALWAYS makes decisions, never hangs

---

### **Phase 4: Adaptive Weights (Week 4)**
**Goal:** Track which models vote correctly over time

**Tasks:**
- [ ] Voting performance tracking
- [ ] Automatic weight adjustment
- [ ] Model specialization detection
- [ ] Analytics dashboard

**Files:**
- `src/ensemble/analytics.py` - Performance tracking
- `src/ensemble/adaptive.py` - Adaptive weighting
- `dashboard/ensemble_stats.html` - Visualization

**Deliverable:** System learns which models to trust for what

---

## 🔬 Research Questions

### **Open Questions to Explore:**

1. **Optimal Committee Size**
   - How many models needed for good consensus?
   - 3 models? 5 models? 7 models?
   - Diminishing returns curve?

2. **Model Selection**
   - Which combinations work best?
   - Should models be diverse or similar?
   - Specialist vs generalist mix?

3. **Voting Calibration**
   - What's the right agreement threshold?
   - Does it vary by domain?
   - Should it adapt over time?

4. **Time Budgets**
   - Optimal time per bullet?
   - When to trigger discussion?
   - When to force decision?

5. **Quality Metrics**
   - How to measure consensus quality?
   - Real-world validation needed
   - A/B testing framework?

---

## 💡 Advanced Concepts

### **1. Disagreement Mining**
When models disagree, there's often a valuable insight:

```python
class DisagreementAnalyzer:
    """Analyze why models disagree."""

    def analyze(self, contested: VoteResults) -> Insight:
        """
        Disagreement types:

        1. Contextual: Both right in different contexts
           Example: "Use async" vs "Use sync"
           → Add conditional: "Use async for I/O, sync for CPU"

        2. Versioning: True for different versions
           Example: Valid for Python 3.9+, not 3.8
           → Add version context

        3. Expertise gap: One model knows better
           Example: Security model catches vulnerability
           → Trust specialist

        4. Ambiguity: Unclear requirement
           Example: "Best practice" undefined
           → Flag for human review
        """
        pass
```

### **2. Dynamic Model Selection**
Don't use all models for everything:

```python
class DynamicCommittee:
    """Select best models for each task/domain."""

    def select_models_for_task(
        self,
        task: TaskInput
    ) -> list[str]:
        """
        Choose models based on:
        - Domain (security → use deepseek)
        - Task type (creative → use qwen3)
        - Historical performance
        - Time budget
        """

        domain_specialists = {
            "security": ["deepseek-coder", "codellama"],
            "algorithms": ["qwen3", "mistral"],
            "api-design": ["phi-2", "deepseek-coder"],
        }

        return domain_specialists.get(
            task.domain,
            self.default_committee  # All models if unsure
        )
```

### **3. Hierarchical Voting**
Multiple rounds with increasing scrutiny:

```
Round 1: Quick Filter (all models, simple majority)
  ├─ Approve obvious good bullets (unanimous)
  ├─ Reject obvious bad bullets (unanimous against)
  └─ Send contested to Round 2

Round 2: Deliberative Review (contested only)
  ├─ Discussion phase
  ├─ Supermajority vote
  └─ Send still-contested to Round 3

Round 3: Expert Panel (most accurate models only)
  ├─ Top 2-3 models by track record
  ├─ Final decision
  └─ Human review if still contested
```

---

## 🚀 Quick Start

### **Minimal Example**
```python
# Configure ensemble
ensemble = EnsembleLearner(
    models=[
        "ollama:qwen3:1.7b",
        "ollama:deepseek-coder:6.7b",
        "ollama:codellama:7b",
    ]
)

# Learn from task
task = TaskInput(
    query="Build password validator",
    type="coding",
    domain="validation"
)

result = ensemble.learn_from_task(
    task=task,
    playbook_id="pb_validation"
)

# Review results
print(f"Proposed: {result.total_proposed}")
print(f"Approved: {result.total_approved}")
print(f"Quality: {result.avg_confidence:.2f}")

for bullet in result.consensus_bullets:
    print(f"\n{bullet.content}")
    print(f"  Agreement: {bullet.agreement_count}/3 models")
    print(f"  Confidence: {bullet.confidence:.2f}")
```

---

## 📚 References

### **Related Concepts**
- **Ensemble Methods:** Random Forests, Boosting (ML)
- **Collective Intelligence:** Wisdom of Crowds
- **Deliberative Democracy:** Structured group decision-making
- **Byzantine Fault Tolerance:** Consensus despite failures

### **Academic Foundations**
- Mixture of Experts (MoE) architectures
- Multi-agent reinforcement learning
- Voting theory & social choice
- Quality filtering through consensus

---

## ⚠️ Risks & Mitigation

### **Risk 1: Groupthink**
**Risk:** All models make same mistake
**Mitigation:**
- Use diverse model architectures
- Include at least one specialist model
- Track disagreement rates (too high or too low = bad)

### **Risk 2: Slow Performance**
**Risk:** Multiple models = 5x slower
**Mitigation:**
- Parallel execution (all models at once)
- GPU optimization
- Cache model loads
- Time budgets force fast decisions

### **Risk 3: Resource Usage**
**Risk:** 5 models = 5x RAM/CPU
**Mitigation:**
- Sequential execution if RAM limited
- Use smaller models (1-7B parameters)
- Quantized models (4-bit)
- Model unloading between tasks

### **Risk 4: Voting Manipulation**
**Risk:** One model dominates voting
**Mitigation:**
- Track voting patterns
- Detect collusion (models always agree)
- Weight by historical accuracy
- Require diversity in approved bullets

---

## 🎯 Success Metrics

### **Quality Metrics**
- [ ] Consensus bullets have 85%+ real-world helpfulness
- [ ] Unanimous bullets have 95%+ helpfulness
- [ ] 3x more useful bullets than single-model
- [ ] Reduced harmful bullet rate by 50%+

### **Efficiency Metrics**
- [ ] Decisions made within time budget (100%)
- [ ] No infinite deliberation loops
- [ ] Process 100 bullets in < 30 minutes
- [ ] 5 models run in < 2x single model time (parallel)

### **Learning Metrics**
- [ ] Playbook grows 3-5x faster
- [ ] Quality improves over time (adaptive weights)
- [ ] Models learn specializations
- [ ] Team consensus matches ensemble consensus

---

## 🔮 Future Enhancements

1. **Human-in-the-Loop**
   - Escalate highly contested bullets to human
   - Learn from human decisions
   - Hybrid human-AI committees

2. **Cross-Task Learning**
   - Models that vote well together in past
   - Committee composition optimization
   - Dynamic model selection

3. **Real-Time Adaptation**
   - Adjust voting weights during session
   - Detect and correct biases live
   - A/B test different strategies

4. **Explainable Decisions**
   - Visualize vote matrix
   - Show discussion synthesis
   - Trace why bullet approved/rejected

---

**Status:** Documented, ready for future implementation
**Estimated Value:** 3-5x learning speed, 25% quality improvement
**Technical Feasibility:** High (builds on existing ACE infrastructure)
**Innovation Level:** High (novel application of ensemble methods to code learning)

---

_This document captures the vision for ACE Ensemble Learning System. Implementation should be phased based on available resources and validated through experiments._
