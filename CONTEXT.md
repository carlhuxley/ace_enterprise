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

**Audit** — Append-only event log. Every TDD cycle emits `CYCLE_COMPLETED` events recording which model was used, success/failure, and cycle counts. Used for model attribution and performance aggregation. Events are stored with hash chain integrity via `AuditStore`.

**LanguagePod** — Language-agnostic protocol for TDD execution. Each pod implements `run_red`, `run_green`, `run_refactor`, and `token_usage`. Implementations include `PythonLanguagePod` and `GoLanguagePod`.

**PodSpec** — Everything a pod needs to execute one phase: `feature_requirement`, `test_file`, `implementation_file`, `cycle_number`, `error_output` (feedback from a previous failed GREEN, set by TDDCycleRunner).

**PhaseResult** — Outcome of a single phase (RED, GREEN, or REFACTOR). Contains `passed` (bool), `output` (str), and optional `error` (str).

**CycleResult** — Outcome of a complete TDD cycle. Contains `success`, `feature_requirement`, `red_result`, `green_result`, `refactor_result`, `green_attempts`, `token_usage`, `error`, and `learned_bullets` (list of DeltaBullet).

**TDDCycleRunner** — Orchestrates RED → GREEN → REFACTOR for one feature. Handles GREEN retries with error feedback and aborts on security/policy failures (ForbiddenImport, SecurityBreach, Bandit gate). Optionally runs Reflector/Curator learning loop after successful cycles via `_learn()`.

**WorkerAgent** — Standalone LLM code-generation component. Separates prompt-building and LLM-calling from TDD loop orchestration. Returns raw code strings; file I/O and test execution are the caller's responsibility. Also supports fetching playbook guidance for strategies and test assertion rules.

**IncrementalPlanner** — Determines the next test increment by asking the LLM what single test to write next, given current test and implementation files and playbook guidance. Interface: `next_increment(requirement, cycle_number, ...) → TestIncrement`.

**IterativeTDDRunner** — Kent Beck-style iterative TDD loop. Uses an `IncrementalPlanner` to get the next test increment, then `TDDCycleRunner` to execute RED→GREEN→REFACTOR. Repeats until the planner signals COMPLETE or max iterations reached. Returns `IterativeResult`.

**TestIncrement** — One planned test step: contains `feature_requirement` and file path for the new test.

**IterativeResult** — Outcome of a full iterative TDD session. Contains `complete` (bool), `success` (bool), `iterations` (int), and list of `cycles` (each with cycle details).

**FeatureSpec** — Parsed representation of a Gherkin `.feature` file. Contains the feature description, scenarios, and steps. Provides `as_requirement()` to produce a single string for the TDD loop. Created by `GherkinFeatureBridge`.

**GherkinFeatureBridge** — Parses a Gherkin `.feature` file into a `FeatureSpec`. Used by `IterativeTDDRunner` to feed structured requirements into `IncrementalPlanner`.

**PodmanOrchestrator** — Stateless sidecar execution layer for the Clean Room harness. Runs code in isolated Podman containers with security breach detection via canonical hashing (SHA-256 over sorted filename+content pairs). Raises `SecurityBreachError` if the proposed hash differs from the executed hash.

**SecurityBreachError** — Raised when the code that ran in the container does not match the code that was sent (canonical hash mismatch). Indicates the container executed different code than expected.

**ContainerRunner** (Protocol) — Abstract interface for container lifecycle and pulse execution. Methods: `start()`, `stop()`, `is_alive()`, `send_pulse(files)`. Implemented by `PodmanRunner`.

**PodmanRunner** — Production ContainerRunner backed by rootless Podman. Manages container lifecycle, file transfer, and test execution with timeout and bandit security scanning.

**ImportFilter** — Scans generated code for forbidden imports (e.g., `subprocess`, `os.system`) and blocked builtin calls (e.g., `eval`, `exec`). Raises `ForbiddenImportError` if policy violates.

**ForbiddenImportError** — Security exception raised by ImportFilter when generated code contains a blocked import or builtin.

**ImportValidator** — Validates and automatically corrects import paths in generated code against the project's module structure. Uses a cached module tree to fix incorrect import paths produced by the LLM.

**ContextMap** — A mapping of source files to AST signatures (function/class definitions and their parameters). Built by `ContextMapBuilder` from existing code files. Provides `nodes_relevant_to(test_ids)` to return signatures referenced by given pytest test IDs, enabling the WorkerAgent to include relevant module context during GREEN phase.

