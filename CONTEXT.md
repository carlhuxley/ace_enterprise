# ACE Enterprise — Domain Glossary

This file records the domain language for the ACE Enterprise project.
Use these terms exactly in code, docs, and architecture discussions.

---

## Core Concepts

**ACE Pipeline** — The three-module learning loop: Generator → Reflector → Curator. Generator produces output using playbook guidance; Reflector analyses failures; Curator writes insights back as bullets.

**ACEMLflowCallback** — An MLflow callback that captures ACE knowledge (decisions and patterns) during ML training runs. Stores knowledge in a local file (`knowledge/`) and integrates with MLflow run IDs. A PostgreSQL-backed variant (`PostgresACEMLflowCallback`) stores knowledge directly in the experiment_logs table.

**ACEConfig** — ACE configuration for a project, stored in `.ace/config.yml`. Contains project name, domain, model preferences, and playbook settings.

**AdaptiveBroker** — Routes tasks to the best agent based on historical performance using configurable strategies (budget, balanced, Pareto). Falls back to a default agent when no history exists.

**AgentCapabilities** — Agent capabilities with proficiency ratings. Used by `CapabilityRegistry` to track anonymous agent skills.

**AgentIdentity** — Identity information for an agent (name, version, description) that can be registered with an audit dashboard for human-readable agent attribution.

**AgentPerformanceMetrics** — Performance metrics for an agent (anonymized by agent_ref). Includes success rate, reliability score, variance-adjusted reliability, and complexity handling.

**AnalysisRubric** — Domain-specific evaluation rubric for analytical/research output. Scores coverage, reasoning, accuracy, and citations.

**ArchitectResult** — Result of contract generation from `ContractArchitect`. Contains generated contracts and associated metadata.

**ASTSignature** — A compact representation of a function or class definition (name, parameters, decorators) extracted from source code. Used by ContextMap to provide the LLM with relevant module context during GREEN phase.

**Audit** — Append-only event log. Every TDD cycle emits `CYCLE_COMPLETED` events recording which model was used, success/failure, and cycle counts. Used for model attribution and performance aggregation. Events are stored with hash chain integrity via `AuditStore`.

**AuditClient** — Write-only client for emitting audit events. Supports remote (HTTP via `AuditStore`), local (SQLite via `LocalAuditClient`), and a `NoOpAuditClient` for testing.

**AuditDashboard** — Dashboard for analyzing audit data: computes agent performance, cost analysis, task type strengths, and optimal team suggestions. Supports benchmark comparison.

**AuditEvent** — An immutable audit event with hash chain fields. Used by `AuditStore` for append-only logging.

**AuditEventCreate** — Schema for creating an audit event before hash chain computation.

**AuditEventType** — Enumerates types of audit events (e.g., `CYCLE_COMPLETED`, `CONTRACT_GENERATED`).

**AuditStore** — Append-only audit event store with hash chain integrity. Stores events in PostgreSQL and supports querying, chain verification, and statistics.

