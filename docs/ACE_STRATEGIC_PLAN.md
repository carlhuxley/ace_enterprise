# ACE Enterprise Strategic Plan
**Version:** 2.0 (Revised 2025-11-29)
**Status:** Active
**Previous Direction:** AI self-improvement system
**New Direction:** Institutional knowledge infrastructure

---

## Executive Summary

**Core Pivot:** ACE Enterprise has evolved from an AI self-improvement system (original ACE paper vision) to an **institutional knowledge infrastructure** that produces lasting value through quality artifacts and organizational memory.

**Key Insight:** The value isn't in making AI smarter at coding (LLMs improve on their own). The value is in:
- Quality artifacts (tests, docs, traceability)
- Institutional memory (decisions, rationale, lessons learned)
- Cross-project learning (patterns that work across domains)
- Compliance & audit trails
- Developer productivity (consistency, prevention of rework)

---

## Strategic Vision

### What We're Building

**NOT:** Training wheels for current LLMs (scaffolding that obsoletes)
**YES:** Development middleware that captures organizational knowledge (tool that compounds)

**Architecture:**
```
Developer's Real Project
    ↓
┌──────────────────────────────────────────┐
│  ACE Enterprise (Development Middleware) │
│                                          │
│  Centralized Knowledge Base:             │
│    ~/.ace/knowledge/                     │
│      playbooks/                          │
│        global.json      ← Generic        │
│        healthcare.json  ← Domain         │
│        fintech.json     ← Domain         │
│                                          │
│  Each Bullet Has:                        │
│    - Provenance (human + AI)             │
│    - Projects (cross-project refs)       │
│    - Usefulness (quality signals)        │
│    - Domain tags                         │
│                                          │
│  Project Integration:                    │
│    project/.ace/                         │
│      config.yml    ← References central  │
│      decisions/    ← Local ADRs          │
│                                          │
└──────────────────────────────────────────┘
    ↓
LLM (Qwen, Claude, etc.)
    ↓
Real Code + Tests + Decisions
(Version controlled, CI/CD integrated)
```

### Value Proposition

