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

**AuditCheckpoint** — External anchor for the audit hash chain (`src/audit/checkpoint.py`, ADR 003). `AuditStore.verify_full_chain()` only proves internal self-consistency — it can't detect a wholesale rewrite by anyone with audit-DB write access, since the check has nothing outside the table to compare against. A checkpoint snapshots the chain tip (latest `event_id` + `event_hash`) into `data/audit_checkpoints.jsonl`; because the hash chain is cumulative, matching a checkpoint later proves the entire prefix up to that point is unchanged. **Only meaningful if checkpoint commits are actually pushed** to a git remote the audit-DB credential doesn't control (`scripts/audit_checkpoint.py create|verify`) — a checkpoint that's only ever written locally provides no protection at all, since the same attacker who can rewrite the DB can just as easily rewrite the local file.

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

**DriftDetector** — Detects inadvertent changes to target files during a TDD session. Used by `FileLockContext` to ensure the agent only modifies files it was told to modify.

**EfficiencyReport** — Full token efficiency report, surfaced under the `token_efficiency` key. Contains per-language scores and cross-language comparisons.

**EnsembleLearner** — Orchestrates multiple models learning in parallel. Each model runs Generator → Reflector → Curator, then votes on proposed bullets. Supports cross-voting, deliberation, and configurable voting strategies.

**EnsembleResult** — Complete result from an ensemble learning session. Contains approved, rejected, and pending bullets, plus duration and summary.

**EnvironmentFeedback** — Feedback from the task execution environment. Contains result (SUCCESS/FAILED), actual output, expected output, feedback/error messages, and test report.

**EvaluationRubric** — Abstract base class for domain-specific scoring rubrics. Defines dimensions, scoring logic, and aggregation.

**ExperimentLogger** — Unified logger for TDD and ML experiments. Stores experiments in PostgreSQL (with SQLite fallback) using the ACE architecture: Task, Generator, Environment, Reflector, Curator.

**FeatureSpec** — Parsed representation of a Gherkin .feature file. Contains feature name, description, and scenarios. Produced by `GherkinFeatureBridge`.

**FileLockContext** — Context manager that locks target files during a TDD session and detects inadvertent drift (changes to files outside the lock set). Raises `InadvertentDriftError` if drift is detected on exit.

**ForbiddenImportError** — Raised when generated code contains imports from a blocklist (e.g., `os`, `subprocess`, `shutil`). Detected by `ImportFilter` before code reaches the container.

**Generator** — ACE pipeline module. Executes tasks using playbook-guided LLM generation. Retrieves relevant bullets, builds prompts with playbook context, and tracks bullet usage and feedback.

**GeneratorOutput** — Output from the Generator module. Contains trajectory (reasoning), solution, bullets used, bullet feedback, latency, and token usage.

**GherkinExtractionAgent** — Reverse-engineers Gherkin scenarios from existing code and tests. Uses `CodeAnalyzer` and `TestAnalyzer` for deterministic extraction, with an optional LLM polish pass.

**GherkinFeatureBridge** — Parses a Gherkin .feature file into a `FeatureSpec`. Used by `IterativeTDDRunner` for Gherkin-driven TDD mode.

**GoLanguagePod** — LanguagePod implementation for Go TDD cycles. Uses a Go harness container with `gosec` for security scanning.

**GoRunner** — PodmanRunner pre-configured for the Go harness image. Runs `go test` with `gosec` security scanning.

**HumanDecisionInterface** — Interface for human decision-making in agent routing. Provides full context (agent profiles, costs, capabilities) and records human assignment decisions.

**ImportFilter** — Checks generated code for forbidden imports (e.g., `os`, `subprocess`, `shutil`) and blocked builtins (e.g., `eval`, `exec`, `__import__`). Also detects dynamic imports via `importlib`.

**ImportValidator** — Validates and corrects import paths in generated code. Builds a module cache from the project root and can auto-fix invalid imports.

**IncrementalPlanner** — Determines the next test increment to write by asking the LLM what single test should be written next. Supports both planner-driven and Gherkin-driven modes.

