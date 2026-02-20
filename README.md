# ACE Enterprise

**Double-Blind Agentic Coding Capability Broker**

ACE brokers a pool of AI agents (Claude, Llama, Qwen, Mistral) and humans to build software. The capability broker sees capabilities, not identities. Evaluation is blind. Humans see everything via audit and make final decisions.

## The Vision

```
┌─────────────────────────────────────────────────────────────────┐
│                    CAPABILITY BROKER (Product Manager)                │
│                                                                 │
│   Sees:                           Doesn't see:                  │
│   • Capability tags               • Agent identity              │
│   • Success rate by capability    • Cost per agent              │
│   • Task requirements             • Business priorities         │
│                                                                 │
│   "Capability python+testing has 93% success rate, 3 agents"    │
│                                                                 │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
  ┌───────────┐      ┌───────────────┐    ┌───────────┐
  │ Agent     │      │ Agent         │    │ Agent     │
  │ (anon)    │      │ (anon)        │    │ (anon)    │
  │           │      │               │    │           │
  │ caps:     │      │ caps:         │    │ caps:     │
  │ py,test   │      │ py,go         │    │ review    │
  └───────────┘      └───────────────┘    └───────────┘
        │                   │                   │
        └───────────────────┴───────────────────┘
                            │
                            ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                    BLIND EVALUATION                          │
  │                                                              │
  │   • Tests pass/fail                                          │
  │   • Code quality score                                       │
  │   • Pattern adherence                                        │
  │   • No knowledge of which agent produced output              │
  │                                                              │
  └─────────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                    AUDIT (Hash-chained)                      │
  │                                                              │
  │   • Full visibility for humans only                          │
  │   • Links submissions to real agent IDs                      │
  │   • Costs, performance history, business context             │
  │   • Tamper-evident (blockchain-inspired)                     │
  │   • Human reviews and makes final decisions                  │
  │                                                              │
  └─────────────────────────────────────────────────────────────┘
```

**Why double-blind?**
- No bias toward "big name" models
- Evaluation purely on output quality
- Cheap open-source model's pattern accepted if it scores well
- Expensive proprietary model's pattern rejected if it scores poorly
- Pure meritocracy

## Core Principles

1. **Capability Broker sees capabilities, not identities** - Routes by skill match, not agent preference
2. **Evaluation is blind** - Scores output quality without knowing source
3. **Humans see everything via audit** - Make informed business decisions
4. **Playbook accepts quality patterns anonymously** - Source irrelevant, quality matters
5. **Teams emerge from data** - Audit reveals winning combinations, humans spin off as effGen teams

## What's Built

### MCP Server (Claude Code Integration)

ACE exposes institutional knowledge to Claude Code via MCP protocol:

```json
// .mcp.json
{
  "mcpServers": {
    "ace": {
      "command": "python",
      "args": ["-m", "mcp_server", "--playbook-file", "playbook.json"]
    }
  }
}
```

**Tools available:**
- `get_guidance` - Query patterns with context-aware verdicts (APPLY, ASK_FIRST, SKIP)
- `learn` - Add knowledge to playbook
- `query` - Semantic search
- `feedback` - Mark patterns helpful/harmful
- `build_feature` - TDD cycle with learning

### CGR³ Retrieval (Context Graph Retrieve-Rank-Reason)

Smart pattern retrieval that understands context:

1. **Retrieve** - Semantic search for candidate patterns
2. **Rank** - Score by context match (team, project, tech stack, temporal validity)
3. **Reason** - Determine verdict:
   - `APPLY` - High confidence, use this pattern
   - `ASK_FIRST` - Medium confidence, confirm with human
   - `SKIP` - Low relevance or outdated

### Audit System (Hash-Chained)

Blockchain-inspired audit trail:

```python
# Append-only, tamper-evident
class AuditStore:
    def append(self, event: AuditEvent) -> AuditEvent:
        # Each event includes prev_hash → event_hash
        # No UPDATE, no DELETE
        # Chain verification detects tampering
```

