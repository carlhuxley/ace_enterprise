"""
CGR³ (Context Graph Retrieve-Rank-Reason) Service Layer.

This module provides context-aware knowledge retrieval for ACE Enterprise.
Any code generation consumer (TDD agent, IDE plugin, CLI) can use this
service to retrieve institutional knowledge with intelligent reasoning.

Key components:
- InstitutionalKnowledgeService: Main entry point for all consumers
- ContextGraphRetriever: CGR³ pipeline implementation
- RetrievalContext: Context about the current request
- RankedBullet: Bullet with context-aware scoring and verdict

Enterprise-only feature that adds reasoning on top of semantic retrieval.
"""

from src.retrieval.cgr3_retriever import ContextGraphRetriever
from src.retrieval.schemas import (
    KnowledgeResponse,
    RankedBullet,
    ReasoningVerdict,
    RetrievalContext,
)
from src.retrieval.service import InstitutionalKnowledgeService, get_knowledge_service

__all__ = [
    # Schemas
    "RetrievalContext",
    "RankedBullet",
    "ReasoningVerdict",
    "KnowledgeResponse",
    # Retriever
    "ContextGraphRetriever",
    # Service
    "InstitutionalKnowledgeService",
    "get_knowledge_service",
]
