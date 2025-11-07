# ACE Autonomous Learning - Practical Roadmap

**Document Version**: 1.0
**Date**: November 7, 2025
**Status**: Planning
**Philosophy**: Human-in-the-loop, incremental improvements

---

## Overview

This roadmap focuses on **practical, incremental improvements** to ACE's learning capabilities while maintaining human oversight. We're not building a fully autonomous system - we're making the existing agent smarter and more helpful.

**Current State**: 8,000 LOC with working ACE loop, ensemble learning, basic TDD agent
**Goal**: Enhance learning quality and make the agent more useful for real development work
**Timeline**: 4-6 weeks for Phase 1, future phases TBD based on results

---

## Philosophy

### What We're Building

✅ **Better learning from successes** - Extract higher quality patterns
✅ **Learning from failures (with human review)** - Understand what went wrong
✅ **Smarter bullet retrieval** - Get more relevant context
✅ **Playbook quality tools** - Help humans curate better playbooks
✅ **Useful for real work** - Actually help developers build features

### What We're NOT Building

❌ **Fully autonomous agent** - Always requires human oversight
❌ **Auto-retry on failure** - Human reviews failures and decides next steps
❌ **Complex multi-file projects** - Focus on single-file features first
❌ **Production deployment** - Research/development tool for now

---

## Current State Assessment

### ✅ What Works Well

1. **Core ACE Loop** - Generator → Reflector → Curator works reliably
2. **Ensemble Learning** - Multi-model voting produces quality bullets
3. **T-Shaped Retrieval** - Cross-playbook learning is functional (bug fixed Nov 7)
4. **TDD Cycle** - RED → GREEN → REFACTOR → LEARN produces working code
5. **Playbook Storage** - JSON-based persistence is simple and debuggable

### ⚠️ What Needs Improvement

1. **Bullet Quality** - Many bullets are too generic or redundant
2. **Failure Analysis** - Currently just stops, doesn't extract learning
3. **Retrieval Relevance** - Sometimes retrieves irrelevant bullets
4. **Playbook Curation** - No tools to review/prune/improve bullets
5. **Learning Visibility** - Hard to see what agent learned and why

---

## Phase 1: Learning Quality Improvements

**Duration**: 4-6 weeks
**Effort**: ~1,200 LOC
**Goal**: Make existing learning more effective

### 1.1 Enhanced Failure Analysis (Week 1-2)

**Goal**: When agent fails, help human understand why

**Implementation**:
```python
# Location: src/agents/failure_analyzer.py (new file, ~300 LOC)

class FailureAnalyzer:
    def analyze_failure(
        self,
        test_result: TestResult,
        implementation: str,
        test_code: str
    ) -> FailureReport:
        """
        Generate detailed failure report for human review.

        Returns:
        - Error classification (syntax, logic, assertion, etc.)
        - Root cause hypothesis (what likely went wrong)
        - Code diff showing what was attempted
        - Suggested fixes (for human to apply manually)
        - Similar past failures (if any)
        """
```

**Output Example**:
```
❌ FAILURE REPORT - Cycle 4: test_mark_complete

Error Type: AssertionError
Error: Expected [{'task': 'A', 'completed': True}, {'task': 'B', 'completed': False}]
       Got     [{'task': 'B', 'completed': False}, {'task': 'A', 'completed': True}]

Root Cause: Ordering Issue
  The implementation used two separate lists:
  - self.tasks = ['B']           (incomplete)
  - self.completed_tasks = ['A']  (complete)

  When combined (self.tasks + self.completed_tasks), incomplete items come first,
  but test expects original insertion order.

Suggested Fix:
  Use single list with state flags instead of separate lists:

  # Instead of:
  self.tasks = []
  self.completed_tasks = []

  # Use:
  self.tasks = [
      {"task": "A", "status": "complete"},
      {"task": "B", "status": "incomplete"}
  ]

Would you like to:
  1. Retry with suggested fix
  2. Learn from this failure (add bullet to playbook)
  3. Skip this test for now
  4. Show me the full code
```

