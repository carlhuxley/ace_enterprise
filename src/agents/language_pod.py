"""
LanguagePod protocol — language-agnostic interface for TDD execution pods.

Each pod implements RED → GREEN → REFACTOR for one target language.
The LEARN phase (playbook bullets, ensemble voting) remains in the harness.

See docs/adr/002-language-pod-interface.md for design rationale.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class PodSpec:
    """Everything a pod needs to execute one phase."""

    feature_requirement: str
    test_file: Path
    implementation_file: Path
    cycle_number: int


@dataclass
class PhaseResult:
    """Outcome of a single phase (RED, GREEN, or REFACTOR)."""

    passed: bool
    output: str
    error: str | None = None


@dataclass
class TokenUsage:
    """Token consumption for one complete TDD cycle."""

    cycle_number: int
    input_tokens: int
    output_tokens: int


@runtime_checkable
class LanguagePod(Protocol):
    """
    Protocol for language-specific TDD execution pods.

    Implementors must execute all three phases and report token usage.
    No language specifics (file conventions, toolchain details) belong here.
    """

    def run_red(self, spec: PodSpec) -> PhaseResult:
        """Write a failing test for the given spec. Must return passed=False."""
        ...

    def run_green(self, spec: PodSpec) -> PhaseResult:
        """Write implementation code that makes the test pass."""
        ...

    def run_refactor(self, spec: PodSpec) -> PhaseResult:
        """Improve code quality while keeping tests green."""
        ...

    def token_usage(self) -> list[TokenUsage]:
        """Return per-cycle token consumption, ordered by cycle_number."""
        ...
