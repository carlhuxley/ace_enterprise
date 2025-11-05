# Ensemble ACE Evaluation Framework

**Purpose**: Empirically prove that ensemble learning + deliberation outperforms single-model ACE

**Date**: 2025-10-28
**Status**: Design Phase

---

## Hypothesis

**Ensemble ACE will outperform single-model ACE by:**
1. Producing higher-quality bullets (better task performance)
2. Achieving target accuracy faster (fewer training examples needed)
3. Being more robust (handling edge cases better)
4. Providing better diversity (covering more failure modes)

---

## Evaluation Metrics

### Primary Metrics

**1. Task Success Rate**
- % of tasks solved correctly
- Measured on held-out test set
- **Target**: Ensemble ≥ 5% higher than single-model

**2. Bullet Quality Score**
- Helpful ratio: `helpful / (helpful + harmful)`
- Averaged across all bullets
- **Target**: Ensemble ≥ 0.10 higher ratio

**3. Learning Efficiency**
- Number of training examples to reach 70% accuracy
- **Target**: Ensemble reaches target 20% faster

**4. Diversity Score**
- Unique failure modes covered by bullets
- **Target**: Ensemble covers 30% more failure modes

### Secondary Metrics

**5. Bullet Rejection Rate**
- % of proposed bullets rejected by voting
- Indicates quality filtering effectiveness

**6. Deliberation Impact**
- Vote changes during deliberation
- % of contested bullets that change outcome

**7. Cost Efficiency**
- Accuracy improvement per dollar spent
- `(accuracy_gain / token_cost)`

**8. Convergence Stability**
- Variance in performance across runs
- Lower variance = more stable

---

## Experimental Design

### Baseline: Single-Model ACE

**Setup:**
```python
# Traditional ACE with one model
single_learner = ACELearner(
    model="ollama/qwen2.5-coder:1.5b",
    playbook_id="baseline_pb"
)
```

**Process:**
1. Generator proposes bullets from task failures
2. Reflector analyzes and creates bullets
3. Curator adds bullets to playbook
4. No voting, no deliberation

### Treatment 1: Ensemble Without Deliberation

**Setup:**
```python
# Ensemble voting but no deliberation
ensemble_no_delib = EnsembleLearner(
    models=[
        ("ollama", "qwen2.5-coder:1.5b"),
        ("ollama", "qwen2.5-coder:0.5b"),
        ("ollama", "deepseek-coder:1.3b"),
    ],
    voting_strategy=MajorityVoting(),
    enable_deliberation=False,  # Disable deliberation
    playbook_id="ensemble_no_delib_pb"
)
```

**Process:**
1. Each model proposes bullets
2. Cross-voting on all proposals
3. Majority vote determines approval
4. No discussion/deliberation

### Treatment 2: Ensemble With Deliberation

**Setup:**
```python
# Full ensemble with deliberation
ensemble_with_delib = EnsembleLearner(
    models=[
        ("ollama", "qwen2.5-coder:1.5b"),
        ("ollama", "qwen2.5-coder:0.5b"),
        ("ollama", "deepseek-coder:1.3b"),
    ],
    voting_strategy=MajorityVoting(),
    enable_deliberation=True,  # Enable deliberation
    deliberation_threshold_low=0.4,
    deliberation_threshold_high=0.6,
    max_deliberation_rounds=2,
    playbook_id="ensemble_with_delib_pb"
)
```

**Process:**
1. Each model proposes bullets
2. Cross-voting on all proposals
3. Contested bullets (40-60%) trigger deliberation
4. Models see reasoning, can revise votes
5. Final majority vote

---

## Benchmark Tasks

### Dataset: Custom ACE Benchmark

**Requirements:**
- Diverse task types (coding, debugging, analysis)
- Known ground truth
- Varying difficulty levels
- Representative of real-world usage

**Proposed Tasks (50 total):**

**Category 1: Code Generation (15 tasks)**
- Simple functions (validate email, parse date)
- Complex algorithms (binary search, graph traversal)
- API integration (REST calls, auth)

**Category 2: Debugging (15 tasks)**
- Off-by-one errors
- Type mismatches
- Logic errors
- Edge case failures

**Category 3: Code Analysis (10 tasks)**
- Security vulnerability detection
- Performance optimization opportunities
- Code smell identification

