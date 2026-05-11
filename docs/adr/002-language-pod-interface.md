# ADR 002 — LanguagePod Interface

**Status:** Accepted  
**Date:** 2026-05-11  
**Issue:** ace_enterprise-g1p

## Context

The multi-language transpilation feature (ace_enterprise-j5s, ace_enterprise-h3r) requires a
stable, language-agnostic contract between the TDD harness and each language-specific executor.
Without a formal interface, pod implementations would diverge and the token efficiency reporter
(ace_enterprise-k8t) would have no common data structure to aggregate.

## Decision

Define `LanguagePod` as a `typing.Protocol` in `src/agents/language_pod.py` with four methods:
`run_red`, `run_green`, `run_refactor`, and `token_usage`. Three supporting dataclasses
(`PodSpec`, `PhaseResult`, `TokenUsage`) carry all inputs and outputs.

## Key choices and rationale

### `PodSpec` bundles both file paths
Test file and implementation file are always needed together — RED needs to know the impl path
to generate correct imports; GREEN needs both to read and write. A single spec object prevents
the interface from changing when a phase turns out to need the other path.

### `PhaseResult` carries no token fields
Token tracking lives in `token_usage()` at cycle granularity, not per phase. The token
efficiency score (ace_enterprise-k8t) only requires cycle-level totals, and per-phase tracking
would couple every LLM call to the protocol contract.

### LEARN phase excluded from the protocol
The LEARN phase (ensemble voting, playbook bullet promotion) is harness-specific logic. A pod
should be a thin test-runner + code-generator. Keeping LEARN in the harness means pods have no
dependency on `PlaybookManager` or `EnsembleLearner`.

### `@runtime_checkable`
Allows `isinstance(pod, LanguagePod)` in tests and factory code without importing concrete types.
No performance cost at protocol definition time.

### `run_refactor` receives full `PodSpec`
`gofmt`/`go vet` only need the file path, but a Python pod using an LLM for refactoring may want
the feature description for context. Passing `PodSpec` is forward-compatible; pods that don't
need the extra context can ignore it.

### subprocess vs in-process
Pods invoke language toolchains (pytest, `go test`, `gofmt`) via subprocess. This keeps pod
implementations independent of the harness process and avoids import conflicts. Pods are
responsible for managing their own subprocess calls and capturing output.

## Consequences

- All pod implementations (Python, Go, future languages) must satisfy the `LanguagePod` protocol.
- The harness interacts with pods exclusively through `PodSpec`, `PhaseResult`, and `TokenUsage`.
- Adding a new language requires only a new class implementing four methods — no harness changes.
- The LEARN phase remains a harness concern and is not part of the protocol.
