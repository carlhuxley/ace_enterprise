# ACE Enterprise — Domain Glossary

This file records the domain language for the ACE Enterprise project.
Use these terms exactly in code, docs, and architecture discussions.

---

## Core Concepts

**Playbook** — A persistent, versioned collection of bullets (learned patterns) scoped to a domain or model. The central knowledge store that guides generation.

**Bullet** — A single actionable piece of learned knowledge stored in a Playbook. Organised into sections: `strategies_and_hard_rules`, `code_snippets`, `troubleshooting`, `domain_knowledge`, `test_assertion_rules`, `session-wins`, `global-go-bullets`.

**ACE Pipeline** — The three-module learning loop: Generator → Reflector → Curator. Generator produces output using playbook guidance; Reflector analyses failures; Curator writes insights back as bullets.

**Generator** — ACE pipeline module. Retrieves relevant bullets from the Playbook and uses them to guide LLM code generation. Interface: `execute(task, playbook_id) → GeneratorOutput`.

**Reflector** — ACE pipeline module. Analyses task failures and extracts structured insights (`error_identification`, `root_cause`, `correct_approach`, `key_insight`). Interface: `reflect(task, generator_output, environment_feedback) → ReflectorOutput`.

**Curator** — ACE pipeline module. Synthesises Reflector insights into delta bullets and applies them to the Playbook with deduplication and token-budget enforcement. Interface: `curate(reflector_output, playbook_id) → CuratorOutput`, `apply_updates(playbook_id, curator_output) → list[str]`.

**Ensemble** — Multi-model consensus system. Multiple LLMs vote on outputs; `EnsembleLearner` aggregates results and calls the ACE pipeline to commit learned patterns.

**TDD Cycle** — The four-phase loop: RED (write failing test) → GREEN (write minimal code to pass) → REFACTOR (improve quality) → LEARN (extract patterns via ACE pipeline or Ensemble).

**AutonomousTDDAgent** — The primary TDD entry point. Plans incremental tests using Ensemble, executes TDD cycles, and learns via the ACE pipeline. GREEN phase uses Generator for playbook-guided generation; retry learning routes through Curator.

**ModuleTDDBuilder** — Contract-driven TDD executor. Takes a `ModuleContract` from `ModuleArchitect` and builds each function via TDD. Emits audit events per function. Does not use the ACE pipeline directly.

**ModuleContract** — A structured specification of a module: its functions (`FunctionSpec`), shared state, integration tests, and complexity score. Produced by `ModuleArchitect`.

**Audit** — Append-only event log. Every TDD cycle emits `CYCLE_COMPLETED` events recording which model was used, success/failure, and cycle counts. Used for model attribution and performance aggregation.

**LanguagePod** — Language-agnostic protocol for TDD execution. Each pod implements `run_red`, `run_green`, `run_refactor`, and `token_usage`. Implementations include `PythonLanguagePod` and `GoLanguagePod`.

**TDDCycleRunner** — Orchestrates RED → GREEN → REFACTOR for one feature. Handles GREEN retries with error feedback and aborts on security/policy failures. Optionally runs Reflector/Curator learning loop after successful cycles.

**WorkerAgent** — Standalone LLM code-generation component. Separates prompt-building and LLM-calling from TDD loop orchestration. Returns raw code strings; file I/O and test execution are the caller's responsibility.

**PodmanOrchestrator** — Stateless sidecar execution layer for the Clean Room harness. Runs code in isolated Podman containers with security breach detection via canonical hashing.

**PodmanRunner** — Production ContainerRunner backed by rootless Podman. Manages container lifecycle and file transfer for isolated code execution.

**ExperimentLogger** — Unified logger for TDD and ML experiments. Stores experiments in PostgreSQL with fallback to SQLite. Logs task, generator, environment, reflector, and curator data per cycle.

**PlaybookManager** — Core playbook operations: creation, updates, merging, and retrieval. Supports incremental delta updates, semantic deduplication, fine-grained retrieval, and token budget management.

**BulletRetriever** — Hybrid retrieval system for selecting relevant bullets from playbooks. Supports cross-model retrieval and contextual filtering.