**InstitutionalKnowledgeService** — Central knowledge retrieval service for all code generation activities. Provides guidance for TDD cycles, implementation, and anti-patterns.

**InterfaceContract** — Defines what needs to be implemented: function signature, input/output schemas, test cases, and fixtures. Used by `ContractOrchestrator`.

**IterativeResult** — Outcome of a full iterative TDD session. Contains `complete`, `success`, `iterations`, and `cycles` (list of `CycleResult`).

**IterativeTDDRunner** — Kent Beck-style RED→GREEN→REFACTOR loop. Plans increments via `IncrementalPlanner`, executes cycles via a LanguagePod, and supports Gherkin-driven mode.

**LanguagePod** — Protocol for language-specific TDD execution pods. Each pod implements `run_red`, `run_green`, `run_refactor`, and `token_usage`. Implementations: `PythonLanguagePod`, `TypeScriptLanguagePod`, `GoLanguagePod`.

**LanguageRunResult** — Outcome of a full RED→GREEN→REFACTOR run for one language. Contains success, token usage, and error information.

**LanguageScore** — Token efficiency metrics for one language's run. Contains tokens per cycle, total tokens, and efficiency score.

**LessonExtractor** — Extracts TDD lessons from resolved beads issues. Categorizes failures and produces structured lessons for prompt injection.

**LLMClient** — Unified LLM client supporting multiple providers (OpenAI, Anthropic, DeepSeek, Together AI, OpenRouter, Ollama, vLLM). Handles API key management, provider selection, and response parsing.

**LLMQuotaExhaustedError** — Raised when the provider reports the API key has no credit/quota left.

**LocalAuditClient** — Audit client that writes directly to a local SQLite database. Used for development/testing without a PostgreSQL audit store.

**MarkdownImporter** — Imports knowledge from markdown files into playbook bullets. Parses markdown headings as sections and list items as bullets.

**MLExperimentKnowledge** — Knowledge base for ML experiments. Integrates with MLflow run tracking to store decisions and patterns from ML training runs.

**ModelAttributionTracker** — Tracks OpenRouter model attribution in performance metrics. Records completions with model ID, provider, task type, and quality scores.

**ModelFamilyMetrics** — Aggregated metrics for a model family (e.g., all `qwen/` models). Computes success rate and average quality score across the family.

**ModelMetrics** — Aggregated performance metrics for a model. Contains success rate, average quality score, and task-type breakdowns.

**ModelPerformance** — Performance metrics for a single model in the ensemble. Tracks proposal success rate and agreement rate with final consensus.

**ModelProfile** — Strength/weakness profile derived from per-model task-type metrics. Used by `PerformanceAggregator` for routing decisions.

**ModuleArchitect** — Generates module-level contracts for stateful systems. Considers shared state, database schemas, and inter-module dependencies.

**ModuleContract** — Contract for an entire module with shared state. Contains function specs, shared state definition, and integration tests.

**ModuleTDDBuilder** — Builds module implementations using TDD methodology. Iterates over function specs, building each via TDD-style cycles.

**NoOpAuditClient** — No-op audit client for testing or when audit is disabled. Accepts events but discards them.

**PerformanceAggregator** — Aggregates performance metrics from the audit trail. Computes success rates, reliability scores, latency-quality reports, and regression alerts per agent.

**PhaseResult** — Outcome of a single phase (RED, GREEN, or REFACTOR). Contains `passed`, `output`, `error`, and optional `formatted_files`.

**Playbook** — A collection of learned knowledge organized into sections. Each playbook has a domain, version, and metadata. Persisted as JSON files in `data/playbooks/`.

**PlaybookEnforcer** — Enforces playbook rules like ace-006 (high-frequency feedback). Checks edit ratios against configured limits.

**PlaybookManager** — Core playbook operations: creation, updates, merging, and retrieval. Supports incremental delta updates, semantic deduplication, token budget management, and file-based persistence.

**PlaybookMetadata** — Metadata for a playbook: domain, base model, total tokens, total bullets.