**For Developers:**
- Faster feature development (Gherkin → Tests → Implementation)
- Consistency enforcement (organizational patterns automatically applied)
- Knowledge at fingertips (don't re-solve problems)
- Reduced cognitive load (remember why decisions were made)

**For Organizations:**
- Institutional memory (decisions don't leave when people do)
- Cross-project learning (patterns proven across teams)
- Compliance documentation (audit trail built-in)
- Quality assurance (comprehensive tests, traceable requirements)
- Onboarding acceleration (new developers learn from playbooks)

**For Teams:**
- Shared knowledge base (everyone benefits from everyone's learnings)
- Domain expertise accumulation (healthcare patterns, fintech patterns)
- Decision transparency (why things were built this way)
- Reduced rework (avoid repeating past mistakes)

---

## Architectural Principles

### 1. Centralized Knowledge with Project Context

**Principle:** All knowledge stored centrally, tagged with project references.

**Why:** Enables cross-project learning while maintaining traceability.

**Implementation:**
```json
// Central knowledge base
{
  "bullet_id": "ctx-00589",
  "content": "RBAC: Use AND logic when security > convenience",
  "rationale": "More restrictive = more secure by default",

  "provenance": {
    "created_by": {
      "human": "developer@company.com",
      "ai_models": [
        {"provider": "togetherai", "model": "Qwen", "license": "Apache-2.0"}
      ],
      "ensemble": {"votes": {...}, "consensus": 1.0},
      "conversation_id": "conv_abc123"
    },
    "created_at": "2025-11-29T17:15:00Z"
  },

  "projects": [
    {
      "project_id": "healthcare_app_1",
      "learned_date": "2025-11-29",
      "context": "HIPAA compliance",
      "developer": "dev@company.com"
    },
    {
      "project_id": "banking_api",
      "learned_date": "2025-10-15",
      "context": "PCI-DSS compliance",
      "developer": "other@company.com"
    }
  ],

  "domain": "access_control",
  "tags": ["security", "rbac", "healthcare", "fintech"],

  "usefulness": {
    "score": 0.95,
    "times_applied": 12,
    "times_helpful": 11,
    "times_overridden": 1
  }
}
```

### 2. Hybrid Playbooks with Natural Selection

**Principle:** Support both generic patterns (scaffolding) and project-specific knowledge (tool). Let usage data determine what survives.

**Playbook Types:**

**Global Playbook** (Generic patterns - scaffolding):
- Common coding practices
- Generic anti-patterns
- TDD best practices
- **Fate:** Usage decreases as LLMs improve (natural obsolescence)

**Domain Playbooks** (Domain-specific - tool):
- Healthcare: HIPAA requirements, PHI logging patterns
- Fintech: PCI-DSS compliance, transaction patterns
- **Fate:** Value persists (domain knowledge doesn't change with AI improvement)

**Natural Selection Mechanism:**
```python
# Usage tracking over time
Year 1 (GPT-4):  Global patterns used 80% → Still helpful
Year 2 (GPT-5):  Global patterns used 40% → Less helpful
Year 3 (GPT-6):  Global patterns used 10% → Mostly obsolete

# Domain patterns remain valuable
Year 1-3: Domain patterns used 100% → Always needed
```

### 3. Full Provenance Tracking

**Principle:** Every piece of knowledge tracks who (human + AI) created it, when, why, and where.

**Required Provenance:**
- Human contributor (email, role)
- AI models involved (provider, model, license)
- Ensemble voting (if applicable)
- Creation timestamp
- Context (phase, cycle, feature)
- Conversation link (full discussion)
- Projects that learned/applied it
- Usefulness metrics

**Benefits:**
- Auditability (who decided what)
- Licensing compliance (track proprietary model usage)
- Quality analysis (which models/humans produce best patterns)
- Credit attribution (recognize contributions)

### 4. Project Integration Flexibility

**Principle:** Projects can reference central knowledge (default) or maintain local customizations (optional).

**Default (Recommended):**
```
project/.ace/
  config.yml       ← References central playbooks
  decisions/       ← Local ADRs only
```

**Optional Enhancements:**
```
project/.ace/
  config.yml
  cache/           ← Local cache for offline work
    playbook.json
    last_sync: "2025-11-29T17:00:00Z"
  overrides.json   ← Project-specific customizations
  decisions/
```

---

## Implementation Roadmap

### Phase 1: Foundation (Current → Q1 2026)

**Goal:** Refactor from demo tool to development middleware

**Key Deliverables:**

1. **Centralized Knowledge Base**
   - Migrate existing `data/playbooks/` to `~/.ace/knowledge/`
   - Implement schema with full provenance
   - Add project tagging and cross-references
   - Status: ⏳ Not started

2. **Enhanced Provenance**
   - Track human contributors
   - Track AI models with licenses
   - Link to conversation history
   - Quality metrics (usefulness, helpfulness)
   - Status: ⏳ Not started

3. **Project Integration**
   - `.ace/config.yml` schema
   - Central knowledge query system
   - Local decision records (ADRs)
   - Status: ⏳ Not started

4. **Real Project Workflow**
   - CLI: `ace build-feature gherkin/feature.feature`
   - Generate in actual project (not /tmp)
   - Git integration
   - Status: ⏳ Not started

**Success Criteria:**
- ✅ Single project using ACE in real workflow
- ✅ Knowledge stored centrally with provenance
- ✅ Cross-session learning working
- ✅ Decision records linked to implementation

### Phase 2: Cross-Project Learning (Q1-Q2 2026)

**Goal:** Demonstrate value across multiple projects

**Key Deliverables:**

1. **Domain Playbooks**
   - Healthcare playbook (HIPAA patterns)
   - Fintech playbook (PCI-DSS patterns)
   - Automatic domain detection
   - Status: ⏳ Not started

2. **Quality Signals**
   - Usefulness scoring across projects
   - Pattern effectiveness tracking
   - Automatic pattern promotion/demotion
   - Status: ⏳ Not started

3. **Knowledge Deduplication**
   - Detect duplicate patterns
   - Merge similar learnings
   - Suggest generalizations
   - Status: ⏳ Not started

4. **Developer Dashboard**
   - View knowledge contributions
   - Query patterns by domain/project
   - Analyze model effectiveness
   - Track licensing compliance
   - Status: ⏳ Not started

**Success Criteria:**
- ✅ 3+ projects using ACE
- ✅ Cross-project patterns identified
- ✅ Domain expertise accumulating
- ✅ Measurable quality improvement

### Phase 3: Institutional Memory (Q2-Q3 2026)

**Goal:** Become organizational knowledge platform

**Key Deliverables:**

1. **Collaborative Decision Capture**
   - Human-AI discussion logging
   - Automatic ADR generation
   - Decision rationale extraction
   - Status: ⏳ Not started

2. **Knowledge Retrieval**
   - Semantic search across knowledge base
   - Context-aware pattern suggestions
   - Similar decision finder
   - Status: ⏳ Not started

3. **Compliance & Audit**
   - Generate audit reports
   - License compliance verification
   - Decision trail visualization
   - Status: ⏳ Not started

4. **Team Onboarding**
   - Project knowledge overview
   - Domain pattern training
   - Decision history exploration
   - Status: ⏳ Not started

**Success Criteria:**
- ✅ 10+ projects using ACE
- ✅ New developers onboard faster
- ✅ Compliance audits pass with ACE docs
- ✅ Knowledge compounds visibly

### Phase 4: Ecosystem (Q3 2026+)

**Goal:** IDE integration, multi-organization support

**Key Deliverables:**

1. **IDE Plugins**
   - VSCode extension
   - JetBrains plugin
   - Status: ⏳ Not started

2. **Multi-Organization**
   - Organization-level knowledge bases
   - Cross-org pattern sharing (opt-in)
   - Private domain playbooks
   - Status: ⏳ Not started

3. **API & Integrations**
   - REST API for knowledge base
   - CI/CD integrations
   - Slack/Teams notifications
   - Status: ⏳ Not started

---

## Success Metrics

### Developer Productivity
- Time to implement feature (Gherkin → Tests → Code)
- Rework rate (how often do we revisit decisions)
- Onboarding time (new developer to productive)

### Knowledge Quality
- Pattern usefulness score (helpful / applied)
- Cross-project adoption (pattern used in N projects)
- Decision clarity (rationale documented)

### Organizational Value
- Compliance audit time (reduced with automatic docs)
- Knowledge retention (decisions don't leave with people)
- Domain expertise accumulation (patterns per domain)

### Technical Quality
- Test coverage (comprehensive from Gherkin)
- Requirement traceability (Gherkin → Tests → Code)
- Decision auditability (full provenance)

---

## Risk Mitigation

### Risk: Generic playbooks become obsolete with better LLMs
**Mitigation:** Hybrid approach. Let natural selection determine what survives. Focus on domain-specific knowledge that persists.

### Risk: Knowledge base becomes too large/noisy
**Mitigation:**
- Quality scoring (promote helpful, demote unhelpful)
- Deduplication (merge similar patterns)
- Archival (move unused patterns to archive)

### Risk: Licensing contamination from proprietary models
**Mitigation:**
- Full provenance tracking (know which model created what)
- License compliance reporting
- Migration path to open-source models

### Risk: Adoption friction (developers don't use ACE)
**Mitigation:**
- Start with high-value use cases (Gherkin-driven features)
- Demonstrate ROI (faster development, better docs)
- Make it optional (reference central knowledge by default)
- Progressive enhancement (works better as you use it more)

---

## Competitive Differentiation

### vs. GitHub Copilot / Cursor
**Copilot/Cursor:** Code completion, chat-based coding
**ACE:** Institutional knowledge, decision capture, cross-project learning, compliance docs

### vs. Traditional Documentation
**Docs:** Static, manually maintained, often outdated
**ACE:** Living knowledge, automatically captured, usage-validated, provenance-tracked

### vs. ADR Tools
**ADR Tools:** Manual decision recording
**ACE:** Automatic decision capture from development conversation, linked to implementation

### Unique Value
ACE is the only system that:
1. Captures knowledge **during** development (not after)
2. Links decisions to **actual code** (not separate docs)
3. Provides **cross-project learning** (patterns improve across teams)
4. Tracks **full provenance** (human + AI + conversation)
5. Integrates **workflow** (not bolt-on documentation)

---

## Open Questions

1. **Knowledge sharing model:** Should organizations share domain playbooks? Privacy concerns?
2. **Pricing model:** Per-developer? Per-organization? Per-project?
3. **Integration strategy:** Build IDE plugins ourselves or partner?
4. **AI model strategy:** Support all providers or focus on open-source?
5. **Community:** Open-source core vs. commercial features?

---

## Appendix: Terminology

**Playbook:** Collection of learned patterns and decisions
**Bullet:** Single piece of knowledge (pattern, decision, learning)
**Provenance:** Full history of who/what/when/why for knowledge
**Domain Playbook:** Knowledge specific to industry/domain
**ADR:** Architectural Decision Record (rationale for decisions)
**Institutional Memory:** Organization's collective knowledge
**Natural Selection:** Usage-driven determination of valuable patterns

---

**Last Updated:** 2025-11-29
**Next Review:** Q1 2026
**Owned By:** Core team + user contributions
