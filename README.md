# ACE Enterprise

**Hardened Zero-Trust Execution Engine & Double-Blind Agentic Capability Broker**

ACE Enterprise is a production-grade framework for running, evaluating, and learning from autonomous AI coding agents. It treats generated code as untrusted input — executing all tasks inside rootless, air-gapped Podman container pods (`--network none`, `--cap-drop=all`) across Python, TypeScript, and Go.

Inspired by research in Agentic Context Engineering ([arXiv:2510.04618](https://arxiv.org/abs/2510.04618)), ACE continuously distills execution feedback into an institutional Playbook, allowing open-source and proprietary models to self-correct without retraining.

---

## Clean-Room Synthesis (`bootstrap/`)

An included demonstration workload built on top of ACE's core engine — the same `PodmanOrchestrator` and `TypeScriptRunner` that run the Python/TypeScript/Go pods below.

`bootstrap/` demonstrates how ACE's containerized sandbox, Gherkin specs, and AST clean-room gates can take a private Python codebase and synthesize an independent, Apache-2.0-stamped TypeScript repository — with a tamper-evident SHA-256 audit log proving no private source code crossed the execution boundary.

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

**Status:** The clean-room TypeScript pipeline is an included demonstration workload, used to validate AST-gated clean-room synthesis against this codebase. It's provided as an optional tool in `bootstrap/` and isn't required for core Python/TypeScript/Go execution.

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

**Status:** Both stages are now wired into live entry points, opt-in:

- **Routing** — `AdaptiveBroker` picks the model for a build. `ace tdd` reads a `candidate_models:` list from `.ace/config.yaml`; the MCP `build_feature` tool takes a `models` array. With 2+ candidates the broker ranks them on `CYCLE_COMPLETED` audit history for that language and routes the run (falling back to the first candidate with no history). The chosen model and verdict come back to the caller and land on the audit chain as a `ROUTING_DECISION` event. `PerformanceAggregator` drives it; `BrokerAdvisor` and `CapabilityRegistry` remain standalone. (A `--model openrouter/qwen/qwen3-coder` flag on `ace tdd` / `ace project` overrides both routing and the `.env` default for one run.)
- **Blind evaluation** — the MCP `build_feature_ensemble` tool builds a Python feature with 2+ candidate models, each in its own throwaway sandbox, then scores every implementation through `BlindEvaluator` under an opaque `submission_id` (the evaluator never sees which model wrote which), commits the winner, and reports a `ConsensusBuilder` convergence summary. Emits `BLIND_EVALUATION` (no attribution) and `ENSEMBLE_SELECTION` (winner revealed) audit events. `EnsembleLearner`'s cross-model voting is not yet on this path.

Still preview: cost / `quality_score` telemetry (no pricing table or automated quality instrument exists), so the broker's BUDGET/BALANCED/PARETO modes have no real data — only BEST_QUALITY and Bayesian success-rate routing are meaningful today. See [Roadmap](#roadmap).

---

## What's Built

### Adaptive Capability Broker

- **AdaptiveBroker** — Routes tasks by budget, balanced, or Pareto strategies with latency caps
- **BayesianEstimate** — Beta-Binomial posterior over success rates; statistically robust estimates from small sample sizes
- **CapabilityRegistry** — Anonymous agent registration with proficiency ratings
- **CostQualityAnalyzer** (`src/analytics/`) — Pareto frontier analysis; suggests best model for a given complexity level
- **DistillationRouter** (`src/playbook/`) — Routes to cheaper models when quality delta is within tolerance

`AdaptiveBroker` + `BayesianEstimate` route live builds when 2+ candidate models are configured (`ace tdd` via `.ace/config.yaml`'s `candidate_models:`, MCP `build_feature` via `models`); see the Status note under [The Broker](#the-broker). `CapabilityRegistry` and `BrokerAdvisor` are implemented and unit-tested but not yet on a live path.

### Blind Evaluation

- **BlindEvaluator** — Rubric-based scoring: `CodeGenerationRubric`, `TestWritingRubric`, `AnalysisRubric`, `DocumentationRubric`
- **ConsensusBuilder** — Aggregates votes across multiple evaluators
- **EnsembleLearner** — Distils consensus patterns into Playbook bullets

`BlindEvaluator` + `ConsensusBuilder` run live via the MCP `build_feature_ensemble` tool (multi-candidate Python builds); see the Status note under [The Broker](#the-broker). `EnsembleLearner`'s cross-model voting is not yet on that path. Scoring a submission's tests always runs inside the same rootless Podman sandbox as the TDD engine (`--network none`, `--cap-drop=all`) — submission code is untrusted input by design and is never executed on the host.

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

### Polyglot Container Harness

- **Native language pods** (`src/agents/`) — `PythonLanguagePod`, `TypeScriptLanguagePod`, `GoLanguagePod` run RED/GREEN/REFACTOR cycles inside isolated Podman containers: `--network none`, `--cap-drop=all`, `--security-opt no-new-privileges`, read-only workspace mounts, and canonical-hash tamper detection on every phase result
- **Security gates per language** — Bandit (Python), eslint-plugin-security (TypeScript), gosec (Go); any HIGH-severity finding blocks the commit before it reaches disk

### LanguagePod Is a Domain-Extension Point, Not Just a Language One

`LanguagePod` (`src/agents/language_pod.py`) is named after what's been built against it, not what it requires. It's a `Protocol` with four methods (`run_red`, `run_green`, `run_refactor`, `token_usage`), each returning a `PhaseResult(passed: bool, output: str, error: str | None, formatted_files)` — nothing in that interface mentions test frameworks, source code, or any particular verification tool, just "did this phase pass, what was the output." Its input, `PodSpec`, is equally untyped-to-domain: `feature_requirement: str`, `test_file: Path`, `implementation_file: Path`, `cycle_number: int` — two paths, a requirement string, and an integer. Nothing there requires the paths to point at source code.

Critically, `TDDCycleRunner` — the orchestrator that drives the whole RED→GREEN→REFACTOR loop — never branches on language or domain itself. Its entire interaction with a pod is `self._pod.run_red(spec)` / `run_green(spec)` / `run_refactor(spec)` / `token_usage()`; all domain-specific behavior lives inside the pod, not the runner. And downstream, `TDDCycleRunner._learn()` builds the Reflector's input (`EnvironmentFeedback`) from `result.green_result.output` / `.error` — it never inspects what produced them. `PythonLanguagePod`, `TypeScriptLanguagePod`, and `GoLanguagePod` are three independent implementations proving the abstraction holds across pytest, vitest, and `go test` — but nothing about the protocol, the spec, or the runner is specific to running code at all. A pod whose `run_green()` validates a data pipeline against a schema, or checks a config file against a security policy, and returns an honest `PhaseResult`, would be a fully valid `LanguagePod` today, with no changes anywhere in the Reflector → Curator → Playbook loop.

**This is an architecturally proven extension point, not a shipped capability.** Three pods exist and all three wrap code-verification test runners; no non-code pod (data-contract validation, config/policy checking, or otherwise) has actually been built — these are illustrations of what the interface permits, not features. The verifiable claim is narrow: `PodSpec`'s types, `PhaseResult`'s shape, and `TDDCycleRunner`'s dispatch impose no domain constraint. Writing a genuinely new pod is real, unstarted work — the same effort `GoLanguagePod` itself required — not a config flag.

**Extending it:** a new pod just needs to implement the four `LanguagePod` methods. But `LanguagePod` being a `Protocol` means conformance is structural, not enforced — satisfying the method signatures is all Python checks; nothing requires a new pod to actually use the sandbox. The zero-trust guarantees (`--network none`, `--cap-drop=all`, `--security-opt no-new-privileges`, read-only mounts) aren't inherited automatically — they hold because `PythonLanguagePod`, `TypeScriptLanguagePod`, and `GoLanguagePod` each independently take a `PodmanOrchestrator` in their constructor and route execution through it. A new pod has to deliberately follow that same pattern to keep the same guarantees; nothing stops one from skipping it.

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

`CGR³`, `PlaybookManager`, `BulletClusterer`, and `BulletDeduplicator` are all wired into live entry points (`mcp_server/`, `benchmarks/runner.py`, `bootstrap/orchestrate.py`).

**PlaybookReliabilityAnalyzer** (`src/reliability/`) — Tracks first-pass GREEN success rate per bullet. Implemented and unit-tested, but — like the Broker and Blind Evaluation subsystems above — has no call sites outside its own module and tests; not yet wired into a live entry point.

### Audit System

- **AuditStore** — Append-only PostgreSQL store with hash-chain verification
- **AuditDashboard** — Agent performance, cost analysis, task-type strengths, optimal team suggestions
- **ModelAttributionTracker** — Daily performance metrics per model family
- **Audit Collector** — Write-only HTTP endpoint (POST /events); agents can append, never query
- **Audit Query API** (`src/audit/api.py`) — Separate read-only service (GET only) for compliance officers, administrators, and debugging tools; runs independently from the collector with no write capability
- **Audit Checkpoint** (`src/audit/checkpoint.py`) — External anchoring for the hash chain: periodically commits the latest event's id/hash to a git-tracked JSONL file, so a compromised DB credential can't silently rewrite the chain and still pass `verify_full_chain()`

### MCP Server (Claude Code Integration)

Local development only — the server communicates over stdio, spawned as a subprocess by your MCP client (Claude Code, Claude Desktop) on your own machine. It isn't a network service and isn't meant to be deployed remotely.

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

Tools: `get_guidance` (CGR³ verdict), `learn` (add bullet), `query` (semantic search), `feedback`, `build_feature` (sandboxed TDD, optional broker routing via `models`), `build_feature_ensemble` (multi-candidate blind build), `build_project` (decompose a spec into a module DAG and build it).

### ClaudeCliClient — No API Key Required

Drop-in `LLMClient` replacement using the local `claude --print` CLI. No API keys, no billing — uses the active Claude Code session. Confined to a pure text completion (`--tools ""`, `--strict-mcp-config`, `--setting-sources ""`, a no-tools system prompt) and strips `CLAUDE*` env vars to prevent nested-session detection.

Reachable from:
- **`ace tdd --model claude-cli`** and **`ace project --model claude-cli`** (or `claude-cli/haiku` to pick a faster model)
- the MCP tools (`build_feature` / `build_feature_ensemble` / `build_project`) — the default when no `model` arg is given
- `bootstrap/orchestrate.py --client claude-cli`

Each LLM call spawns a fresh `claude` subprocess (~2.5s boot). Fine for `ace tdd` / `ace project` (dozens of calls); **`benchmarks/runner.py` is API-only** — a full ablation makes hundreds of calls and the spawn overhead would dominate.

---

## Demos

`demos/` has 11 runnable scripts, each demonstrating one subsystem end-to-end. They vary in what they need beyond a bare `uv sync`:

| Demo | What it shows | Requires |
|---|---|---|
| `demo_gherkin_extraction.py` | Reverse-engineers Gherkin scenarios from a sample OAuth client + its tests | Nothing — generates its own fixture |
| `demo_advanced_extraction.py` | Same extraction, aimed at ACE's own `src/ml/experiment_knowledge.py` to show it scaling to real production code | Nothing |
| `demo_cross_language_migration.py` | Takes extracted Gherkin and scaffolds a parallel Go implementation via `GoStepGenerator` | Nothing (run `demo_gherkin_extraction.py` first) |
| `demo_pld.py` | DBSCAN clustering, supplier/license detection, and provenance-filtered prompt distillation for weak/cheap student models | Nothing — loads from a checked-in playbook archive |
| `demo_test_review.py` | Shows `TestReviewAgent` flagging missing assertions/edge cases while explicitly ignoring AAA-comment style | Nothing |
| `demo_gherkin_extraction_pgvector.py` | Extracts Gherkin, converts scenarios to knowledge bullets, stores them with embeddings | PostgreSQL + pgvector (`docker-compose up -d postgres`) |
| `demo_semantic_pattern_search.py` | Cross-domain semantic search, three distance metrics, section/multi-playbook filtering | PostgreSQL + pgvector, and the previous demo's data |
| `demo_unified_experiment_logging.py` | TDD cycles and ML experiments logged to the same `experiment_logs` table via `ExperimentLogger` | PostgreSQL |
| `demo_ensemble_local.py` | 3 local models propose bullets in parallel, cross-vote on each other's proposals with LLM reasoning, majority vote decides | Ollama, with `qwen2.5-coder:1.5b`/`0.5b` and `deepseek-coder:1.3b` pulled |
| `demo_playbook_qa.py` | Answers questions grounded in playbook bullets (single-model + ensemble-consensus modes), then an interactive REPL | An LLM provider configured; Ollama specifically for the ensemble portion |
| `demo_mlflow_ace.py` | Real MLflow-tracked scikit-learn runs, with `ACEMLflowCallback` capturing the *decisions* and *rationale* MLflow itself doesn't track | `uv sync --extra ml` (mlflow, scikit-learn, numpy) |

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

Bootstrap model slots (`MODEL_PASS1`, `MODEL_PASS2`, `MODEL_EXTRACT`) are set in `bootstrap/orchestrate.py`. `MODEL_EXTRACT` and `MODEL_PASS1` currently use `anthropic/claude-haiku-4-5` for cheap synthesis; `MODEL_PASS2` escalates to `anthropic/claude-sonnet-4-5` on repeated failure.

OpenRouter's free-tier (`:free`-suffixed) model catalog turns over frequently — models used elsewhere in this repo's tests/scripts have gone unlisted mid-project. Check [openrouter.ai/models](https://openrouter.ai/models) (filter by price) for what's currently free rather than relying on any specific model ID staying available.

---

## Project Structure

```
ace_enterprise/
├── src/
│   ├── agents/          # TDD agents, language pods, runners
│   ├── broker/          # AdaptiveBroker, CapabilityRegistry, BayesianEstimate
│   ├── analytics/       # CostQualityAnalyzer, SuccessRateCalculator, attribution
│   ├── audit/           # AuditStore, collector, dashboard
│   ├── benchmark/       # BlindEvaluator, rubrics, ModelAttributionTracker
│   ├── ensemble/        # ConsensusBuilder, EnsembleLearner, VotingSystem
│   ├── contracts/       # ContractArchitect, Decomposer, Orchestrator, Validator, ModuleArchitect
│   ├── retrieval/       # CGR³, ContextScorer, InstitutionalKnowledgeService
│   ├── playbook/        # PlaybookManager, BulletClusterer, BulletDeduplicator, DistillationRouter
│   ├── reliability/     # PlaybookReliabilityAnalyzer, TDDCycleAnalyzer — not yet wired into a live entry point
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
    └── adr/                    # ADR-001 through ADR-003
```

---

## Roadmap

### Shipped
- [x] Clean-room TypeScript OSS synthesis pipeline (Stages 1–5)
- [x] Contract interface synthesis path (Stage 2.5 — IO/wiring modules)
- [x] Tamper-evident audit chain published into OSS repo
- [x] CGR³ retrieval with 5-dimension context scoring
- [x] Playbook with DBSCAN clustering, semantic dedup, bullet lineage
- [x] Autonomous TDD agent with ACE Pipeline learning loop
- [x] Contract-driven development (Architect → Decomposer → Orchestrator)
- [x] AuditDashboard — performance, costs, team formation suggestions
- [x] ClaudeCliClient (API-key-free LLM via local claude CLI)
- [x] MCP server with CGR³ tools
- [x] MLflow integration (ACEMLflowCallback)
- [x] TDD engine audit trail carries real per-model telemetry (`actor_id`, `elapsed_seconds`, `task_type`) — the data contract `AdaptiveBroker` needs, ahead of it being wired to consume it
- [x] BlindEvaluator / CodeGenerationRubric run submission code inside the Podman sandbox (`--network none`, `--cap-drop=all`) instead of the host — closed a gap where scoring untrusted submissions executed them directly on the host
- [x] ContractValidator / validate_module run implementer-submitted code inside the Podman sandbox instead of `exec()`/`eval()`-ing it in-process — same gap, closed for the contract-driven pipeline
- [x] `scripts/stress_test_coding.py` (model-output validation for local dev benchmarking) sandboxed the same way — no LLM-generated code executes outside Podman anywhere in the repo, `scripts/` included
- [x] Live adversarial e2e tests proving the sandbox holds against real attacks, not just claimed flags: network egress, host-environment exfiltration, and CAP_SYS_ADMIN/read-only-mount privilege escalation all fail from inside a real container (`tests/e2e/test_enterprise_e2e_showcase.py`)
- [x] AdaptiveBroker wired into a live routing decision point — `ace tdd` (`.ace/config.yaml` `candidate_models:`) and MCP `build_feature` (`models`) route a build to one of 2+ candidates on audit history, emitting a `ROUTING_DECISION` event
- [x] BlindEvaluator + ConsensusBuilder wired into a live multi-candidate flow — MCP `build_feature_ensemble` builds with N models, scores each implementation blind, commits the winner, emits `BLIND_EVALUATION` / `ENSEMBLE_SELECTION` events
- [x] Multi-module projects ([#8](https://github.com/carlhuxley/ace_enterprise/issues/8)) — `ace tdd` builds every `.feature` in a project in `@depends_on(...)` topological order; `ace project <spec>` / MCP `build_project` decompose a spec into a module DAG (`ProjectArchitect`), print it for approval, then build each module in dependency order via `ModuleArchitect` → `ModuleTDDBuilder`, writing `src/<m>.py` + `tests/test_<m>.py` and running the suite as a cross-module assembly check (`CONTRACT_DECOMPOSED` / `PROJECT_BUILD_COMPLETED` events)

### Preview (implemented + unit-tested, not yet wired into a live entry point)
- [ ] CapabilityRegistry — anonymous agent registration with proficiency ratings
- [ ] BrokerAdvisor
- [ ] CostQualityAnalyzer with Pareto frontier
- [ ] DistillationRouter
- [ ] EnsembleLearner cross-model voting (ConsensusBuilder's convergence analysis is live via `build_feature_ensemble`; the LLM-vote path is not)

### Planned
- [ ] Project Architect follow-ups ([#8](https://github.com/carlhuxley/ace_enterprise/issues/8)): incremental re-planning (re-plan remaining modules after each build), cross-module integration `.feature`s, and container reuse across modules — the v1 flow is one-shot decomposition, per-module containers, assembly via the whole suite.
- [ ] `build_feature_ensemble` for TypeScript / Go (needs per-language rubrics; `CodeGenerationRubric` is Python-only)
- [ ] cost and quality_score telemetry (no pricing table or quality-scoring instrument exists yet — required before AdaptiveBroker's budget/balanced/Pareto routing modes have real data to act on)
- [ ] A2A Protocol Adapter (expose ACE's capability broker as an HTTP A2A server)
- [ ] effGen MCP adapter (connect open-source models as broker agents)
- [ ] Web UI for knowledge browsing and team formation
- [ ] Multi-organisation knowledge sharing with provenance
- [ ] IDE plugins (VSCode, JetBrains)

---

## Benchmark: Does the Playbook Causally Help?

`benchmarks/` runs a 3-arm ablation to isolate the Playbook's causal effect,
separate from any benefit of simply letting a model retry: **Arm 1**
(zero-shot baseline), **Arm 2** (blind retry — same failure feedback, no
Playbook bullets), **Arm 3** (ACE — same feedback, plus curated bullets).
Arm 2 and Arm 3 share an identical base prompt, differing only in whether
bullets are present, so any gap between them is attributable to the
Playbook rather than to retrying itself. `net_causal_uplift` is
`ace_recovery_rate − control_recovery_rate`, measured only over the subset
of tasks that failed Arm 1.

Latest verified run — `qwen/qwen3-coder-30b-a3b-instruct` via OpenRouter,
30 tasks (numeric edge cases, security boundaries, concurrency boundaries),
5 independent runs with fresh playbooks each:

| Metric | Mean | Std dev |
|---|---|---|
| Pass@1 (zero-shot) | 89.3% | ±4.3% |
| Control recovery (blind retry) | 47.3% | ±16.9% |
| ACE recovery (playbook retry) | 63.0% | ±24.4% |
| **Net causal uplift** | **+15.7%** | ±15.1% |

Full report: [`benchmarks/reports/20260828T212436Z_qwen_qwen3-coder-30b-a3b-instruct_x5runs.json`](benchmarks/reports/20260828T212436Z_qwen_qwen3-coder-30b-a3b-instruct_x5runs.json).

**Read this honestly, not as a victory lap.** With only ~3–6 tasks failing
Arm 1 per run, a single task flipping arms swings `net_causal_uplift` by
1/N — the ±15% std dev is real, not a rounding artifact. Net uplift has
landed positive on average in every independent 5-run study against this
model, which is a genuine, repeated signal that the Playbook beats
blind retry — but the exact magnitude isn't statistically distinguishable
between the studies. See `benchmarks/reports/` for the full history,
including runs that surfaced real bugs (a markdown-fence extraction
bug that inflated one run's numbers, later found and fixed) rather than
just the flattering result. `--runs 1` is not a real measurement; treat
anything below `--runs 5` as illustrative only.

Reproduce:

```bash
pytest -q
python -m benchmarks.runner --model qwen/qwen3-coder-30b-a3b-instruct \
  --provider openrouter --runs 5
```

---

## Security

Because ACE executes generated code inside rootless, air-gapped Podman containers (`--network none`, `--cap-drop=all`), security is a primary design goal. To report potential container escape vectors or sandbox vulnerabilities, please refer to [SECURITY.md](SECURITY.md).

---

## Why ACE?

**ACE** = Agentic Context Engineering (Stanford/SambaNova, arXiv:2510.04618)

The system operates on merit and rules, not trust or identity. Historical performance is the only signal the broker acts on. Humans see the full picture via the audit trail and make final decisions.

**Research basis:**
- ACE Framework: arXiv:2510.04618v1
- Dynamic Cheatsheet: arXiv:2504.07952v1

---

*Architecture docs auto-generated at [`docs/SYSTEM_ARCHITECTURE.md`](docs/SYSTEM_ARCHITECTURE.md) — regenerate with `.venv/bin/python generate_live_docs.py`*
