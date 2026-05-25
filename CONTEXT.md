# ACE Enterprise — Domain Glossary

This file records the domain language for the ACE Enterprise project.
Use these terms exactly in code, docs, and architecture discussions.

---

## Core Concepts

**ACE Pipeline** — The three-module learning loop: Generator → Reflector → Curator. Generator produces output using playbook guidance; Reflector analyses failures; Curator writes insights back as bullets.

**ACEMLflowCallback** — An MLflow callback that captures ACE knowledge (decisions and patterns) during ML training runs. Stores knowledge in a local file (`knowledge/`) and integrates with MLflow run IDs. A PostgreSQL-backed variant (`PostgresACEMLflowCallback`) stores knowledge directly in the experiment_logs table.

**ACEConfig** — ACE configuration for a project, stored in `.ace/config.yml`. Contains project name, domain, model preferences, and playbook settings.

**AdaptiveBroker** — Routes tasks to the best agent based on historical performance using configurable strategies (budget, balanced, Pareto). Falls back to a default agent when no history exists.

**AgentPerformanceMetrics** — Performance metrics for an agent (anonymized by agent_ref). Includes success rate, reliability score, variance-adjusted reliability, and complexity handling.

**AnalysisRubric** — Domain-specific evaluation rubric for analytical/research output. Scores coverage, reasoning, accuracy, and citations.

**ASTSignature** — A compact representation of a function or class definition (name, parameters, decorators) extracted from source code. Used by ContextMap to provide the LLM with relevant module context during GREEN phase.

**Audit** — Append-only event log. Every TDD cycle emits `CYCLE_COMPLETED` events recording which model was used, success/failure, and cycle counts. Used for model attribution and performance aggregation. Events are stored with hash chain integrity via `AuditStore`.

**AuditClient** — Write-only client for emitting audit events. Supports remote (HTTP via `AuditStore`) and local (SQLite) backends, plus a `NoOpAuditClient` for testing.

**AuditDashboard** — Dashboard for analyzing audit data: computes agent performance, cost analysis, task type strengths, and optimal team suggestions. Supports benchmark comparison.

**AuditStore** — Append-only audit event store with hash chain integrity. Stores events in PostgreSQL and supports querying, chain verification, and statistics.