**PlaybookQA** — Q&A system that answers coding questions using playbook knowledge. Supports single-model and ensemble answers.

**PlaybookReliabilityAnalyzer** — Correlates bullet retrieval with first-pass GREEN outcomes. Computes `BulletReliability` for each bullet in a playbook.

**PodFactory** — Creates LanguagePod instances for a given language identifier. Used by `PolyglotTDDRunner` to instantiate pods dynamically.

**PodmanOrchestrator** — Stateless sidecar execution layer for the Clean Room harness. Verifies workspace integrity via `canonical_hash` and detects `SecurityBreachError` when `H_proposed ≠ H_executed`.

**PodmanRunner** — Production ContainerRunner implementation using rootless Podman. Manages container lifecycle, file transfer, and test execution with `--network none` isolation.

**PodRun** — Input data for one pod's execution of a feature. Contains language, feature requirement, test file, implementation file, and token usage.

**PodSpec** — Everything a pod needs to execute one phase: feature requirement, test file, implementation file, cycle number, error feedback, and optional Gherkin context.

**PolyglotRunResult** — Combined results for all languages in a polyglot TDD run. Includes per-language results and token efficiency comparison.

**PolyglotTDDRunner** — Drives a RED→GREEN→REFACTOR loop for each requested language and compares token efficiency across languages.

**PostgresACEMLflowCallback** — PostgreSQL-backed MLflow callback that stores ACE knowledge directly in the experiment_logs table.

**PostgresBulletRetriever** — PostgreSQL-backed retrieval system using pgvector for semantic search. Supports vector similarity search, cross-model retrieval, and contextual filtering.

**PostgresPlaybookAdapter** — PostgreSQL-backed playbook manager that maintains compatibility with the in-memory `PlaybookManager` interface.

**ProductionDataAnalyzer** — Analyzes quality data from existing experiment_logs. Extracts model performance metrics, backfills quality scores, and generates production reports.

**ProjectArchitecture** — Manages cached project architecture information. Provides folder structure with purposes for intelligent file placement.

**ProjectConfig** — Manages project configuration (.ace/config.yml). Supports loading, saving, and initialization of ACE configuration for a project.

**ProjectDetector** — Detects and analyzes Python project structure. Finds project root, source directory, test directory, and package manager.

**ProjectStructure** — Represents the project folder structure with purposes. Used by `ProjectAwareTDD` for intelligent file placement.

**Provenance** — Model/bullet provenance for ownership-aware matching. Tracks model name, provider, and license type. Used by `DistillationRouter` to filter training data by license compatibility.

**PulseResult** — Raw response from the container runner. Contains test output, pass/fail status, and security scan results (bandit/eslint findings).

**PythonLanguagePod** — LanguagePod implementation for Python TDD cycles. Delegates code generation to `WorkerAgent` and test execution to `PodmanOrchestrator`. Uses atomic file writes via `commit_to_disk`.

**RankedBullet** — A bullet with context-aware ranking from CGR³. Contains the bullet, context score, context gaps, and reasoning verdict.

**ReasoningVerdict** — Verdict from the Reason phase of CGR³. One of `APPLY`, `ASK_FIRST`, `SKIP`.

**RedundancyPreChecker** — Pre-checks proposed tests for redundancy before the RED phase. Uses keyword extraction and synonym matching to detect implicitly covered tests.

**Reflector** — ACE pipeline module. Analyzes task execution and extracts insights: error identification, root cause, correct approach, key insight, and code invariant. Supports iterative refinement with quality scoring.

**ReflectorOutput** — Output from the Reflector module. Contains error identification, root cause, correct approach, key insight, code invariant, bullet tags, iterations, and quality score.

**RegressionAlert** — Fired when a quality regression is detected between model versions. Contains model ID, baseline version, current version, and severity.

**RegressionDetector** — Tracks quality scores by (model_id, version) and detects regressions. Supports CUSUM change-point detection and configurable thresholds.

**RetrievalContext** — Context for the current retrieval request in CGR³. Contains temporal, team, tech stack, project, and domain context.

