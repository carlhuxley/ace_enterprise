# MLflow + ACE Integration

**Status:** Prototype Complete
**Created:** 2025-11-30
**Purpose:** Extend ACE's institutional knowledge capture to ML experimentation

---

## Overview

This integration extends ACE Enterprise from software development to ML experimentation by bridging MLflow's execution tracking with ACE's decision knowledge capture.

### The Gap This Fills

**MLflow tracks:**
- Parameters (learning_rate, batch_size, etc.)
- Metrics (accuracy, loss, etc.)
- Artifacts (models, plots)
- Code versions

**MLflow doesn't track:**
- WHY you chose those parameters
- WHAT alternatives you considered
- WHAT you learned when experiments failed
- PATTERNS that work across multiple experiments

**ACE fills the gap by capturing:**
- Decision rationale ("tried Adam because SGD was unstable in pilot runs")
- Rejected alternatives ("considered AdamW but license concerns")
- Learned insights ("increasing batch size > 256 requires warmup")
- Cross-experiment patterns ("HIPAA datasets benefit from differential privacy")

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Your ML Training Code                     │
└──────────────────────────────────────────────────────────────┘
                              │
                              ├─────────────────────┐
                              ▼                     ▼
                    ┌──────────────────┐  ┌──────────────────┐
                    │   MLflow         │  │  ACE Knowledge   │
                    │                  │  │                  │
                    │  • Parameters    │  │  • Decisions     │
                    │  • Metrics       │  │  • Rationale     │
                    │  • Artifacts     │  │  • Alternatives  │
                    │  • Code versions │  │  • Patterns      │
                    │  • Run metadata  │  │  • Insights      │
                    └──────────────────┘  └──────────────────┘
                              │                     │
                              └─────────┬───────────┘
                                        ▼
                          ┌──────────────────────────┐
                          │ Unified Query Interface  │
                          │                          │
                          │ "Show me runs where we   │
                          │  decided to use Adam     │
                          │  and what we learned"    │
                          └──────────────────────────┘
```

---

## Components

### 1. `MLExperimentKnowledge` - Knowledge Schema

Structured storage for ML experiment decisions and patterns.

**Key classes:**
- `ExperimentDecision`: Single decision with question, answer, rationale, alternatives
- `ExperimentPattern`: Cross-experiment pattern with success rate and application guidance
- `MLExperimentKnowledge`: Container for all decisions and patterns

**Example decision:**
```python
{
  "decision_id": "dec_image_clf_20251130_143022_1",
  "timestamp": "2025-11-30T14:30:22Z",
  "question": "Which optimizer to use?",
  "decision": "Adam with lr=0.001",
  "rationale": "SGD showed instability in pilot runs",
  "alternatives_considered": ["SGD", "AdamW", "RMSprop"],
  "context": {
    "mlflow_run_id": "abc123",
    "previous_run_loss": 0.45
  },
  "human_contributor": "data_scientist@company.com",
  "ai_models": [
    {"provider": "anthropic", "model": "claude-sonnet-3.5"}
  ],
  "outcome": "successful",
  "learned_insight": "Adam converged 2x faster than SGD"
}
```

**Example pattern:**
```python
{
  "pattern_id": "pat_image_clf_20251130_143500",
  "pattern_name": "Learning rate warmup for large batches",
  "description": "Gradually increase learning rate for first epoch when batch_size > 256",
  "when_to_apply": "When batch_size > 256 and using Adam/AdamW",
  "implementation": "Use lr_scheduler.LinearLR(start_factor=0.1, total_iters=1000)",
  "observed_in_experiments": ["run_123", "run_456", "run_789"],
  "success_rate": 0.85,
  "avg_improvement": 0.03,
  "antipatterns": [
    "Don't combine with learning rate decay in first epoch"
  ],
  "domain_tags": ["computer_vision", "large_batch_training"]
}
```

### 2. `ACEMLflowCallback` - Automatic Capture

Captures knowledge during training with minimal code changes.

**Usage:**
```python
from src.ml import ACEMLflowCallback
import mlflow

ace = ACEMLflowCallback(
    experiment_name="my_experiment",
    human_contributor="data_scientist@company.com"
)