**Category 4: Refactoring (10 tasks)**
- Extract method
- Simplify conditionals
- Remove duplication

**Difficulty Distribution:**
- Easy: 20 tasks (baseline accuracy ~80%)
- Medium: 20 tasks (baseline accuracy ~50%)
- Hard: 10 tasks (baseline accuracy ~20%)

---

## Evaluation Protocol

### Phase 1: Training (Offline Learning)

**For each condition (Baseline, Treatment 1, Treatment 2):**

1. **Initialize**: Empty playbook
2. **Training Split**: Use 40 tasks (80% of dataset)
3. **Process**:
   - Run each task
   - Collect failure feedback
   - Generate/vote on bullets
   - Update playbook
   - Track metrics per epoch

4. **Epochs**: Run 3 epochs over training set
5. **Checkpoints**: Save playbook after each epoch

**Tracked Metrics Per Epoch:**
- Task success rate
- Playbook size (bullet count, token count)
- Bullet quality metrics
- Training time
- Token usage

### Phase 2: Evaluation (Held-Out Test)

**For each condition:**

1. **Test Split**: Use 10 tasks (20% of dataset)
2. **Process**:
   - Load final playbook from training
   - Run test tasks (no learning)
   - Measure success rate
   - Analyze which bullets were used

3. **Metrics**:
   - Test accuracy
   - Bullet utilization rate
   - Error type coverage

### Phase 3: Statistical Analysis

**Comparisons:**

1. **Baseline vs Ensemble (No Delib)**
   - Does voting improve quality?
   - Is peer review valuable?

2. **Ensemble (No Delib) vs Ensemble (With Delib)**
   - Does deliberation add value?
   - When does it help most?

3. **Cost-Benefit Analysis**
   - Accuracy per dollar
   - Time to target accuracy
   - ROI calculation

**Statistical Tests:**
- Paired t-test for accuracy differences
- Cohen's d for effect size
- Bootstrap confidence intervals
- Multiple hypothesis correction (Bonferroni)

**Significance Level**: p < 0.05

---

## Implementation Plan

### Step 1: Build Benchmark Dataset

**Tasks:**
- [ ] Define 50 benchmark tasks with ground truth
- [ ] Organize by category and difficulty
- [ ] Create test harness for automated evaluation
- [ ] Validate tasks with manual review

**Deliverable**: `benchmark/ace_benchmark_v1.json`

### Step 2: Implement Evaluation Harness

**Tasks:**
- [ ] Create `EvaluationRunner` class
- [ ] Support all 3 conditions (baseline, ensemble-no-delib, ensemble-with-delib)
- [ ] Automated metrics collection
- [ ] Progress tracking and checkpointing
- [ ] Result export (JSON, CSV)

**Deliverable**: `src/evaluation/runner.py`

### Step 3: Run Experiments

**Tasks:**
- [ ] Run Baseline (single-model ACE)
- [ ] Run Treatment 1 (ensemble without deliberation)
- [ ] Run Treatment 2 (ensemble with deliberation)
- [ ] Collect all metrics
- [ ] Store raw results

**Deliverable**: `results/experiment_2025_10_28/`

### Step 4: Analyze Results

**Tasks:**
- [ ] Statistical significance tests
- [ ] Effect size calculations
- [ ] Generate comparison charts
- [ ] Write findings report

**Deliverable**: `docs/ENSEMBLE_RESULTS.md`

### Step 5: Publish Findings

**Tasks:**
- [ ] Create visualizations
- [ ] Write blog post
- [ ] Share results with community
- [ ] Update PRD with validated metrics

**Deliverable**: Public results report

---

## Expected Results

### Hypothesis 1: Ensemble Improves Quality

**Expected:**
- Ensemble produces higher helpful ratio (0.75 vs 0.65)
- Ensemble has lower harmful bullet rate (5% vs 15%)
- Statistical significance: p < 0.01

**Why:**
- Peer review catches bad bullets
- Multiple perspectives identify edge cases
- Voting filters out model-specific biases

### Hypothesis 2: Deliberation Adds Value

**Expected:**
- Deliberation improves contested bullets by 10%
- Vote changes in 30% of deliberations
- Final accuracy 3-5% higher than voting alone