**Value**: Human sees clear explanation, can make informed decision

### 1.2 Guided Learning from Failures (Week 2-3)

**Goal**: Help human create good bullets from failures

**Implementation**:
```python
# Location: src/agents/failure_learner.py (new file, ~250 LOC)

class FailureLearner:
    def suggest_bullets_from_failure(
        self,
        failure_report: FailureReport,
        context: dict
    ) -> list[BulletSuggestion]:
        """
        Suggest bullets for human to review/approve.

        Uses ensemble to propose, human approves/edits/rejects.
        """

@dataclass
class BulletSuggestion:
    content: str
    section: str  # strategies, troubleshooting, etc.
    reasoning: str  # Why this bullet would help
    evidence: str  # What failure it addresses
    confidence: float  # How confident we are (0-1)
    tags: list[str]
```

**Interactive Flow**:
```bash
🧠 LEARNING FROM FAILURE

Proposed Bullets:

[1] Section: strategies_and_hard_rules
    Content: "When data needs to maintain insertion order across state changes,
              use a single list with state properties instead of multiple lists."
    Reasoning: Two-list approach lost ordering in TodoList test_mark_complete
    Confidence: 0.85
    Tags: ["architecture", "state-management", "ordering"]

[2] Section: troubleshooting
    Content: "If tests show wrong item order, check if implementation splits
              items across multiple lists (tasks vs completed_tasks)."
    Reasoning: Common mistake when managing stateful collections
    Confidence: 0.75
    Tags: ["debugging", "ordering", "state"]

Actions:
  [a] Approve all
  [1] Approve #1 only
  [2] Approve #2 only
  [e] Edit before approving
  [r] Reject all

Your choice: 1

✅ Added 1 bullet to playbook pb_20251107_936
```

**Value**: Human stays in control but gets good suggestions

### 1.3 Bullet Quality Scoring (Week 3-4)

**Goal**: Help identify and improve low-quality bullets

**Implementation**:
```python
# Location: src/playbook/quality.py (new file, ~350 LOC)

class BulletQualityScorer:
    def score_bullet(self, bullet: Bullet) -> QualityScore:
        """
        Score bullet on multiple dimensions:
        - Specificity (is it actionable vs generic?)
        - Clarity (is it easy to understand?)
        - Uniqueness (is it redundant with others?)
        - Usefulness (has it been used successfully?)
        """

    def find_redundant_bullets(
        self,
        playbook_id: str,
        similarity_threshold: float = 0.85
    ) -> list[tuple[Bullet, Bullet]]:
        """Find bullets that say the same thing"""

    def suggest_improvements(
        self,
        bullet: Bullet,
        issues: list[QualityIssue]
    ) -> list[str]:
        """Suggest how to make bullet better"""

@dataclass
class QualityScore:
    specificity: float  # 0-1
    clarity: float      # 0-1
    uniqueness: float   # 0-1
    usefulness: float   # 0-1 (based on usage stats)
    overall: float      # weighted average
    issues: list[str]   # What's wrong
    suggestions: list[str]  # How to improve
```

**CLI Tool**:
```bash
python -m src.playbook.quality review pb_20251107_936

📊 PLAYBOOK QUALITY REPORT

Playbook: pb_20251107_936 (autonomous_tdd_demo)
Bullets: 15 total

Quality Distribution:
  🟢 High (>0.8):     8 bullets (53%)
  🟡 Medium (0.5-0.8): 5 bullets (33%)
  🔴 Low (<0.5):      2 bullets (13%)

Issues Found:

[1] Bullet #3: "Use good variable names"
    Score: 0.35 (Low)
    Problems:
      - Too generic (specificity: 0.2)
      - Not actionable (clarity: 0.4)
    Suggestions:
      - Add specific examples of good vs bad names
      - Link to specific context (e.g., "In TDD test methods...")

[2] Bullet #7: "Validate input parameters"
    Duplicate of Bullet #4 (similarity: 0.92)
    Suggestion: Merge these bullets

[3] Bullet #12: "Handle errors properly"
    Score: 0.42 (Low)
    Problems:
      - Vague (what does "properly" mean?)
      - No examples
    Suggestions:
      - Specify error types
      - Add code snippet showing how

Actions:
  [d] Delete low-quality bullets
  [m] Merge duplicates
  [i] Improve with suggestions
  [e] Export report to review later
```