with mlflow.start_run():
    # Log decision
    ace.log_decision(
        question="Which optimizer to use?",
        decision="Adam with lr=0.001",
        rationale="Better convergence in pilot runs",
        alternatives=["SGD", "AdamW"]
    )

    # Your training code
    model.fit(X_train, y_train)

    # MLflow logs metrics as usual
    mlflow.log_metric("accuracy", 0.95)

    # Update decision outcome after seeing results
    ace.update_decision_outcome(
        decision_id="dec_xyz",
        outcome="successful",
        learned_insight="Adam improved accuracy by 3%"
    )
```

**Features:**
- Automatic storage to `~/.ace/ml_experiments/{experiment_name}.json`
- Links decisions to MLflow run IDs
- Logs decision metadata to MLflow tags for discoverability
- Context manager for auto-save on exit

### 3. `MLflowKnowledgeQuery` - Unified Querying

Query both MLflow runs and ACE knowledge together.

**Usage:**
```python
from src.ml import MLflowKnowledgeQuery

query = MLflowKnowledgeQuery(
    experiment_name="my_experiment",
    knowledge_dir=Path("~/.ace/ml_experiments")
)

# Get runs with knowledge context
enriched_runs = query.get_enriched_runs()
for run in enriched_runs:
    print(f"Run {run.run_id}: {run.decision_count} decisions")
    print(f"  Failed decisions: {run.has_failed_decisions}")
    print(f"  Applied patterns: {run.applied_patterns}")

# Find runs by decision
runs = query.find_runs_by_decision(
    question="optimizer",
    outcome="successful"
)

# Get decision history
decisions = query.get_decision_history(
    question_keyword="learning rate"
)

# Compare two runs (params + metrics + decisions)
comparison = query.compare_runs(run_id_1, run_id_2)
print(comparison["decision_differences"])

# Get recommendations for new run
recommendations = query.get_recommendations_for_params(
    params={"batch_size": 128, "optimizer": "adam"},
    domain_tags=["computer_vision"]
)
```

**Query capabilities:**
- `get_enriched_runs()`: All runs with knowledge context
- `find_runs_by_decision()`: Filter by decision question/answer/outcome
- `find_runs_by_pattern()`: Runs where pattern was observed
- `get_recommendations_for_params()`: Patterns relevant to current params
- `get_decision_history()`: Chronological decision trail
- `compare_runs()`: Side-by-side comparison including decisions

---

## Demo Walkthrough

Run the complete demo:
```bash
# Install dependencies
pip install mlflow scikit-learn numpy

# Run demo
python demo_mlflow_ace.py
```

**Demo flow:**

1. **Experiment 1 - Baseline**
   - Decision: "Use default hyperparameters for baseline"
   - Rationale: "Establish baseline before optimization"
   - Result: 0.85 accuracy
   - Outcome: Successful

2. **Experiment 2 - Limit Tree Depth**
   - Decision: "Set max_depth=20"
   - Rationale: "Unlimited depth may be overfitting"
   - Result: 0.87 accuracy (+0.02)
   - Outcome: Successful
   - Learned: "Limiting depth improved generalization"

3. **Experiment 3 - More Trees**
   - Decision: "Increase n_estimators to 200"
   - Rationale: "Test if worth compute cost"
   - Result: 0.88 accuracy (+0.01)
   - Outcome: Inconclusive
   - Learned: "Marginal improvement, may not justify 2x cost"

4. **Pattern Extraction**
   - Pattern: "Limited tree depth improves Random Forest generalization"
   - Evidence: 2/3 runs showed improvement
   - Success rate: 67%

5. **Knowledge Queries**
   - View all runs with decision context
   - Find runs by decision question
   - Compare baseline vs best run
   - Get recommendations for future experiments

---

## Integration Scenarios

### Scenario 1: Starting New Experiment

**Before ACE:**
```python
# Hmm, what learning rate should I use?
# Let me check Slack history... can't find it
# Let me ask Sarah... she's on vacation
# Let me try 0.001 and hope for the best
```

**With ACE:**
```python
query = MLflowKnowledgeQuery("my_experiment")

# Get recommendations
recs = query.get_recommendations_for_params(
    params={"optimizer": "adam", "batch_size": 128},
    domain_tags=["computer_vision"]
)

