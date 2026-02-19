"""Project integration - work with real projects instead of /tmp demos."""

from .config import ACEConfig, ProjectConfig
from .detector import ProjectDetector, ProjectInfo

__all__ = [
    'ProjectDetector',
    'ProjectInfo',
    'ProjectConfig',
    'ACEConfig',
]
