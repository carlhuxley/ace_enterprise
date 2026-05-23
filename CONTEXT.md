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

**ModuleContract** — A structured specification of a module: its functions (`FunctionSpec`), shared state, integration tests, and complexity score. Produced by `ModuleArchitect`.

**ModuleTDDBuilder** — Builds module implementations using TDD methodology. Iterates over `FunctionSpec`s from a `ModuleContract`, building each function via TDD-style cycles.

**PerformanceAggregator** — Aggregates performance metrics from the audit trail. Computes `AgentPerformanceMetrics`, `ModelProfile`, Bayesian success-rate estimates, and latency-quality reports for each agent.

**PhaseResult** — Outcome of a single TDD phase (RED, GREEN, or REFACTOR). Contains `passed` (bool), `output` (str), and optional `error` (str).

**Playbook** — A structured knowledge store organized into sections. Each section contains a list of `Bullet` objects. Persisted to JSON files in `data/playbooks/`.

**PlaybookManager** — Core playbook operations: creation, delta updates, semantic deduplication, token budget enforcement, and file-based persistence. Manages playbooks in memory and on disk.

**PlaybookReliabilityAnalyzer** — Correlates bullet retrieval with first-pass GREEN outcomes. Computes `BulletReliability` for each bullet in a playbook.

**PodSpec** — Input specification for a single TDD phase execution. Contains `feature_requirement`, `test_file`, `implementation_file`, `cycle_number`, optional `error_output` for GREEN retries, and optional `gherkin_context`.

**PodmanOrchestrator** — Stateless sidecar execution layer for the Clean Room harness. Sends code files to a container via `pulse()`, runs tests, and returns `PhaseResult`. Raises `SecurityBreachError` when the container runs different code than was sent (hash mismatch).

**PodmanRunner** — Production `ContainerRunner` backed by rootless Podman. Manages container lifecycle (start, stop, send_pulse). Computes workspace hashes for integrity verification.

**PolyglotTDDRunner** — Drives RED→GREEN→REFACTOR loops across multiple `LanguagePod` implementations for the same feature. Produces `PolyglotRunResult` with per-language outcomes and token efficiency comparison.

**PostgresACEMLflowCallback** — PostgreSQL-backed variant of `ACEMLflowCallback`. Stores decisions and patterns directly in the `experiment_logs` table instead of local JSON files.

**Provenance** — Model/bullet provenance for ownership-aware matching in `DistillationRouter`. Tracks supplier, license category, and model origin. Determines whether a teacher model's knowledge can be transferred to a student model.

**PythonLanguagePod** — `LanguagePod` implementation for Python TDD cycles. Delegates code generation to `WorkerAgent` and test execution to `PodmanOrchestrator`. Uses atomic file writes via `commit_to_disk()`.

**Reflector** — ACE pipeline module. Analyses task outcomes, extracts error patterns and root causes, tags bullets as helpful/harmful/neutral, and generates key insights. Supports iterative refinement up to N rounds. Interface: `reflect(task, generator_output, environment_feedback) → ReflectorOutput`.

**SecurityBreachError** — Raised by `PodmanOrchestrator` when the container ran different code than was sent (H_proposed ≠ H_executed). Indicates a hash chain integrity violation.

**TDDCycleAnalyzer** — Measures first-pass GREEN rate and whether it improves over time. Computes `CyclePeriod`-based trends from experiment logs.

**TDDCycleRunner** — Orchestrates one complete TDD cycle: RED → GREEN (with retry) → REFACTOR. GREEN is retried up to `max_green_attempts` times, passing previous failure output back to the pod. Security/policy failures (ForbiddenImport, SecurityBreach, Bandit gate) abort immediately without retrying. Optionally runs the ACE learning loop (Reflector → Curator) after successful cycles.

**TDDLessonInjector** — Injects TDD lessons into agent prompts based on development phase. Uses static lessons from `tdd_lessons.py` and dynamic lessons from `LessonExtractor`.

**TestIncrement** — One planned test step in the TDD loop. Contains the test name, description, and expected behavior. Produced by `IncrementalPlanner`.

**TokenEfficiencyReporter** — Computes token efficiency scores from `LanguagePod` run data. Produces `EfficiencyReport` with per-language scores and cross-language comparisons.

**TokenUsage** — Token consumption for one complete TDD cycle. Contains `cycle_number`, `input_tokens`, and `output_tokens`.

**WorkerAgent** — Standalone LLM code-generation component. Separates prompt-building and LLM-calling from TDD loop orchestration. Receives `PodSpec` and optional context (playbook bullets, AST context map) explicitly; returns code strings. Provides `generate_test()`, `generate_implementation()`, and `generate_refactor()` methods.

---

## Architectural Decisions

**ADR-001: LanguagePod Protocol** — Each target language has a `LanguagePod` implementation that handles RED, GREEN, and REFACTOR phases. The pod is responsible for code generation, execution, and token tracking. The TDD loop orchestration (`TDDCycleRunner`, `IterativeTDDRunner`) is language-agnostic and delegates to pods via the `LanguagePod` protocol.

**ADR-002: WorkerAgent as Pure Generator** — `WorkerAgent` is a pure code-generation component with no file I/O or test execution responsibility. It receives all context explicitly (PodSpec, playbook bullets, AST context map) and returns code strings. File I/O and test execution are the caller's (pod's) responsibility. This separation allows pods to control execution isolation (e.g., Podman containers) independently of generation.

