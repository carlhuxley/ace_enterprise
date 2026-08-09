# ACE Enterprise

**Double-Blind Agentic Coding Capability Broker with Clean-Room OSS Synthesis**

---

## Clean-Room TypeScript Synthesis

ACE can take a private Python codebase and synthesise a legally independent TypeScript public repo — with a tamper-evident audit trail proving no private code crossed the boundary.

This is not a transpiler. It is a full TDD-driven clean-room process:

```
Private Python src/
        │
        ▼  Stage 1 — Gherkin Extraction
           LLM reads private source and writes pure behavioural specs.
           No implementation detail, no private names.
        │
        ▼  Stage 2+3 — TDD Synthesis + Clean-Room Gate
           Each spec drives a red→green→refactor cycle inside a sandboxed
           Vitest container. The synthesised TypeScript is written from the
           behavioural description only — the container never sees the source.
           AST gate blocks any file where a private identifier leaked through.
        │
        ▼  Stage 2.5 — Contract Interface Synthesis
           IO-wiring modules (subprocess adapters, HTTP servers, schema DTOs)
           can't green a unit test in a sandbox. A .contract.yml spec describes
           the TypeScript interface; a single LLM call synthesises it directly.
           Same clean-room and style gates apply.
        │
        ▼  Stage 4 — Stamp
           Apache-2.0 SPDX headers applied to every file.
        │
        ▼  Stage 5 — Commit
           Public OSS repo committed. Every step is on the audit chain.
```

**The audit chain** records every stage event — `GHERKIN_EMIT`, `CLEAN_ROOM_PASS`, `CONTRACT_SYNTH_PASS`, `STYLE_BLOCK`, `GIT_COMMIT` — as a SHA-256 hash chain. Each record's hash is computed from the previous hash plus the event payload. An independent auditor can replay `bootstrap/audit.jsonl` and verify the chain was never altered. The file is published into the OSS repo on every run.

**The gates are layered:**

| Gate | What it checks | On failure |
|---|---|---|
| Clean-room AST | No private identifier in synthesised TypeScript | File deleted, `CLEAN_ROOM_FAIL` on chain |
| TypeScript style | camelCase, no `any`, no Python error names, no bitwise hashes, no stub IDs | File deleted, `STYLE_BLOCK` on chain |
| Contract interface | IO modules: spec drives LLM directly, same gates after | `CONTRACT_SYNTH_FAIL` on chain |
| Apache-2.0 stamp | SPDX header present on every `.ts` file | Stamped before commit |

**Current state:** 105 modules synthesised, 63 passing all gates. The 4 remaining IO-wiring modules (`claude_cli_client`, `collector`, `contract_decomposer`, `contract_schema`) are being synthesised via the contract path added in the latest release.

### Run it

```bash
# Full synthesis run (resumes from where it left off)
.venv/bin/python bootstrap/orchestrate.py --lang typescript

# Single module
.venv/bin/python bootstrap/orchestrate.py --lang typescript --file src/agents/worker_agent.py

# Force re-synthesis of everything
.venv/bin/python bootstrap/orchestrate.py --lang typescript --force
```

---

## The Broker

ACE brokers a pool of AI agents (Claude, Llama, Qwen, Mistral) and humans to build software. The capability broker sees capabilities, not identities. Evaluation is blind. Humans see everything via audit and make final decisions.

```
┌─────────────────────────────────────────────────────────────────┐
│                CAPABILITY BROKER (Product Manager)              │
│                                                                 │
│   Sees:                           Doesn't see:                  │
│   • Capability tags               • Agent identity              │
│   • Bayesian success rate         • Cost per agent              │
│   • Task requirements             • Business priorities         │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
  ┌───────────┐      ┌───────────────┐    ┌───────────┐
  │ Agent     │      │ Agent         │    │ Agent     │
  │ (anon)    │      │ (anon)        │    │ (anon)    │
  └───────────┘      └───────────────┘    └───────────┘
                            │
                            ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                    BLIND EVALUATION                          │
  │   Domain rubrics: code, tests, analysis, documentation       │
  │   No knowledge of which agent produced each submission       │
  └─────────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌─────────────────────────────────────────────────────────────┐
  │               AUDIT (Hash-chained, tamper-evident)           │
  │   Full visibility for humans only. Every decision on chain.  │
  └─────────────────────────────────────────────────────────────┘
```