- Agents can write events, cannot read or modify
- Humans query for full visibility
- Supports compliance and business decisions

### Playbook System

Structured knowledge with provenance:

```json
{
  "sections": {
    "strategies_and_hard_rules": [...],
    "code_snippets": [...],
    "troubleshooting": [...],
    "domain_knowledge": [...]
  }
}
```

Each pattern tracks:
- Who created it (human or AI)
- When and why
- Success rate when applied
- Projects that use it

### Autonomous TDD Agent

Gherkin-driven development with learning:

```
Gherkin scenario → Generate test → Implement code
    → Test fails → Analyze WHY → Store pattern → Retry
    → Future cycles avoid same mistake
```

Features:
- Test redundancy detection (avoid duplicate tests)
- Automatic test correction
- High-frequency feedback enforcement
- Full traceability: Gherkin → tests → implementation → decisions

### Playbook Enforcer

Enforces high-frequency feedback rules:

```python
enforcer = PlaybookEnforcer()
result = enforcer.check_can_edit("src/foo.py")

if not result.allowed:
    print(f"Blocked: {result.reason}")
    # "Untested edit: src/bar.py - run tests first (ace-006)"
```

Tracks edit:test ratio, blocks edits without tests.

## Agent Integration

### effGen (Small Language Models)

Use [effGen](https://github.com/ctrl-gaurav/effGen) to wrap small/open models as ACE agents:

```
┌─────────────────────────────────────────────────────────────────┐
│                    ACE Capability Broker (Blind)                      │
│                                                                 │
└───────────────────────────┬─────────────────────────────────────┘
                            │
    ┌───────────┬───────────┼───────────┬───────────┐
    ▼           ▼           ▼           ▼           ▼
┌───────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────┐
│Claude │ │ effGen  │ │ effGen  │ │ effGen  │ │ Human │
│       │ │ +Qwen   │ │ +Llama  │ │ +Mistral│ │       │
└───────┘ └─────────┘ └─────────┘ └─────────┘ └───────┘
```

**Option B (preferred):** Each model as own effGen instance
- Full isolation
- Independent capability declarations
- Per-model audit tracking

**Emergent team formation:**
1. Audit data accumulates
2. Humans spot winning combinations ("A+C: 94% on tests")
3. Spin off as multi-agent effGen instance
4. ACE sees new capability provider, doesn't know it's a team

## Quick Start

### 1. MCP Integration (Claude Code)

```bash
# Install
pip install -e .

# Configure Claude Code
cat > .mcp.json << 'EOF'
{
  "mcpServers": {
    "ace": {
      "command": "python",
      "args": ["-m", "mcp_server", "--playbook-file", "playbook.json"]
    }
  }
}
EOF

# Claude Code now has access to ACE tools
```

### 2. CLI Usage

```bash
# Query playbook
ace query "how to handle database timeouts"

# Add knowledge
ace learn "Always use connection pooling for PostgreSQL" --type pattern --tags db,postgres

# Build feature with TDD
ace build-feature gherkin/my_feature.feature
```

### 3. TDD Agent Demo

```bash
# Run RBAC demo
python demo_rbac_tdd.py
```

## Project Structure

```
ace_enterprise/
├── src/
│   ├── agents/                    # Autonomous agents
│   │   ├── autonomous_tdd_agent.py  # TDD with learning
│   │   ├── redundancy_checker.py    # Test deduplication
│   │   └── gherkin_extraction_agent.py
│   ├── audit/                     # Hash-chained audit system
│   │   ├── store.py                 # Append-only storage
│   │   ├── client.py                # Write-only client for agents
│   │   └── api.py                   # Read-only API for humans
│   ├── retrieval/                 # CGR³ system
│   │   ├── cgr3_retriever.py        # Context-aware retrieval
│   │   ├── context_scorer.py        # Ranking by context
│   │   └── service.py               # Institutional knowledge service
│   ├── playbook/                  # Knowledge management
│   │   ├── manager.py               # CRUD operations
│   │   └── retrieval.py             # Semantic search
│   ├── utils/
│   │   ├── playbook_enforcer.py     # High-frequency feedback
│   │   └── session_log.py           # Edit/test tracking
│   └── storage/                   # PostgreSQL + pgvector
│
├── mcp_server/                    # MCP protocol server
│   └── tools.py                     # get_guidance, learn, query, etc.
│
├── playbook.json                  # Project playbook
├── .mcp.json                      # MCP configuration
└── tests/                         # Test suite
```

## Architecture

### Layers

| Layer | Sees | Purpose |
|-------|------|---------|
| **Capability Broker** | Capabilities, success rates | Recommend agents by fit |
| **Evaluation** | Output quality only | Score without bias |
| **Playbook** | Patterns, no attribution | Store quality knowledge |
| **Audit** | Everything | Human decision support |

### Data Flow

```
Task → Capability Broker (recommend by capability)
    → Human (decide with audit context)
    → Agent (execute blind)
    → Evaluation (score blind)
    → Playbook (store if quality)
    → Audit (record everything)
```

## Roadmap

### Built
- [x] MCP server with CGR³ retrieval
- [x] Hash-chained audit system
- [x] Playbook with provenance tracking
- [x] Autonomous TDD agent with learning
- [x] Playbook enforcer (high-frequency feedback)
- [x] Test redundancy detection
- [x] Gherkin extraction (reverse engineering)

### In Progress
- [ ] Tests for core modules (autonomous_tdd_agent, playbook_manager, ensemble)
- [ ] Session logging visibility

### Planned: Capability Broker Modules
- [ ] **Capability registry** - Anonymous agent registration
- [ ] **Blind evaluation service** - Score outputs without identity
- [ ] **Capability Broker advisor** - Recommend by capability fit
- [ ] **Human decision interface** - Accept/override recommendations
- [ ] **effGen MCP adapter** - Connect small models
- [ ] **Audit analysis dashboard** - Spot winning teams

### Future
- [ ] IDE plugins (VSCode, JetBrains)
- [ ] Web UI for knowledge browsing
- [ ] Multi-organization knowledge sharing
- [ ] Pattern marketplace

## Configuration

### Environment Variables

```bash
# LLM Provider (open-source recommended)
PROVIDER=togetherai
TOGETHERAI_API_KEY=your_key
MODEL=Qwen/Qwen2.5-Coder-32B-Instruct

# Storage
ACE_KNOWLEDGE_DIR=~/.ace
DATABASE_URL=postgresql://user:pass@localhost/ace

# Audit (separate database)
AUDIT_DATABASE_URL=postgresql://audit:pass@localhost/ace_audit
```

### Playbook Rules

Key rules in `playbook.json`:

- **ace-003**: Tests must pass before adding features
- **ace-006**: High-frequency feedback (test after every edit)
- **ace-007**: Track untested modules, prioritize adding tests

## Why "ACE"?

**ACE** = Agentic Context Engineering (Stanford/SambaNova research)

**Evolution:**
1. Original: AI self-improvement system
2. Pivot: Institutional knowledge infrastructure
3. Current: **Double-blind agentic coding capability broker**

The system operates on merit and rules, not trust or identity. Like blockchain philosophy without needing actual blockchain.

## License

Supports both open-source and commercial LLM providers. Provenance tracking enables audit of which models were used for each decision.

**Recommended for commercial projects:**
- Qwen 2.5 Coder (Apache 2.0)
- DeepSeek V2.5 (MIT)
- Llama 3.1 (permissive)

---

**Status**: Active Development

**Research basis:**
- ACE Framework (Stanford/SambaNova): arXiv:2510.04618v1
- Dynamic Cheatsheet (Stanford): arXiv:2504.07952v1
