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

**Bandit Gate** — A security failure mode detected by Bandit static analysis. When generated code triggers a Bandit finding, `TDDCycleRunner` aborts the cycle immediately (no retry). Detected by `_is_abort()` via the prefix `Bandit gate:`.

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

**canonical_hash** — A deterministic SHA-256 hash over a workspace of files. Computed by sorting (filename + content) pairs and hashing the concatenation. Used by `PodmanOrchestrator` to verify that the container ran exactly the code that was sent.

**CapabilityRegistry** — Anonymous registry of agent capabilities with proficiency ratings. Used by `BrokerAdvisor` to recommend agents by capability fit.

**CGR³ (Context Graph Retrieve-Rank-Reason)** — A retrieval system that scores bullets against request context across multiple dimensions (temporal validity, team locality, tech stack compatibility, project relevance, domain relevance) and issues a verdict (`APPLY`, `ASK_FIRST`, `SKIP`). Core components: `ContextGraphRetriever`, `ContextScorer`, `InstitutionalKnowledgeService`. Sub-types: `RankedBullet` (a bullet with context-aware ranking), `RetrievalContext` (context for the current retrieval request), `ContextGap` (describes a gap in context affecting applicability), `ReasoningVerdict` (verdict from the Reason phase), `KnowledgeResponse` (response from the InstitutionalKnowledgeService).

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

**DeltaBullet** — A new bullet to add to playbook, produced by the Curator. Contains `section`, `content`, and `tags`. Provides `content_hash()` for deduplication.

**DistillationRouter** — Routes tasks to domain-specific distillation playbooks. Uses `DomainRegistry` for domain classification and `Provenance` for license-aware filtering of training data.

**DomainRegistry** — Registry of available domains and their playbook centroids. Used by `DistillationRouter` to classify queries.

**DriftDetector** — Detects unintended modifications to target files during a TDD session. Reports `FileDrift` and raises `InadvertentDriftError` if drift is detected.

**DriftReport** — Result of drift detection. Contains `is_clean()` and `assert_clean()` methods.

**EditCheckResult** — Result of `PlaybookEnforcer.check_can_edit()`. Indicates whether an edit is allowed based on playbook rules (e.g., ace-006 high-frequency feedback).

**EfficiencyReport** — Full token efficiency report, surfaced under the `token_efficiency` key. Produced by `TokenEfficiencyReporter`.

**EffGenAdapter** — MCP adapter for connecting effGen (small language models) to the Capability Broker. Registers agents and checks health.

**EffGenClient** — LLM client adapter for effGen local models, conforming to the `LLMClient` interface.

**EmbeddingService** — Local embedding generation using sentence-transformers. Used by PlaybookManager to compute bullet embeddings.

**EnsembleLearner** — Orchestrates multiple models in parallel: each executes Generator → Reflector → Curator, then bullets are voted on and merged. Supports deliberation and cross-voting.

**EnsembleResult** — Complete result from an ensemble learning session. Contains `approved_bullets()`, `rejected_bullets()`, and a `summary()`.

**EnvironmentFeedback** — Feedback from task execution environment (result, expected vs actual output, test report). Used by Reflector.

**ExistingTest** — Represents an existing test in the codebase. Used by `RedundancyPreChecker`.

**ExperimentLogger** — Unified logger for TDD and ML experiments. Stores in PostgreSQL (fallback to SQLite). Provides `log_tdd_cycle()`, `log_ml_experiment()`, and query methods.

**ExperimentLogModel** — SQLAlchemy model for experiment logs. Contains task_data, generator_data, environment_data, reflector_data, curator_data, result, and timestamps.

**ExtractionResult** — Result of Gherkin extraction from codebase. Contains generated Gherkin feature, scenarios, step definitions, and confidence score.

**FeatureSpec** — Parsed representation of a Gherkin .feature file. Contains `name`, `description`, and list of `ScenarioSpec`. Provides `as_requirement()`.

**FeedbackCollector** — Stores human ratings for evaluated outputs and derives blended scores and drift.

**FileDrift** — Describes a single file that has drifted (changed content) from its expected state.

**FileLockContext** — Context manager that prevents inadvertent drift of target files during a TDD session. Uses `DriftDetector` to verify on exit.

**FolderInfo** — Information about a project folder (path, purpose, contains source or tests). Used by `ProjectStructure`.

