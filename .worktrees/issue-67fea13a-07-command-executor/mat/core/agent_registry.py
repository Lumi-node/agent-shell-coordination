"""Agent membership and heartbeat tracking for multi-agent coordination."""

import threading
import time
from typing import List


class AgentRegistry:
    """
    Maintains live agent membership and automatic timeout.

    An agent is "active" if it has called heartbeat() within the last
    timeout_seconds. After timeout expires, agent is silently removed from
    list_active() and all its locks are orphaned (to be auto-released by
    FileLockManager).

    Thread-safe: all methods acquire internal lock.
    """

    def __init__(self) -> None:
        """Initialize empty registry with internal lock."""
        self._agents: dict[str, tuple[str, float]] = {}
        # agent_id -> (session_token, last_heartbeat_timestamp)
        self._lock: threading.Lock = threading.Lock()

    def register(self, agent_id: str, session_token: str) -> bool:
        """
        Register a new agent.

        Args:
            agent_id: Unique agent identifier (e.g., "agent-A", "refactorer")
            session_token: Secret token for this agent session (not used in Phase 1,
                          but reserved for Phase 2 authentication)

        Returns:
            True if agent registered successfully

        Raises:
            ValueError: If agent_id is empty or None

        Idempotent: Registering same agent_id twice resets heartbeat timestamp
                   and replaces session_token.
        """
        if not agent_id:
            raise ValueError("agent_id cannot be empty or None")

        with self._lock:
            self._agents[agent_id] = (session_token, time.time())
        return True

    def heartbeat(self, agent_id: str) -> bool:
        """
        Reset agent's last-seen timestamp to now.

        Agents should call this periodically (recommend every 10 seconds) to prove
        they're alive. If agent crashes without calling shutdown(), its heartbeat
        stops and agent is removed from list_active() after 30 seconds.

        Args:
            agent_id: Agent to heartbeat

        Returns:
            True if heartbeat succeeded

        Raises:
            ValueError: If agent_id is not registered

        Thread-safe with list_active() and deregister().
        """
        if not agent_id:
            raise ValueError("agent_id cannot be empty or None")

        with self._lock:
            if agent_id not in self._agents:
                raise ValueError(f"agent_id '{agent_id}' is not registered")

            session_token, _ = self._agents[agent_id]
            self._agents[agent_id] = (session_token, time.time())
        return True

    def list_active(self, timeout_seconds: int = 30) -> List[str]:
        """
        Return list of agents that heartbeated within timeout_seconds.

        Agents older than timeout_seconds are NOT returned and are silently
        removed from internal state. If an agent has not called heartbeat()
        in 30 seconds, it is not in this list and its locks are eligible for
        auto-release.

        Args:
            timeout_seconds: Only return agents whose last heartbeat was
                            within this many seconds ago (default 30)

        Returns:
            List of active agent_ids, sorted alphabetically for determinism

        Note: This method has side effect of removing expired agents from
              internal state. Caller should expect list size to shrink as
              agents age out.
        """
        current_time = time.time()

        with self._lock:
            # Identify agents older than timeout_seconds
            expired_agents = []
            for agent_id, (_, last_heartbeat) in self._agents.items():
                if current_time - last_heartbeat > timeout_seconds:
                    expired_agents.append(agent_id)

            # Remove expired agents from registry
            for agent_id in expired_agents:
                del self._agents[agent_id]

            # Return active agents sorted alphabetically
            active_agents = sorted(self._agents.keys())

        return active_agents

    def deregister(self, agent_id: str) -> bool:
        """
        Mark agent as gracefully offline. Remove from registry immediately.

        After calling deregister(), agent cannot heartbeat again (will raise ValueError).
        Agent should call this during shutdown() to signal "I'm done, reclaim my locks".

        Args:
            agent_id: Agent to deregister

        Returns:
            True if agent was registered and removed
            False if agent was already deregistered (idempotent)

        Raises:
            ValueError: If agent_id is empty or None
        """
        if not agent_id:
            raise ValueError("agent_id cannot be empty or None")

        with self._lock:
            if agent_id in self._agents:
                del self._agents[agent_id]
                return True
            return False
