"""
GherkinFeatureBridge — parses a Gherkin .feature file into a FeatureSpec
that PolyglotTDDRunner.run_from_feature() can consume directly.

Keeps parsing simple (no external Gherkin library): reads the Feature: title,
collects Scenario names, and counts Given/When/Then/And/But steps per scenario.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ScenarioSpec:
    """One Gherkin scenario with its step lines."""

    name: str
    steps: list[str] = field(default_factory=list)


@dataclass
class FeatureSpec:
    """Parsed representation of a Gherkin .feature file."""

    title: str
    scenarios: list[ScenarioSpec] = field(default_factory=list)
    # Other feature-file stems this one must be built after, from a
    # `@depends_on(auth, db)` tag above `Feature:`. Used by `ace tdd` to
    # order a directory of features (topological sort).
    depends_on: list[str] = field(default_factory=list)

    def as_requirement(self) -> str:
        """Return a single string suitable for use as feature_requirement."""
        if not self.scenarios:
            return self.title
        parts = ", ".join(
            f"{s.name} ({len(s.steps)} steps)" for s in self.scenarios
        )
        return f"{self.title}. Scenarios: {parts}"


_STEP_RE = re.compile(r"^(Given|When|Then|And|But)\s", re.IGNORECASE)
_SCENARIO_RE = re.compile(r"^Scenario(?:\s+Outline)?:\s*(.+)$", re.IGNORECASE)
_FEATURE_RE = re.compile(r"^Feature:\s*(.+)$", re.IGNORECASE)
# `@depends_on(auth, db)` — repeatable; contents are feature-file stems.
_DEPENDS_ON_RE = re.compile(r"@depends_on\(([^)]*)\)", re.IGNORECASE)


def _parse_depends_on(lines: list[str]) -> list[str]:
    """Collect `@depends_on(...)` stems from the tag lines above `Feature:`.

    Order-preserving, de-duplicated. Tags after `Feature:` are ignored — a
    feature's build-order dependencies belong at the top of the file.
    """
    seen: dict[str, None] = {}
    for line in lines:
        stripped = line.strip()
        if _FEATURE_RE.match(stripped):
            break
        for match in _DEPENDS_ON_RE.finditer(stripped):
            for name in match.group(1).split(","):
                name = name.strip()
                if name:
                    seen.setdefault(name, None)
    return list(seen)


def parse_depends_on(feature_path: Path) -> list[str]:
    """Read only the `@depends_on(...)` stems from a .feature file (no full parse)."""
    lines = Path(feature_path).read_text(encoding="utf-8").splitlines()
    return _parse_depends_on(lines)


class GherkinFeatureBridge:
    """Parses a Gherkin .feature file into a FeatureSpec."""

    @staticmethod
    def parse(feature_path: Path) -> FeatureSpec:
        """
        Parse feature_path and return a FeatureSpec.

        Raises:
            ValueError: if no Feature: line is found.
        """
        lines = Path(feature_path).read_text(encoding="utf-8").splitlines()

        title: str | None = None
        scenarios: list[ScenarioSpec] = []
        current: ScenarioSpec | None = None

        for line in lines:
            stripped = line.strip()

            m = _FEATURE_RE.match(stripped)
            if m:
                title = m.group(1).strip()
                continue

            m = _SCENARIO_RE.match(stripped)
            if m:
                if current is not None:
                    scenarios.append(current)
                current = ScenarioSpec(name=m.group(1).strip())
                continue

            if current is not None and _STEP_RE.match(stripped):
                current.steps.append(stripped)

        if current is not None:
            scenarios.append(current)

        if title is None:
            raise ValueError(
                f"No 'Feature:' line found in {feature_path}"
            )

        return FeatureSpec(
            title=title,
            scenarios=scenarios,
            depends_on=_parse_depends_on(lines),
        )
