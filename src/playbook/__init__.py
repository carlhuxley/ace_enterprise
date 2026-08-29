"""Playbook — versioned collections of learned bullets."""

from src.playbook.manager import PlaybookManager
from src.playbook.postgres_adapter import PostgresPlaybookAdapter
from src.playbook.retrieval import BulletRetriever

__all__ = ["PlaybookManager", "BulletRetriever", "PostgresPlaybookAdapter"]
