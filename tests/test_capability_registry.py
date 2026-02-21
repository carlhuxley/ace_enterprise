"""Tests for CapabilityRegistry - anonymous agent capability tracking."""
import pytest
from datetime import datetime


class TestAgentCapabilities:
    """Tests for AgentCapabilities dataclass."""

    def test_core_strength_is_highest_rated(self):
        """Core strength should be the highest-rated capability."""
        from src.broker.capability_registry import AgentCapabilities

        caps = AgentCapabilities(
            agent_ref="agent-001",
            capabilities={"python": 0.95, "testing": 0.7, "docs": 0.3}
        )

        assert caps.core_strength == "python"

    def test_core_strength_with_tie_picks_first_alphabetically(self):
        """When tied, pick first alphabetically for consistency."""
        from src.broker.capability_registry import AgentCapabilities

        caps = AgentCapabilities(
            agent_ref="agent-001",
            capabilities={"go": 0.9, "python": 0.9}
        )

        assert caps.core_strength == "go"

    def test_empty_capabilities_returns_none(self):
        """Empty capabilities should return None for core_strength."""
        from src.broker.capability_registry import AgentCapabilities

        caps = AgentCapabilities(
            agent_ref="agent-001",
            capabilities={}
        )

        assert caps.core_strength is None


class TestCapabilityRegistry:
    """Tests for CapabilityRegistry."""

    def test_register_capabilities(self):
        """Should register agent capabilities."""
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register("agent-001", {"python": 0.9, "testing": 0.8})

        agents = registry.find_by_capability("python")
        assert "agent-001" in agents

    def test_find_by_capability_with_min_proficiency(self):
        """Should filter by minimum proficiency."""
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register("agent-001", {"python": 0.9})
        registry.register("agent-002", {"python": 0.5})

        agents = registry.find_by_capability("python", min_proficiency=0.7)

        assert "agent-001" in agents
        assert "agent-002" not in agents

    def test_find_by_capability_returns_empty_for_unknown(self):
        """Should return empty list for unknown capability."""
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        agents = registry.find_by_capability("rust")

        assert agents == []

    def test_update_capabilities(self):
        """Should update existing agent capabilities."""
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register("agent-001", {"python": 0.7})
        registry.register("agent-001", {"python": 0.9, "go": 0.8})

        agent = registry.get("agent-001")
        assert agent.capabilities["python"] == 0.9
        assert agent.capabilities["go"] == 0.8


class TestFindBalancedTeam:
    """Tests for team formation."""

    def test_single_agent_covers_all_needs(self):
        """Single agent can satisfy all needs."""
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register("agent-001", {"python": 0.95, "testing": 0.9, "docs": 0.8})

        team = registry.find_balanced_team({"python": 0.9, "testing": 0.8, "docs": 0.6})

        assert len(team) == 1
        assert "agent-001" in team

    def test_two_agents_complement_each_other(self):
        """Two agents together cover needs neither could alone."""
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register("agent-001", {"python": 0.95, "testing": 0.7, "docs": 0.3})
        registry.register("agent-002", {"python": 0.6, "testing": 0.9, "docs": 0.8})

        team = registry.find_balanced_team({"python": 0.9, "testing": 0.8, "docs": 0.6})

        assert len(team) == 2
        assert "agent-001" in team
        assert "agent-002" in team

    def test_returns_empty_if_needs_cannot_be_met(self):
        """Return empty if no combination can meet needs."""
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register("agent-001", {"python": 0.5})

        team = registry.find_balanced_team({"rust": 0.9})

        assert team == []

    def test_prefers_smaller_teams(self):
        """Should prefer fewer agents when possible."""
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register("agent-001", {"python": 0.95, "testing": 0.9})
        registry.register("agent-002", {"python": 0.8})
        registry.register("agent-003", {"testing": 0.8})

        team = registry.find_balanced_team({"python": 0.9, "testing": 0.8})

        # agent-001 alone covers both needs
        assert len(team) == 1
        assert "agent-001" in team


class TestCapabilityStats:
    """Tests for capability statistics."""

    def test_get_capability_stats(self):
        """Should return stats about registered capabilities."""
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register("agent-001", {"python": 0.9, "testing": 0.8})
        registry.register("agent-002", {"python": 0.7, "go": 0.9})

        stats = registry.get_capability_stats()

        assert stats["python"]["agent_count"] == 2
        assert stats["python"]["avg_proficiency"] == 0.8
        assert stats["testing"]["agent_count"] == 1
        assert stats["go"]["agent_count"] == 1
