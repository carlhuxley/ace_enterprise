"""
LanguagePod protocol — language-agnostic interface for TDD execution pods.

Each pod implements RED → GREEN → REFACTOR for one target language.
The LEARN phase (playbook bullets, ensemble voting) remains in the harness.

See docs/adr/002-language-pod-interface.md for design rationale.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from src.analytics.token_efficiency import TokenUsage  # re-export

__all__ = ["PodSpec", "PhaseResult", "TokenUsage", "LanguagePod"]


@dataclass
class PodSpec:
    """Everything a pod needs to execute one phase."""

    feature_requirement: str
    test_file: Path
    implementation_file: Path
    cycle_number: int
    error_output: str = ""  # feedback from a previous failed GREEN, set by TDDCycleRunner
    gherkin_context: str | None = None  # full feature file text when driving from Gherkin
    # ace_enterprise#64: additional EXISTING files a coordinated GREEN-phase
    # edit must also touch, beyond implementation_file -- e.g. a small change
    # that spans an enum in one module and a method using it in another.
    # Empty by default, so every existing single-file caller is unaffected.
    # Support is pod-specific (currently PythonLanguagePod, patch-mode only);
    # a pod that doesn't support it should treat a non-empty list as an
    # error, not silently ignore it.
    extra_target_files: list[Path] = field(default_factory=list)


@dataclass
class PhaseResult:
    """Outcome of a single phase (RED, GREEN, or REFACTOR)."""

    passed: bool
    output: str
    error: str | None = None
    # Deterministic reformatting of submitted files (e.g. gofmt for Go),
    # populated when the underlying toolchain auto-formats. None otherwise.
    formatted_files: dict[str, str] | None = None
    # Playbook bullet IDs retrieved for this phase's generation (GREEN/patch
    # strategy bullets). Only populated by pods that route through a
    # WorkerAgent-style bullet retrieval; None for pods that don't track it.
    retrieved_bullet_ids: list[str] | None = None


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