**ExperimentLogger** — Unified logger for TDD and ML experiments. Stores experiments in PostgreSQL with fallback to SQLite (`ace_experiments.db`). Logs task, generator, environment, reflector, and curator data per cycle.

**PlaybookManager** — Core playbook operations: creation, updates, merging, and retrieval. Supports incremental delta updates, semantic deduplication, fine-grained retrieval, and token budget management. Also provides `get_bullets(section)` to return bullet content strings from all loaded playbooks.

**BulletRetriever** — Hybrid retrieval system for selecting relevant bullets from playbooks. Supports cross-model retrieval and contextual filtering (by confidence, domain, project).

**DeltaBullet** — A new bullet to add to a playbook, produced by the Curator. Contains content, section, and tags. Has a `content_hash` method for fast deduplication.

**BulletCreate** — Input schema for adding a bullet via PlaybookManager. Contains content, section, tags, and optional fields for provenance (model, provider, license) and contextual retrieval (confidence, domains, projects).

**CGR³ (Context Graph Retrieve-Rank-Reason)** — A retrieval system that scores bullets against request context across multiple dimensions (temporal validity, team locality, tech stack compatibility, project relevance, domain relevance) and issues a verdict (`APPLY`, `ASK_FIRST`, `SKIP`). Core components: `ContextGraphRetriever`, `ContextScorer`, `InstitutionalKnowledgeService`.

**InstitutionalKnowledgeService** — Central knowledge retrieval service for all code generation activities. Wraps `BulletRetriever` and `CGR³` to return guidance, anti-patterns, and context-aware suggestions.

**DistillationRouter** — Routes tasks to domain-specific distillation playbooks for cross-model knowledge transfer. Uses `DomainRegistry` to classify query domains and `Provenance` to filter bullets by supplier, license, and model origin, ensuring appropriate knowledge flow between student and teacher models.

**Provenance** — Tracks the origin of a bullet or model (name, provider, license category). Used by `DistillationRouter` to determine whether a bullet (teacher) can teach a student model based on cross-supplier proprietary rules.

**DomainRegistry** — Maintains a registry of domains and their playbook signatures. Aggregates playbook embeddings to compute domain centroids for query classification.

**PlaybookReliabilityAnalyzer** — Correlates bullet retrieval with first-pass GREEN success across TDD cycles. Computes per-bullet first-pass rates to identify which bullets most improve outcomes.

**TDDCycleAnalyzer** — Measures first-pass GREEN rate over time, split into configurable time periods, to detect improvement or regression in TDD cycle efficiency.

**BulletDeduplicator** — Handles semantic deduplication of bullets using embedding similarity (cosine distance). Supports configurable thresholds and duplicate-preservation strategies.

**BulletClusterer** — DBSCAN-based clustering for playbook bullets. Groups semantically related bullets and selects representatives by helpful ratio, centrality, or recency.

**EmbeddingService** — Generates embeddings for playbook bullets using a local sentence-transformers model. Used for semantic similarity in deduplication and retrieval. Singleton accessed via `get_embedding_service()`.

**ModuleArchitect** — Generates module-level contracts for stateful systems. Produces a `ModuleContract` containing `FunctionSpec`s, shared state, integration tests, and complexity score. Used by `ModuleTDDBuilder`.

**ContractArchitect** — Generates interface contracts from natural language requirements. Decomposes requirements into `InterfaceContract` objects and emits audit events for contract generation and decomposition.

**ContractOrchestrator** — Orchestrates contract-driven development: registers contracts, provides implementation prompts via `get_implementation_prompt()`, and validates submitted implementations against test cases.

**PolyglotTDDRunner** — Orchestrates TDD cycles across multiple `LanguagePod`s (languages) and reports token efficiency comparison. Uses a `PodFactory` to create language-specific pods.

**GoLanguagePod** — LanguagePod implementation for Go TDD cycles. Generates Go test code, compiles and runs tests with `go test` in a Podman container.

**SuccessRateCalculator** — Measures experiment success rates across experiment types, playbook versions, and time windows. Used to track improvement over time.

**CostQualityAnalyzer** — Analyzes cost-quality tradeoffs for ML model performance data. Computes cost efficiency metrics, Pareto frontiers, and suggests best model for given complexity.

**TokenEfficiencyReporter** — Computes token efficiency scores from LanguagePod run data. Generates cross-language comparisons and efficiency reports for the PolyglotTDDRunner.

**ProductionDataAnalyzer** — Analyzes quality data from experiment logs to extract model performance metrics, backfill quality scores via BlindEvaluator, and generate production reports.