**DeltaBullet** — A new bullet to add to a playbook, produced by the Curator. Contains content, section, and tags. Has a `content_hash` method for fast deduplication.

**PodSpec** — Everything a pod needs to execute one phase: feature requirement, test file path, implementation file path, cycle number, and optional error feedback from a previous failed GREEN.

**PhaseResult** — Outcome of a single phase (RED, GREEN, or REFACTOR): passed boolean, output string, and optional error string.

**CycleResult** — Outcome of a complete TDD cycle: success, feature requirement, phase results, green attempts, token usage, optional error, and learned bullets.

**SecurityBreachError** — Raised when `H_proposed ≠ H_executed` — the container ran different code than was sent. Triggers immediate cycle abort.

**ForbiddenImportError** — Raised when generated code contains forbidden imports or blocked builtin calls. Triggers immediate cycle abort.

**ImportFilter** — Validates generated code against a blocklist of forbidden imports and blocked builtins.

**ContextMap** — AST-based context map that tracks function signatures and their relationships to test files. Used by WorkerAgent to provide module context during implementation generation.

**TestIncrement** — Represents one increment in a TDD cycle: test name, description, test file, and implementation file.

**TestResult** — Result of running tests: passed/failed status, output, and error.

**BulletFeedback** — Feedback on bullet usefulness from the Generator, tagged as "helpful", "harmful", or "neutral".

**EnvironmentFeedback** — Feedback from task execution environment: result (SUCCESS/FAILED), actual output, expected output, feedback/error messages, and test report.

**TaskInput** — Task input from user: id, query, type, difficulty, and optional context.

**GeneratorOutput** — Output from Generator module: trajectory (reasoning), solution, bullets used, bullet feedback, latency, and tokens used.

**ReflectorOutput** — Output from Reflector module: error identification, root cause, correct approach, key insight, bullet tags, iterations, and quality score.

**CuratorOutput** — Output from Curator module: delta bullets and reasoning.

**PlaybookMetadata** — Playbook metadata: domain, base model, total tokens, total bullets.

**BulletCreate** — Schema for creating a new bullet: content, section, tags, model provenance, confidence score, applicable domains, project IDs, team ID.

**Bullet** — Complete bullet schema with metadata: id, content, section, tags, helpful/harmful counts, timestamps, embedding, model provenance, confidence score, applicable domains, project IDs, team ID.

**ExperimentLogModel** — SQLAlchemy model for experiment logs: stores task data, generator data, environment data, reflector data, curator data, result, playbook version, timestamps.

**PlaybookRepository** — PostgreSQL repository for playbooks and bullets with pgvector integration for semantic search.

**TokenUsage** — Token consumption for one complete TDD cycle: cycle number, input tokens, output tokens.

**PodRun** — Input data for one pod's execution of a feature: language, feature requirement, token usage, success, quality score.

**LanguageScore** — Token efficiency metrics for one language's run: tokens per cycle, success rate, quality score.

**CrossLanguageComparison** — Comparison between two or more languages for the same feature: token efficiency ratios, success rate differences.

**EfficiencyReport** — Full token efficiency report, surfaced under the token_efficiency key.

**TokenEfficiencyReporter** — Computes token efficiency scores from LanguagePod run data.

**SuccessRateCalculator** — Measures experiment success rates across the system: overall rate, rate by type, rate by playbook version, trend over time.

**PlaybookReliabilityAnalyzer** — Correlates bullet retrieval with first-pass GREEN outcomes. Computes bullet reliability scores.

**TDDCycleAnalyzer** — Measures first-pass GREEN rate and whether it improves over time.

**CostQualityAnalyzer** — Analyzes cost-quality tradeoffs for ML model performance data. Computes Pareto frontiers and quality per dollar metrics.

**ModelAttributionTracker** — Tracks OpenRouter model attribution in performance metrics. Records completions with model ID, provider, task type, success, quality score, latency, and cost.

**ProductionDataAnalyzer** — Analyzes quality data from existing experiment_logs. Extracts model performance metrics and generates production quality reports.

**BlindEvaluator** — Scores outputs without knowing which agent produced them. Uses domain-specific rubrics or built-in heuristic scoring.

