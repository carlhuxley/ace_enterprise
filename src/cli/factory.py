"""Build an AutonomousTDDAgent wired to a target project."""

from __future__ import annotations

from pathlib import Path

from src.agents.autonomous_tdd_agent import AutonomousTDDAgent
from src.agents.test_review_agent import TestReviewAgent
from src.cli.config import ProjectConfig
from src.config.settings import settings
from src.ensemble.learner import EnsembleLearner
from src.utils.llm_client import LLMClient


def build_agent(config: ProjectConfig) -> AutonomousTDDAgent:
    """Construct a fully-wired AutonomousTDDAgent for the given project config.

    Models are taken from ACE's own settings (.env). The playbook_id comes from
    config, scoping learned patterns to this project. Two-tier global/local
    retrieval will be layered in when the playbook scope module is built.
    """
    provider = settings.default_llm_provider
    model = _default_model(provider)

    llm_client = LLMClient(provider=provider, model=model)

    ensemble = EnsembleLearner(
        models=[(provider, model)],
        playbook_id=config.playbook_id,
    )

    reviewer = TestReviewAgent(llm_client=llm_client)

    return AutonomousTDDAgent(
        ensemble_learner=ensemble,
        test_reviewer=reviewer,
        project_root=config.project_root,
        test_dir=config.test_dir,
        src_dir=config.src_dir,
        max_iterations=config.max_iterations,
    )


def _default_model(provider: str) -> str:
    model_map = {
        "ollama": settings.ollama_default_model,
        "openrouter": settings.openrouter_default_model,
        "anthropic": settings.anthropic_default_model,
        "openai": settings.openai_default_model,
        "deepseek": settings.deepseek_default_model,
        "togetherai": settings.togetherai_default_model,
    }
    return model_map.get(provider, settings.ollama_default_model)