**ModelAttributionTracker** — Tracks OpenRouter model attribution: records both the requested model and the actual model that served the request. Computes per-model success rates, latency, and cost metrics.

**PerformanceAggregator** — Aggregates performance metrics from the audit trail to compute success rates, latency, cost, and reliability scores per agent. Supports Bayesian estimation and regression detection via `RegressionDetector`.

**AdaptiveBroker** — Routes tasks to the best agent based on historical performance using configurable strategies (budget, balanced, Pareto). Falls back to a default agent when no history exists.

**CapabilityRegistry** — Anonymous registry of agent capabilities with proficiency ratings. Used by `BrokerAdvisor` to recommend agents by capability fit.

**RegressionDetector** — Tracks quality scores by (model_id, version) and detects regressions between consecutive versions using CUSUM change-point detection. Fires `RegressionAlert` when a regression is detected.

**BlindEvaluator** — Evaluates submissions without disclosing which agent produced them. Supports rubric-based scoring for code, tests, documentation, and analysis using domain-specific rubrics (e.g., `CodeGenerationRubric`, `TestWritingRubric`).

**AuditClient** — Write-only client for emitting audit events. Supports remote (HTTP via `AuditStore`) and local (SQLite) backends, plus a `NoOpAuditClient` for testing.

**AuditStore** — Append-only audit event store with hash chain integrity. Stores events in PostgreSQL and supports querying, chain verification, and statistics.

**AuditDashboard** — Dashboard for analyzing audit data: computes agent performance, cost analysis, task type strengths, and optimal team suggestions. Supports benchmark comparison.

**RedundancyPreChecker** — Pre-checks proposed tests for redundancy against existing tests before the RED phase. Uses keyword extraction and synonym mapping to detect implicit coverage.

**TestReviewAgent** — Validates test quality after writing in the RED phase. Checks test structure, naming, assertions, and edge cases. Can use LLM for deep analysis. Returns `TestReviewResult` with a quality score.

**TDDFailureRecorder** — Records TDD failures with full context and automatically adds troubleshooting bullets to the playbook. Part of the self-healing automation.

**TDDLessonInjector** — Injects formatted TDD lessons into LLM prompts based on the development phase (RED, GREEN, REFACTOR). Lessons are derived from `TDDFailureRecorder` and static anti-patterns.

**LessonExtractor** — Extracts TDD lessons from resolved beads issues. Categorises failures and creates reusable lesson records.

**PlaybookEnforcer** — Enforces playbook edit ratio rules (ace-006) to maintain a high frequency of feedback compared to code changes. Checks if an edit is allowed based on session metrics.

**SessionLog** — Simple session tracker that logs file edits and test runs during a dogfooding session. Used by `PlaybookEnforcer` to compute edit-to-test ratios.

**GherkinExtractionAgent** — Reverse engineers Gherkin scenarios from existing code and tests. Extracts method signatures and test assertions to produce Gherkin feature files and step definitions.

---

## Architectural Decisions

- **Podman isolation with canonical hashing**: All generated code executes in rootless Podman containers. The `PodmanOrchestrator` computes a deterministic SHA-256 hash over the workspace files before sending; the `PodmanRunner` computes the same hash inside the container. A mismatch (`SecurityBreachError`) aborts the cycle immediately.

- **Language-agnostic LanguagePod protocol**: Each language (Python, Go) provides its own `LanguagePod` implementation that handles code generation, file I/O, and test execution. The TDD loop code (`TDDCycleRunner`, `IterativeTDDRunner`) is language-agnostic.

- **Iterative TDD via IncrementalPlanner + TDDCycleRunner**: Rather than planning all tests upfront, `IncrementalPlanner` queries the LLM for the single next test to write, given current progress. This enables adaptive, step-by-step development.

- **Security-first abort policy**: `TDDCycleRunner` treats `ForbiddenImportError`, `SecurityBreachError`, and `Bandit gate:` errors as non-retryable. Any such failure ends the cycle immediately without further attempts.

- **Learning loop after successful GREEN**: When a `Reflector` and `Curator` are provided, `TDDCycleRunner` runs the ACE pipeline (reflect → curate → apply) after each successful cycle. Learned patterns are written back to the playbook for future cycles.

- **Experiment persistence with PostgreSQL/SQLite fallback**: `ExperimentLogger` tries PostgreSQL first; if unavailable, it falls back to a local SQLite file so that TDD cycles are never lost.

