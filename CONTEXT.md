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

**PodSpec** — Everything a pod needs to execute one phase: `feature_requirement`, `test_file`, `implementation_file`, `cycle_number`, `error_output` (feedback from a previous failed GREEN, set by TDDCycleRunner).

**PhaseResult** — Outcome of a single phase (RED, GREEN, or REFACTOR). Contains `passed` (bool), `output` (str), and optional `error` (str).

**CycleResult** — Outcome of a complete TDD cycle. Contains `success`, `feature_requirement`, `red_result`, `green_result`, `refactor_result`, `green_attempts`, `token_usage`, `error`, and `learned_bullets` (list of DeltaBullet).

**TDDCycleRunner** — Orchestrates RED → GREEN → REFACTOR for one feature. Handles GREEN retries with error feedback and aborts on security/policy failures (ForbiddenImport, SecurityBreach, Bandit gate). Optionally runs Reflector/Curator learning loop after successful cycles via `_learn()`.

**WorkerAgent** — Standalone LLM code-generation component. Separates prompt-building and LLM-calling from TDD loop orchestration. Returns raw code strings; file I/O and test execution are the caller's responsibility.

**IncrementalPlanner** — Determines the next test increment by asking the LLM what single test to write next, given current test and implementation files and playbook guidance. Interface: `next_increment(requirement, cycle_number, ...) → TestIncrement`.

**IterativeTDDRunner** — Kent Beck-style iterative TDD loop. Uses an `IncrementalPlanner` to get the next test increment, then `TDDCycleRunner` to execute RED→GREEN→REFACTOR. Repeats until the planner signals COMPLETE or max iterations reached. Returns `IterativeResult`.

**TestIncrement** — One planned test step: contains `feature_requirement` and file path for the new test.

**IterativeResult** — Outcome of a full iterative TDD session. Contains `complete` (bool), `success` (bool), `iterations` (int), and list of `cycles` (each with cycle details).

**PodmanOrchestrator** — Stateless sidecar execution layer for the Clean Room harness. Runs code in isolated Podman containers with security breach detection via canonical hashing (SHA-256 over sorted filename+content pairs). Raises `SecurityBreachError` if the proposed hash differs from the executed hash.

**SecurityBreachError** — Raised when the code that ran in the container does not match the code that was sent (canonical hash mismatch). Indicates the container executed different code than expected.

**ContainerRunner** (Protocol) — Abstract interface for container lifecycle and pulse execution. Methods: `start()`, `stop()`, `is_alive()`, `send_pulse(files)`. Implemented by `PodmanRunner`.

**PodmanRunner** — Production ContainerRunner backed by rootless Podman. Manages container lifecycle, file transfer, and test execution with timeout and bandit security scanning.

**ImportFilter** — Scans generated code for forbidden imports (e.g., `subprocess`, `os.system`) and blocked builtin calls (e.g., `eval`, `exec`). Raises `ForbiddenImportError` if policy violates.

**ForbiddenImportError** — Security exception raised by ImportFilter when generated code contains a blocked import or builtin.

**ExperimentLogger** — Unified logger for TDD and ML experiments. Stores experiments in PostgreSQL with fallback to SQLite (`ace_experiments.db`). Logs task, generator, environment, reflector, and curator data per cycle.

**PlaybookManager** — Core playbook operations: creation, updates, merging, and retrieval. Supports incremental delta updates, semantic deduplication, fine-grained retrieval, and token budget management. Also provides `get_bullets(section)` to return bullet content strings from all loaded playbooks.

**BulletRetriever** — Hybrid retrieval system for selecting relevant bullets from playbooks. Supports cross-model retrieval and contextual filtering (by confidence, domain, project).

**DeltaBullet** — A new bullet to add to a playbook, produced by the Curator. Contains content, section, and tags. Has a `content_hash` method for fast deduplication.

**BulletCreate** — Input schema for adding a bullet via PlaybookManager. Contains content, section, tags, and optional fields for provenance (model, provider, license) and contextual retrieval (confidence, domains, projects).

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

- **Bullet deduplication with embedding fallback**: `PlaybookManager` uses exact-match deduplication by default, with a placeholder for future semantic similarity checking via embeddings.

- **WorkerAgent as prompt builder**: `WorkerAgent` encapsulates all prompt construction and LLM calling. It accepts `PodSpec`, error feedback, and optional AST context map; returns raw code strings. File I/O remains the caller's (`LanguagePod`) responsibility.
