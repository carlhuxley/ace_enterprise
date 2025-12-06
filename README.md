# ACE Enterprise

**Institutional Knowledge Infrastructure for Software Development and ML Experimentation**

ACE Enterprise transforms how organizations capture, share, and reuse knowledge from software development and ML experimentation. Instead of decisions and insights being lost in Slack messages or abandoned notebooks, ACE automatically captures the *why* behind your work and makes it queryable for future projects.

## What We're Building

ACE has evolved from a research prototype into **institutional memory infrastructure**:

- **Software Development**: Autonomous TDD agent that learns from failures and builds project-specific knowledge
- **ML Experimentation**: MLflow integration that captures decision rationale, alternatives, and learned insights
- **Cross-Project Learning**: Centralized knowledge base that surfaces relevant patterns from past work

### The Core Problem

Traditional tools track *what* happened:
- Git tracks code changes
- MLflow tracks experiment parameters and metrics
- JIRA tracks tasks

But they don't capture *why*:
- Why did you choose this approach?
- What alternatives did you consider?
- What did you learn when it failed?
- Would this pattern help a colleague's project?

**ACE fills this gap** by automatically capturing decisions, rationale, and learned insights as structured, queryable knowledge.

## Key Features

### Autonomous TDD Agent
- **Gherkin-driven development**: Write business requirements, agent generates tests and implementation
- **Semantic learning**: Learns from failures and stores patterns in project playbook
- **Test redundancy detection**: Analyzes existing tests and implementation to avoid redundant tests
- **Automatic test correction**: Identifies and fixes malformed tests during development
- **Full traceability**: Links Gherkin scenarios → tests → implementation → decisions

### Gherkin Extraction (Reverse Engineering)
- **Extract from legacy code**: Reverse-engineer Gherkin from existing Python code and tests
- **Safe refactoring**: Extract specs as blueprint, rebuild with clean implementation
- **Cross-language migration**: Python → Go/Rust/Java/TypeScript with behavior preservation
- **Documentation generation**: Auto-generate business-readable docs from legacy systems
- **Migration validation**: Both old and new implementations pass same Gherkin = behavior preserved

### MLflow + ACE Integration
- **Decision capture**: "Why did I choose Adam optimizer?" answered 3 months later
- **Alternative tracking**: "What else did we try? What failed?"
- **Pattern extraction**: "Learning rate warmup works for batch_size > 256 (85% success rate)"
- **Cross-experiment learning**: Apply proven patterns from past projects
- **Unified queries**: Search across both execution data (MLflow) and knowledge (ACE)

### Playbook System
- **Automatic learning**: Failures generate semantic patterns, not just error logs
- **Contextual retrieval**: Only relevant patterns shown when needed
- **Provenance tracking**: Full auditability - which human and AI made each decision
- **Cross-project sharing**: Patterns used in 10 projects = high value signal
- **Natural selection**: Generic patterns obsolete as AI improves, institutional knowledge persists

## Quick Start

### Try the ML Experimentation Demo

Demonstrates decision capture during ML training:

```bash
# Install dependencies
pip install -r requirements-ml.txt

# Run demo (trains 3 experiments, captures decisions, extracts patterns)
python demo_mlflow_ace.py
```

The demo shows:
1. Three RandomForest experiments with different hyperparameters
2. Decision capture ("Why max_depth=20? → Prevent overfitting")
3. Outcome tracking ("Successful - improved accuracy by 2%")
4. Pattern extraction ("Limited tree depth improves generalization")
5. Knowledge queries ("Show me all successful optimizer decisions")

**Storage**: `~/.ace/ml_experiments/image_classification_demo.json`

### Try the Autonomous TDD Agent

Demonstrates Gherkin-driven development with learning:

```bash
# Run RBAC demo
python demo_rbac_tdd.py
```

The demo shows:
1. Reads Gherkin acceptance tests (`gherkin_acceptance_tests/rbac.feature`)
2. Generates unit tests automatically using TDD cycles
3. Implements code to make tests pass
4. Learns from failures (e.g., "Don't test constructor parameters - implicitly validated")
5. Stores learned patterns in playbook for future cycles

**Storage**: Generated code in `/tmp/ace_demo_*/`, playbooks in project directory

### Try Gherkin Extraction (Reverse Engineering)

Demonstrates extracting Gherkin from existing code for safe refactoring and cross-language migration:

```bash
# Extract Gherkin from existing Python code
python3 demo_gherkin_extraction.py

# Full workflow: Python → Gherkin → Go
python3 demo_cross_language_migration.py
```

The demo shows:
1. **Analyze** existing Python code and tests (OAuth client example)
2. **Extract** Gherkin scenarios capturing business behavior
3. **Generate** Go step definitions from extracted Gherkin
4. **Scaffold** Go implementation ready for coding
5. **Validate** both Python and Go pass same specs