**RoutingResult** — Result of adaptive routing decision. Contains selected agent, confidence score, and routing mode used.

**ScoringDimension** — One measurable axis within a rubric. Has name, weight, and scoring function.

**SecurityBreachError** — Raised when `H_proposed ≠ H_executed` — the container ran different code than was sent. Detected by `PodmanOrchestrator` via `canonical_hash` verification.

**SemanticCodeAnalyzer** — Analyzes code for security-sensitive patterns: SQL injection, eval/exec usage, hardcoded secrets.

**SuccessRateCalculator** — Measures experiment success rates across the system. Computes overall rate, rate by type, rate by playbook version, and trends over time.

**TDDCycleAnalyzer** — Measures first-pass GREEN rate and whether it improves over time. Computes per-period rates and trend analysis.

**TDDCycleRunner** — Orchestrates RED → GREEN → REFACTOR for one feature. Handles GREEN retries with error feedback, aborts on security/policy failures, and supports optional learning loop (Reflector → Curator) and audit trail.

**TDDFailureRecorder** — Records TDD failures and interventions for self-improvement. Creates beads issues and adds troubleshooting bullets to the playbook.

**TDDLessonInjector** — Injects TDD lessons into agent prompts based on development phase. Retrieves lessons from experiment logs and formats them for prompt injection.

**TestAnalyzer** — Analyzes test code to extract test scenarios, assertions, and structure. Used by `GherkinExtractionAgent`.

**TestIncrement** — One planned test step in the TDD loop. Contains feature requirement, test file, implementation file, and optional Gherkin scenario reference.

**TestReviewAgent** — Reviews test quality before TDD implementation. Checks structure, naming, assertions, and edge cases. Supports LLM-based deep analysis.

**TestWritingRubric** — Evaluation rubric for test suite output. Scores edge cases, assertions, naming, and coverage.

**TokenEfficiencyReporter** — Computes token efficiency scores from LanguagePod run data. Produces per-language scores and cross-language comparisons.

**TokenUsage** — Token consumption for one complete TDD cycle. Contains cycle number, input tokens, output tokens, and model attribution (actual model, requested model, provider).

**TypeScriptLanguagePod** — LanguagePod for TypeScript TDD cycles via vitest in a rootless Podman container. Normalises file paths to `.ts` extensions.

**TypeScriptRunner** — PodmanRunner pre-configured for the TypeScript harness image. Runs vitest with eslint-plugin-security for security scanning.

**TypeScriptWorkerAgent** — Generates TypeScript code for each TDD phase. Supports fallback to a secondary LLM client and escalation after configurable retries.

**Vote** — A single model's vote on a proposed bullet. Contains model ID, vote type (APPROVE/REJECT/ABSTAIN), confidence, and reasoning.

**VoteResults** — Aggregated results from voting on multiple bullets. Contains approval percentage and per-bullet vote counts.

**VotingStrategy** — Base class for voting strategies. Implementations: `MajorityVoting`, `SupermajorityVoting`, `WeightedVoting`, `UnanimousVoting`, `EscalatingVoting`.

**WorkerAgent** — Standalone LLM code-generation component. Separates prompt-building + LLM-calling from TDD loop orchestration. Generates code for RED, GREEN, and REFACTOR phases given a PodSpec and optional context (playbook bullets, AST context map).

---

## Architectural Decisions

**ADR 001 — LanguagePod Protocol** — Each target language gets its own `LanguagePod` implementation that encapsulates all language-specific concerns (file conventions, toolchain, test runner). The TDD loop (`TDDCycleRunner`, `IterativeTDDRunner`) is language-agnostic and communicates with pods via the `LanguagePod` protocol.

**ADR 002 — Podman Clean Room** — All code execution happens inside rootless Podman containers with `--network none` and read-only workspace mounts. The `PodmanOrchestrator` verifies workspace integrity via `canonical_hash` to detect tampering. Security scanning (Bandit, eslint) runs *after* execution as a commit gate, not a pre-check.

