# MLflow + ACE Quick Start Guide

**Goal:** Capture ML experiment knowledge in 3 lines of code

---

## Installation

```bash
pip install mlflow scikit-learn numpy
```

---

## Basic Usage (3 Steps)

### 1. Import and Create Callback

```python
from src.ml import ACEMLflowCallback
import mlflow

ace = ACEMLflowCallback(
    experiment_name="my_experiment",
    human_contributor="your.email@company.com"
)
```

### 2. Log Decisions During Training

```python
with mlflow.start_run():
    # Log a decision
    ace.log_decision(
        question="Which optimizer?",
        decision="Adam with lr=0.001",
        rationale="SGD was unstable",
        alternatives=["SGD", "AdamW"]
    )

    # Your normal training code
    model.fit(X, y)

    # MLflow metrics
    mlflow.log_metric("accuracy", 0.95)
```

### 3. Query Later

```python
from src.ml import MLflowKnowledgeQuery

query = MLflowKnowledgeQuery("my_experiment")

# See all decisions
for d in query.get_decision_history():
    print(f"{d.question} → {d.decision}")
    print(f"  Why: {d.rationale}")
```

---

## Common Queries

### "What did we try for learning rates?"

```python
decisions = query.get_decision_history(
    question_keyword="learning rate"
)
```

### "Which runs were successful?"

```python
runs = query.find_runs_by_decision(
    outcome="successful"
)
```

### "What should I try for batch_size=128?"

```python
recs = query.get_recommendations_for_params(
    params={"batch_size": 128}
)

for pattern, reason in recs:
    print(f"{pattern.pattern_name}")
    print(f"  {pattern.implementation}")
```

### "Compare my best and worst run"

```python
runs = query.get_enriched_runs()
best = max(runs, key=lambda r: r.metrics.get("accuracy", 0))
worst = min(runs, key=lambda r: r.metrics.get("accuracy", 0))

comparison = query.compare_runs(best.run_id, worst.run_id)
print(comparison["decision_differences"])
```

---

## Advanced: Log Patterns

After multiple experiments, extract patterns:

```python
ace.log_pattern(
    pattern_name="Learning rate warmup for large batches",
    description="Gradual LR increase prevents instability",
    when_to_apply="When batch_size > 256",
    implementation="lr_scheduler.LinearLR(start_factor=0.1)",
    observed_in_runs=["run_1", "run_2", "run_3"],
    success_rate=0.85,
    domain_tags=["computer_vision"]
)
```

---

## Advanced: Update Decision Outcomes

```python
# After experiment completes
ace.update_decision_outcome(
    decision_id="dec_xyz_123",
    outcome="successful",  # or "failed" or "inconclusive"
    learned_insight="Adam improved accuracy by 3%"
)
```

---

## Where is Knowledge Stored?

- **ACE Knowledge:** `~/.ace/ml_experiments/{experiment_name}.json`
- **MLflow Runs:** `~/.ace/mlruns/` (or your tracking URI)

---

## Run the Demo

```bash
python demo_mlflow_ace.py
```

Shows:
- 3 experiments with decision capture
- Pattern extraction
- All query examples

---

## Full Documentation

- **Complete Guide:** [docs/mlflow_integration.md](mlflow_integration.md)
- **Summary:** [docs/mlflow_integration_summary.md](mlflow_integration_summary.md)
- **Demo Code:** [demo_mlflow_ace.py](../demo_mlflow_ace.py)

---

## Cheat Sheet

| Task | Code |
|------|------|
| **Create callback** | `ace = ACEMLflowCallback("exp_name")` |
| **Log decision** | `ace.log_decision(question, decision, rationale, alternatives)` |
| **Update outcome** | `ace.update_decision_outcome(decision_id, outcome, insight)` |
| **Log pattern** | `ace.log_pattern(name, desc, when, impl, runs, success_rate)` |
| **Query decisions** | `query.get_decision_history()` |
| **Find by outcome** | `query.find_runs_by_decision(outcome="successful")` |
| **Get recommendations** | `query.get_recommendations_for_params(params)` |
| **Compare runs** | `query.compare_runs(run_id_1, run_id_2)` |

---

## Example Decision Schema

```json
{
  "decision_id": "dec_...",
  "timestamp": "2025-11-30T14:30:22Z",
  "question": "Which optimizer?",
  "decision": "Adam with lr=0.001",
  "rationale": "SGD was unstable",
  "alternatives_considered": ["SGD", "AdamW"],
  "context": {"mlflow_run_id": "..."},
  "outcome": "successful",
  "learned_insight": "Adam converged faster"
}
```

---

## Tips

1. **Log decisions as you make them** - Don't wait until the end
2. **Include rationale** - Future you will thank you
3. **List alternatives** - Shows what was considered
4. **Update outcomes** - Close the learning loop
5. **Extract patterns** - After 3+ similar experiments
6. **Query regularly** - Use the knowledge you capture

---

**Questions?** See full documentation at [docs/mlflow_integration.md](mlflow_integration.md)