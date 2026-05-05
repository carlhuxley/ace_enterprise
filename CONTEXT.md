# ACE Enterprise — Domain Glossary

This file records the domain language for the ACE Enterprise project.
Use these terms exactly in code, docs, and architecture discussions.

---

## Core Concepts

**Playbook** — A persistent, versioned collection of bullets (learned patterns) scoped to a domain or model. The central knowledge store that guides generation.

**Bullet** — A single actionable piece of learned knowledge stored in a Playbook. Organised into sections: `strategies_and_hard_rules`, `code_snippets`, `troubleshooting`, `domain_knowledge`.

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

---

## Architectural Decisions (in progress)

- `AutonomousTDDAgent` is the canonical TDD entry point. `TDDAgent` is a legacy module (used only by old demo scripts) and is pending deletion.
- The GREEN phase of `AutonomousTDDAgent` uses `Generator` for playbook-guided generation and routes learned bullets through `Curator.apply_updates()` (not direct `add_bullet()`) so deduplication and token budgets apply.