**ADR 003 — Audit Hash Chain** — The audit log uses a SHA-256 hash chain for tamper evidence. Each event stores `prev_hash` and `event_hash`. External checkpoints (`AuditCheckpoint`) anchor the chain tip to a git repository outside the audit DB's control for meaningful integrity verification.

**ADR 004 — Playbook as File System** — Playbooks are persisted as JSON files in `data/playbooks/`. The `PlaybookManager` provides an in-memory cache with file-based persistence. PostgreSQL adapters (`PostgresPlaybookAdapter`, `PostgresBulletRetriever`) are available for production deployments.

**ADR 005 — Generator → Reflector → Curator Pipeline** — The ACE learning loop is a three-stage pipeline. Generator produces output using playbook guidance. Reflector analyzes failures and extracts insights. Curator synthesises insights into playbook bullets. Each stage is independently testable and swappable.

**ADR 006 — Cross-Model Retrieval** — Bullets can be retrieved across playbooks within the same domain. The `BulletRetriever` supports a `cross_model_hybrid` mode that combines primary and secondary playbook bullets with configurable weighting.

**ADR 007 — Content Safety Backstop** — All bullet content is screened by `screen_bullet_content()` before persistence. REJECT-tier patterns (instruction hijack, delimiter spoofing) are blocked unconditionally. FLAG-tier content gets a `needs-review` tag and reduced confidence score. Flagged content cannot be promoted by ordinary positive feedback — only human review via `clear_review_flag()` can remove the flag.

**ADR 008 — TDD Cycle Runner with Learning** — `TDDCycleRunner` supports an optional learning loop: after a successful GREEN phase, Reflector + Curator run to extract patterns and write them back to the playbook. This is decoupled from the core RED→GREEN→REFACTOR cycle and can be enabled/disabled independently.

**ADR 009 — Model Attribution in Audit** — Every audit event carries an `actor_id` that identifies the specific LLM model (e.g., `openrouter/deepseek/deepseek-v4`). This enables `PerformanceAggregator` to distinguish agents and `AdaptiveBroker` to route based on per-model performance. The fallback `_ACTOR_ID` ("tdd-agent-cycle-runner") is used only when no model_id is supplied.

**ADR 010 — Iterative TDD with Incremental Planning** — `IterativeTDDRunner` uses `IncrementalPlanner` to determine the next test increment. The planner asks the LLM what single test should be written next, supporting both free-form and Gherkin-driven modes. This enables Kent Beck-style incremental TDD where each cycle adds exactly one test.

**ADR 011 — Polyglot TDD** — `PolyglotTDDRunner` drives the same feature through multiple language pods and compares token efficiency. Each language gets its own `LanguagePod` instance, and results are aggregated into a `CrossLanguageComparison`.

**ADR 012 — File Locking for Session Integrity** — `FileLockContext` locks target files during a TDD session and detects inadvertent drift. On exit, it verifies that only the locked files were modified, raising `InadvertentDriftError` if other files changed. This prevents the agent from making unintended modifications.

**ADR 013 — Experiment Logger with Fallback** — `ExperimentLogger` tries PostgreSQL first and falls back to SQLite (`ace_experiments.db`) if the database is unavailable. This ensures TDD cycles are always persisted even without a running database.

**ADR 014 — Code Invariant in Reflector** — The Reflector extracts a `code_invariant` field: the exact Python boolean expression, function call, or code pattern that must hold for correctness. This is stored as bare code (not prose) and embedded verbatim in Curator-generated bullets to ensure precision.

**ADR 015 — Curator Bullet Parsing with Code Fence Support** — The Curator's `_parse_synthesis` method correctly handles multi-line bullet content that includes fenced code blocks. It tracks code fence state to prevent content loss when a bullet contains a code block after a colon-introduced line.

**ADR 016 — Semantic Deduplication in PlaybookManager** — `PlaybookManager._is_redundant()` uses both exact-match (cheap) and semantic similarity (via embeddings) to detect duplicate bullets. This prevents the Curator from adding semantically identical bullets that differ only in wording.
