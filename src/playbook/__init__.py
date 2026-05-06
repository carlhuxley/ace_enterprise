"""Playbook — versioned collections of learned bullets."""

from src.playbook.manager import PlaybookManager
from src.playbook.retrieval import BulletRetriever
from src.playbook.postgres_adapter import PostgresPlaybookAdapter

__all__ = ["PlaybookManager", "BulletRetriever", "PostgresPlaybookAdapter"]