**Value**: Humans can maintain playbook quality over time

### 1.4 Smarter Retrieval (Week 4-5)

**Goal**: Retrieve more relevant bullets

**Implementation**:
```python
# Location: src/playbook/smart_retrieval.py (new file, ~300 LOC)

class SmartRetriever:
    def retrieve_with_context(
        self,
        query: str,
        task_context: TaskContext,
        playbook_id: str
    ) -> list[tuple[Bullet, float, str]]:
        """
        Retrieve bullets using multiple signals:
        1. Semantic similarity (existing)
        2. Task type matching (new)
        3. Historical effectiveness (new)
        4. Recency boost (new)
        """

@dataclass
class TaskContext:
    task_type: str  # "test_writing", "implementation", "refactor"
    domain: str  # "crud", "calculation", "validation", etc.
    phase: str  # "RED", "GREEN", "REFACTOR", "LEARN"
    previous_failures: list[str]  # If retrying
    file_type: str  # ".py", ".js", etc.
```

**Improvements**:
- **Type matching**: For test writing, prioritize test-related bullets
- **Effectiveness**: Boost bullets that have high success rate
- **Recency**: Slight boost to recently-used bullets (working memory)
- **Negative filtering**: Exclude bullets that failed in similar contexts

**Value**: Agent gets better context, makes fewer mistakes

### 1.5 Learning Dashboard (Week 5-6)

**Goal**: Visualize what agent is learning

**Implementation**:
```python
# Location: src/playbook/dashboard.py (new file, ~250 LOC)

class LearningDashboard:
    def generate_html_report(
        self,
        playbook_id: str,
        time_range: timedelta = timedelta(days=7)
    ) -> str:
        """Generate interactive HTML dashboard"""
```

**Dashboard Sections**:

1. **Playbook Growth**
   - Bullet count over time (line chart)
   - Bullets by section (pie chart)
   - Learning rate (bullets/task)

2. **Bullet Effectiveness**
   - Top 10 most useful bullets
   - Bottom 10 least useful bullets
   - Usage frequency heatmap

3. **Task Performance**
   - Success rate over time
   - Average cycles per feature
   - Common failure patterns

4. **Recent Activity**
   - Last 10 learned bullets
   - Recent tasks completed
   - Recent failures analyzed

**CLI**:
```bash
python -m src.playbook.dashboard pb_20251107_936 --open

📊 Opening dashboard in browser...
   http://localhost:8080/dashboard/pb_20251107_936
```

**Value**: Human can see learning progress at a glance

---

## Phase 1 Deliverables

### Code
- [x] FailureAnalyzer (300 LOC)
- [x] FailureLearner (250 LOC)
- [x] BulletQualityScorer (350 LOC)
- [x] SmartRetriever (300 LOC)
- [x] LearningDashboard (250 LOC)

**Total**: ~1,450 LOC

### Tools
- [x] `python -m src.agents.failure_analyzer` - Analyze test failures
- [x] `python -m src.playbook.quality review <playbook_id>` - Review bullet quality
- [x] `python -m src.playbook.dashboard <playbook_id>` - View learning dashboard

### Documentation
- [x] Failure analysis guide
- [x] Bullet quality best practices
- [x] Dashboard usage guide

