"""EffGen MCP adapter - connects small language models to ACE.

effGen is a framework for running small language models as coding agents.
This adapter integrates effGen instances with the Capability Broker.

Key features:
- Register effGen agents with capability registry
- Track endpoints for MCP communication
- Support multi-agent effGen teams
- Health checking
"""

from dataclasses import dataclass, field
from typing import Any

from src.broker.capability_registry import CapabilityRegistry


@dataclass
class EffGenAgentConfig:
    """Configuration for an effGen agent.

    Captures endpoint, model info, and declared capabilities.
    """

    agent_ref: str
    endpoint: str  # MCP endpoint for this effGen instance
    model_name: str  # e.g., "Qwen/Qwen2.5-Coder-7B"
    capabilities: dict[str, float] = field(default_factory=dict)
    is_multi_agent: bool = False
    team_members: list[str] = field(default_factory=list)


@dataclass
class TaskRequest:
    """Task request in MCP format.

    Serializable for sending to effGen via MCP.
    """

    task_id: str
    task_type: str  # e.g., "code_generation", "testing", "review"
    prompt: str
    context: dict[str, Any] = field(default_factory=dict)

    def to_mcp_params(self) -> dict[str, Any]:
        """Serialize to MCP parameters format."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "prompt": self.prompt,
            "context": self.context,
        }


@dataclass
class TaskResponse:
    """Response from an effGen task execution.

    Parsed from MCP response.
    """

    task_id: str
    output: str
    tokens_used: int
    success: bool

    @classmethod
    def from_mcp_response(cls, response: dict[str, Any]) -> "TaskResponse":
        """Parse MCP response into TaskResponse."""
        return cls(
            task_id=response["task_id"],
            output=response.get("output", ""),
            tokens_used=response.get("tokens_used", 0),
            success=response.get("success", False),
        )


@dataclass
class HealthStatus:
    """Health status of an effGen agent."""

    status: str  # "healthy", "unhealthy", "unknown"
    last_check: str | None = None
    error: str | None = None


class EffGenAdapter:
    """Adapter for integrating effGen instances with Capability Broker.

    Handles:
    - Agent registration with capability registry
    - Endpoint management for MCP communication
    - Health checking
    """

    def __init__(self, registry: CapabilityRegistry) -> None:
        """Initialize adapter.

        Args:
            registry: Capability registry for agent registration
        """
        self._registry = registry
        self._agents: dict[str, EffGenAgentConfig] = {}

    def register_agent(self, config: EffGenAgentConfig) -> None:
        """Register an effGen agent.

        Stores config and registers capabilities with the registry.

        Args:
            config: Agent configuration
        """
        self._agents[config.agent_ref] = config

        # Register capabilities with the broker's registry
        if config.capabilities:
            self._registry.register(config.agent_ref, config.capabilities)

    def get_endpoint(self, agent_ref: str) -> str | None:
        """Get MCP endpoint for an agent.

        Args:
            agent_ref: Agent reference

        Returns:
            Endpoint URL or None if agent not found
        """
        config = self._agents.get(agent_ref)
        if config:
            return config.endpoint
        return None

    def check_health(self, agent_ref: str) -> HealthStatus:
        """Check health of an effGen agent.

        Without actual network connection, returns unknown status.

        Args:
            agent_ref: Agent reference

        Returns:
            HealthStatus with current status
        """
        if agent_ref not in self._agents:
            return HealthStatus(
                status="unknown",
                error="Agent not registered"
            )

        # Without actual MCP connection, we can't determine health
        # In production, this would make an HTTP request to the endpoint
        return HealthStatus(status="unknown")

    def get_agent_config(self, agent_ref: str) -> EffGenAgentConfig | None:
        """Get configuration for an agent.

        Args:
            agent_ref: Agent reference

        Returns:
            Agent configuration or None if not found
        """
        return self._agents.get(agent_ref)

    def list_agents(self) -> list[str]:
        """List all registered agent references."""
        return list(self._agents.keys())