**Use cases:**
- Refactor legacy Python code safely
- Migrate Python → Go/Rust for performance
- Document legacy systems in business-readable format
- Enable polyglot microservices with shared specs

**Storage**:
- Gherkin: `extracted_gherkin/oauth.feature`
- Go impl: `go_oauth_implementation/`

## Project Structure

```
ace_enterprise/
├── src/
│   ├── agents/                    # Autonomous development agents
│   │   ├── autonomous_tdd_agent.py  # Gherkin-driven TDD with learning
│   │   ├── gherkin_extraction_agent.py  # Extract Gherkin from existing code
│   │   └── go_step_generator.py     # Generate Go step definitions
│   ├── ml/                        # ML experiment knowledge
│   │   ├── experiment_knowledge.py  # Decision and pattern schema
│   │   ├── mlflow_callback.py       # Auto-capture during training
│   │   └── query_interface.py       # Unified MLflow + ACE queries
│   ├── playbook/                  # Playbook management
│   │   ├── bullet_manager.py        # CRUD for knowledge bullets
│   │   ├── semantic_retrieval.py    # Contextual pattern retrieval
│   │   └── models.py                # Playbook data models
│   ├── llm/                       # LLM provider abstraction
│   ├── storage/                   # Database models
│   ├── utils/                     # Utilities
│   └── config/                    # Configuration
│
├── gherkin_acceptance_tests/      # Acceptance test scenarios
│   ├── oauth.feature              # OAuth authentication scenarios
│   ├── rbac.feature               # Role-based access control scenarios
│   └── steps/                     # Step definitions (API contract)
│
├── demo_mlflow_ace.py             # ML experiment knowledge demo
├── demo_rbac_tdd.py               # Autonomous TDD demo
├── demo_gherkin_extraction.py     # Extract Gherkin from code demo
├── demo_cross_language_migration.py  # Python → Go migration demo
├── requirements-ml.txt            # ML dependencies
│
├── docs/
│   ├── ACE_STRATEGIC_PLAN.md      # Strategic vision and roadmap
│   ├── mlflow_integration.md      # MLflow + ACE architecture
│   ├── mlflow_integration_summary.md
│   ├── gherkin_driven_unit_tests.md  # ATDD approach
│   ├── gherkin_extraction.md      # Reverse engineering guide
│   └── mlflow_quick_start.md
│
└── USER_CONTRIBUTIONS.md          # Session logs and insights
```

## Architecture

### Hybrid Approach: Scaffolding + Tool

ACE implements a **natural selection strategy**:

1. **Generic patterns** (pytest usage, mocking patterns)
   - Short-term value: Help current AI models
   - Long-term: Obsolete as AI capabilities improve
   - Self-cleaning: Usage data shows when patterns no longer needed

2. **Institutional knowledge** (project-specific decisions)
   - Short-term value: Consistency across team
   - Long-term: Persists indefinitely
   - Compounds: HIPAA requirements, incident learnings, architectural decisions

**Central Knowledge Base**: `~/.ace/knowledge/`
- `playbooks/global.json` - Generic patterns
- `playbooks/healthcare.json` - Domain patterns from ALL healthcare projects
- `ml_experiments/` - ML experiment decisions and patterns

### Learning Loop

```
┌─────────────────────────────────────────────────────────┐
│                    Work (TDD or ML)                     │
└────────────────────┬────────────────────────────────────┘
                     │
                ┌────▼────┐
                │ Failure │
                └────┬────┘
                     │
          ┌──────────▼──────────┐
          │   LEARN (Analyze)   │ ← What went wrong? Why?
          │  • Root cause       │   What pattern is this?
          │  • Semantic insight │
          └──────────┬──────────┘
                     │
          ┌──────────▼──────────┐
          │  STORE (Playbook)   │ ← Structured, tagged bullet
          │  • Provenance       │
          │  • Tags for retrieval│
          └──────────┬──────────┘
                     │
          ┌──────────▼──────────┐
          │ RETRIEVE (Context)  │ ← Only relevant patterns
          │  • Semantic search  │   shown when needed
          │  • Success rate     │
          └──────────┬──────────┘
                     │
                ┌────▼────┐
                │ Success │
                └─────────┘
```

### Provenance Tracking

Every decision and pattern includes:
```json
{
  "provenance": {
    "created_by": {
      "human": "developer@company.com",
      "ai_models": [
        {"provider": "togetherai", "model": "Qwen/Qwen2.5-Coder-32B-Instruct", "license": "Apache-2.0"}
      ]
    },
    "created_at": "2025-12-01T10:30:00Z",
    "conversation_id": "conv_abc123"
  },
  "projects": ["healthcare_app_1", "fintech_fraud_detection"],
  "usefulness_score": 0.85,
  "times_applied": 12,
  "times_successful": 10
}
```