**ForbiddenImportError** — Exception raised when generated code uses a blocked import or builtin. Caught by `PythonLanguagePod` to abort the phase.

**FunctionBuildResult** — Result of building one function via TDD in `ModuleTDDBuilder`.

**FunctionSpec** — Specification for a function within a module contract. Contains signature, docstring, and test hints.

**Generator** — ACE pipeline module. Executes tasks using playbook-guided LLM. Retrieves relevant bullets, builds prompts, and records trajectory/solution.

**GeneratorOutput** — Output from the Generator module. Contains `trajectory`, `solution`, `bullets_used`, `bullet_feedback`, `latency_ms`, `tokens_used`.

**GherkinExtractionAgent** — Reverse-engineers Gherkin scenarios from existing code and tests. Produces `ExtractionResult`.

**GherkinFeatureBridge** — Parses a Gherkin .feature file into a `FeatureSpec`. Used by `IterativeTDDRunner` for Gherkin-driven mode.

**GoLanguagePod** — LanguagePod implementation for Go TDD cycles.

**GoStepGenerator** — Generates Go step definitions for Gherkin scenarios.

**HumanDecision** — A human's assignment decision containing requirements, chosen agent, and rationale.

**HumanDecisionInterface** — Interface for human decision-making. Provides `get_context()`, `record_decision()`, and history/stats.

**HumanFeedback** — A single human quality rating for an evaluated output, with provider role and comment.

**IdGenerator** — Utilities for generating unique IDs for playbooks, bullets, experiments, checkpoints, and tasks.

**Implementation** — Result of implementing a contract. Contains code, test results, and metadata.

**ImportFilter** — Blocks forbidden imports and builtins in generated code. Used by `PythonLanguagePod`.

**ImportValidationError** — Raised when import validation fails and cannot be auto-corrected.

**ImportValidator** — Validates and corrects import paths in generated code. Builds a module cache to resolve relative imports.

**IncrementalPlanner** — Determines the next test increment to write by asking the LLM what should be tested next. Used by `IterativeTDDRunner`.

**InstitutionalKnowledgeService** — Central knowledge retrieval service for all code generation activities. Provides `get_guidance()`, `get_guidance_for_tdd()`, `get_guidance_for_implementation()`, `get_anti_patterns()`.

**InterfaceContract** — Defines what needs to be implemented: signatures, input/output schemas, test cases, and fixtures. Used by `ContractOrchestrator`.

**IterativeResult** — Outcome of a full iterative TDD session from `IterativeTDDRunner`. Contains `success`, `complete`, `iterations`, and list of `CycleResult`.

**IterativeTDDRunner** — Kent Beck-style RED→GREEN→REFACTOR loop. Uses `IncrementalPlanner` to plan tests and a `LanguagePod` to execute phases. Supports Gherkin-driven mode.

**KnowledgeResponse** — Response from `InstitutionalKnowledgeService`. Contains ranked bullets with verdicts and provides `questions()` for `ASK_FIRST` patterns.

**LanguagePod** — Protocol for language-specific TDD execution pods. Implementations must provide `run_red()`, `run_green()`, `run_refactor()`, and `token_usage()`.

**LanguageRunResult** — Outcome of a full RED→GREEN→REFACTOR run for one language in `PolyglotTDDRunner`.

**LanguageScore** — Token efficiency metrics for one language's run. Produced by `TokenEfficiencyReporter`.

**LatencyQualityReport** — Latency-quality correlation summary for one agent.

**LessonExtractor** — Extracts TDD lessons from resolved beads issues. Used by `TDDLessonInjector`.

**LicenseCategory** — License category for provenance tracking (e.g., mit, apache, proprietary). Used by `DistillationRouter`.

**LLMClient** — Unified LLM client supporting OpenRouter, OpenAI, Anthropic, DeepSeek, Together AI, Ollama, vLLM, and Claude CLI.

**LocalAuditClient** — Audit client that writes directly to local SQLite for development/testing.

**MarkdownImporter** — Imports knowledge from markdown files into playbook bullets. Parses headings as sections and bullet points as content.

**ModelAttributionTracker** — Tracks OpenRouter model attribution in performance metrics. Records per-model success rates, quality scores, and trend detection.