**Why double-blind?** No bias toward big-name models. A cheap open-source model's output is accepted if it scores well; an expensive model's output is rejected if it scores poorly. Pure meritocracy.

---

## What's Built

### Adaptive Capability Broker

- **AdaptiveBroker** — Routes tasks by budget, balanced, or Pareto strategies with latency caps
- **BayesianEstimate** — Beta-Binomial posterior over success rates; statistically robust estimates from small sample sizes
- **CapabilityRegistry** — Anonymous agent registration with proficiency ratings
- **CostQualityAnalyzer** — Pareto frontier analysis; suggests best model for a given complexity level
- **DistillationRouter** — Routes to cheaper models when quality delta is within tolerance

### Blind Evaluation

- **BlindEvaluator** — Rubric-based scoring: `CodeGenerationRubric`, `TestWritingRubric`, `AnalysisRubric`, `DocumentationRubric`
- **ConsensusBuilder** — Aggregates votes across multiple evaluators
- **EnsembleLearner** — Distils consensus patterns into Playbook bullets

### Autonomous TDD Agent (ACE Pipeline)

```
Gherkin → RED → GREEN → REFACTOR
       → Reflector analyses failures
       → Curator writes delta bullets to Playbook
       → Next cycle benefits from what was learned
```

- **AutonomousTDDAgent** — Plans incremental tests via Ensemble, runs TDD cycles, promotes session wins to Playbook
- **IterativeTDDRunner** — Up to N cycles with per-scenario GREEN retries; every cycle on the audit chain
- **IncrementalPlanner** — Plans next test from existing coverage and playbook guidance
- **WorkerAgent / TypeScriptWorkerAgent** — LLM-backed code generators with playbook-guided prompts

### Contract-Driven Development

- **ContractArchitect** — Decomposes natural language requirements into typed `ContractSpec` objects with test cases
- **ContractDecomposer** — Breaks specs into discrete function contracts (id, signature, test cases, complexity, hints)
- **ContractOrchestrator** — Registers contracts, supplies implementation prompts, validates submissions
- **ContractValidator** — Runs contract test cases against submitted code

### Institutional Knowledge — CGR³ + Playbook

Context-aware retrieval that understands *where* and *when* a pattern applies:

```
Query → Retrieve (semantic search)
      → Rank (temporal validity, team locality, tech stack, project, domain)
      → Reason → Verdict: APPLY / ASK_FIRST / SKIP
```

- **CGR³** — Full Retrieve-Rank-Reason pipeline
- **PlaybookManager** — CRUD with file and PostgreSQL backends
- **BulletClusterer** — DBSCAN clustering to surface representative patterns and prune redundancy
- **BulletDeduplicator** — Cosine-similarity dedup with configurable thresholds
- **PlaybookReliabilityAnalyzer** — Tracks first-pass GREEN success rate per bullet

### Audit System

- **AuditStore** — Append-only PostgreSQL store with hash-chain verification
- **AuditDashboard** — Agent performance, cost analysis, task-type strengths, optimal team suggestions
- **ModelAttributionTracker** — Daily performance metrics per model family
- **Audit Collector** — Write-only HTTP endpoint (POST /events); agents can append, never query

### MCP Server (Claude Code Integration)

```json
{
  "mcpServers": {
    "ace": {
      "command": "python",
      "args": ["-m", "mcp_server", "--playbook-file", "playbook.json"]
    }
  }
}
```

Tools: `get_guidance` (CGR³ verdict), `learn` (add bullet), `query` (semantic search), `feedback`, `build_feature`.

### ClaudeCliClient — No API Key Required

Drop-in `LLMClient` replacement using the local `claude --print` CLI. No API keys, no billing — uses the active Claude Code session. Strips `CLAUDE*` env vars before subprocess invocation to prevent nested-session detection.

---

## Configuration