for pattern, reason in recs:
    print(f"{pattern.pattern_name}")
    print(f"  Success rate: {pattern.success_rate:.2f}")
    print(f"  Implementation: {pattern.implementation}")
    # → "Learning rate warmup for large batches"
    # → Success rate: 0.85
    # → Implementation: "Use lr_scheduler.LinearLR(...)"
```

### Scenario 2: Experiment Failed - Capture Learning

**Before ACE:**
```python
# Experiment failed. Let me write a note...
# Where should I write it? Slack? Google Doc? Notebook comment?
# Probably forget it in 2 weeks anyway
```

**With ACE:**
```python
ace.update_decision_outcome(
    decision_id="dec_xyz",
    outcome="failed",
    learned_insight="AdamW with this dataset causes loss spikes. "
                    "Stick with Adam or reduce learning rate by 10x"
)
# Automatically saved and queryable later
```

### Scenario 3: Onboarding New Team Member

**Before ACE:**
```
New person: "Why did we choose these hyperparameters?"
You: "Uh... Sarah tried a bunch of things last quarter. Check run 47 maybe?"
New person: "Run 47 has params but no explanation..."
You: "Yeah, we should document better..."
```

**With ACE:**
```python
# New team member queries the knowledge base
decisions = query.get_decision_history()

for decision in decisions:
    print(f"Q: {decision.question}")
    print(f"A: {decision.decision}")
    print(f"Why: {decision.rationale}")
    print(f"Alternatives considered: {decision.alternatives_considered}")
    print(f"Outcome: {decision.outcome}")
    print(f"Learned: {decision.learned_insight}")
    print()

# Complete context for every decision ever made
```

### Scenario 4: Cross-Project Learning

**Before ACE:**
```
You: "We're starting a new healthcare CV project"
You: "Wonder if any patterns from our fintech CV project apply..."
You: "Let me dig through old notebooks... can't find them"
```

**With ACE:**
```python
# Central knowledge base: ~/.ace/ml_experiments/

query_healthcare = MLflowKnowledgeQuery("healthcare_imaging")
query_fintech = MLflowKnowledgeQuery("fintech_fraud_detection")

# Get patterns from fintech project
fintech_patterns = query_fintech.knowledge.get_successful_patterns()

# Filter for CV patterns
cv_patterns = [
    p for p in fintech_patterns
    if "computer_vision" in p.domain_tags
]

# Apply to healthcare project
for pattern in cv_patterns:
    print(f"Pattern from fintech that might help:")
    print(f"  {pattern.pattern_name}")
    print(f"  {pattern.when_to_apply}")
    # Apply pattern to new healthcare project
```

---

## Storage Structure

```
~/.ace/
  ml_experiments/
    image_classification_demo.json    ← ACE knowledge
    nlp_sentiment_analysis.json
    healthcare_imaging.json
  mlruns/                             ← MLflow tracking
    0/
      abc123/                          ← Run ID
        params/
        metrics/
        artifacts/
