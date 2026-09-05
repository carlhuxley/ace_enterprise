"""
MetricBound — generic physical-invariant extraction for SimulationPod.

Decoupled from any specific physical scenario (peg-in-hole, fruit-picking
grip force, trajectory following, deburring, ...): a Gherkin spec names its
own metrics by whatever words it uses ("radial error", "grip force",
"tracking error"), and a SimulationScenario plugin (see
src/agents/simulation_scenario.py) reports metrics under those same names at
run time. Neither this module nor SimulationOracle needs to know what any
given metric physically means.
"""
import re
from dataclasses import dataclass
from typing import Literal

__all__ = ["MetricBound", "extract_invariants"]

Operator = Literal["<=", "<", ">=", ">", "=="]
Scope = Literal["instantaneous", "final", "integral"]


@dataclass(frozen=True)
class MetricBound:
    """One physical acceptance criterion, e.g. 'peak_force <= 12.0 (instantaneous)'.

    scope="instantaneous" -- checked every step; any single violation fails the run.
    scope="final"         -- a convergence target: success requires the metric to
                              satisfy the bound by some point within `within_steps`.
    scope="integral"      -- checked once at the end, against the metric's value
                              accumulated (summed) over the whole run.
    """

    metric: str
    operator: Operator
    threshold: float
    scope: Scope
    within_steps: int | None = None


_NUM = r"(-?\d+(?:\.\d+)?)"
_KEYWORD = r"(?:given|when|then|and|but)"

# "Then <metric> must never exceed <value>" -- instantaneous upper bound.
_UPPER_RE = re.compile(
    rf"{_KEYWORD}\s+(?:the\s+)?(.+?)\s+must\s+never\s+exceed\s+{_NUM}", re.IGNORECASE,
)
# "And <metric> must maintain >= <value>" -- instantaneous lower bound.
_LOWER_RE = re.compile(
    rf"{_KEYWORD}\s+(?:the\s+)?(.+?)\s+must\s+maintain\s*>=\s*{_NUM}", re.IGNORECASE,
)
# "And final <metric> must reach <= <value> within <steps>" -- convergence target.
_CONVERGENCE_RE = re.compile(
    rf"{_KEYWORD}\s+final\s+(.+?)\s+must\s+reach\s*<=\s*{_NUM}\s+within\s+(\d+)(?:\s*steps?)?",
    re.IGNORECASE,
)


def _clean_metric_name(raw: str) -> str:
    return re.sub(r"\s+", "_", raw.strip().lower())


def extract_invariants(gherkin_text: str | None) -> list[MetricBound]:
    """Parse every metric bound declared in a Gherkin scenario's steps.

    Returns one MetricBound per matched clause -- a scenario may declare any
    number of metrics, over any physical task. Text that matches no pattern
    is ignored; callers needing a fallback should use the target
    SimulationScenario's own default_invariants().
    """
    if not gherkin_text:
        return []

    bounds: list[MetricBound] = []
    for match in _UPPER_RE.finditer(gherkin_text):
        bounds.append(MetricBound(
            metric=_clean_metric_name(match.group(1)),
            operator="<=",
            threshold=float(match.group(2)),
            scope="instantaneous",
        ))
    for match in _LOWER_RE.finditer(gherkin_text):
        bounds.append(MetricBound(
            metric=_clean_metric_name(match.group(1)),
            operator=">=",
            threshold=float(match.group(2)),
            scope="instantaneous",
        ))
    for match in _CONVERGENCE_RE.finditer(gherkin_text):
        bounds.append(MetricBound(
            metric=_clean_metric_name(match.group(1)),
            operator="<=",
            threshold=float(match.group(2)),
            scope="final",
            within_steps=int(match.group(3)),
        ))
    return bounds
