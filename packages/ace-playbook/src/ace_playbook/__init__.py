"""ACE playbook: pattern storage, CGR³ retrieval, and self-optimizing knowledge base."""

from src.playbook.manager import PlaybookManager
from src.playbook.retrieval import BulletRetriever
from src.playbook.postgres_adapter import PostgresPlaybookAdapter
from src.retrieval.cgr3_retriever import ContextGraphRetriever
from src.retrieval.service import InstitutionalKnowledgeService, get_knowledge_service

__all__ = [
    "PlaybookManager",
    "BulletRetriever",
    "PostgresPlaybookAdapter",
    "ContextGraphRetriever",
    "InstitutionalKnowledgeService",
    "get_knowledge_service",
]