```

**Separation of concerns:**
- MLflow: Execution data (what happened)
- ACE: Knowledge data (why it happened)
- Linked by run IDs

---

## Benefits

### For Individual Researchers

1. **Never forget why:** "Why did I choose these hyperparameters 3 months ago?"
2. **Learn from failures:** Failed experiments are learning opportunities
3. **Build on past work:** Don't repeat same experiments unknowingly

### For Teams

1. **Shared knowledge:** Everyone learns from everyone's experiments
2. **Faster onboarding:** New members understand past decisions
3. **Consistency:** Apply proven patterns across projects
4. **Avoid rework:** Don't repeat failed approaches

### For Organizations

1. **Institutional memory:** Knowledge doesn't leave when people do
2. **Cross-project patterns:** Learn from all ML projects
3. **Compliance:** Full audit trail of decisions
4. **ROI visibility:** Track which decisions led to improvements

---

## Future Enhancements

### Phase 1 Improvements (Next)

1. **Auto-pattern extraction**
   - Analyze successful runs to automatically identify patterns
   - Cluster similar decisions across experiments
   - Suggest pattern generalizations

2. **Semantic search**
   - Vector embeddings for decisions and patterns
   - "Show me experiments similar to this one"
   - "What did we learn about overfitting?"

3. **Integration with notebook**
   - Jupyter extension for inline decision capture
   - "Log this decision to ACE" button
   - Render recommendations in notebook

### Phase 2 - Advanced Features

1. **Multi-project intelligence**
   - Domain-specific pattern libraries (CV, NLP, etc.)
   - Cross-organization learning (opt-in)
   - Pattern marketplace

2. **Active guidance**
   - "Your batch_size is high, consider warmup pattern"
   - "Similar runs with this config failed, see why..."
   - Real-time recommendations during training

3. **Visualization**
   - Decision tree explorer
   - Pattern effectiveness over time
   - What-if analysis (counterfactuals)

---

## Comparison to Alternatives

### vs. Experiment Tracking Only (MLflow/Weights & Biases)

| Feature | MLflow Alone | MLflow + ACE |
|---------|-------------|--------------|
| Track parameters | ✅ | ✅ |
| Track metrics | ✅ | ✅ |
| Track artifacts | ✅ | ✅ |
| **WHY decisions were made** | ❌ | ✅ |
| **Alternatives considered** | ❌ | ✅ |
| **Learned insights** | ❌ | ✅ |
| **Cross-experiment patterns** | ❌ | ✅ |
| **Query by rationale** | ❌ | ✅ |

### vs. Notebooks/Documentation

| Feature | Notebooks | ACE |
|---------|-----------|-----|
| Write notes | ✅ | ✅ |
| Link to runs | Manual | Automatic |
| Search by decision | ❌ | ✅ |
| Track outcomes | Manual | Automatic |
| Cross-project learning | ❌ | ✅ |
| Structured queries | ❌ | ✅ |
| Gets outdated | ✅ Often | ❌ Auto-tracked |

---

## Example Knowledge Queries

```python
from src.ml import MLflowKnowledgeQuery

query = MLflowKnowledgeQuery("my_experiment")

# 1. "What have we learned about learning rates?"
decisions = query.get_decision_history(question_keyword="learning rate")
for d in decisions:
    if d.outcome == "failed":
        print(f"Don't: {d.decision} → {d.learned_insight}")

# 2. "Which patterns work best for computer vision?"
patterns = query.knowledge.get_patterns_by_domain("computer_vision")
patterns.sort(key=lambda p: p.success_rate, reverse=True)

# 3. "Show me successful runs with Adam optimizer"
runs = query.find_runs_by_decision(
    decision="Adam",
    outcome="successful"
)

# 4. "What's different between my best and worst run?"
runs = query.get_enriched_runs()
best = max(runs, key=lambda r: r.metrics.get("accuracy", 0))
worst = min(runs, key=lambda r: r.metrics.get("accuracy", 0))
comparison = query.compare_runs(best.run_id, worst.run_id)

# 5. "What should I try for a new run with batch_size=256?"
recs = query.get_recommendations_for_params({"batch_size": 256})
```

---

## Getting Started

### Installation

```bash
# Required
pip install mlflow

# For demo
pip install scikit-learn numpy
```

### Quick Start

```python
from src.ml import ACEMLflowCallback
import mlflow

# 1. Create callback
ace = ACEMLflowCallback(
    experiment_name="my_first_experiment",
    human_contributor="your_email@company.com"
)

# 2. Start MLflow run
with mlflow.start_run():
    # 3. Log decisions as you make them
    ace.log_decision(
        question="What should I try first?",
        decision="Baseline with defaults",
        rationale="Need to establish baseline",
        alternatives=["Skip baseline and optimize immediately"]
    )

    # 4. Your normal training code
    # ... model.fit(X, y) ...

    # 5. Log to MLflow
    mlflow.log_param("learning_rate", 0.001)
    mlflow.log_metric("accuracy", 0.95)

# Knowledge automatically saved!
```

### Query Later

```python
from src.ml import MLflowKnowledgeQuery

query = MLflowKnowledgeQuery("my_first_experiment")

# See all your decisions
for decision in query.get_decision_history():
    print(f"{decision.question} → {decision.decision}")
```

---

## Documentation Links

- [ACE Strategic Plan](./ACE_STRATEGIC_PLAN.md)
- [MLflow Documentation](https://mlflow.org/docs/latest/index.html)
- [Demo Source Code](../demo_mlflow_ace.py)

---

**Last Updated:** 2025-11-30
**Status:** Prototype complete, ready for pilot projects
**Feedback:** Submit issues or suggestions to ACE team