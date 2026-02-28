# ACE: AI Coding Engine

**The problem:** AI writes plausible code, not working code.

You can prompt Claude or GPT to "use TDD" and it will produce code that *looks* like TDD was followed. But without execution, there's no ground truth. The model says "this test would fail" - but would it?

**ACE closes the loop.** Write test → run it → see real failure → implement → run again → see real pass. Actual execution, not imagination.

**Machine-written, machine-verified.**

```
AI writes the tests
AI writes the code
pytest verifies it actually works
AI fixes until it passes
Integration tests verify it works together
```

Not "AI wrote it, trust it." It's "AI wrote it, **proved it works.**"

Human provides requirements and approval. Machine does the labor and verification.

---

## Core Insight

```
Prompting "use TDD":           ACE:

Model: "Test would fail"       Model: writes test
Model: "Now it passes"         ACE: pytest → FAILED (actual)
Model: "Done ✓"                Model: sees error, implements
                               ACE: pytest → PASSED (actual)
```

The gap is execution feedback. Real error messages catch real bugs.

---

## Architecture: Four Systems Working Together

```
┌─────────────────────────────────────────────────────────┐
│                      REQUEST                             │
│        "Build a rate limiter with sliding window"        │
└─────────────────────────────────────────────────────────┘
          │                                    │
          ▼                                    ▼
┌──────────────────────┐           ┌──────────────────────┐
│  BROKER              │           │  PLAYBOOK            │
│  Which model?        │           │  Which patterns?     │
│  Routes based on     │           │  Retrieves with      │
│  task/cost/fallback  │           │  APPLY/SKIP/ASK      │
└──────────────────────┘           └──────────────────────┘
          │                                    │
          └──────────────┬─────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│  TDD BUILDER                                             │
│  Contract + Patterns + Model → Working code              │
│  Actually runs pytest. Real failures. Real passes.       │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  AUDIT                                                   │
│  Logs every call. Tracks costs. Full attribution.        │
└─────────────────────────────────────────────────────────┘
```

**Four distinct systems:**

| System | Responsibility |
|--------|---------------|
| **Broker** | Picks which model to use (routing, fallbacks, cost) |
| **Playbook** | Picks which patterns to inject (retrieval, verdicts) |
| **TDD Builder** | Runs the actual red-green-refactor loop |
| **Audit** | Logs everything for compliance/debugging |

---

## 1. TDD Builder: Kent Beck Style with Emergent Planning

**Not "generate all code at once" - iterative TDD like a human would do.**

### Multiple Cycles Until Done

Each cycle determines the next test based on what exists:

```
Cycle 1: "What's the first test?"     → test_add_basic
Cycle 2: "What's missing?"            → test_add_negative_numbers
Cycle 3: "What edge cases?"           → test_add_overflow
Cycle 4: "Requirement satisfied?"     → Yes, stop
```

**Emergent planning**: Tests aren't planned upfront. Each cycle sees what's implemented, what's tested, and decides what's next. Keeps going until requirement is covered - including edge cases.

**Stopping the gallop**: Models want to write everything at once and claim it works. The TDD loop forces discipline:

- Can't move to cycle 2 until cycle 1's test *actually passes*
- Can't claim "done" when pytest says FAILED
- Has to fix each increment before moving on
- Methodical over vibe coding

**Python today, extensible to other languages**: Currently uses pytest. The core loop is language-agnostic (write test → run → parse → iterate), but adding a new language requires a test runner adapter and output parser. Not plug-and-play, but not a rewrite either.

**Future: Contract-driven language transpilation**: Since contracts and Gherkin are language-agnostic, you could:

1. Build in Python (your comfort zone)
2. Keep the contracts + Gherkin, discard the Python code
3. Run TDD in Go/TypeScript/Rust using the same contracts
4. Get working code in the new language, verified by the same specs

Not automatic transpilation - re-implementation guided by specification. The TDD loop ensures the new code passes the same behavioral tests.

### Each Cycle: RED → GREEN → REFACTOR → LEARN

```
RED:      Write failing test (refines if it passes unexpectedly)
GREEN:    Write minimal code to pass (retries with error feedback)
REFACTOR: Clean up
LEARN:    Extract patterns for playbook
```

### Real Execution, Not Imagination

The TDD builder actually runs pytest and captures real output:

```
# RED phase - ACE runs the test
$ pytest test_calculator.py
FAILED test_calculator.py::test_add
    assert add(2, 2) == 4
    AssertionError: assert None == 4

# Model sees REAL failure, writes implementation

# GREEN phase - ACE runs again
$ pytest test_calculator.py
PASSED test_calculator.py::test_add
```

The model sees `AssertionError: assert None == 4` - not a guess. Real test runner, real failures, real passes.

---

## 2. Broker: Smart Routing = Cheaper Models

The broker routes requests to models based on task complexity and cost:

```python
# Typical flow
architect_model = "claude-sonnet"      # Smart, runs once
builder_model = "llama-3.3-70b:free"   # Cheap, runs many times
```

**Good context means cheaper models can do the work.**

A 70B model with clear instructions and relevant patterns often beats a 400B model with vague requirements. The architect + playbook provide that context, so smaller models succeed.

- Fallback chains if one model fails
- Cost tiers (free → cheap → premium)
- All through OpenRouter

---

## 3. Playbook: Self-Optimizing Patterns (Not Static Files)

**Not another CLAUDE.md or rules file.**

| Static files (CLAUDE.md, .cursorrules) | ACE Playbook |
|----------------------------------------|--------------|
| Manually written and maintained | Learned from TDD cycles |
| You remember to update it (or don't) | Updates automatically |
| Same weight for everything | Confidence scores based on outcomes |
| Grep/keyword matching | Semantic search for relevance |
| Gets stale | Gets better |

**The learning loop:**

```
TDD cycle succeeds → Pattern extracted → Playbook updated → Next cycle uses it
```

Patterns accumulate with confidence scores:

```yaml
patterns:
  - id: ctx-00042
    content: "For FastAPI endpoints, always add response_model"
    confidence: 0.92
    learned_from: 47 successful builds

  - id: ctx-00089
    content: "pytest fixtures go in conftest.py, not test files"
    confidence: 0.87
    learned_from: 23 TDD cycles
```

**It gets better the more you use it.** First TDD run is cold. After 50 runs, it knows your codebase patterns, your testing conventions, what works.

**Context-aware retrieval with reasoning:**

Pattern retrieval isn't just "find similar" - it reasons about whether a pattern applies:

```
┌─────────────────────────────────────────────────────────┐
│  Query: "How to handle database connections?"           │
│  Context: FastAPI project, Python 3.11, async           │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  Pattern: "Use connection pooling with SQLAlchemy"      │
│  Verdict: APPLY ✓                                       │
│  (Context matches: FastAPI + SQLAlchemy common)         │
├─────────────────────────────────────────────────────────┤
│  Pattern: "Use Django ORM with settings.py"             │
│  Verdict: SKIP ✗                                        │
│  (Context mismatch: Django pattern, FastAPI project)    │
├─────────────────────────────────────────────────────────┤
│  Pattern: "Consider async drivers for FastAPI"          │
│  Verdict: ASK_FIRST ?                                   │
│  (Relevant but need to confirm: using async DB?)        │
└─────────────────────────────────────────────────────────┘
```

Three verdicts:
- **APPLY** - Context matches, safe to use
- **SKIP** - Context mismatch, wrong pattern for this situation
- **ASK_FIRST** - Relevant but needs clarification before applying

Solo dev: local playbook, your patterns.
Team: shared playbook, org-wide standards that improve over time.

**Why playbooks instead of fine-tuning?**

| Playbooks | Fine-tuning |
|-----------|-------------|
| No ML infrastructure | Requires training pipeline, compute |
| Instant updates | Requires retraining |
| Explainable (see what's applied) | Black box |
| Works with any model | Locked to one base model |
| Reversible (remove bad patterns) | Can't "untrain" |
| Few examples needed | Needs lots of training data |
| Use best models (Claude, GPT-4) | Often limited to smaller models |

Playbooks = **RAG for your coding patterns**. Model stays general-purpose (good at reasoning), patterns injected at runtime (your specific knowledge). Best of both worlds.

---

## 4. MCP Server: Plug Into Any Agent

ACE exposes its capabilities via [Model Context Protocol](https://modelcontextprotocol.io/):

```json
{
  "tools": [
    "get_guidance",    // Context-aware pattern retrieval with verdicts
    "learn",           // Add knowledge to playbook
    "query",           // Semantic search
    "feedback",        // Mark patterns helpful/harmful
    "build_feature"    // TDD feature development
  ]
}
```

**Any MCP-compatible agent can use ACE's playbook and TDD system.** Claude Desktop, custom agents, IDE integrations - they all get access to:

- Your accumulated patterns
- Context-aware guidance (APPLY/SKIP/ASK_FIRST)
- TDD build capability

Not locked to one tool. ACE becomes infrastructure other agents can use.

---

## 5. Audit: Enterprise-Ready from Day One

Audit trail built into the architecture, not bolted on:

```python
# Every LLM call is logged
{
    "event_type": "llm_call",
    "model": "claude-sonnet-4",
    "prompt_tokens": 1523,
    "completion_tokens": 847,
    "cost_usd": 0.0234,
    "session_id": "feature-xyz",
    "timestamp": "2024-01-15T10:23:45Z"
}
```

Works for solo devs (local SQLite). Designed for teams (centralized, RBAC, compliance).

---

## Open Source Strategy

| Open Source | Enterprise |
|-------------|------------|
| TDD loop with execution | Centralized audit, dashboards |
| Multi-model routing | Team playbooks, SSO |
| Local audit trail | Compliance reports, RBAC |
| Local playbook | Usage analytics, budget controls |
| CLI, all core tooling | Priority support |

Philosophy: Full-featured for individuals. Enterprise adds team governance.

---

## The Flow: Requirements → Contract → Gherkin → Working Code

### Step 1: Natural Language Requirements

```
"Build a rate limiter with sliding window. Should track requests
per user, configurable window size and max requests. Return
true/false for is_allowed, and include a reset method."
```

### Step 2: Module Architect Generates Contract (YAML)

```yaml
# rate_limiter.contract.yml
contracts:
  - id: rate-001
    function_name: is_allowed
    signature: "(user_id: str) -> bool"
    docstring: "Check if user can make a request"
    complexity: 2
    test_cases:
      - name: under_limit
        input: "('alice',)"
        expected: "True"
      - name: over_limit
        input: "('bob',)"
        expected: "False"
    hints:
      - "Track timestamps per user"
      - "Use sliding window algorithm"

  - id: rate-002
    function_name: reset
    signature: "(user_id: str) -> None"
    docstring: "Reset request count for user"
    complexity: 1
    test_cases:
      - name: reset_clears
        input: "('carol',)"
        expected: "None"
```

### Step 3: Gherkin Feature File Generated

```gherkin
Feature: Rate Limiter with Sliding Window

  Scenario: Allow requests under limit
    Given a rate limiter with max 5 requests per 60 seconds
    When user "alice" makes 3 requests
    Then is_allowed returns true for user "alice"

  Scenario: Block requests over limit
    Given a rate limiter with max 5 requests per 60 seconds
    When user "bob" makes 6 requests
    Then is_allowed returns false for user "bob"

  Scenario: Reset clears request count
    Given a rate limiter with max 5 requests per 60 seconds
    And user "carol" has made 5 requests
    When reset is called for user "carol"
    Then is_allowed returns true for user "carol"

  Scenario: Sliding window expires old requests
    Given a rate limiter with max 5 requests per 2 seconds
    When user "dave" makes 5 requests
    And 3 seconds pass
    Then is_allowed returns true for user "dave"
```

### Step 4: TDD Builder Runs Red-Green-Refactor

```
# RED - Tests generated from Gherkin, all fail
$ pytest test_rate_limiter.py
FAILED test_allow_under_limit - NameError: name 'RateLimiter' is not defined
FAILED test_block_over_limit - NameError: name 'RateLimiter' is not defined
...

# GREEN - Implementation written to pass tests
$ pytest test_rate_limiter.py
PASSED test_allow_under_limit
PASSED test_block_over_limit
PASSED test_reset_clears_count
PASSED test_sliding_window_expires

# Output: working rate_limiter.py with tests
```

**From English to working code with tests, through a verifiable contract.**

---

## Key Questions This Answers

**"Can't I just prompt Claude to use TDD?"**

You can, and it'll write code that looks like TDD. But it's imagining test results. ACE runs real tests and feeds real failures back.

**"Why not just use Cursor/Copilot?"**

Those are great for generation. ACE is about verification. Use whatever AI tool you want - ACE ensures the output actually works.

**"What's the enterprise value?"**

Governance. Your devs are using AI to write code. ACE gives you: audit trails (who generated what), policy control (approved models, budget limits), shared patterns (team standards).

---

## Status

Active development. Core TDD loop working. Looking for feedback on the approach.

---

*Built for enterprise. Works for individuals.*