**EvaluationRubric** — Abstract base for domain-specific scoring rubrics. Implementations include CodeGenerationRubric, TestWritingRubric, DocumentationRubric, and AnalysisRubric.

**RubricResult** — Aggregated result from running a rubric over one output: dimension scores, weighted total score.

**ScoringDimension** — One measurable axis within a rubric: name, weight, description.

**DimensionScore** — Score awarded on a single dimension: score (0-100), weighted score.

**FeedbackCollector** — Stores human ratings and derives blended/drift scores for automated evaluation calibration.

**HumanFeedback** — A single human quality rating for an evaluated output: evaluation ID, rating (1-5), provider ID, provider role, comment, timestamp.

**AdaptiveBroker** — Routes tasks to best agent based on historical performance. Supports multiple routing modes: budget, balanced, pareto.

**PerformanceAggregator** — Aggregates performance metrics from audit trail. Computes success rates, reliability scores, Bayesian estimates, and latency-quality reports per agent.

**CapabilityRegistry** — Registry for anonymous agent capability tracking. Supports finding agents by capability and building balanced teams.

**BrokerAdvisor** — Recommends agents by capability fit. Calculates match scores between task requirements and agent capabilities.

**HumanDecisionInterface** — Interface for human decision-making in agent assignment. Provides full context and records decisions.

**RegressionDetector** — Tracks quality scores by (model_id, version) and detects regressions using CUSUM change-point detection.

**RegressionAlert** — Fired when a quality regression is detected: model ID, baseline version, current version, severity, details.

**ModelProfile** — Strength/weakness profile derived from per-model task-type metrics.

**AgentPerformanceMetrics** — Performance metrics for an agent: success rate, reliability score, variance-adjusted reliability, complexity handling.

**BayesianEstimate** — Posterior summary of a Beta-Binomial success-rate model: mean, credible interval, confidence.

**ConsensusBuilder** — Builds consensus from multiple model proposals. Clusters similar bullets and merges into best representatives.

**VotingSystem** — Main voting system that can apply different strategies: majority, supermajority, weighted, unanimous, escalating.

**Vote** — A single model's vote on a proposed bullet: model ID, vote type (approve/reject/abstain), confidence, reasoning.

**ConsensusBullet** — A proposed bullet with voting metadata: content, section, votes, approval rate, contested status.

**EnsembleResult** — Complete result from ensemble learning session: approved bullets, rejected bullets, pending bullets, duration, model performance.

**ModelPerformance** — Track individual model's performance in ensemble: proposal success rate, agreement rate.

**DistillationRouter** — Routes tasks to domain-specific distillation playbooks. Supports provenance-aware filtering and prompt-level distillation.

**Provenance** — Model/bullet provenance for ownership-aware matching. Detects supplier and license category.

**DomainRegistry** — Registry of available domains and their playbook signatures. Classifies queries to domains by similarity to domain centroids.

**BulletClusterer** — DBSCAN-based clustering for playbook bullets. Supports multiple representative selection strategies.

**BulletCluster** — A cluster of semantically related bullets: size, average helpful ratio, models represented.

**ClusteringResult** — Result of DBSCAN clustering operation: clusters, coverage by model.

**BulletDeduplicator** — Handles semantic deduplication of bullets using embedding similarity.

**ContextGraphRetriever** — CGR³: Context Graph Retrieve-Rank-Reason. Context-aware bullet retrieval with lineage tracking and verdict explanation.

**ContextScorer** — Scores bullets against request context across multiple dimensions: temporal, team, tech stack, project, domain.

**InstitutionalKnowledgeService** — Central knowledge retrieval service for all code generation activities. Provides guidance for TDD cycles and implementation.

**RetrievalContext** — Context for the current retrieval request: project, team, tech stack, domain, temporal constraints.

**RankedBullet** — A bullet with context-aware ranking from CGR³: bullet, score, context score, verdict, lineage.

**ReasoningVerdict** — Verdict from the Reason phase of CGR³: APPLY, ASK_FIRST, SKIP.

**ContextGap** — Describes a gap in context that affects pattern applicability: dimension, severity, description.

