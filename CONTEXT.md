# ACE Enterprise — Domain Glossary

This file records the domain language for the ACE Enterprise project.
Use these terms exactly in code, docs, and architecture discussions.

---

## Core Concepts

**ACE Pipeline** — The three-module learning loop: Generator → Reflector → Curator. Generator produces output using playbook guidance; Reflector analyses failures; Curator writes insights back as bullets.

**ACEMLflowCallback** — An MLflow callback that captures ACE knowledge (decisions and patterns) during ML training runs. Stores knowledge in a local file (`knowledge/`) and integrates with MLflow run IDs. A PostgreSQL-backed variant (`PostgresACEMLflowCallback`) stores knowledge directly in the experiment_logs table.

**AdaptiveBroker** — Routes tasks to the best agent based on historical performance using configurable strategies (budget, balanced, Pareto). Falls back to a default agent when no history exists.

**AgentPerformanceMetrics** — Performance metrics for an agent (anonymized by agent_ref). Includes success rate, reliability score, variance-adjusted reliability, and complexity handling.

**ASTSignature** — A compact representation of a function or class definition (name, parameters, decorators) extracted from source code. Used by ContextMap to provide the LLM with relevant module context during GREEN phase.

**Audit** — Append-only event log. Every TDD cycle emits `CYCLE_COMPLETED` events recording which model was used, success/failure, and cycle counts. Used for model attribution and performance aggregation. Events are stored with hash chain integrity via `AuditStore`.

**AuditClient** — Write-only client for emitting audit events. Supports remote (HTTP via `AuditStore`) and local (SQLite) backends, plus a `NoOpAuditClient` for testing.

**AuditDashboard** — Dashboard for analyzing audit data: computes agent performance, cost analysis, task type strengths, and optimal team suggestions. Supports benchmark comparison.

**AuditStore** — Append-only audit event store with hash chain integrity. Stores events in PostgreSQL and supports querying, chain verification, and statistics.

