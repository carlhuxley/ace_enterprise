"""Project integration - work with real projects instead of /tmp demos."""

from .detector import ProjectDetector, ProjectInfo
from .config import ProjectConfig, ACEConfig

__all__ = [
    'ProjectDetector',
    'ProjectInfo',
    'ProjectConfig',
    'ACEConfig',
]