**KnowledgeResponse** — Response from the InstitutionalKnowledgeService: ranked bullets, questions for ASK_FIRST patterns.

**GherkinFeatureBridge** — Parses a Gherkin .feature file into a FeatureSpec for use as a feature requirement.

**FeatureSpec** — Parsed representation of a Gherkin .feature file: feature name, scenarios, background. Has `as_requirement()` method.

**ScenarioSpec** — One Gherkin scenario with its step lines.

**GherkinExtractionAgent** — Reverse engineers Gherkin scenarios from existing code and tests. Produces GherkinFeature objects.

**CodeAnalyzer** — Analyzes Python code to extract structure and APIs: classes, functions, signatures.

**TestAnalyzer** — Analyzes test code to extract test scenarios: test functions, assertions, setup/teardown.

**PolyglotTDDRunner** — Orchestrates RED→GREEN→REFACTOR across multiple LanguagePods for the same feature. Compares token efficiency across languages.

**PodFactory** — Creates LanguagePod instances for a given language identifier.

**GoLanguagePod** — LanguagePod implementation for Go TDD cycles.

**GoStepGenerator** — Generates Go step definitions for Gherkin scenarios.

**ContractArchitect** — Generates contracts from natural language requirements. Emits CONTRACT_GENERATED and CONTRACT_DECOMPOSED audit events.

**ContractDecomposer** — Breaks user specs into interface contracts. Produces ContractSpec objects.

**ContractOrchestrator** — Orchestrates contract-driven development: registers contracts, manages implementations, validates against contracts.

**InterfaceContract** — Defines what needs to be implemented: function signatures, test cases, fixtures.

**ContractSpec** — Contract specification loaded from YAML: functions, test cases, fixtures.

**ModuleArchitect** — Generates module-level contracts for stateful systems. Produces ModuleContract with FunctionSpecs and IntegrationTests.

**FunctionSpec** — Specification for a function within a module: name, parameters, return type, description, test cases.

**IntegrationTest** — Integration test that exercises multiple functions within a module.

**ModuleBuildResult** — Result of building complete module via TDD: function results, integration test results, code.

**FunctionBuildResult** — Result of building one function via TDD: success, code, test results.

**ProjectDetector** — Detects and analyzes Python project structure: project root, source directory, test directory, project type, package manager.

**ProjectInfo** — Information about a detected Python project: name, root, src dir, test dir, type, Python version, package manager.

**ACEConfig** — ACE configuration for a project (.ace/config.yml): project name, domain, model settings, playbook settings.

**ProjectConfig** — Manages project configuration loading, saving, and initialization.

**DecisionRecord** — Architectural Decision Record for a feature: title, status, context, decision, consequences, alternatives.

**PlaybookQA** — Q&A system that answers coding questions using playbook knowledge. Supports single-model and ensemble answers.

**QAAnswer** — Answer to a coding question with playbook context: answer, confidence, bullets used, models used.

**MarkdownImporter** — Import knowledge from markdown files into playbook bullets. Parses markdown by headings into structured bullets.

**PlaybookEnforcer** — Enforces playbook rules like ace-006 (high-frequency feedback). Checks edit ratios against session logs.

**SessionLog** — Simple session tracker for dogfooding loop visibility. Logs edits and test runs.

**FileLockContext** — Context manager that detects inadvertent file drift during TDD cycles. Raises InadvertentDriftError if files change unexpectedly.

**DriftDetector** — Detects file drift by comparing current file hashes against snapshots taken at context entry.

**ImportValidator** — Validates and corrects import paths in generated code. Builds module cache from project structure.

**ContextMapBuilder** — Builds ContextMap from source files by parsing AST signatures.

**ASTSignature** — Compact representation of a function or class signature: name, parameters, return type, file path, line number.

**FileSignatures** — All AST signatures extracted from a single file.

**LLMClient** — Unified LLM client supporting multiple providers: OpenAI, Anthropic, DeepSeek, Together AI, OpenRouter, Ollama, vLLM.

**EffGenClient** — LLM client adapter for effGen local models.

**EmbeddingService** — Local embedding generation using sentence-transformers.

**EffGenAdapter** — Adapter for integrating effGen instances with Capability Broker.