**AutonomousTDDAgent** — The primary TDD entry point. Plans incremental tests using Ensemble, executes TDD cycles, and learns via the ACE pipeline. GREEN phase uses Generator for playbook-guided generation; retry learning routes through Curator. After a successful GREEN phase, promotes session-wins bullets to the playbook. If a test passes unexpectedly during RED phase (i.e., doesn't fail), attempts to refine it so it actually fails before proceeding.

**BlindEvaluator** — Evaluates submissions without disclosing which agent produced them. Supports rubric-based scoring for code, tests, documentation, and analysis using domain-specific rubrics (e.g., `CodeGenerationRubric`, `TestWritingRubric`).

**BrokerAdvisor** — Advises on agent selection by capability fit. Uses `CapabilityRegistry` to recommend agents for a task.

**BrokerConfig** — Configuration for `AdaptiveBroker`, including routing strategy, budget cap, and latency limits.

**Bullet** — A single actionable piece of learned knowledge stored in a Playbook. Organised into sections: `strategies_and_hard_rules`, `code_snippets`, `troubleshooting`, `domain_knowledge`, `test_assertion_rules`, `session-wins`, `global-go-bullets`.

**BulletClusterer** — DBSCAN-based clustering for playbook bullets. Groups semantically related bullets and selects representatives by helpful ratio, centrality, or recency.

**BulletCreate** — Input schema for adding a bullet via PlaybookManager. Contains content, section, tags, and optional fields for provenance (model, provider, license) and contextual retrieval (confidence, domains, projects).

**BulletDeduplicator** — Handles semantic deduplication of bullets using embedding similarity (cosine distance). Supports configurable thresholds and duplicate-preservation strategies.

**BulletLineage** — Tracks relationships between bullets for knowledge lineage (e.g., superseded-by, derived-from).

**BulletReliability** — The first-pass GREEN success rate for a specific bullet across TDD cycles. Computed by `PlaybookReliabilityAnalyzer`.

**BulletRetriever** — Hybrid retrieval system for selecting relevant bullets from playbooks. Supports cross-model retrieval and contextual filtering (by confidence, domain, project).

**CapabilityRegistry** — Anonymous registry of agent capabilities with proficiency ratings. Used by `BrokerAdvisor` to recommend agents by capability fit.

**CGR³ (Context Graph Retrieve-Rank-Reason)** — A retrieval system that scores bullets against request context across multiple dimensions (temporal validity, team locality, tech stack compatibility, project relevance, domain relevance) and issues a verdict (`APPLY`, `ASK_FIRST`, `SKIP`). Core components: `ContextGraphRetriever`, `ContextScorer`, `InstitutionalKnowledgeService`.

**CodeAnalysis** — Result of analyzing a Python source file: extracted classes, methods, imports, and type annotations. Produced by `CodeAnalyzer` in the Gherkin extraction process.

**CodeGenerationRubric** — A domain-specific evaluation rubric for Python code output. Scores syntax, structure, test compatibility, and security.

**CodeReuseDetector** — Detects opportunities for code reuse in the project by analyzing feature requirements and suggesting existing utilities, base classes, and imports.

**CodeAnalyzer** — Analyzes Python code to extract method signatures, class structures, and type annotations. Used by `GherkinExtractionAgent`.

**ConsensusBuilder** — Clusters similar bullet proposals from multiple models and builds consensus by merging or selecting the best representative.

**ContextMap** — A mapping of source files to AST signatures (function/class definitions and their parameters). Built by `ContextMapBuilder` from existing code files. Provides `nodes_relevant_to(test_ids)` to return signatures referenced by given pytest test IDs, enabling the WorkerAgent to include relevant module context during GREEN phase.

**ContextScorer** — Scores bullets against request context across five dimensions: temporal validity, team locality, tech stack compatibility, project relevance, and domain relevance.

**ContractArchitect** — Generates interface contracts from natural language requirements. Decomposes requirements into `InterfaceContract` objects and emits audit events for contract generation and decomposition.

**ContractDecomposer** — Breaks user specifications into structured `InterfaceContract` objects. Supports YAML-based contract definitions and LLM-assisted decomposition.

**ContractOrchestrator** — Orchestrates contract-driven development: registers contracts, provides implementation prompts via `get_implementation_prompt()`, and validates submitted implementations against test cases.

**ContractSpec** — A single contract specification loaded from YAML. Contains method signatures, input/output schemas, and test cases.

**ContractValidator** — Validates an implementation against a contract by running the contract's test cases against the provided code.

**CostQualityAnalyzer** — Analyzes cost-quality tradeoffs for ML model performance data. Computes cost efficiency metrics, Pareto frontiers, and suggests best model for given complexity.

**Curator** — ACE pipeline module. Synthesises Reflector insights into delta bullets and applies them to the Playbook with deduplication and token-budget enforcement. Interface: `curate(reflector_output, playbook_id) → CuratorOutput`, `apply_updates(playbook_id, curator_output) → list[str]`.

**CyclePeriod** — A time window (start, end) used by `TDDCycleAnalyzer` to compute first-pass rates over equal-width periods.

**CycleResult** — Outcome of a complete TDD cycle. Contains `success`, `feature_requirement`, `red_result`, `green_result`, `refactor_result`, `green_attempts`, `token_usage`, `error`, and `learned_bullets` (list of DeltaBullet).

**DeltaBullet** — A new bullet to add to a playbook, produced by the Curator. Contains content, section, and tags. Has a `content_hash` method for fast deduplication.

**DistillationRouter** — Routes tasks to domain-specific distillation playbooks for cross-model knowledge transfer. Uses `DomainRegistry` to classify query domains and `Provenance` to filter bullets by supplier, license, and model origin, ensuring appropriate knowledge flow between student and teacher models.

**DocumentationRubric** — A domain-specific evaluation rubric for Markdown documentation. Scores completeness, clarity, examples, and formatting.

**DomainRegistry** — Maintains a registry of domains and their playbook signatures. Aggregates playbook embeddings to compute domain centroids for query classification.

**EffGenAdapter** — Connects small language models (via MCP protocol) to the Capability Broker, registering them as agents with health checks and task execution.

**EfficiencyReport** — Token efficiency report from `TokenEfficiencyReporter`, containing per-language scores and cross-language comparisons.

**EmbeddingService** — Generates embeddings for playbook bullets using a local sentence-transformers model. Used for semantic similarity in deduplication and retrieval. Singleton accessed via `get_embedding_service()`.

**Ensemble** — Multi-model consensus system. Multiple LLMs vote on outputs; `EnsembleLearner` aggregates results and calls the ACE pipeline to commit learned patterns.

**EnsembleLearner** — Orchestrates multiple models in parallel, executes the ACE pipeline (Generator → Reflector → Curator) for each, votes on proposed bullets, and commits approved patterns to the playbook.

**EnvironmentFeedback** — Feedback from task execution environment. Contains result (SUCCESS/FAILED), actual output, expected output, error messages, and test reports.

**ExperimentKnowledge** — Structured knowledge base for ML experiments, integrating decisions and patterns with MLflow run tracking. Persisted to JSON files.

**ExperimentLogger** — Unified logger for TDD and ML experiments. Stores experiments in PostgreSQL with fallback to SQLite (`ace_experiments.db`). Logs task, generator, environment, reflector, and curator data per cycle.

**FeatureSpec** — Parsed representation of a Gherkin `.feature` file. Contains the feature description, scenarios, and steps. Provides `as_requirement()` to produce a single string for the TDD loop. Created by `GherkinFeatureBridge`.

**FeedbackCollector** — Stores human quality ratings for evaluated outputs and derives blended scores and drift measurements. Supports multiple raters per evaluation and configurable blending weights.

**FileDrift** — Detects unintended changes to locked files during TDD execution. Used by `FileLockContext` to ensure generated code is not modified externally.

**ForbiddenImportError** — Security exception raised by ImportFilter when generated code contains a blocked import or builtin.

**FunctionSpec** — Specification for a single function within a module contract, including name, parameters, return type, and behavior.

**Generator** — ACE pipeline module. Retrieves relevant bullets from the Playbook and uses them to guide LLM code generation. Interface: `execute(task, playbook_id) → GeneratorOutput`.

**GeneratorOutput** — Output from the Generator module: reasoning trajectory, solution, list of bullet IDs used, bullet feedback map, latency, and token count.

**GherkinExtractionAgent** — Reverse engineers Gherkin scenarios from existing code and tests. Extracts method signatures and test assertions to produce Gherkin feature files and step definitions.

**GherkinFeatureBridge** — Parses a Gherkin `.feature` file into a `FeatureSpec`. Used by `IterativeTDDRunner` to feed structured requirements into `IncrementalPlanner`.

**GoLanguagePod** — LanguagePod implementation for Go TDD cycles. Generates Go test code, compiles and runs tests with `go test` in a Podman container.

**GoStepGenerator** — Generates Go step definitions for Gherkin scenarios. Takes a feature file and produces corresponding Go code with regex patterns for each step.

**HumanDecisionInterface** — Provides humans with full decision context (agent profiles, costs, capabilities) and records their assignment decisions for audit and analysis.

**ImportFilter** — Scans generated code for forbidden imports (e.g., `subprocess`, `os.system`) and blocked builtin calls (e.g., `eval`, `exec`). Raises `ForbiddenImportError` if policy violates.

**ImportValidator** — Validates and automatically corrects import paths in generated code against the project's module structure. Uses a cached module tree to fix incorrect import paths produced by the LLM.

**IncrementalPlanner** — Determines the next test increment by asking the LLM what single test to write next, given current test and implementation files and playbook guidance. Interface: `next_increment(requirement, cycle_number, ...) → TestIncrement`.

**InstitutionalKnowledgeService** — Central knowledge retrieval service for all code generation activities. Wraps `BulletRetriever` and `CGR³` to return guidance, anti-patterns, and context-aware suggestions.

**IntegrationTest** — A test that exercises multiple functions within a module to verify shared state and end-to-end behavior.

**InterfaceContract** — Defines what needs to be implemented: method signatures, input/output schemas, test cases, and fixtures. Produced by `ContractArchitect` and `ContractDecomposer`.

**IterativeResult** — Outcome of a full iterative TDD session. Contains `complete` (bool), `success` (bool), `iterations` (int), and list of `cycles` (each with cycle details).

**IterativeTDDRunner** — Kent Beck-style iterative TDD loop. Uses an `IncrementalPlanner` to get the next test increment, then `TDDCycleRunner` to execute RED→GREEN→REFACTOR. Repeats until the planner signals COMPLETE or max iterations reached. Returns `IterativeResult`.

**LanguagePod** — Language-agnostic protocol for TDD execution. Each pod implements `run_red`, `run_green`, `run_refactor`, and `token_usage`. Implementations include `PythonLanguagePod` and `GoLanguagePod`.

**LanguageScore** — Token efficiency metrics for one language's run of a feature (total tokens, cycles, efficiency score).

**LessonExtractor** — Extracts TDD lessons from resolved beads issues. Categorises failures and creates reusable lesson records.

**LicenseCategory** — Classification of a model's license (open_source, permissive, proprietary, unknown). Used by `DistillationRouter` for provenance-based filtering.

**MLflowKnowledgeQuery** — Unified interface to query MLflow runs enriched with ACE knowledge (decisions and patterns).

**ModelAttributionTracker** — Tracks OpenRouter model attribution: records both the requested model and the actual model that served the request. Computes per-model success rates, latency, and cost metrics.

**ModelFamilyMetrics** — Aggregated performance metrics for a model family (e.g., all `qwen/` models).

**ModelProfile** — Strength/weakness profile derived from per-model task-type metrics. Used by `BrokerAdvisor`.

**ModuleArchitect** — Generates module-level contracts for stateful systems. Produces a `ModuleContract` containing `FunctionSpec`s, shared state, integration tests, and complexity score. Used by `ModuleTDDBuilder`.

**ModuleContract** — A structured specification of a module: its functions (`FunctionSpec`), shared state, integration tests,
