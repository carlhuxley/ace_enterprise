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

**DomainMatch** — Result of domain classification by `DomainRegistry`. Contains domain name and similarity score.

**DomainRegistry** — Registry of available domains and their playbook centroids. Used by `DistillationRouter` to classify queries.

**DriftDetector** — Detects unintended modifications to target files during a TDD session. Reports `FileDrift` and raises `InadvertentDriftError` if drift is detected.

**DriftReport** — Result of drift detection. Contains `is_clean()` and `assert_clean()` methods.

**EditCheckResult** — Result of `PlaybookEnforcer.check_can_edit()`. Indicates whether an edit is allowed based on playbook rules (e.g., ace-006 high-frequency feedback).

**EfficiencyReport** — Full token efficiency report, surfaced under the `token_efficiency` key. Produced by `TokenEfficiencyReporter`.

**EffGenAdapter** — MCP adapter for connecting effGen (small language models) to the Capability Broker. Registers agents and checks health.

**EffGenClient** — LLM client adapter for effGen local models, conforming to the `LLMClient` interface.

**EmbeddingService** — Local embedding generation using sentence-transformers. Used by PlaybookManager to compute bullet embeddings.

**EnrichedRun** — An MLflow run enriched with ACE knowledge (decisions and patterns). Produced by `MLflowKnowledgeQuery`.

**EnsembleLearner** — Orchestrates multiple models in parallel: each executes Generator → Reflector → Curator, then bullets are voted on and merged. Supports deliberation and cross-voting.

**EnsembleResult** — Complete result from an ensemble learning session. Contains `approved_bullets()`, `rejected_bullets()`, and a `summary()`.

**EnvironmentFeedback** — Feedback from task execution environment (result, expected vs actual output, test report). Used by Reflector.

**EvaluationResult** — Result of blind evaluation of a submission. Contains quality score and dimension scores.

**ExistingTest** — Represents an existing test in the codebase. Used by `RedundancyPreChecker`.

**ExperimentDecision** — Captures a decision made during ML experimentation. Contains question, decision, rationale, and outcome.

**ExperimentLogger** — Unified logger for TDD and ML experiments. Stores in PostgreSQL (fallback to SQLite). Provides `log_tdd_cycle()`, `log_ml_experiment()`, and query methods.

**ExperimentLogModel** — SQLAlchemy model for experiment logs. Contains task_data, generator_data, environment_data, reflector_data, curator_data, result, and timestamps.

**ExperimentPattern** — Cross-experiment pattern learned from multiple ML runs. Contains pattern name, description, success rate, and domain tags.

**ExtractionResult** — Result of Gherkin extraction from codebase. Contains generated Gherkin feature, scenarios, step definitions, and confidence score.

**FeatureSpec** — Parsed representation of a Gherkin .feature file. Contains `name`, `description`, and list of `ScenarioSpec`. Provides `as_requirement()`.

**FeedbackCollector** — Stores human ratings for evaluated outputs and derives blended scores and drift.

**FileDrift** — Describes a single file that has drifted (changed content) from its expected state.

**FileLockContext** — Context manager that prevents inadvertent drift of target files during a TDD session. Uses `DriftDetector` to verify on exit.

**Fixtures** — Test fixtures for setup/teardown in contract-driven development. Used by `InterfaceContract`.

**FolderInfo** — Information about a project folder (path, purpose, contains source or tests). Used by `ProjectStructure`.

**ForbiddenImportError** — Exception raised when generated code uses a blocked import or builtin. Caught by `PythonLanguagePod` to abort the phase.

**FunctionBuildResult** — Result of building one function via TDD in `ModuleTDDBuilder`.

**FunctionSpec** — Specification for a function within a module contract. Contains signature, docstring, and test hints.

**Generator** — ACE pipeline module. Executes tasks using playbook-guided LLM. Retrieves relevant bullets, builds prompts, and records trajectory/solution.

**GeneratorOutput** — Output from the Generator module. Contains `trajectory`, `solution`, `bullets_used`, `bullet_feedback`, `latency_ms`, `tokens_used`.

**GherkinExtractionAgent** — Reverse-engineers Gherkin scenarios from existing code and tests. Produces `ExtractionResult`.

**GherkinFeature** — A complete Gherkin feature with name, description, and scenarios. Produced by `GherkinExtractionAgent`.

**GherkinFeatureBridge** — Parses a Gherkin .feature file into a `FeatureSpec`. Used by `IterativeTDDRunner` for Gherkin-driven mode.