**ModelFamilyMetrics** — Aggregated metrics for a model family (e.g., all qwen/* models).

**ModelMetrics** — Aggregated performance metrics for a single model (success rate, avg quality score).

**ModelPerformance** — Performance metrics for a single model in production analysis (`ProductionDataAnalyzer`) or ensemble tracking.

**ModelProfile** — Strength/weakness profile derived from per-model task-type metrics. Used by `PerformanceAggregator`.

**ModuleArchitect** — Generates module-level contracts for stateful systems (shared database, dependencies). Produces `ModuleContract`.

**ModuleArchitectResult** — Result of module contract generation from `ModuleArchitect`.

**ModuleBuildResult** — Result of building a complete module via TDD in `ModuleTDDBuilder`.

**ModuleContract** — Contract for an entire module with shared state, database tables, and integration tests.

**ModuleDependencies** — Dependencies between modules (imports, schema references).

**ModuleTDDBuilder** — Builds module implementations using TDD methodology. Iterates over `FunctionSpec`, generates and validates each function.

**NoOpAuditClient** — No-op audit client for testing or when audit is disabled.

**PerformanceAggregator** — Extracts metrics from audit trail and provides agent performance, model profiles, Bayesian estimates, and regression alerts.

**PhaseResult** — Outcome of a single phase (RED, GREEN, or REFACTOR). Contains `passed`, `output`, and optional `error`.

**Playbook** — A collection of learned knowledge organized into sections. Contains metadata (domain, version) and a list of `Bullet` per section.

**PlaybookEnforcer** — Enforces playbook rules like ace-006 (high-frequency feedback). Checks edit ratios against historical session data.

**PlaybookManager** — Core playbook operations: creation, delta updates, deduplication, token budget management, persistence to JSON files.

**PlaybookMetadata** — Metadata for a playbook (domain, base_model, total_tokens, total_bullets).

**PlaybookQA** — Q&A system that answers coding questions using playbook knowledge. Supports single model and ensemble answers.

**PlaybookReliabilityAnalyzer** — Correlates bullet retrieval with first-pass GREEN outcomes. Computes `BulletReliability` for each bullet.

**PlaybookRepository** — PostgreSQL repository for playbooks and bullets with pgvector integration for semantic search.

**PodFactory** — Creates `LanguagePod` instances for a given language identifier.

**PodmanOrchestrator** — Stateless sidecar execution layer for the Clean Room harness. Uses `ContainerRunner` to send code and verify execution integrity via `canonical_hash`.

**PodmanRunner** — Production `ContainerRunner` backed by rootless Podman.

**PodRun** — Input data for one pod's execution of a feature. Used by `TokenEfficiencyReporter`.

**PodSpec** — Everything a pod needs to execute one phase: `feature_requirement`, `test_file`, `implementation_file`, `cycle_number`, `error_output`, `gherkin_context`.

**PolyglotRunResult** — Combined results for all languages in a polyglot TDD run, including token efficiency comparison.

**PolyglotTDDRunner** — Drives a RED→GREEN→REFACTOR loop for each requested language and compares token efficiency.

**PostgresACEMLflowCallback** — MLflow callback that stores knowledge directly in PostgreSQL experiment_logs table.

**PostgresBulletRetriever** — PostgreSQL-backed retrieval system using pgvector for semantic search.

**PostgresPlaybookAdapter** — PostgreSQL-backed playbook manager that maintains compatibility with in-memory `PlaybookManager` API.

**ProductionDataAnalyzer** — Analyzes quality data from experiment_logs for model performance metrics and trend reports.

**ProjectArchitecture** — Cached project architecture information (folder structure, purposes).

**ProjectConfig** — Manages project configuration from `.ace/config.yml`. Provides detection and auto-creation.

**ProjectDetector** — Detects and analyzes Python project structure (root, src, test dirs, package manager, Python version).

**ProjectInfo** — Information about a detected Python project (name, root, src dir, test dir, type, python version, package manager).

**ProjectStructure** — Represents the project folder structure with purposes for intelligent file placement.

**ProposedTest** — Represents a test being proposed for the next TDD cycle. Used by `RedundancyPreChecker`.

**Provenance** — Model/bullet provenance for ownership-aware matching. Contains supplier, license category, and `can_teach()` check.

**PulseResult** — Raw response from the container runner, including bandit analysis and test results.

**PythonLanguagePod** — LanguagePod implementation for Python TDD cycles. Uses `WorkerAgent` for code generation and `PodmanOrchestrator` for execution.

**QAAnswer** — Answer to a coding question with playbook context, confidence, and supporting bullets.

**QualityBaseline** — Quality summary for one (model_id, version) pair in `RegressionDetector`.

**RankedBullet** — A bullet with context-aware ranking from CGR³. Contains bullet, score, dimension scores, and verdict.

**RatePeriod** — A time window for success rate calculation in `SuccessRateCalculator`.

**ReasoningVerdict** — Verdict from the Reason phase of CGR³: `APPLY`, `ASK_FIRST`, or `SKIP`.

**RedundancyPreChecker** — Pre-checks proposed tests for redundancy before RED phase. Uses keyword extraction and semantic overlap.

**RedundancyResult** — Result of redundancy pre-check. Contains `is_redundant`, `reason`, and optional `similar_test`.

**Reflector** — ACE pipeline module. Analyses task outcomes, extracts error patterns, root causes, and key insights. Tags bullets as helpful/harmful/neutral.

**ReflectorOutput** — Output from the Reflector module. Contains `error_identification`, `root_cause`, `correct_approach`, `key_insight`, `bullet_tags`, `quality_score`.

**RegressionAlert** — Fired when a quality regression is detected by `RegressionDetector`. Contains model_id, baseline, current, and severity.

**RegressionDetector** — Tracks quality scores by (model_id, version) and detects regressions using CUSUM or threshold-based methods.

**RepresentativeStrategy** — Strategy for selecting cluster representatives: `helpful_ratio`, `centrality`, `recency`. Used by `BulletClusterer`.

**RetrievalContext** — Context for the current retrieval request in CGR³. Contains temporal, team, tech stack, project, and domain fields.

**RoutingResult** — Result of adaptive routing decision (from `AdaptiveBroker`) or distillation routing (from `DistillationRouter`).

**RoutingVerdict** — Verdict for routing decision in `DistillationRouter` (e.g., ROUTE, FALLBACK).

**ScenarioSpec** — One Gherkin scenario with its step lines (Given, When, Then). Part of `FeatureSpec`.

**ScoringDimension** — One measurable axis within an evaluation rubric. Contains name, description, weight.

**SecurityBreachError** — Raised when H_proposed ≠ H_executed — the container ran different code than was sent. Detected by `PodmanOrchestrator`.

**SemanticCodeAnalyzer** — Detects risky patterns in generated code (SQL injection, eval, exec, secrets).

**SessionLog** — Simple session tracker for dogfooding loop visibility. Logs edits and test runs to a file.

**Settings** — Application settings loaded from ACE's `.env` file. Validates database, Redis, LLM provider, and feature flags.

**StepDefinition** — A step definition for Gherkin steps (mapping step regex to code).

**Submission** — A submission to be evaluated by `BlindEvaluator`. Contains output, context, and optional rubric.

**SuccessRateCalculator** — Measures experiment success rates across the system by type, version, and time period.

**Supplier** — Model supplier/owner for provenance matching (e.g., OpenAI, Meta, Mistral).

**TaskCompletion** — Record of a completed task with model attribution (model_id, requested_model, provider, success, quality score).

**TaskInput** — Input to a task from the user. Contains `query`, `type`, `difficulty`, `context`.

**TDDCycleAnalyzer** — Measures first-pass GREEN rate and trend over time from experiment log records.

**TDDCycleRunner** — Orchestrates one complete TDD cycle: RED → GREEN (with retry) → REFACTOR, with optional learning loop.

**TDDFailureCategory** — Categories of TDD failures for analysis (e.g., test_design, implementation, mocking).

**TDDFailureRecorder** — Records TDD failures and interventions for self-improvement. Creates beads issues and playbook bullets.

**TDDLesson** — A lesson learned from a TDD failure. Contains category, root cause, and description.

**TDDLessonInjector** — Injects TDD lessons into agent prompts based on development phase.

**TDDResult** — Final result of autonomous TDD session from `AutonomousTDDAgent`.

**TestAnalyzer** — Analyzes test code to extract test scenarios, assertions, and setup patterns.

**TestAssertion** — A single assertion extracted from a test (type, expected, actual).

**TestCase** — A test case for validating implementation in
