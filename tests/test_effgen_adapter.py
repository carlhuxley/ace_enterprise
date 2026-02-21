"""Tests for effGen MCP adapter - connects small models to ACE."""
import pytest


class TestEffGenAgentConfig:
    """Tests for effGen agent configuration."""

    def test_config_has_endpoint(self):
        """Should have MCP endpoint for effGen instance."""
        from src.broker.effgen_adapter import EffGenAgentConfig

        config = EffGenAgentConfig(
            agent_ref="effgen-qwen-001",
            endpoint="http://localhost:8001",
            model_name="Qwen/Qwen2.5-Coder-7B"
        )

        assert config.endpoint == "http://localhost:8001"
        assert config.model_name == "Qwen/Qwen2.5-Coder-7B"

    def test_config_declares_capabilities(self):
        """Should declare capabilities with proficiency."""
        from src.broker.effgen_adapter import EffGenAgentConfig

        config = EffGenAgentConfig(
            agent_ref="effgen-qwen-001",
            endpoint="http://localhost:8001",
            model_name="Qwen/Qwen2.5-Coder-7B",
            capabilities={"python": 0.85, "testing": 0.7}
        )

        assert config.capabilities["python"] == 0.85


class TestEffGenAdapter:
    """Tests for EffGenAdapter."""

    def test_register_agent(self):
        """Should register effGen agent with capability registry."""
        from src.broker.effgen_adapter import EffGenAdapter, EffGenAgentConfig
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        adapter = EffGenAdapter(registry)

        config = EffGenAgentConfig(
            agent_ref="effgen-qwen-001",
            endpoint="http://localhost:8001",
            model_name="Qwen/Qwen2.5-Coder-7B",
            capabilities={"python": 0.85, "testing": 0.7}
        )

        adapter.register_agent(config)

        # Should be in registry
        agents = registry.find_by_capability("python", min_proficiency=0.8)
        assert "effgen-qwen-001" in agents

    def test_register_multiple_agents(self):
        """Should register multiple effGen agents."""
        from src.broker.effgen_adapter import EffGenAdapter, EffGenAgentConfig
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        adapter = EffGenAdapter(registry)

        adapter.register_agent(EffGenAgentConfig(
            agent_ref="effgen-qwen-001",
            endpoint="http://localhost:8001",
            model_name="Qwen/Qwen2.5-Coder-7B",
            capabilities={"python": 0.85}
        ))
        adapter.register_agent(EffGenAgentConfig(
            agent_ref="effgen-llama-001",
            endpoint="http://localhost:8002",
            model_name="meta-llama/Llama-3.1-8B",
            capabilities={"python": 0.8, "go": 0.7}
        ))

        agents = registry.find_by_capability("python")
        assert len(agents) == 2

    def test_get_agent_endpoint(self):
        """Should retrieve endpoint for registered agent."""
        from src.broker.effgen_adapter import EffGenAdapter, EffGenAgentConfig
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        adapter = EffGenAdapter(registry)

        adapter.register_agent(EffGenAgentConfig(
            agent_ref="effgen-qwen-001",
            endpoint="http://localhost:8001",
            model_name="Qwen/Qwen2.5-Coder-7B",
            capabilities={"python": 0.85}
        ))

        endpoint = adapter.get_endpoint("effgen-qwen-001")
        assert endpoint == "http://localhost:8001"


class TestEffGenTaskExecution:
    """Tests for task execution via effGen."""

    def test_create_task_request(self):
        """Should create MCP-formatted task request."""
        from src.broker.effgen_adapter import EffGenAdapter, EffGenAgentConfig, TaskRequest
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        adapter = EffGenAdapter(registry)

        request = TaskRequest(
            task_id="task-001",
            task_type="code_generation",
            prompt="Write a function to calculate fibonacci",
            context={"language": "python"}
        )

        # Should be serializable for MCP
        as_dict = request.to_mcp_params()
        assert as_dict["task_id"] == "task-001"
        assert as_dict["prompt"] is not None

    def test_parse_task_response(self):
        """Should parse MCP response from effGen."""
        from src.broker.effgen_adapter import TaskResponse

        # Simulate effGen MCP response
        mcp_response = {
            "task_id": "task-001",
            "output": "def fibonacci(n): ...",
            "tokens_used": 150,
            "success": True
        }

        response = TaskResponse.from_mcp_response(mcp_response)

        assert response.task_id == "task-001"
        assert response.output is not None
        assert response.success is True


class TestEffGenMultiAgent:
    """Tests for multi-agent effGen instances."""

    def test_register_multi_agent_instance(self):
        """Should support multi-agent effGen (team) as single registration."""
        from src.broker.effgen_adapter import EffGenAdapter, EffGenAgentConfig
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        adapter = EffGenAdapter(registry)

        # Multi-agent effGen team registered as one agent
        config = EffGenAgentConfig(
            agent_ref="effgen-team-alpha",
            endpoint="http://localhost:8010",
            model_name="multi-agent",  # indicates team
            capabilities={"python": 0.95, "testing": 0.95, "docs": 0.9},
            is_multi_agent=True,
            team_members=["qwen-7b", "llama-8b", "mistral-7b"]
        )

        adapter.register_agent(config)

        # Should appear as single agent with combined capabilities
        agents = registry.find_by_capability("python", min_proficiency=0.9)
        assert "effgen-team-alpha" in agents


class TestEffGenHealthCheck:
    """Tests for health checking effGen instances."""

    def test_check_agent_health(self):
        """Should check if effGen agent is healthy."""
        from src.broker.effgen_adapter import EffGenAdapter, EffGenAgentConfig
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        adapter = EffGenAdapter(registry)

        adapter.register_agent(EffGenAgentConfig(
            agent_ref="effgen-qwen-001",
            endpoint="http://localhost:8001",
            model_name="Qwen/Qwen2.5-Coder-7B",
            capabilities={"python": 0.85}
        ))

        # Without actual connection, should return unknown
        health = adapter.check_health("effgen-qwen-001")
        assert health.status in ["healthy", "unhealthy", "unknown"]
