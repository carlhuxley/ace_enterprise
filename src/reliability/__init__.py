"""Reliability analysis — TDD cycle health and playbook bullet effectiveness."""

import importlib

__all__ = [
    "TDDCycleAnalyzer",
    "CyclePeriod",
    "PlaybookReliabilityAnalyzer",
    "BulletReliability",
]

# Lazy (PEP 562): tdd_cycle_analyzer pulls in ExperimentLogger ->
# PlaybookRepository -> src.utils.embedding -> sentence_transformers/torch,
# a ~6s import cost. Eagerly importing both submodules here meant any
# caller that only needed PlaybookReliabilityAnalyzer (audit-log-only, no
# ExperimentLogger involved -- see playbook_analyzer.py) paid that cost too,
# every time, including once per playbook in dream_rsi's dream_runner.py.
_LAZY = {
    "TDDCycleAnalyzer": "src.reliability.tdd_cycle_analyzer",
    "CyclePeriod": "src.reliability.tdd_cycle_analyzer",
    "PlaybookReliabilityAnalyzer": "src.reliability.playbook_analyzer",
    "BulletReliability": "src.reliability.playbook_analyzer",
}


def __getattr__(name: str):
    module_path = _LAZY.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)