**Benefits:**
- Legal compliance (track proprietary model usage)
- Quality analysis (which models produce best patterns)
- Developer credit (track contributions)
- Audit trail (who decided what, when, why)

## Use Cases

### 1. ML Experimentation Knowledge

**Before ACE:**
```
Researcher 3 months later: "Why did I use lr=0.001? Can't remember..."
New team member: "Why do we use Adam here? No one knows..."
```

**With ACE:**
```python
from src.ml import MLflowKnowledgeQuery

query = MLflowKnowledgeQuery("my_experiment")

# See decision history
for decision in query.get_decision_history():
    print(f"{decision.question} → {decision.decision}")
    print(f"Why: {decision.rationale}")
    print(f"Alternatives: {decision.alternatives_considered}")
    print(f"Outcome: {decision.learned_insight}")
```

### 2. Cross-Project Pattern Reuse

**Before ACE:**
```
"Starting a new healthcare CV project. Wonder if patterns from fintech apply?"
"Let me dig through old notebooks... can't find them..."
```

**With ACE:**
```python
# Get patterns from other domains
healthcare_query = MLflowKnowledgeQuery("healthcare_imaging")
fintech_query = MLflowKnowledgeQuery("fintech_fraud")

cv_patterns = [
    p for p in fintech_query.knowledge.get_successful_patterns()
    if "computer_vision" in p.domain_tags
]

# Apply proven patterns to new project
for pattern in cv_patterns:
    print(f"Pattern: {pattern.pattern_name}")
    print(f"Success rate: {pattern.success_rate}")
    print(f"When to apply: {pattern.when_to_apply}")
```

### 3. Autonomous Development with Learning

**Before ACE:**
```
Write test → Implement code → Test fails → Debug → Repeat
(Each failure is lost knowledge)
```

**With ACE:**
```
Write Gherkin scenario → Agent generates test → Implements code
→ Test fails → Agent analyzes WHY → Stores pattern → Retries with knowledge
→ Future cycles avoid same mistake
```

### 4. Cross-Language Migration

**Before ACE:**
```
"We need to migrate this Python service to Go for performance"
→ Manual rewrite, hoping behavior matches
→ No verification, lots of bugs, risky deployment
```

**With ACE:**
```python
# Extract Gherkin from existing Python
python3 demo_gherkin_extraction.py

# Generates language-agnostic specs:
# Feature: OAuth Authentication
#   Scenario: Generate authorization URL
#     Given an OAuth client with credentials
#     When I generate an authorization URL
#     Then the URL should contain required parameters

# Generate Go implementation
python3 demo_cross_language_migration.py

# Implement in Go
cd go_oauth_implementation
# Edit steps/oauth_steps.go

# Validate both pass same specs
behave features/oauth.feature  # Python ✓
go test -v                      # Go ✓

# Both pass = behavior preserved!
```

**Benefits:**
- Safe migration with behavior verification
- Incremental (one module at a time)
- Polyglot microservices with shared specs
- Performance gains with confidence

## Documentation

### Strategic Vision
- [Strategic Plan](./docs/ACE_STRATEGIC_PLAN.md) - Full architectural vision and roadmap
- [User Contributions](./USER_CONTRIBUTIONS.md) - Session logs with key insights and discoveries

### Implementation Guides
- [MLflow Integration](./docs/mlflow_integration.md) - Complete ML experiment knowledge architecture
- [MLflow Quick Start](./docs/mlflow_quick_start.md) - Quick reference for ML integration
- [Gherkin-Driven TDD](./docs/gherkin_driven_unit_tests.md) - Acceptance test-driven development approach
- [Gherkin Extraction](./docs/gherkin_extraction.md) - Reverse engineering and cross-language migration guide

### Legacy Docs (Historical)
- [Product Requirements Document](./PRD.md) - Original system specifications
- [Architecture Guide](./docs/architecture.md) - (Needs update to reflect current vision)

## Tech Stack

### Core
- **Language**: Python 3.11+
- **LLM Providers**: TogetherAI (Qwen, DeepSeek), Anthropic, OpenAI
- **Knowledge Storage**: JSON files at `~/.ace/` (simple, portable, version-controllable)

### ML Integration
- **MLflow**: Experiment tracking (parameters, metrics, artifacts)
- **ACE**: Decision tracking (rationale, alternatives, insights)
- **scikit-learn**: Demo experiments

### TDD Agent
- **pytest**: Test execution
- **behave**: Gherkin parsing (step definitions)
- **Playbook system**: Semantic pattern storage and retrieval

### Development (Legacy - for future API)
- **Framework**: FastAPI
- **Database**: PostgreSQL 15+ with pgvector
- **Cache**: Redis 7+
- **Monitoring**: Prometheus + Grafana

## Roadmap