**ADR-003: TDDCycleRunner with Retry and Abort** — GREEN phase retries up to `max_green_attempts` times, passing previous failure output as `error_output` in the PodSpec. Security/policy failures (ForbiddenImport, SecurityBreach, Bandit gate) abort the cycle immediately without retrying. The learning loop (Reflector → Curator) runs only after GREEN passes, ensuring there is real code to reflect on.

**ADR-004: Podman Clean Room Execution** — All test execution happens inside a Podman container via `PodmanOrchestrator`. The orchestrator sends code files as a pulse, the container runs tests, and returns results. Hash chain integrity (`canonical_hash`) ensures the container ran exactly the code that was sent. `SecurityBreachError` is raised on hash mismatch.

**ADR-005: Iterative TDD with IncrementalPlanner** — `IterativeTDDRunner` uses `IncrementalPlanner` to determine the next test increment, then delegates to `TDDCycleRunner` for execution. The planner asks the LLM what single test to write next, given current test and implementation files and playbook guidance. The loop repeats until the planner signals COMPLETE or max iterations reached.

**ADR-006: ExperimentLogger with PostgreSQL Fallback** — `ExperimentLogger` stores all TDD and ML experiments in PostgreSQL. If PostgreSQL is unavailable, it falls back to a local SQLite file (`ace_experiments.db`), ensuring TDD cycles are always persisted. The logger uses the ACE architecture (Task, Generator, Environment, Reflector, Curator) for structured experiment data.

**ADR-007: PlaybookManager with File Persistence** — `PlaybookManager` stores playbooks in memory and persists them as JSON files in `data/playbooks/`. Supports incremental delta updates, semantic deduplication, token budget enforcement, and section-based organization. Bullets include provenance metadata (model, provider, license) and contextual retrieval fields (confidence, domains, projects).

**ADR-008: Reflector with Iterative Refinement** — The `Reflector` module supports iterative refinement of analysis up to `max_refinement_rounds`. Each iteration produces a quality score; refinement stops when quality >= 0.8 or max rounds reached. The reflector tags bullets as helpful/harmful/neutral based on task outcome and generator feedback.

**ADR-009: Curator with LLM Synthesis** — The `Curator` module uses an LLM to synthesize reflector insights into delta bullets. It parses the LLM response for section-organized bullet content and applies updates via `PlaybookManager.apply_delta()`. Supports redundancy checking and token budget enforcement.

**ADR-010: Generator with Cross-Model Retrieval** — The `Generator` module supports two retrieval modes: model-specific (single playbook) and cross-model hybrid (primary + domain playbooks). Cross-model retrieval uses `BulletRetriever.retrieve_cross_model()` with configurable secondary weight. The generator builds prompts with playbook context organized by section.

**ADR-011: ImportFilter for Security** — All generated code passes through `ImportFilter` before execution. The filter blocks forbidden imports (e.g., `subprocess`, `os.system`) and dangerous builtins (e.g., `eval`, `exec`). Violations raise `ForbiddenImportError`, which triggers immediate cycle abort in `TDDCycleRunner`.

**ADR-012: Atomic File Writes** — `PythonLanguagePod` uses `commit_to_disk()` for atomic file writes: write to a `.tmp` file, then `os.replace()` to the target path. This prevents partial writes from corrupting test or implementation files during concurrent or interrupted cycles.

**ADR-013: Test Import Auto-Injection** — `PythonLanguagePod` automatically prepends `from <module_name> import *` to test files if the implementation module is not already imported. This ensures tests can reference implementation functions without explicit import management by the LLM.

**ADR-014: Token Usage Tracking via Interception** — `PythonLanguagePod` intercepts the LLM client's `generate` method to track prompt and completion tokens per cycle. Token usage is recorded as `TokenUsage` objects and reset after each phase, providing per-cycle token accounting.

**ADR-015: Default Test Assertion Rules** — `WorkerAgent` maintains a set of default test assertion rules (`_DEFAULT_TEST_RULES`) that are seeded into the playbook's `test_assertion_rules` section on first use. These rules guide the LLM to write property-based assertions instead of exact-value assertions when multiple correct outputs exist.

**ADR-016: TDDCycleRunner Learning Loop Integration** — The `TDDCycleRunner` optionally runs the ACE learning loop (Reflector → Curator) after each successful cycle. The learning loop constructs `TaskInput`, `GeneratorOutput`, and `EnvironmentFeedback` from the cycle's artifacts, calls the reflector to analyze the outcome, then the curator to synthesize delta bullets, and writes them to the playbook via `apply_updates`. Failures in the learning step are logged as warnings and do not abort the cycle.

**ADR-017: WorkerAgent Prompt Construction** — `WorkerAgent` builds phase-specific prompts internally using `_test_prompt`, `_impl_prompt`, and `_refactor_prompt`. The test prompt includes existing test code and assertion rules; the implementation prompt includes error output from previous GREEN attempts, module context from the AST context map, and playbook guidance; the refactor prompt includes the current implementation code. All prompts instruct the LLM to output only valid Python code, and `_extract_code` strips markdown fences from the response.

**ADR-018: Code Extraction with Truncation Handling** — `WorkerAgent._extract_code` handles LLM responses that may be truncated (missing closing ``` fence) by matching an unclosed code fence pattern as a fallback. This ensures partial responses from models that hit token limits still yield usable code.
