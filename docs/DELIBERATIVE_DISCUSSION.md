# Deliberative Discussion System

**Status**: ✅ COMPLETE
**Date**: 2025-10-28
**Priority**: Critical (Phase 2 #2 improvement)

---

## Overview

Implemented deliberative discussion for contested bullets in the ensemble learning system. When votes are close (e.g., 40-60% approval), models engage in discussion by seeing each other's reasoning and reconsidering their votes.

This was identified as the **#2 critical improvement** for Phase 2 of ensemble learning (after LLM-based voting).

## What Changed

### Before (Simple Voting)
```python
# After cross-voting, immediately apply strategy
approved, rejected = voting_strategy.vote_on_bullets(bullets)
```

**Problems:**
- Close votes (50/50 split) were decided arbitrarily
- Models never saw each other's reasoning
- No opportunity to revise votes based on peers' arguments
- Borderline bullets might be misjudged

### After (Deliberative Discussion)
```python
# After cross-voting, check for contested bullets
if enable_deliberation:
    contested = [b for b in bullets if 0.4 <= b.approval_rate <= 0.6]
    for bullet in contested:
        for round in range(max_rounds):
            # Show each model all other votes + reasoning
            # Models can revise their vote
            # Stop if consensus reached or no votes change
```

**Improvements:**
- ✅ Models see peers' reasoning before final decision
- ✅ Opportunity to change vote based on convincing arguments
- ✅ Multiple discussion rounds (configurable, default: 2)
- ✅ Auto-stops when consensus reached or votes stabilize
- ✅ Tracks deliberation rounds per bullet
- ✅ Fully backward compatible (can be disabled)

---

## How It Works

### 1. Identify Contested Bullets

After initial cross-voting, identify bullets with approval rates in the "contested" range:

```python
def is_contested(self, threshold_low=0.4, threshold_high=0.6) -> bool:
    """Check if approval rate is between thresholds."""
    approval = count(APPROVE) / (count(APPROVE) + count(REJECT))
    return threshold_low <= approval <= threshold_high
```

**Default thresholds:**
- Low: 40% approval
- High: 60% approval
- Bulletswith 40-60% approval trigger discussion

### 2. Conduct Discussion Rounds

For each contested bullet:

**Round 1:**
1. Show each model ALL other votes and reasoning
2. Prompt model to reconsider its vote
3. Model can CHANGE vote if convinced by arguments
4. Model can KEEP vote if still stands by assessment
5. Update votes in place

**Round 2 (if still contested):**
- Repeat with updated votes
- Stop early if consensus reached (e.g., now 80% approval)
- Stop early if no votes changed (stable disagreement)

**Max rounds:** Configurable (default: 2) to prevent infinite loops

### 3. Apply Final Voting Strategy

After deliberation, apply voting strategy as normal:
- Majority voting: >50% approval needed
- Supermajority: >66% approval needed
- Etc.

---

## Implementation Details

### Configuration Options

```python
learner = EnsembleLearner(
    models=[...],
    playbook_id="...",
    enable_deliberation=True,  # Enable/disable deliberation
    deliberation_threshold_low=0.4,  # Lower bound for contested (40%)
    deliberation_threshold_high=0.6,  # Upper bound for contested (60%)
    max_deliberation_rounds=2,  # Maximum rounds per bullet
)
```

### Key Methods

**`_conduct_deliberation(bullets, model_proposals) -> int`**
- Identifies contested bullets
- Runs discussion rounds for each
- Returns count of deliberated bullets

**`_get_deliberation_vote(bullet, model_id, current_vote, llm_client) -> Vote`**
- Gets updated vote after seeing peers' reasoning
- Returns same vote if unchanged, new vote if changed
- Handles errors gracefully (keeps current vote)

**`_create_deliberation_prompt(bullet, voter_id, current_vote) -> str`**
- Creates prompt showing all other votes + reasoning
- Includes guidelines for reconsidering
- Emphasizes: only change if convinced, not to agree

### Deliberation Prompt Example

```
# Deliberative Discussion: Reconsider Your Vote

**Contested Bullet** (close vote, 50% approval):
Section: code_snippets
Content: Always use regex for email validation: ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$

**Your Current Vote**:
✅ APPROVE (confidence: 0.80)
Your reasoning: Regex is fast and sufficient for most email validation needs.

**Other Models' Votes and Reasoning**:
- **ollama/qwen2.5-coder:0.5b**: ❌ REJECT (confidence: 0.75)
  Reasoning: Regex doesn't handle all RFC 5322 edge cases. Libraries like 'email-validator' are more robust and maintainable.

- **ollama/deepseek-coder:1.3b**: ✅ APPROVE (confidence: 0.65)
  Reasoning: For basic validation, regex is acceptable. Full RFC compliance rarely needed in practice.

**Task**: After reading the other models' arguments, reconsider your vote.

**Guidelines**:
- If others raised valid points you didn't consider, you MAY change your vote
- If you still stand by your original assessment, keep your vote
- Don't change just to agree - only change if convinced by the arguments

**Response Format**:
VOTE: [APPROVE/REJECT/ABSTAIN]
CONFIDENCE: [0.0-1.0]
REASONING: [1-2 sentences explaining your decision, mention if you were convinced by others' arguments or why you're keeping your vote]

Your reconsidered vote:
```

### Vote Updating

```python
def add_vote(self, vote: Vote, allow_update: bool = False) -> None:
    """
    Add or update a vote.

    Args:
        vote: Vote to add
        allow_update: If True, replaces existing vote (for deliberation)
    """
    existing_idx = find_vote_by_model(vote.model_id)
    if existing_idx:
        if allow_update:
            votes[existing_idx] = vote  # Replace for deliberation
        else:
            raise ValueError("Model already voted")
    else:
        votes.append(vote)
```

---

## Usage

### Enable Deliberation (Default)

```python
learner = EnsembleLearner(
    models=[
        ("ollama", "qwen2.5-coder:1.5b"),
        ("ollama", "qwen2.5-coder:0.5b"),
        ("ollama", "deepseek-coder:1.3b"),
    ],
    playbook_id="pb_20251028_001",
    enable_deliberation=True,  # Default: True
)

result = learner.learn_from_task(task, feedback)

# Check which bullets were deliberated
deliberated = [b for b in result.consensus_bullets if b.deliberation_rounds > 0]
print(f"{len(deliberated)} bullets underwent deliberation")
```

### Disable Deliberation

```python
learner = EnsembleLearner(
    models=[...],
    playbook_id="...",
    enable_deliberation=False,  # Skip deliberation
)
```

### Custom Thresholds

```python
learner = EnsembleLearner(
    models=[...],
    playbook_id="...",
    deliberation_threshold_low=0.3,  # More sensitive (30-70% triggers)
    deliberation_threshold_high=0.7,
    max_deliberation_rounds=3,  # More discussion rounds
)
```

### Inspect Deliberation Results

```python
for bullet in result.consensus_bullets:
    if bullet.deliberation_rounds > 0:
        print(f"\nBullet: {bullet.content[:50]}...")
        print(f"Deliberation rounds: {bullet.deliberation_rounds}")
        print(f"Final approval: {bullet.approval_rate:.0%}")
        print(f"\nVotes:")
        for vote in bullet.votes:
            print(f"  {vote.model_id}: {vote.vote.value} ({vote.confidence:.2f})")
            print(f"    {vote.reasoning}")
```

---

## Testing

**Test script:** `test_deliberation.py`

Runs ensemble learning with deliberation enabled and reports:
- Number of contested bullets
- Deliberation rounds per bullet
- Vote changes during discussion
- Final approval/rejection decisions

**Expected behavior:**
- 0-30% of bullets typically require deliberation
- 1-2 rounds usually sufficient
- Some votes will change based on peers' arguments
- Consensus often reached in round 1

---

## Performance Considerations

### Latency Impact

**Without deliberation:**
- Cross-voting: N bullets × M models = N×M votes
- Time: ~2-5 seconds per vote = O(N×M) time

**With deliberation:**
- Cross-voting: N×M votes
- Deliberation: C contested bullets × M models × R rounds = additional C×M×R votes
- Typical: 20% contested, 2 rounds = 0.4×N×M additional votes
- Time increase: ~40% for typical cases

**Example:**
- 10 bullets, 3 models = 30 initial votes
- 2 contested bullets → 2 × 3 × 2 = 12 deliberation votes
- Total: 42 votes (40% increase)
- Time: 90s → 126s (~40% slower)

### Cost Impact

**Token usage per deliberation vote:**
- Input: ~400 tokens (prompt + all votes' reasoning)
- Output: ~100 tokens (new vote + reasoning)
- Total: ~500 tokens per deliberation vote

**Example:**
- 10 bullets, 20% contested = 2 bullets
- 2 × 3 models × 2 rounds = 12 deliberation votes
- 12 × 500 = 6,000 additional tokens
- Still cheaper than adding a 4th model!

### Optimization Opportunities

1. **Parallel deliberation**: Vote updates can be parallelized per bullet
2. **Early stopping**: Skip round 2 if round 1 reached consensus
3. **Adaptive rounds**: Use more rounds only for highly contested bullets
4. **Caching**: Cache deliberation prompts for similar bullet patterns

---

## Metrics

Tracked in `VoteResults`:
- `avg_deliberation_rounds`: Average rounds per bullet
- `highly_contested`: Count of bullets requiring deliberation

**Tracked per bullet:**
- `deliberation_rounds`: Number of discussion rounds (0 = no deliberation)

---

## Examples

### Example 1: Consensus Reached in Round 1

**Initial votes:** 2 APPROVE, 1 REJECT (67% approval - not contested)
**Result:** No deliberation triggered

### Example 2: Vote Change in Round 1

**Initial votes:** 2 APPROVE, 1 REJECT (50% approval - contested!)

**Round 1:**
- Model A (APPROVE): Sees Model B's reasoning, changes to REJECT
- Model B (REJECT): Keeps vote
- Model C (APPROVE): Keeps vote

**Final votes:** 1 APPROVE, 2 REJECT (33% approval)
**Result:** Bullet REJECTED (majority reject)

### Example 3: Stable Disagreement

**Initial votes:** 2 APPROVE, 1 REJECT (50% approval)

**Round 1:** No votes change
**Result:** Stop deliberation (stable disagreement), apply voting strategy

---

## Backward Compatibility

- ✅ Disabled by default in older code (existing tests pass)
- ✅ `enable_deliberation=False` skips all deliberation logic
- ✅ Zero overhead when disabled
- ✅ All existing API unchanged
- ✅ Data models backward compatible (added optional fields)

---

## Future Enhancements

### Phase 3 (Next Sprint)

1. **Structured debate formats**: Formal debate with rebuttals
2. **Model-specific deliberation styles**: Some models more persuasive
3. **Deliberation summary**: LLM summarizes key arguments
4. **Vote explanation depth**: Longer reasoning for contested bullets
5. **Learning from past deliberations**: Track which arguments convince models

### Advanced Features

6. **Async deliberation**: Run rounds in background
7. **Partial consensus**: Accept 2/3 consensus without full discussion
8. **Expert weighting**: Weight votes by model's historical accuracy
9. **Domain-specific deliberation**: Different thresholds per domain

---

## Related Files

- **Implementation**: `src/ensemble/learner.py:418-727`
- **Data models**: `src/ensemble/models.py:102-148` (add_vote, get_vote, is_contested)
- **Test script**: `test_deliberation.py`
- **Voting system**: `src/ensemble/voting.py`

---

## Success Criteria

✅ All success criteria met:

1. ✅ Contested bullets trigger deliberation
2. ✅ Models see each other's reasoning
3. ✅ Votes can be updated based on arguments
4. ✅ Multiple rounds supported (configurable)
5. ✅ Auto-stops when consensus reached or votes stable
6. ✅ Tracks deliberation metadata per bullet
7. ✅ Backward compatible (can be disabled)
8. ✅ Test demonstrates functionality

---

## Conclusion

The deliberative discussion system transforms ensemble voting from a simple aggregation to a **collaborative peer review process**. Models don't just vote—they discuss, debate, and potentially change their minds based on compelling arguments from peers.

This upgrade was the **#2 priority** for Phase 2 (after LLM-based voting) and successfully enables more nuanced consensus building.

**Next recommended improvements:**
1. ✅ **LLM-based voting** - COMPLETE
2. ✅ **Deliberative discussion** - COMPLETE
3. 🔜 Persist ensemble results to database (#3 priority)
4. 🔜 Quality prediction before playbook addition (#6 priority)