**TaskRequest** — Task request in MCP format for effGen agents.

**TaskResponse** — Response from an effGen task execution.

**ACEMLflowCallback** — Callback to capture ACE knowledge during MLflow experiments. Logs decisions and patterns.

**PostgresACEMLflowCallback** — MLflow callback that stores knowledge in PostgreSQL via ExperimentLogger.

**MLExperimentKnowledge** — Knowledge base for ML experiments: decisions, patterns, integration with MLflow run tracking.

**ExperimentDecision** — Captures a decision made during ML experimentation: question, decision, rationale, alternatives, outcome.

**ExperimentPattern** — Cross-experiment pattern learned from multiple runs: name, description, when to apply, implementation, success rate.

**MLflowKnowledgeQuery** — Unified interface to query MLflow runs with ACE knowledge context.

**EnrichedRun** — MLflow run enriched with ACE knowledge: decisions, patterns, recommendations.

**TDDFailureRecorder** — Records TDD failures and interventions for self-improvement. Creates beads issues and adds troubleshooting bullets to playbook.

**FailureContext** — Context about a TDD failure for recording: task, error, test code, implementation code, attempts.

**InterventionRecord** — Record of intervention after TDD failure: experiment ID, intervention description, timestamp.

**TDDFailureCategory** — Categories of TDD failures for analysis: test_design, implementation, mocking, environment, etc.

**TDDLesson** — A lesson learned from a TDD failure: category, root cause, lesson, test name, timestamp.

**LessonExtractor** — Extracts TDD lessons from resolved beads issues.

**TDDLessonInjector** — Injects TDD lessons into agent prompts based on development phase.

**TestReviewAgent** — Validates test quality before implementation. Checks test structure, naming, assertions, and edge cases.

**TestReviewResult** — Result of reviewing a test file: issues found, quality score, critical issues.

**TestQualityIssue** — An issue found in test quality: type, severity, description, line number.

**RedundancyPreChecker** — Pre-checks proposed tests for redundancy before RED phase. Extracts keywords and checks implicit coverage.

**ExistingTest** — Represents an existing test in the codebase: name, file, function names, assertions.

**ProposedTest** — Represents a test being proposed for the next TDD cycle: name, description, assertions.

**RedundancyResult** — Result of redundancy pre-check: is_redundant, reason, similar_existing_tests.

**ProjectArchitecture** — Manages cached project architecture information from knowledge graph.

**ProjectStructure** — Represents the project folder structure with purposes for intelligent file placement.

**CodeReuseDetector** — Detects opportunities for code reuse in the project. Finds utilities, base classes, and suggests imports.

**FolderInfo** — Information about a project folder: path, purpose, keywords.

**PlaybookPostgresAdapter** — PostgreSQL-backed playbook manager that maintains compatibility with PlaybookManager interface.

**PostgresBulletRetriever** — PostgreSQL-backed retrieval system using pgvector for semantic search.

**ExperimentLog** — Complete experiment log schema with all fields for storage and retrieval.

**Checkpoint** — Versioned snapshot of a playbook with metrics for rollback support.

**CheckpointMetrics** — Performance metrics at checkpoint time: success rate, token usage, bullet count.

**RollbackRequest** — Request to rollback to a checkpoint: playbook ID, checkpoint ID, reason.

**RollbackResult** — Result of a rollback operation: success, restored checkpoint, affected bullets.

**PerformanceMetrics** — Real-time performance metrics: success rate, latency, token usage, cost.

**RegressionAlert** — Alert for performance regression: model, version, metric, severity, timestamp.

**BulletLineage** — Represents a relationship between two bullets for knowledge lineage: parent ID, child ID, relationship type, timestamp.

**BulletLineageModel** — SQLAlchemy model for tracking relationships between bullets.

**PlaybookModel** — SQLAlchemy model for playbook storage.

**BulletModel** — SQLAlchemy model for bullet storage with embedding support.

**ExperimentLogModel** — SQLAlchemy model for experiment log storage.

**CheckpointModel** — SQLAlchemy model for checkpoint storage.

**PerformanceMetricModel** — SQLAlchemy model for time-series performance metrics.