**AutonomousTDDAgent** — The primary TDD entry point. Plans incremental tests using Ensemble, executes TDD cycles, and learns via the ACE pipeline. GREEN phase uses Generator for playbook-guided generation; retry learning routes through Curator. After a successful GREEN phase, promotes session-wins bullets to the playbook. If a test passes unexpectedly during RED phase (i.e., doesn't fail), attempts to refine it so it actually fails before proceeding.

**Bandit Gate** — A security failure mode detected by Bandit static analysis. When generated code triggers a Bandit finding, `TDDCycleRunner` aborts the cycle immediately (no retry). Detected by `_is_abort()` via the prefix `Bandit gate:`.

**BayesianEstimate** — Posterior summary of a Beta-Binomial success-rate model used by `PerformanceAggregator` for statistically robust agent performance estimates.

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

**canonical_hash** — A deterministic SHA-256 hash over a workspace of files. Computed by sorting (filename + content) pairs and hashing the concatenation. Used by `PodmanOrchestrator` to verify that the container ran exactly the code that was sent.

**CapabilityRegistry** — Anonymous registry of agent capabilities with proficiency ratings. Used by `BrokerAdvisor` to recommend agents by capability fit.

**CGR³ (Context Graph Retrieve-Rank-Reason)** — A retrieval system that scores bullets against request context across multiple dimensions (temporal validity, team locality, tech stack compatibility, project relevance, domain relevance) and issues a verdict (`APPLY`, `ASK_FIRST`, `SKIP`). Core components: `ContextGraphRetriever`, `ContextScorer`, `InstitutionalKnowledgeService`. Sub-types: `RankedBullet` (a bullet with context-aware ranking), `RetrievalContext` (context for the current retrieval request), `ContextGap` (describes a gap in context affecting applicability), `ReasoningVerdict` (verdict from the Reason phase), `KnowledgeResponse` (response from the InstitutionalKnowledgeService).

**ClaudeCliClient** — Drop-in replacement for `LLMClient` using the local `claude -p` command-line interface. Useful for development without API keys.

**CodeAnalysis** — Result of analyzing a Python source file: extracted classes, methods, imports, and type annotations. Produced by `CodeAnalyzer` in the Gherkin extraction process.

**CodeGenerationRubric** — A domain-specific evaluation rubric for Python code output. Scores syntax, structure, test compatibility, and security.

**CodeReuseDetector** — Detects opportunities for code reuse in the project by analyzing feature requirements and suggesting existing utilities, base classes, and imports.

**CodeAnalyzer** — Analyzes Python code to extract method signatures, class structures, and type annotations. Used by `GherkinExtractionAgent`.

**ConsensusBuilder** — Clusters similar bullet proposals from multiple models and builds consensus by merging or selecting the best representative.

**ContextGraphRetriever** — CGR³ component that executes the retrieve-rank-reason pipeline. Takes a query, bullets, and context, and returns ranked bullets with verdicts.

**ContextMap** — A mapping of source files to AST signatures (function/class definitions and their parameters). Built by `ContextMapBuilder` from existing code files. Provides `nodes_relevant_to(test_ids)` to return signatures referenced by given pytest test IDs, enabling the WorkerAgent to include relevant module context during GREEN phase.

**ContextMapBuilder** — Builds a `ContextMap` by parsing Python source files and extracting AST signatures for functions and classes.

**ContextScorer** — Scores bullets against request context across five dimensions: temporal validity, team locality, tech stack compatibility, project relevance, domain relevance.

**ContractArchitect** — Generates interface contracts from natural language requirements. Decomposes requirements into `InterfaceContract` objects and emits audit events for contract generation and decomposition.

**ContractDecomposer** — Breaks user specifications into structured `InterfaceContract` objects. Supports YAML-based contract definitions and LLM-assisted decomposition.

**ContractOrchestrator** — Orchestrates contract-driven development: registers contracts, provides implementation prompts via `get_implementation_prompt()`, and validates submitted implementations against test cases.

**ContractSpec** — A single contract specification loaded from YAML. Contains method signatures, input/output schemas, and test cases.

**ContractValidator** — Validates an implementation against a contract by running the contract's test cases against the provided code.

**CostQualityAnalyzer** — Analyzes cost-quality tradeoffs for ML model performance data. Computes cost efficiency metrics, Pareto frontiers, and suggests best model for given complexity.

**CyclePeriod** — A time window (start, end) used by `TDDCycleAnalyzer` to compute first-pass rates over equal-width periods.

**CycleResult** — Outcome of a complete TDD cycle. Contains `success`, `feature_requirement`, `red_result`, `green_result`, `refactor_result`, `green_attempts`, `token_usage`, `error`, and `learned_bullets` (list of DeltaBullet).

**Curator** — ACE pipeline module. Synthesises Reflector insights into delta bullets and applies them to the Playbook with deduplication and token-budget enforcement. Interface: `curate(reflector_output, playbook_id) → CuratorOutput`, `apply_updates(playbook_id, curator_output) → list[str]`.

**DailyMetrics** — Performance metrics for a single day, used by `ModelAttributionTracker`. Contains success rate and average quality score.

**DecisionRecord** — An Architectural Decision Record (ADR) documenting what was built and why. Generated by `generate_adr_from_tdd_result()` from TDD session results.

**DeltaBullet** — A new bullet to add to a playbook, produced by the Curator. Contains content, section, and tags. Has a `content_hash` method for fast deduplication.

**DistillationRouter** — Routes tasks to domain-specific distillation playbooks for cross-model knowledge transfer. Uses `DomainRegistry` to classify query domains and `Provenance` to filter bullets by supplier, license, and model origin, ensuring appropriate knowledge flow between student and teacher models. Associated types: `LicenseCategory` (license category for provenance tracking), `Supplier` (model supplier/owner), `DomainMatch` (result of domain classification), `RouterConfig` (configuration for the router).

**DocumentationRubric** — A domain-specific evaluation rubric for Markdown documentation. Scores completeness, clarity, examples, and formatting.

**DomainRegistry** — Maintains a registry of domains and their playbook signatures. Aggregates playbook embeddings to compute domain centroids for query classification.

**DriftReport** — Report of unintended file changes detected by `FileLockContext` during TDD execution. Contains per-file diffs and a `is_clean()` predicate.

**EffGenAdapter** — Connects small language models (via MCP protocol) to the Capability Broker, registering them as agents with health checks and task execution.

**EffGenClient** — LLM client adapter for effGen local models, implementing the same interface as `LLMClient` for use with the Generator/Reflector pipeline.

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

**FileLockContext** — Context manager that locks target files (test and implementation) during a TDD cycle and checks for unintended drift on exit. Raises `InadvertentDriftError` if files were modified outside of the pod's write operations.

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

**InstitutionalKnowledgeService** — Central knowledge retrieval service for all code generation activities. Wraps `BulletRetriever` and `CGR³` to return guidance, anti-patterns, and context-aware suggestions. Returns `KnowledgeResponse` with ranked bullets and verdicts.

**IntegrationTest** — A test that exercises multiple functions within a module to verify shared state and end-to-end behavior.

**InterfaceContract** — Defines what needs to be implemented: method signatures, input/output schemas, test cases, and fixtures. Produced by `ContractArchitect` and `ContractDecomposer`.

**IterativeResult** — Outcome of a full iterative TDD session. Contains `complete` (bool), `success` (bool), `iterations` (int), and list of `cycles` (each with cycle details).

**IterativeTDDRunner** — Kent Beck-style iterative TDD loop. Uses an `IncrementalPlanner` to get the next test increment, then `TDDCycleRunner` to execute RED→GREEN→REFACTOR. Repeats until the planner signals COMPLETE or max iterations reached. Returns `IterativeResult`.

**LanguagePod** — Language-agnostic protocol for TDD execution. Each pod implements `run_red`, `run_green`, `run_refactor`, and `token_usage`. Implementations include `PythonLanguagePod`, `GoLanguagePod`, and `TypeScriptLanguagePod`.

**LanguageRunResult** — Outcome of a full RED→GREEN→REFACTOR run for one language in a polyglot TDD session. Contains success, cycles, token usage, and efficiency score.

**LanguageScore** — Token efficiency metrics for one language's run of a feature (total tokens, cycles, efficiency score).

**LessonExtractor** — Extracts TDD lessons from resolved beads issues. Categorises failures and creates reusable lesson records.

**LLMClient** — Unified LLM client supporting multiple providers (OpenAI, Anthropic, DeepSeek, Together AI, OpenRouter, Ollama, vLLM). Used by all ACE modules for LLM interactions.

**MarkdownImporter** — Imports knowledge from markdown files into playbook bullets. Parses headings into sections and extracts bullet content.

**MLExperimentKnowledge** — Knowledge base for ML experiments that integrates decisions and patterns with MLflow run tracking. Persists to JSON files.

**MLflowKnowledgeQuery** — Unified interface to query MLflow runs enriched with ACE knowledge (decisions and patterns). Supports filtering by decision criteria and pattern names.

**ModelAttributionTracker** — Tracks OpenRouter model attribution in performance metrics. Records which model actually served each request (actual_model vs requested_model) for accurate performance analysis.

**ModelFamilyMetrics** — Aggregated metrics for a model family (e.g., all qwen/ models). Includes success rate and average quality score.

**ModelProfile** — Strength/weakness profile derived from per-model task-type metrics by `PerformanceAggregator`. Used by `AdaptiveBroker` for nuanced routing.

**ModuleArchitect** — Generates module-level contracts for stateful systems with shared state, database schemas, and integration tests.

**ModuleTDDBuilder** — Builds module implementations using TDD methodology. Builds each function in a module contract via TDD-style iteration, then runs integration tests.

**PhaseResult** — Outcome of a single TDD phase (RED, GREEN, or REFACTOR). Contains `passed` (bool), `output` (str), and `error` (str | None).

**Playbook** — A collection of learned knowledge organized into sections. Each playbook has a unique ID, version, metadata (domain, base_model), and sections containing bullets.

**PlaybookEnforcer** — Enforces playbook rules like ace-006 (high-frequency feedback) by checking edit ratios before allowing file edits.

**PlaybookManager** — Manages playbook operations: creation, updates, merging, and retrieval. Supports incremental delta updates, semantic deduplication, token budget management, and file-based persistence.

**PlaybookQA** — Q&A system that answers coding questions using playbook knowledge. Supports single-model and ensemble answering with confidence scoring.

**PlaybookReliabilityAnalyzer** — Correlates bullet retrieval with first-pass GREEN outcomes. Computes `BulletReliability` for each bullet in a playbook.

**PodFactory** — Creates `LanguagePod` instances for a given language identifier. Used by `PolyglotTDDRunner` to instantiate pods for each target language.

**PodSpec** — Everything a pod needs to execute one phase. Contains `feature_requirement`, `test_file`, `implementation_file`, `cycle_number`, `error_output`, and `gherkin_context`.

**PodmanOrchestrator** — Stateless sidecar execution layer for the Clean Room harness. Sends code to a Podman container for isolated execution and verifies code integrity via `canonical_hash`. Raises `SecurityBreachError` when the container ran different code than was sent.

**PodmanRunner** — Production `ContainerRunner` backed by rootless Podman. Manages container lifecycle (start, stop, send_pulse) and computes workspace hashes.

**PolyglotTDDRunner** — Orchestrates RED→GREEN→REFACTOR across multiple LanguagePods for the same feature. Produces `PolyglotRunResult` with per-language results and token efficiency comparison.

**PostgresACEMLflowCallback** — PostgreSQL-backed MLflow callback for ACE knowledge capture. Stores decisions and patterns directly in the experiment_logs table, integrated with the ExperimentLogger system.

**PostgresPlaybookAdapter** — PostgreSQL-backed playbook manager that maintains the same interface as `PlaybookManager`. Uses `PlaybookRepository` for persistence and supports pgvector-based semantic search.

**PostgresBulletRetriever** — PostgreSQL-backed bullet retriever using pgvector for efficient similarity search. Compatible with `BulletRetriever` interface but leverages database-level vector indexes.

**ProductionDataAnalyzer** — Analyzes quality data from experiment_logs to extract model performance metrics, backfill quality scores, and generate production reports.

**ProjectArchitecture** — Manages cached project architecture information, including folder purposes for intelligent file placement in TDD cycles.

**ProjectConfig** — Manages ACE project configuration via `.ace/config.yml`. Provides `load`, `save`, `initialize`, and `get_or_create` methods.

**ProjectDetector** — Detects and analyzes Python project structure (root, src, test directories, project type, package manager) from a starting directory.

**Provenance** — Model/bullet provenance tracking for ownership-aware knowledge transfer. Used by `DistillationRouter` to filter bullets by supplier, license, and model origin.

**RatePeriod** — A time window used by `SuccessRateCalculator` for trend computation. Contains start, end, and computed rate.

**RedundancyPreChecker** — Pre-checks proposed tests for redundancy before the RED phase. Analyzes existing tests and proposed test names to avoid duplicate test logic.

**Reflector** — ACE pipeline module. Analyzes task execution and extracts learning insights: error identification, root cause, correct approach, and key insight. Supports iterative refinement with quality scoring.

**RegressionAlert** — Fired by `RegressionDetector` when a quality regression is detected between model versions. Contains model_id, baseline_version, current_version, and magnitude.

**RegressionDetector** — Tracks quality scores by (model_id, version) and detects performance regressions using statistical tests (quality baseline comparison and CUSUM detection).

**RoutingResult** — Result of an adaptive routing decision. Contains the selected agent_ref, routing score, and verdict.

**RoutingVerdict** — Verdict from the distillation router indicating whether to apply, ask first, or skip a knowledge pattern for a given student model.

**SecurityBreachError** — Raised by `PodmanOrchestrator` when the computed `canonical_hash` of the sent files does not match the hash computed inside the container. Indicates the container ran different code than what was sent.

**SemanticCodeAnalyzer** — Scans generated code for security issues beyond static imports, detecting SQL injection, `eval()`, `exec()`, and secrets. Used in conjunction with `ImportFilter` and Bandit for comprehensive security gating.

**SessionLog** — Simple session tracker for dogfooding loop visibility. Logs file edits and test runs during a session, producing summary statistics.

**SuccessRateCalculator** — Measures experiment success rates across the system. Computes overall rate, rate by type, rate by playbook version, and trends over equal time windows.

**TDDCycleAnalyzer** — Measures first-pass GREEN rate and whether it improves over time. Uses `ExperimentLogger` data to compute per-period rates.

**TDDCycleRunner** — Runs one complete TDD cycle: RED → GREEN (with retry) → REFACTOR. GREEN is retried up to `max_green_attempts`, passing failure output back to the pod. Security/policy failures (ForbiddenImport, SecurityBreach, Bandit gate) abort immediately. Optionally runs Reflector+Curator after successful cycles to write learned bullets to the playbook.

**TDDFailureCategory** — Enum of TDD failure categories for analysis: `TEST_DESIGN`, `IMPLEMENTATION`, `MOCKING`, `ASSERTION`, `TIMEOUT`, `SYNTAX`, etc.

**TDDFailureRecorder** — Records TDD failures with full context and attempted fixes. Creates beads issues and playbook bullets for self-healing automation.

**TDDLesson** — A lesson learned from a TDD failure, with category, root cause, and actionable guidance for future cycles.

**TDDLessonInjector** — Injects TDD lessons into agent prompts based on development phase (RED, GREEN, REFACTOR). Uses both static known lessons and dynamic lessons from experiment_logs.

**TestIncrement** — One planned test step in the TDD loop. Contains test name, description, and optional Gherkin scenario reference.

**TestReviewAgent** — Reviews test files for quality before implementation. Checks structure, naming, assertions, and edge cases. Optionally uses the LLM for deep analysis.

**TestReviewResult** — Result of reviewing a test file: list of quality issues, overall score, and pass/fail threshold check.

**TestWritingRubric** — Domain-specific evaluation rubric for test suite output. Scores edge cases, assertions, naming, and coverage.

**TokenEfficiencyReporter** — Computes token efficiency scores from LanguagePod run data. Produces per-language scores and cross-language comparisons.

**TokenUsage** — Token consumption for one complete TDD cycle. Contains cycle_number, input_tokens, output_tokens.

**TypeScriptLanguagePod** — LanguagePod implementation for TypeScript TDD cycles. Uses a TypeScript worker agent and Podman-based container running vitest.

**TypeScriptRunner** — PodmanRunner pre-configured for the TypeScript harness image. Parses vitest JSON output for pass/fail determination.

**TypeScriptWorkerAgent** — Generates TypeScript code for each TDD phase given a PodSpec. Builds prompts specific to TypeScript conventions and vitest.

**VoteType** — Types of votes a model can cast in the ensemble: `APPROVE`, `REJECT`, `ABSTAIN`.

**VotingSystem** — Main voting system that applies configurable strategies (`MajorityVoting`, `SupermajorityVoting`, `WeightedVoting`, `UnanimousVoting`, `EscalatingVoting`) to ensemble bullet proposals.

**WorkerAgent** — Standalone LLM code-generation component. Receives feature context and optional constraints (playbook bullets, AST context map) explicitly and returns code strings. Used by LanguagePods for RED, GREEN, and REFACTOR phases. Contains default test assertion rules (`_DEFAULT_TEST_RULES`) and the `_TEST_RULES_SECTION` constant.

---

## Architectural Decisions

- **LanguagePod Protocol (ADR-002)**: Each target language gets a Pod implementing `run_red`, `run_green`, `run_refactor`, and `token_usage`. The protocol is language-agnostic; file conventions and toolchain details live inside the pod. Pods delegate code generation to language-specific WorkerAgents (e.g., `WorkerAgent`, `TypeScriptWorkerAgent`). A `PodFactory` creates pods for a given language identifier, used by `PolyglotTDDRunner`.

- **Clean Room Harness**: All test execution happens inside a Podman container to isolate side effects. Code integrity is verified via `canonical_hash`: a SHA-256 hash of sorted (filename + content) pairs is computed before sending and verified after execution. If hashes don't match, `SecurityBreachError` is raised.

- **ACE Learning Loop**: The three-module pipeline (Generator → Reflector → Curator) runs after each successful GREEN phase when `TDDCycleRunner` is configured with a reflector and curator. Curator writes delta bullets directly to the playbook via `PlaybookManager.apply_delta()`. This decouples learning from the TDD orchestration.

- **Playbook Storage**: Playbooks are persisted as JSON files in `data/playbooks/` by default. The `PostgresPlaybookAdapter` provides an alternative backend using PostgreSQL with pgvector for semantic search. The `PlaybookManager` falls back gracefully if PostgreSQL is unavailable.

- **Experiment Logging**: All TDD cycles and ML experiments are logged to a unified `experiment_logs` table in PostgreSQL. The `ExperimentLogger` falls back to SQLite (`ace_experiments.db`) when PostgreSQL is unreachable, ensuring no cycle is lost.

- **Iterative TDD Architecture**: The `IterativeTDDRunner` decouples planning from execution. `IncrementalPlanner` decides what test to write next; `TDDCycleRunner` executes each RED→GREEN→REFACTOR cycle. This allows both planner-driven (Kent Beck style) and Gherkin-driven modes.

- **WorkerAgent Contract**: The `WorkerAgent` separates prompt-building and LLM-calling from orchestration. It receives task context and constraints explicitly and returns raw code strings. The pod (e.g., `PythonLanguagePod`) handles file I/O and test execution. Default test assertion rules (`_DEFAULT_TEST_RULES`) are seeded into the playbook's `test_assertion_rules` section on first use.

- **Cross-Model Knowledge Transfer**: `DistillationRouter` and `DomainRegistry` enable selective knowledge sharing between models. Provenance tracking ensures appropriate licensing restrictions are respected when transferring bullets between teacher and student models.

- **Ensemble Voting**: When multiple models generate bullets, the `EnsembleLearner` uses configurable voting strategies (majority, supermajority, weighted, unanimous, escalating) to approve patterns. Contestation triggers deliberative rounds where models explain their votes.

- **CGR³ Retrieval**: The Context Graph Retrieve-Rank-Reason system scores bullets across five contextual dimensions before deciding whether to apply, ask first, or skip. This prevents irrelevant or stale knowledge from being injected into generation prompts. The system produces `RankedBullet`, `ContextGap`, and `KnowledgeResponse` types for fine-grained reasoning.

- **Security Gates**: Generated code passes through `ImportFilter` (forbidden imports/builtins), Bandit static analysis, and optionally `SemanticCodeAnalyzer` for deeper security scanning (SQL injection, eval, exec, secrets). Any violation aborts the cycle immediately without retry, both in `PythonLanguagePod` and `TDDCycleRunner`.

- **Contract-Driven Development**: `ContractArchitect` and `ContractDecomposer` produce structured `InterfaceContract` objects from requirements. `ModuleArchitect` extends this to stateful modules with integration tests. `ModuleTDDBuilder` builds each function in a contract via TDD.

- **Adaptive Broker**: `AdaptiveBroker` routes tasks to the best agent based on historical performance. `PerformanceAggregator` computes metrics from the audit trail, and `BrokerAdvisor` recommends agents by capability fit. `HumanDecisionInterface` provides full context for human override. `RoutingResult` encapsulates the routing decision.

- **TDD Failure Learning**: TDD failures are recorded by `TDDFailureRecorder` with full context and categorized using `TDDFailureCategory`. Lessons are extracted and stored in the experiment_logs, then injected into future prompts by `TDDLessonInjector`. This creates a self-healing loop that reduces repeated mistakes over time.