**Why:**
- Models learn from peers' reasoning
- Argumentation reveals flaws
- Consensus is more robust than simple voting

### Hypothesis 3: Faster Convergence

**Expected:**
- Ensemble reaches 70% accuracy in 25 examples vs 35 for baseline
- 30% reduction in training examples needed

**Why:**
- Higher quality bullets from start
- Less noise in playbook
- Fewer harmful bullets to unlearn

### Hypothesis 4: Cost Effective

**Expected:**
- 3x token cost but 40% accuracy improvement
- ROI: 0.13 accuracy per dollar (vs 0.10 for baseline)

**Why:**
- Better bullets justify higher cost
- Fewer iterations needed overall
- Quality > quantity

---

## Risk Mitigation

### Risk 1: No Significant Difference

**If ensemble doesn't outperform baseline:**

**Possible Causes:**
- Benchmark too easy (ceiling effect)
- Models too similar (low diversity)
- Voting strategy suboptimal

**Mitigation:**
- Use harder benchmark tasks
- Include more diverse models (different architectures)
- Try supermajority or weighted voting

### Risk 2: Cost Prohibitive

**If improvement doesn't justify cost:**

**Mitigation:**
- Use ensemble only for critical tasks
- Hybrid: single-model for easy, ensemble for hard
- Optimize with faster models (0.5b instead of 1.5b)

### Risk 3: Deliberation Doesn't Help

**If deliberation adds cost but no accuracy:**

**Mitigation:**
- Disable deliberation by default
- Use only for highly contested bullets (45-55%)
- Reduce max rounds to 1

---

## Success Criteria

### Minimum Viable Success

- ✅ Ensemble ≥ 3% more accurate than baseline (statistically significant)
- ✅ Ensemble bullet quality ≥ 0.10 higher helpful ratio
- ✅ Results reproducible across 3 independent runs

### Target Success

- ✅ Ensemble ≥ 5% more accurate than baseline
- ✅ Deliberation adds ≥ 2% over voting alone
- ✅ 20% faster convergence (fewer examples to target accuracy)
- ✅ Cost per accuracy point ≥ 10% better

### Stretch Success

- ✅ Ensemble ≥ 10% more accurate
- ✅ Deliberation changes outcome in 40% of contested cases
- ✅ 30% faster convergence
- ✅ Publishable findings (blog post or paper)

---

## Timeline

**Week 1: Preparation**
- Define benchmark tasks
- Build evaluation harness
- Validate infrastructure

**Week 2: Experiments**
- Run baseline
- Run ensemble (no deliberation)
- Run ensemble (with deliberation)

**Week 3: Analysis**
- Statistical tests
- Generate visualizations
- Write findings report

**Week 4: Publication**
- Create blog post
- Share results
- Update documentation

**Total: 4 weeks**

---

## Tools and Infrastructure

### Required Tools

1. **Evaluation Harness**: `src/evaluation/runner.py`
2. **Metrics Tracker**: `src/evaluation/metrics.py`
3. **Statistical Analysis**: `scripts/analyze_results.py`
4. **Visualization**: `scripts/plot_results.py`

### Data Storage

```
results/
├── experiment_2025_10_28/
│   ├── baseline/
│   │   ├── epoch_1_metrics.json
│   │   ├── epoch_2_metrics.json
│   │   ├── epoch_3_metrics.json
│   │   └── final_playbook.json
│   ├── ensemble_no_delib/
│   │   └── ...
│   ├── ensemble_with_delib/
│   │   └── ...
│   └── comparison.json
└── visualizations/
    ├── accuracy_comparison.png
    ├── learning_curves.png
    └── cost_benefit.png
```

---

## Next Steps

1. **Immediate**: Create benchmark dataset
2. **This Week**: Build evaluation harness
3. **Next Week**: Run first experiment (baseline)
4. **Following Week**: Run ensemble experiments
5. **Month End**: Publish results

**Owner**: Engineering Team
**Reviewers**: Product, Research
**Deadline**: 2025-11-28 (4 weeks)

---

## References

- Stanford/SambaNova ACE Paper: arXiv:2510.04618v1
- AppWorld Benchmark: https://appworld.dev
- Ensemble Methods in ML: Zhou (2012)
- Deliberative AI: Irving et al. (2018)