- **PlaybookManager file-based persistence**: Playbooks are stored as JSON files in `data/playbooks/`. The manager loads all on startup and saves on each write (unless auto-save is disabled for batch operations).

- **Generator retrieval modes**: The Generator supports both model-specific retrieval (single playbook) and cross-model hybrid retrieval (primary playbook + domain-related playbooks from other models), controlled by `settings.retrieval_mode`.

- **Bullet deduplication with embedding fallback**: `PlaybookManager` uses exact-match deduplication by default, with a placeholder for future semantic similarity checking via embeddings. The `BulletDeduplicator` class provides a dedicated semantic deduplication interface.

- **WorkerAgent as prompt builder**: `WorkerAgent` encapsulates all prompt construction and LLM calling. It accepts `PodSpec`, error feedback, and optional AST context map; returns raw code strings. File I/O remains the caller's (`LanguagePod`) responsibility.

- **CGR³ context-aware retrieval**: Bullets are scored against request context (temporal, team, tech stack, project, domain) and a verdict is issued (`APPLY`, `ASK_FIRST`, `SKIP`). This enables fine-grained, context-sensitive knowledge application. Used by `InstitutionalKnowledgeService` for all code generation queries.

- **Distillation Router for cross-model knowledge**: A `DistillationRouter` routes tasks to domain-specific distillation playbooks, filtering bullets by provenance (model supplier, license) to ensure appropriate knowledge transfer between models. This prevents proprietary knowledge from leaking across suppliers.

- **Reliability analysis as a feedback loop**: `PlaybookReliabilityAnalyzer` and `TDDCycleAnalyzer` compute first-pass GREEN rates per bullet and over time, enabling data-driven refinement of playbook quality and TDD process improvement.

- **GherkinFeatureBridge for iterative TDD**: `IterativeTDDRunner` uses `GherkinFeatureBridge` to parse `.feature` files into `FeatureSpec` objects, feeding structured requirements to the planner.

- **ContextMap for AST-aware generation**: `WorkerAgent` uses `ContextMap` to provide the LLM with function signatures and imports from existing code during the GREEN phase, reducing integration errors.

- **PodFactory for polyglot TDD**: `PolyglotTDDRunner` uses a `PodFactory` to create language-specific `LanguagePod` instances, enabling the same TDD loop across Python, Go, and other languages. Token efficiency is reported via `TokenEfficiencyReporter`.

- **Redundancy pre-check before RED**: `RedundancyPreChecker` compares proposed tests against existing tests using keyword extraction and synonym mapping to avoid writing redundant tests.

- **Test review after RED**: `TestReviewAgent` validates test quality after writing, scoring structure, naming, assertions, and edge cases before proceeding to GREEN.

- **TDD lesson injection into prompts**: `TDDLessonInjector` formats lessons from past failures captured by `TDDFailureRecorder` and injects them into LLM prompts per phase to avoid repeating mistakes.

- **TDDFailureRecorder self-healing**: Records failures and automatically adds troubleshooting bullets to the playbook via `PlaybookManager`, reducing future failure rates.

- **Edit-to-test ratio enforcement**: `PlaybookEnforcer` enforces a maximum edit-to-test ratio during dogfooding sessions tracked by `SessionLog`, ensuring high feedback frequency.

- **PostgreSQL audit store with hash chain**: `AuditStore` stores events immutably with SHA-256 hash chain verification, supporting append-only storage and integrity checking. `AuditClient` provides a write-only client with local and remote backends.

- **Performance aggregator for adaptive routing**: `PerformanceAggregator` feeds metrics into `AdaptiveBroker`, which routes tasks to the best-performing agent using configurable strategies (budget, balanced, Pareto). `CapabilityRegistry` and `BrokerAdvisor` support anonymous capability-based recommendations.

- **Blind evaluation with domain rubrics**: `BlindEvaluator` scores outputs without agent identity, using rubric-based evaluation for code (`CodeGenerationRubric`), tests (`TestWritingRubric`), documentation (`DocumentationRubric`), and analysis (`AnalysisRubric`).

- **Model attribution tracking**: `ModelAttributionTracker` records both the requested and actual model (from OpenRouter) for accurate per-model performance metrics. Used by `ProductionDataAnalyzer` and `CostQualityAnalyzer` to drive cost-aware routing.

- **Contract-driven development**: `ContractArchitect` and `ContractOrchestrator` enable contract-driven development alongside TDD. Contracts are generated from requirements, then used to validate implementations. `ModuleArchitect` extends this to stateful modules with shared state and integration tests.
