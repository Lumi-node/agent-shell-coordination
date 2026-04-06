"""High-level API for autonomous agents to coordinate commands.

This module will be fully implemented in issue-08-agent-coordinator.
For now, it provides a stub that allows imports to succeed.
"""

from typing import List
from mat.execution.command_executor import ExecutionResult


class AgentCoordinator:
    """
    High-level API for autonomous agents to coordinate commands.

    Placeholder implementation for issue-01-project-setup.
    Full implementation in issue-08-agent-coordinator.
    """

    def __init__(
        self,
        agent_id: str,
        heartbeat_interval_seconds: int = 10
    ) -> None:
        """Create coordinator instance for this agent.

        Args:
            agent_id: Unique identifier for this agent
            heartbeat_interval_seconds: How often to send heartbeat (default 10)

        Raises:
            ValueError: If agent_id is empty or None
        """
        if not agent_id:
            raise ValueError("agent_id cannot be empty")

        self._agent_id = agent_id
        self._heartbeat_interval = heartbeat_interval_seconds

    def execute(
        self,
        command: str,
        timeout_seconds: int = 60
    ) -> ExecutionResult:
        """Execute a command with automatic lock management.

        Args:
            command: Shell command string to execute
            timeout_seconds: Max time for command execution (default 60)

        Returns:
            ExecutionResult with exit code, stdout, stderr, duration, locks_held

        Raises:
            ValueError: If command is empty or None
        """
        raise NotImplementedError("Full implementation in issue-08")

    def set_env(self, var_name: str, value: str) -> None:
        """Set an environment variable shared across all agents.

        Args:
            var_name: Environment variable name (e.g., "PATH", "PYTHONPATH")
            value: Value to set

        Raises:
            ValueError: If var_name is empty or None
        """
        if not var_name:
            raise ValueError("var_name cannot be empty")

    def get_env(self, var_name: str) -> str:
        """Get an environment variable from the shared registry.

        Args:
            var_name: Environment variable name

        Returns:
            Value of environment variable, or empty string if not set
        """
        return ""

    def list_agents(self) -> List[str]:
        """List all currently active agents.

        Returns:
            List of active agent_ids (agents that heartbeated within 30 seconds)
        """
        return []

    def shutdown(self) -> None:
        """Gracefully shutdown this agent.

        Side effects:
        - Deregisters agent from registry
        - Stops heartbeat thread
        - Does NOT release locks (those auto-release after timeout)
        """
        pass