**RegressionAlertModel** — SQLAlchemy model for regression alerts.

**RollbackHistoryModel** — SQLAlchemy model for rollback audit trail.

**AuditEvent** — An immutable audit event with hash chain integrity: event type, actor, payload, timestamp, hash, previous hash.

**AuditEventCreate** — Schema for creating an audit event (client-side, before hash chain).

**AuditEventType** — Types of audit events: CYCLE_COMPLETED, CONTRACT_GENERATED, CONTRACT_DECOMPOSED, etc.

**AuditStore** — Append-only audit event store with hash chain integrity verification.

**AuditClient** — Write-only audit client for ACE agents. Supports sync and async modes.

**LocalAuditClient** — Audit client that writes directly to local SQLite database for development/testing.

**NoOpAuditClient** — No-op audit client for testing or when audit is disabled.

**AuditDashboard** — Dashboard for analyzing audit data: agent performance, cost analysis, task type strengths, team suggestions.

**AgentPerformance** — Performance metrics for an agent: success rate, task types, latency, cost.

**AgentIdentity** — Identity information for an agent (hidden from broker): name, provider, model.

**AuditQuery** — Query parameters for searching audit events: time range, event types, actors, session IDs.

**AuditResult** — Result of an audit query: events, total count, pagination.

**SubmitFeedbackRequest** — REST request schema for submitting human evaluation feedback.

**FeedbackResponse** — REST response schema for feedback submission.

**FeedbackListResponse** — REST response schema for listing feedback.

**DriftResponse** — REST response schema for drift detection results.

**Settings** — Application settings loaded from ACE's .env file: LLM provider, model, database URLs, playbook settings, retrieval settings.

**ProjectConfig (CLI)** — Loads .ace/config.yaml and auto-detects project layout for CLI operations.

---

## Architectural Decisions (in progress)

- `AutonomousTDDAgent` is the canonical TDD entry point. `TDDAgent` is a legacy module (used only by old demo scripts) and is pending deletion.
- The GREEN phase of `AutonomousTDDAgent` uses `Generator` for playbook-guided generation and routes learned bullets through `Curator.apply_updates()` (not direct `add_bullet()`) so deduplication and token budgets apply.
- `TDDCycleRunner` is the primary orchestrator for single-cycle TDD execution. It handles GREEN retries with error feedback and aborts on security/policy failures (`ForbiddenImport`, `SecurityBreach`, `Bandit gate`). The learning loop (Reflector → Curator → playbook write) is optional and runs only after GREEN passes.
- `WorkerAgent` separates prompt-building and LLM-calling from TDD loop orchestration. It returns raw code strings; file I/O and test execution are the caller's (pod's) responsibility.
- `PythonLanguagePod` has two construction paths: wrapping `AutonomousTDDAgent` (original path) or using `WorkerAgent` + `PodmanOrchestrator` (containerized path). The containerized path uses `ImportFilter` for security validation and `PodmanOrchestrator` for isolated execution with security breach detection.
- `PodmanOrchestrator` uses canonical hashing (`canonical_hash`) to detect security breaches where `H_proposed ≠ H_executed`. This triggers `SecurityBreachError` and immediate cycle abort.
- `ExperimentLogger` falls back to SQLite (`ace_experiments.db`) when PostgreSQL is unavailable, ensuring TDD cycles are always persisted.
- `PlaybookManager` uses file-based persistence (JSON files in `data/playbooks/`) with auto-save on mutations. `PlaybookRepository` provides PostgreSQL-backed persistence with pgvector for semantic search.
- The `test_assertion_rules` section in playbooks stores assertion contract rules that guide test generation. Default rules are seeded when a playbook is first created.
- `ContextMap` provides AST-based context for implementation generation, mapping test node IDs to relevant function signatures.
- The `_ensure_test_import` function in `PythonLanguagePod` automatically prepends `from <module_name> import *` to test code if the module isn't already imported, ensuring test files can reference implementation functions.
- `TokenUsage` tracking is done by intercepting the LLM client's `generate` method in both `AutonomousTDDAgent` and `WorkerAgent` paths, accumulating prompt and completion tokens per cycle.