**GherkinScenario** — A Gherkin scenario to be generated, containing steps (Given, When, Then). Produced by `GherkinExtractionAgent`.

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

**InterventionRecord** — Record of a human intervention after a TDD failure. Contains experiment ID, intervention description, and timestamp.

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

**MethodSignature** — Represents a method signature extracted from code by `CodeAnalyzer`. Contains name, parameters, return type, and decorators.

**MLflowKnowledgeQuery** — Unified interface to query MLflow runs with ACE knowledge context. Returns `EnrichedRun` objects.

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

**MultiRunResult** — Aggregated result across N evaluations of the same task. Contains mean, variance, and per-run scores.

**NoOpAuditClient** — Audit client that discards events. Used for testing or when audit is disabled.

**PhaseResult** — Outcome of a single TDD phase (RED, GREEN, or REFACTOR). Contains `passed`, `output`, and optional `error`. Used by `LanguagePod` implementations.

**Playbook** — A structured knowledge store organised into sections. Contains bullet points (strategies, code snippets, troubleshooting, domain knowledge, test rules, session wins). Managed by `PlaybookManager`.

**PlaybookEnforcer** — Enforces playbook rules such as ace-006 (high-frequency feedback). Checks edit ratios against session data.

**PlaybookManager** — Core playbook operations: creation, delta updates, semantic deduplication, token budget management, and file-based JSON persistence.

**PlaybookQA** — Q&A system that answers coding questions using playbook knowledge. Supports multi-model ensemble answers.

**PlaybookReliabilityAnalyzer** — Correlates bullet retrieval with first-pass GREEN outcomes to compute per-bullet reliability.

**PlaybookRepository** — PostgreSQL-backed repository for playbooks and bullets with pgvector semantic search integration.

**PodFactory** — Creates `LanguagePod` instances for a given language identifier. Used by `PolyglotTDDRunner`.

**PodRun** — Input data for one pod's execution of a feature, used by `TokenEfficiencyReporter`.

**PodSpec** — Everything a pod needs to execute one phase: `feature_requirement`, `test_file`, `implementation_file`, `cycle_number`, `error_output`, and optional `gherkin_context`.

**PodmanOrchestrator** — Stateless sidecar execution layer for the Clean Room harness. Uses `canonical_hash` to verify execution integrity. Raises `SecurityBreachError` when the container ran different code than was sent.

**PodmanRunner** — Production `ContainerRunner` backed by rootless Podman. Supports CPU/memory constraints and test timeouts.

**PolyglotRunResult** — Combined results for all languages from `PolyglotTDDRunner`, including token efficiency comparison.

**PolyglotTDDRunner** — Drives RED→GREEN→REFACTOR across multiple `LanguagePod` implementations and compares token efficiency.

**PostgresACEMLflowCallback** — PostgreSQL-backed variant of `ACEMLflowCallback` that stores knowledge directly in the experiment_logs table.

**PostgresBulletRetriever** — PostgreSQL-based bullet retrieval using pgvector. Used as the production retriever backend.

**PostgresPlaybookAdapter** — PostgreSQL-backed playbook manager maintaining compatibility with `PlaybookManager` interface.

**ProductionDataAnalyzer** — Analyzes quality data from experiment_logs to extract model performance metrics and generate reports.

**ProductionReport** — Comprehensive production quality report from `ProductionDataAnalyzer`. Includes per-model success rates, latency, cost, and trends.

**ProjectArchitecture** — Manages cached project architecture information from the knowledge graph.

**ProjectConfig** — ACE configuration manager. Loads/saves `.ace/config.yml` and detects project layout.

**ProjectDetector** — Detects and analyzes Python project structure (root, src dir, test dir, package manager, Python version).

**ProjectInfo** — Information about a detected Python project (name, root, src/test dirs, type, version, package manager).

**ProjectStructure** — Represents the project folder structure with purposes. Used by `ProjectArchitecture` to determine file placement.

**ProposedTest** — Represents a test being proposed for the next TDD cycle. Used by `RedundancyPreChecker`.

**Provenance** — Model/bullet provenance for ownership-aware matching in distillation. Provides `can_teach()` to check license compatibility.

**PulseResult** — Raw response from the container runner, including bandit analysis.

**PythonLanguagePod** — `LanguagePod` implementation for Python TDD cycles. Uses `WorkerAgent` for code generation and `PodmanOrchestrator` for isolated execution. Performs atomic disk writes via `commit_to_disk()`.