**AutonomousTDDAgent** — The primary TDD entry point. Plans incremental tests using Ensemble, executes TDD cycles, and learns via the ACE pipeline. GREEN phase uses Generator for playbook-guided generation; retry learning routes through Curator. After a successful GREEN phase, promotes session-wins bullets to the playbook. If a test passes unexpectedly during RED phase (i.e., doesn't fail), attempts to refine it so it actually fails before proceeding.

**Bandit Gate** — A security failure mode triggered by a HIGH-severity Bandit static-analysis finding on generated Python code (the TypeScript equivalent uses eslint-plugin-security, sharing the same `PulseResult.bandit_high`/`bandit_medium`/`bandit_low` fields). Detected by `_is_abort()`/`_is_security_failure()` via the prefix `Security gate:` in `PhaseResult.error`. Bandit runs *after* pytest execution inside the container, not before — it is a commit-time/retry gate, not a pre-execution check: it prevents the flagged result from being written to disk and aborts the TDD cycle immediately (no retry), but the code has already executed once inside the sandboxed container by the time it fires. The container's `--network none` isolation and read-only workspace mount are what actually contain the code while it runs.

**BayesianEstimate** — Posterior summary of a Beta-Binomial success-rate model used by `PerformanceAggregator` for statistically robust agent performance estimates.

**BlindEvaluator** — Evaluates submissions without disclosing which agent produced them. Supports rubric-based scoring for code, tests, documentation, and analysis using domain-specific rubrics (e.g., `CodeGenerationRubric`, `TestWritingRubric`).

**BrokerAdvisor** — Advises on agent selection by capability fit. Uses `CapabilityRegistry` to recommend agents for a task.

**BrokerConfig** — Configuration for `AdaptiveBroker`, including routing strategy, budget cap, and latency limits.

**Bullet** — A single actionable piece of learned knowledge stored in a Playbook. Organised into sections: `strategies_and_hard_rules`, `code_snippets`, `troubleshooting`, `domain_knowledge`, `test_assertion_rules`, `session-wins`, `global-go-bullets`.

**BulletCluster** — A cluster of semantically related bullets produced by `BulletClusterer`. Contains bullets, centroid, and representative bullet.

**BulletClusterer** — DBSCAN-based clustering for playbook bullets. Groups semantically related bullets and selects representatives by helpful ratio, centrality, or recency.

**BulletCreate** — Input schema for adding a bullet via PlaybookManager. Contains content, section, tags, and optional fields for provenance (model, provider, license) and contextual retrieval (confidence, domains, projects).

**BulletDeduplicator** — Handles semantic deduplication of bullets using embedding similarity (cosine distance). Supports configurable thresholds and duplicate-preservation strategies.

**BulletLineage** — Tracks relationships between bullets for knowledge lineage (e.g., superseded-by, derived-from).

**BulletReliability** — The first-pass GREEN success rate for a specific bullet across TDD cycles. Computed by `PlaybookReliabilityAnalyzer`.

**BulletRetriever** — Hybrid retrieval system for selecting relevant bullets from playbooks. Supports cross-model retrieval and contextual filtering (by confidence, domain, project).

**BulletSection** — Enum of playbook sections for organizing bullets (e.g., `strategies_and_hard_rules`, `code_snippets`). Used by `EnsembleLearner` and `Curator`.

**canonical_hash** — A deterministic SHA-256 hash over a workspace of files. Computed by sorting (filename + content) pairs and hashing the concatenation. Used by `PodmanOrchestrator` to verify that the container ran exactly the code that was sent.

**CapabilityRegistry** — Anonymous registry of agent capabilities with proficiency ratings. Used by `BrokerAdvisor` to recommend agents by capability fit.

**CGR³ (Context Graph Retrieve-Rank-Reason)** — A retrieval system that scores bullets against request context across multiple dimensions (temporal validity, team locality, tech stack compatibility, project relevance, domain relevance) and issues a verdict (`APPLY`, `ASK_FIRST`, `SKIP`). Core components: `ContextGraphRetriever`, `ContextScorer`, `InstitutionalKnowledgeService`. Sub-types: `RankedBullet` (a bullet with context-aware ranking), `RetrievalContext` (context for the current retrieval request), `ContextGap` (describes a gap in context affecting applicability), `ReasoningVerdict` (verdict from the Reason phase), `KnowledgeResponse` (response from the InstitutionalKnowledgeService).

**ClassAnalysis** — Analysis of a single class extracted from source code by `CodeAnalyzer`. Contains class name, methods, and decorators.

**ClaudeCliClient** — Drop-in replacement for `LLMClient` using the local `claude -p` command-line interface. Useful for development without API keys.

**ClusteringResult** — Result of DBSCAN clustering operation on bullets. Contains clusters, coverage by model, and metadata.

**CodeAnalysis** — Result of analyzing a Python source file: extracted classes, methods, imports, and type annotations. Produced by `CodeAnalyzer` in the Gherkin extraction process.

**CodeGenerationRubric** — A domain-specific evaluation rubric for Python code output. Scores syntax, structure, test compatibility, and security.

**CodeReuseDetector** — Detects opportunities for code reuse in the project by analyzing feature requirements and suggesting existing utilities, base classes, and imports.

**CodebaseContext** — Context about the existing codebase used by `ModuleArchitect` for generating module contracts.

**CodeAnalyzer** — Analyzes Python code to extract method signatures, class structures, and type annotations. Used by `GherkinExtractionAgent`.

**ConsensusBuilder** — Clusters similar bullet proposals from multiple models and builds consensus by merging or selecting the best representative.

**ConsensusBullet** — A proposed bullet with voting metadata from the ensemble. Tracks votes, approval rate, and confidence.

**ContainerRunner** — Protocol (interface) for executing code in an isolated container. Implemented by `PodmanRunner` and `TypeScriptRunner`.

**ContextGraphRetriever** — CGR³ component that executes the retrieve-rank-reason pipeline. Takes a query, bullets, and context, and returns ranked bullets with verdicts.

**ContextMap** — A mapping of source files to AST signatures (function/class definitions and their parameters). Built by `ContextMapBuilder` from existing code files. Provides `nodes_relevant_to(test_ids)` to return signatures referenced by given pytest test IDs, enabling the WorkerAgent to include relevant module context during GREEN phase.

**ContextMapBuilder** — Builds a `ContextMap` by parsing Python source files and extracting AST signatures for functions and classes.

**ContextScorer** — Scores bullets against request context across five dimensions: temporal validity, team locality, tech stack compatibility, project relevance, domain relevance.

**ContractArchitect** — Generates interface contracts from natural language requirements. Decomposes requirements into `InterfaceContract` objects and emits audit events for contract generation and decomposition.

**ContractDecomposer** — Breaks user specifications into structured `InterfaceContract` objects. Supports YAML-based contract definitions and LLM-assisted decomposition.

**ContractOrchestrator** — Orchestrates contract-driven development: registers contracts, provides implementation prompts via `get_implementation_prompt()`, and validates submitted implementations against test cases.

**ContractSpec** — A single contract specification loaded from YAML. Contains method signatures, input/output schemas, and test cases.

**ContractStatus** — Status of a contract implementation (e.g., pending, in progress, validated).

**ContractValidator** — Validates an implementation against a contract by running the contract's test cases against the provided code.

**CostQualityAnalyzer** — Analyzes cost-quality tradeoffs for ML model performance data. Computes cost efficiency metrics, Pareto frontiers, and suggests best model for given complexity.

**CrossLanguageComparison** — Comparison between two or more languages for the same feature in terms of token efficiency.

**Curator** — ACE pipeline module. Synthesises Reflector insights into delta bullets and applies them to the Playbook with deduplication and token-budget enforcement. Interface: `curate(reflector_output, playbook_id) → CuratorOutput`, `apply_updates(playbook_id, curator_output) → list[str]`.

**CuratorOutput** — Output from the Curator module. Contains `delta_bullets` (list of `DeltaBullet`) and `reasoning`. Produced by `Curator.curate()`.

**CyclePeriod** — A time window (start, end) used by `TDDCycleAnalyzer` to compute first-pass rates over equal-width periods.

**CycleResult** — Outcome of a complete TDD cycle. Contains `success`, `feature_requirement`, `red_result`, `green_result`, `refactor_result`, `green_attempts`, `token_usage`, `error`, and `learned_bullets` (list of `DeltaBullet`). Defined in both `TDDCycleRunner` and `AutonomousTDDAgent`.

**DailyMetrics** — Performance metrics for a single day, used by `ModelAttributionTracker`. Contains success rate and average quality score.

**DecisionContext** — Full context for human decision-making: agent profiles, costs, capabilities, and task requirements.

**DecisionRecord** — An Architectural Decision Record (ADR) documenting the rationale and context of a design decision. Generated by `generate_adr_from_tdd_result()`.

**DecisionResult** — Result of recording a human decision via `HumanDecisionInterface`.

**DeltaBullet** — A new bullet to add to playbook, produced by the Curator. Contains `section`, `content`, and `tags`. Provides `content_hash()` for SHA-256 based deduplication.

**DimensionScore** — Score awarded on a single dimension within an evaluation rubric. Contains raw score and weighted score.

**DistillationRouter** — Routes tasks to domain-specific distillation playbooks. Uses `DomainRegistry` for domain classification and `Provenance` for license-aware filtering of training data.

**DocumentationRubric** — Evaluation rubric for Markdown documentation output. Scores completeness, clarity, examples, and formatting.

**DomainMatch** — Result of domain classification by `DomainRegistry`. Contains domain name and similarity score.

**DomainRegistry** — Registry of available domains and their playbook centroids. Used by `DistillationRouter` to classify queries.

**DriftDetector
