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

**PlaybookManager** — Core playbook operations: creation, updates, merging, and retrieval. Supports incremental delta updates, semantic deduplication, fine-grained retrieval, and token budget management. Also provides `get_bullets(section)` to return bullet content strings from all loaded playbooks.

**BulletRetriever** — Hybrid retrieval system for selecting relevant bullets from playbooks. Supports cross-model retrieval and contextual filtering.

**DeltaBullet** — A new bullet to add to a playbook, produced by the Curator. Contains content, section, and tags. Has a `content_hash` method for fast deduplication.

**PodSpec** — Everything a pod needs to execute one phase: feature requirement, test file path