**QualityBaseline** — Quality summary for one (model_id, version) pair. Used by `RegressionDetector`.

**RankedBullet** — A bullet with context-aware ranking from CGR³. Contains bullet, score, and verdict.

**RatePeriod** — A time period used by `SuccessRateCalculator` for trend analysis.

**ReasoningVerdict** — Verdict from the Reason phase of CGR³ (`APPLY`, `ASK_FIRST`, or `SKIP`).

**Recommendation** — A recommended agent for a task, produced by `BrokerAdvisor`. Contains agent reference, match score, and capabilities.

**RedundancyPreChecker** — Pre-checks proposed tests for redundancy before the RED phase. Extracts keywords and checks implicit coverage.

**RedundancyResult** — Result of redundancy pre-check: indicates whether a proposed test is redundant.

**Reflector** — ACE pipeline module. Analyses generator performance against environment feedback and extracts error patterns, root causes, and key insights. Supports iterative refinement rounds.

**ReflectorOutput** — Output from the Reflector module. Contains `error_identification`, `root_cause`, `correct_approach`, `key_insight`, `bullet_tags`, `iterations`, and `quality_score`.

**RegressionAlert** — Fired when a quality regression is detected by `RegressionDetector`. Contains model, versions, and score delta.

**RegressionDetector** — Tracks quality scores by (model_id, version) and detects regressions using configurable thresholds and CUSUM change-point detection.

**RepresentativeStrategy** — Strategy for selecting cluster representatives in `BulletClusterer` (by helpful_ratio, centrality, or recency).

**RetrievalContext** — Context for a CGR³ retrieval request: contains temporal, team, tech_stack, project, and domain context.

**RoutingResult** — Result of adaptive routing decision from `AdaptiveBroker`. Contains agent reference, confidence, and reasoning.

**RouterConfig** — Configuration for `DistillationRouter`: includes high/low confidence thresholds, cross-supplier proprietary flag, and cache TTL.

**RubricResult** — Aggregated result from running a rubric over one output. Contains dimension scores and total score.

**ScoringDimension** — One measurable axis within an evaluation rubric (name, weight, description).

**SecurityBreachError** — Raised by `PodmanOrchestrator` when `H_proposed ≠ H_executed` — the container ran different code than was sent.

**SemanticCodeAnalyzer** — Base class for analyzing code semantics. Sub-classes: `SQLAnalyzer`, `EvalAnalyzer`, `ExecAnalyzer`, `SecretAnalyzer`.

**SessionLog** — Tracks edits and tests in the current session for dogfooding loop visibility.

**Settings** — Application settings loaded from ACE's `.env` file. Includes database URLs, model preferences, token budgets, and feature flags.

**StepDefinition** — A step definition for Gherkin steps (Given/When/Then with pattern and function). Produced by `GherkinExtractionAgent`.

**Submission** — A submission to be evaluated by `BlindEvaluator`. Contains code, tests, documentation, and metadata.

**SuccessRateCalculator** — Measures experiment success rates across the system. Supports filtering by type, playbook version, and time windows.

**Supplier** — Model supplier/owner for provenance matching in distillation routing. Detected by `detect_supplier()`.

**TaskCompletion** — Record of a completed task with model attribution. Used by `ModelAttributionTracker`.

**TaskInput** — Task input to the Generator module. Contains `id`, `query`, `type`, `difficulty`, and `context`.

**TaskRequirements** — Requirements for a task in `BrokerAdvisor`. Contains required capabilities, minimum proficiency, and complexity.

**TDDCycleAnalyzer** — Measures first-pass GREEN rate and whether it improves over time. Computes per-period rates and trend.

**TDDCycleRunner** — Orchestrates RED → GREEN → REFACTOR for one feature. Supports GREEN retries with error feedback and aborts on security/policy failures (ForbiddenImport, SecurityBreach, Bandit gate). Optionally runs Reflector/Curator after successful cycles for learning.

**TDDFailureRecorder** — Records TDD failures and interventions for self-improvement. Creates beads issues and playbook bullets from failures.

**TDDFailureCategory** — Enum of TDD failure categories (test_design, implementation, mocking, etc.).

**TDDLesson** — A lesson learned from a TDD failure. Contains category, root cause, and lesson description.

**TDDLessonInjector** — Injects TDD lessons into agent prompts based on development phase.

**TestAnalyzer** — Analyzes test code to extract test scenarios, assertions, and structure. Used by `GherkinExtractionAgent`.