```bash
# LLM via OpenRouter
DEFAULT_LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_DEFAULT_MODEL=anthropic/claude-sonnet-4-5

# Storage
DATABASE_URL=postgresql://user:pass@localhost/ace
AUDIT_DATABASE_URL=postgresql://audit:pass@localhost/ace_audit
```

Bootstrap model slots (`MODEL_PASS1`, `MODEL_PASS2`, `MODEL_EXTRACT`) are set in `bootstrap/orchestrate.py`. Currently all three use `anthropic/claude-sonnet-4-5` via OpenRouter.

Free models for development: `qwen/qwen3-coder:free`, `qwen/qwen3-14b:free`, `google/gemma-3-27b-it:free`

---

## Project Structure

```
ace_enterprise/
├── src/
│   ├── agents/          # TDD agents, language pods, runners
│   ├── broker/          # AdaptiveBroker, CapabilityRegistry, ModuleArchitect
│   ├── analytics/       # CostQualityAnalyzer, DistillationRouter, attribution
│   ├── audit/           # AuditStore, collector, dashboard
│   ├── benchmark/       # BlindEvaluator, ConsensusBuilder
│   ├── contracts/       # ContractArchitect, Decomposer, Orchestrator, Validator
│   ├── retrieval/       # CGR³, ContextScorer, InstitutionalKnowledgeService
│   ├── playbook/        # PlaybookManager, BulletClusterer, ReliabilityAnalyzer
│   └── storage/         # PostgreSQL + pgvector
├── bootstrap/           # Clean-room TypeScript synthesis pipeline
│   ├── orchestrate.py       # pipeline entry point (Stages 1–5)
│   ├── extract.py           # Stage 1: Gherkin extraction
│   ├── clean_room.py        # Stage 3: AST clean-room + style gates
│   ├── stamp.py             # Stage 4: Apache-2.0 stamping
│   ├── audit_log.py         # tamper-evident SHA-256 hash chain
│   ├── audit.jsonl          # chain record (published into OSS repo)
│   └── features/
│       ├── *.feature        # Gherkin specs (Stages 1→2)
│       └── *.contract.yml   # Contract specs (Stage 2.5, IO modules)
├── mcp_server/          # MCP protocol server
└── docs/
    ├── SYSTEM_ARCHITECTURE.md  # auto-generated — do not edit
    └── adr/                    # ADR-001 through ADR-014
```

---

## Roadmap

### Shipped
- [x] Clean-room TypeScript OSS synthesis pipeline (Stages 1–5)
- [x] Contract interface synthesis path (Stage 2.5 — IO/wiring modules)
- [x] Tamper-evident audit chain published into OSS repo
- [x] AdaptiveBroker with Bayesian success-rate estimation
- [x] BlindEvaluator with four domain rubrics
- [x] CGR³ retrieval with 5-dimension context scoring
- [x] Playbook with DBSCAN clustering, semantic dedup, bullet lineage
- [x] Autonomous TDD agent with ACE Pipeline learning loop
- [x] Contract-driven development (Architect → Decomposer → Orchestrator)
- [x] CostQualityAnalyzer with Pareto frontier
- [x] DistillationRouter
- [x] AuditDashboard — performance, costs, team formation suggestions
- [x] ClaudeCliClient (API-key-free LLM via local claude CLI)
- [x] MCP server with CGR³ tools
- [x] MLflow integration (ACEMLflowCallback)

### Planned
- [ ] effGen MCP adapter (connect open-source models as broker agents)
- [ ] Web UI for knowledge browsing and team formation
- [ ] Multi-organisation knowledge sharing with provenance
- [ ] IDE plugins (VSCode, JetBrains)

---

## Why ACE?

**ACE** = Agentic Context Engineering (Stanford/SambaNova, arXiv:2510.04618)

The system operates on merit and rules, not trust or identity. Historical performance is the only signal the broker acts on. Humans see the full picture via the audit trail and make final decisions.

**Research basis:**
- ACE Framework: arXiv:2510.04618v1
- Dynamic Cheatsheet: arXiv:2504.07952v1

---

*Architecture docs auto-generated at [`docs/SYSTEM_ARCHITECTURE.md`](docs/SYSTEM_ARCHITECTURE.md) — regenerate with `.venv/bin/python generate_live_docs.py`*