### ✅ Completed (v0.1)
- [x] Strategic pivot to institutional knowledge infrastructure
- [x] Autonomous TDD agent with Gherkin-driven development
- [x] Semantic learning from failures (automatic pattern extraction)
- [x] Test redundancy detection
- [x] Automatic test correction
- [x] MLflow + ACE integration for ML experiments
- [x] Decision capture with provenance tracking
- [x] Pattern extraction across experiments
- [x] Unified query interface (MLflow + ACE)
- [x] Gherkin extraction from existing code (reverse engineering)
- [x] Cross-language migration support (Python → Go)
- [x] Go step definition generation
- [x] Working demos (ML, TDD, and extraction)

### Phase 1: Production Readiness (Current)
- [ ] Unit tests for all core components
- [ ] Integration tests for TDD agent
- [ ] Performance testing (large playbooks, many experiments)
- [ ] Error handling and recovery
- [ ] Logging and observability improvements

### Phase 2: Enhanced Learning
- [ ] Automatic pattern extraction from ML experiments (analyze runs → suggest patterns)
- [ ] Semantic search using embeddings (vector similarity for decisions/patterns)
- [ ] Cross-domain pattern transfer (suggest CV patterns for NLP tasks)
- [ ] Pattern effectiveness tracking over time

### Phase 3: Developer Experience
- [ ] Jupyter extension for inline decision capture
- [ ] VSCode extension for TDD agent integration
- [ ] Web UI for browsing knowledge base
- [ ] CLI for knowledge queries (`ace query "learning rate warmup"`)
- [ ] Pattern recommendation system

### Phase 4: Enterprise Features
- [ ] Multi-user support with RBAC
- [ ] Team knowledge sharing (opt-in cross-organization learning)
- [ ] API for integration with other tools
- [ ] Compliance features (GDPR, audit logs)
- [ ] Pattern marketplace (curated, domain-specific libraries)

## Configuration

### LLM Providers

**Recommended (Open Source License):**
```bash
# TogetherAI with Qwen (Apache 2.0)
PROVIDER=togetherai
TOGETHERAI_API_KEY=your_key
MODEL=Qwen/Qwen2.5-Coder-32B-Instruct

# DeepSeek (MIT License)
MODEL=deepseek-ai/DeepSeek-V2.5
```

**Also supported:**
- Anthropic Claude (commercial)
- OpenAI GPT (commercial)
- Local Ollama (any model)

### Storage

**Default:** `~/.ace/`
```
~/.ace/
  knowledge/
    playbooks/
      global.json              # Generic patterns
      healthcare.json          # Domain-specific patterns
  ml_experiments/
    image_classification.json  # ML experiment knowledge
    nlp_sentiment.json
```

**Customizable:** Set `ACE_KNOWLEDGE_DIR` environment variable

## License Compliance

ACE supports both open-source and commercial LLM providers. For production use:

**Recommended for commercial projects:**
- Qwen 2.5 Coder (Apache 2.0)
- DeepSeek V2.5 (MIT)
- Llama 3.1 (permissive)

**Commercial providers require compliance:**
- OpenAI: Check ToS Section 2c (output usage restrictions)
- Anthropic: Review commercial license
- Google: Check Gemini terms

**Provenance tracking** enables audit of which models were used for each decision, supporting compliance requirements.

## Contributing

We welcome contributions! Key areas:

1. **Playbook patterns**: Share successful patterns from your domain
2. **Integration adapters**: Connect ACE to other tools (TensorBoard, Weights & Biases, etc.)
3. **Domain expertise**: Healthcare, fintech, robotics pattern libraries
4. **Documentation**: Improve guides and examples

See [USER_CONTRIBUTIONS.md](./USER_CONTRIBUTIONS.md) for examples of valuable contributions.

## Support

- **Documentation**: Check `/docs` for detailed guides
- **Issues**: Open GitHub issues for bugs or feature requests
- **Discussions**: Share patterns and use cases
- **Strategic Plan**: See [ACE_STRATEGIC_PLAN.md](./docs/ACE_STRATEGIC_PLAN.md) for vision

## Why "ACE Enterprise"?

**ACE** = Agentic Context Engineering (from Stanford/SambaNova research)

**Enterprise** = Focus on institutional knowledge that persists beyond individuals:
- Survives team turnover
- Compounds across projects
- Provides audit trails
- Scales organization-wide

We've evolved from the original ACE research paper to focus on **institutional memory infrastructure** - the artifacts (tests, decisions, patterns) that have lasting value regardless of AI capability.

---

**Status**: Active Development (v0.1)

**Built on research from:**
- ACE Framework (Stanford/SambaNova): arXiv:2510.04618v1
- Dynamic Cheatsheet (Stanford): arXiv:2504.07952v1

**Strategic Direction:**
From "self-improving AI" → "institutional knowledge infrastructure that produces valuable artifacts"