### Tests
- [x] Unit tests for all new modules
- [x] Integration test: TodoList with failure analysis
- [x] Integration test: Quality scoring on real playbook
- [x] Integration test: Dashboard generation

---

## Success Metrics

### Quantitative

1. **Bullet Quality**
   - Target: >70% of bullets score >0.7
   - Baseline: Unknown (measure first)

2. **Retrieval Relevance**
   - Target: >80% of retrieved bullets used in solution
   - Measure: Manual review of 20 tasks

3. **Learning Efficiency**
   - Target: <5% duplicate bullets
   - Measure: Similarity analysis

### Qualitative

1. **Failure Understanding**
   - Survey: Can human understand failure from report? (>90% yes)

2. **Bullet Usefulness**
   - Survey: Are suggested bullets helpful? (>70% yes)

3. **Dashboard Value**
   - Survey: Is dashboard useful for playbook maintenance? (>80% yes)

---

## Future Phases (Post Phase 1)

Based on Phase 1 results, we might pursue:

### Phase 2: Usage Analytics (3-4 weeks)
- Track which bullets help most
- A/B testing for bullet effectiveness
- Automatic bullet deprecation (mark as outdated, not delete)

### Phase 3: Multi-Task Learning (4-5 weeks)
- Cross-task pattern recognition
- Meta-patterns ("For X type of task, use Y approach")
- Playbook forking/merging for different domains

### Phase 4: Collaboration Features (3-4 weeks)
- Share playbooks between developers
- Import/export high-quality bullets
- Community playbook repository

**Decision Point**: Review Phase 1 results before committing to Phase 2

---

## Resource Requirements

### Phase 1

**Team**: 1 senior engineer, 4-6 weeks full-time

**Infrastructure**:
- Development: Local (Ollama) or OpenAI API
- API costs: ~$200-400 for testing
- Storage: <1GB

**Total Cost**: ~$20,000-30,000 (engineer time + API)

---

## Getting Started

### Week 1 Tasks

1. **Day 1-2**: Implement FailureAnalyzer
   - Error classification
   - Root cause analysis
   - Pretty-printed reports

2. **Day 3-4**: Test with TodoList
   - Run autonomous TDD demo
   - Force failure in cycle 4
   - Verify report is helpful

3. **Day 5**: Write documentation
   - How to use FailureAnalyzer
   - Example failure reports
   - Best practices

### Demo at End of Week 1

```bash
python demo_with_failure_analysis.py

# Output:
[Cycle 1-3] ✅
[Cycle 4: test_mark_complete]
  RED ✅
  GREEN ❌

  ═══════════════════════════════════════
  ❌ FAILURE ANALYSIS
  ═══════════════════════════════════════

  Error: AssertionError in test ordering
  Root Cause: Two-list approach loses insertion order

  Suggested Fix: Use single list with state flags

  [View full report] [Learn from failure] [Retry manually]
```

**Success Criteria**: Failure report is clear and actionable

---

## Risks & Mitigation

### Risk: Scope Creep
- **Mitigation**: Strict focus on Phase 1, no feature adds
- **Check**: Weekly review of scope

### Risk: Low Adoption
- **Mitigation**: Focus on practical tools developers will use
- **Check**: Get feedback from 2-3 users mid-phase

### Risk: Bullet Quality Hard to Measure
- **Mitigation**: Start with simple heuristics, iterate
- **Check**: Manual review of 50 bullets to calibrate scoring

---

## Appendix: Rejected Ideas

These ideas were considered but deferred:

1. **Auto-retry on failure** - Too risky, human should review first
2. **Fully autonomous agent** - Not the goal, human oversight is valuable
3. **Complex architectural decisions** - Too ambitious for Phase 1
4. **Multi-file project support** - Single-file is enough to start
5. **Production deployment** - Research tool for now

These might be revisited in future phases based on needs.

---

**Document Owner**: ACE Development Team
**Last Updated**: November 7, 2025
**Next Review**: End of Phase 1 (Week 6)