**TestAssertion** — A single assertion extracted from a test. Contains type, expected vs actual values, and location.

**TestIncrement** — One planned test step in the TDD loop. Contains description, test name, implementation file, and Gherkin scenario reference.

**TestQualityIssue** — An issue found in test quality by `TestReviewAgent`. Contains severity, type, and description.

**TestReviewAgent** — Reviews test quality before TDD implementation. Checks structure, naming, assertions, edge cases, and optionally uses LLM deep review.

**TestReviewResult** — Result of reviewing a test file. Contains score, issues, and `is_good_quality()` threshold check.

**TestScenario** — A test scenario extracted from test code by `TestAnalyzer`. Contains name, setup, action, and assertions.

**TestWritingRubric** — Evaluation rubric for test suite output. Scores edge cases, assertions, naming, and coverage.

**TokenEfficiencyReporter** — Computes token efficiency scores from `LanguagePod` run data. Produces per-language scores and cross-language comparisons.

**TokenUsage** — Token consumption for one complete TDD cycle. Contains `cycle_number`, `input_tokens`, and `output_tokens`. Re-exported from `analytics.token_efficiency`.

**TypeScriptLanguagePod** — `LanguagePod` for TypeScript TDD cycles via vitest in a rootless Podman container.

**TypeScriptRunner** — `PodmanRunner` pre-configured for the TypeScript harness image.

**TypeScriptWorkerAgent** — Generates TypeScript code for each TDD phase given a `PodSpec`.

**VersionRate** — Success rate for a specific playbook version. Used by `SuccessRateCalculator`.

**Vote** — A single model's vote on a proposed bullet. Contains voter model, vote type (approve/reject/abstain), confidence, and reasoning.

**VoteResults** — Aggregated results from voting on multiple bullets. Contains `approval_percentage()`.

**VoteType** — Enum of vote types: approve, reject, abstain.

**VotingStrategy** — Base class for ensemble voting strategies (majority, supermajority, weighted, unanimous, escalating).

**VotingSystem** — Main voting system that applies different strategies to bullet votes. Supports contested bullet detection and disagreement analysis.

**WorkerAgent** — Standalone LLM code-generation component. Separates prompt-building from TDD loop orchestration. Provides `generate_test()` for RED, `generate_implementation()` for GREEN, and `generate_refactor()` for REFACTOR. Accepts `PodSpec`, playbook bullets, and AST context map.

## Architectural Decisions

1. **TDD as the primary workflow** — All code generation follows RED→GREEN→REFACTOR cycles. `TDDCycleRunner` orchestrates individual cycles; `IterativeTDDRunner` chains multiple cycles via `IncrementalPlanner`.

2. **Three-module ACE pipeline** — Generator, Reflector, and Curator operate over each TDD cycle's outcome. The learning loop is optional and configured by passing `reflector` and `curator` parameters to `TDDCycleRunner`.

3. **Security failures abort immediately** — Forbidden imports, security breaches, and Bandit gate findings abort the cycle with no retry. This is enforced by `_is_abort()` in `TDDCycleRunner`.

4. **LanguagePod protocol** — Each target language implements `LanguagePod` (RED → GREEN → REFACTOR). The learning phase (playbook bullets, ensemble) remains in the harness. See `docs/adr/002-language-pod-interface.md`.

5. **Playbook as structured JSON store** — Playbooks persist to `data/playbooks/` as JSON files. PostgreSQL with pgvector is available as an alternative backend via `PlaybookRepository`.

6. **WorkerAgent separates generation concerns** — The `WorkerAgent` handles prompt-building and LLM calls; file I/O and test execution belong to the `LanguagePod`. This allows pods to inject language-specific rules and import validation.

7. **Validation rule system for tests** — The `test_assertion_rules` section in playbooks stores assertion contracts (e.g., property-based testing for non-deterministic outputs). These rules are injected into RED phase prompts by `WorkerAgent`.

8. **Gherkin-driven mode** — `IterativeTDDRunner` supports both planner-driven and Gherkin-driven modes. In Gherkin mode, acceptance criteria are parsed from `.feature` files and drive scenario-by-scenario development.

9. **Container isolation via Podman** — All test execution happens in rootless Podman containers. `PodmanOrchestrator` uses `canonical_hash` to verify execution integrity and detect code substitution.

10. **Experiment logging with PostgreSQL fallback** — `ExperimentLogger` prefers PostgreSQL but falls back to local SQLite (`ace_experiments.db`) when the database is unavailable, ensuring TDD cycles are always persisted.
