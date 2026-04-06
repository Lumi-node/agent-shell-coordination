"""Unit tests for AgentRegistry."""

import threading
import time
from typing import List

import pytest

from mat.core.agent_registry import AgentRegistry


class TestRegister:
    """Tests for AgentRegistry.register()."""

    def test_register_new_agent(self) -> None:
        """Test registering a new agent returns True."""
        registry = AgentRegistry()
        result = registry.register("agent-A", "token-123")
        assert result is True

    def test_register_idempotent(self) -> None:
        """Test registering same agent twice resets timestamp."""
        registry = AgentRegistry()
        registry.register("agent-A", "token-123")
        time.sleep(0.01)
        result = registry.register("agent-A", "token-456")
        assert result is True

    def test_register_empty_agent_id_raises(self) -> None:
        """Test registering with empty agent_id raises ValueError."""
        registry = AgentRegistry()
        with pytest.raises(ValueError, match="agent_id cannot be empty"):
            registry.register("", "token-123")

    def test_register_none_agent_id_raises(self) -> None:
        """Test registering with None agent_id raises ValueError."""
        registry = AgentRegistry()
        with pytest.raises(ValueError, match="agent_id cannot be empty"):
            registry.register(None, "token-123")  # type: ignore


class TestHeartbeat:
    """Tests for AgentRegistry.heartbeat()."""

    def test_heartbeat_updates_timestamp(self) -> None:
        """Test heartbeat resets the timestamp."""
        registry = AgentRegistry()
        registry.register("agent-A", "token-123")
        time.sleep(0.01)
        result = registry.heartbeat("agent-A")
        assert result is True

    def test_heartbeat_unknown_agent_raises(self) -> None:
        """Test heartbeat on unknown agent raises ValueError."""
        registry = AgentRegistry()
        with pytest.raises(ValueError, match="is not registered"):
            registry.heartbeat("agent-unknown")

    def test_heartbeat_empty_agent_id_raises(self) -> None:
        """Test heartbeat with empty agent_id raises ValueError."""
        registry = AgentRegistry()
        with pytest.raises(ValueError, match="agent_id cannot be empty"):
            registry.heartbeat("")

    def test_heartbeat_none_agent_id_raises(self) -> None:
        """Test heartbeat with None agent_id raises ValueError."""
        registry = AgentRegistry()
        with pytest.raises(ValueError, match="agent_id cannot be empty"):
            registry.heartbeat(None)  # type: ignore


class TestListActive:
    """Tests for AgentRegistry.list_active()."""

    def test_list_active_empty_registry(self) -> None:
        """Test list_active on empty registry returns empty list."""
        registry = AgentRegistry()
        result = registry.list_active()
        assert result == []

    def test_list_active_single_agent(self) -> None:
        """Test list_active returns single registered agent."""
        registry = AgentRegistry()
        registry.register("agent-A", "token-123")
        result = registry.list_active()
        assert result == ["agent-A"]

    def test_list_active_multiple_agents_sorted(self) -> None:
        """Test list_active returns agents sorted alphabetically."""
        registry = AgentRegistry()
        registry.register("agent-C", "token-c")
        registry.register("agent-A", "token-a")
        registry.register("agent-B", "token-b")
        result = registry.list_active()
        assert result == ["agent-A", "agent-B", "agent-C"]

    def test_list_active_filters_by_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test list_active removes agents older than timeout."""
        registry = AgentRegistry()

        # Mock time.time() to control timestamp
        mock_time = 1000.0
        monkeypatch.setattr(time, "time", lambda: mock_time)

        registry.register("agent-A", "token-a")
        result = registry.list_active(timeout_seconds=30)
        assert result == ["agent-A"]

        # Advance time by 20 seconds
        mock_time = 1020.0
        monkeypatch.setattr(time, "time", lambda: mock_time)
        result = registry.list_active(timeout_seconds=30)
        assert result == ["agent-A"]

        # Advance time by 40 seconds (total 40s from registration)
        mock_time = 1040.0
        monkeypatch.setattr(time, "time", lambda: mock_time)
        result = registry.list_active(timeout_seconds=30)
        assert result == []

    def test_list_active_custom_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test list_active with custom timeout_seconds."""
        registry = AgentRegistry()

        mock_time = 1000.0
        monkeypatch.setattr(time, "time", lambda: mock_time)

        registry.register("agent-A", "token-a")
        registry.register("agent-B", "token-b")

        # Advance time by 5 seconds
        mock_time = 1005.0
        monkeypatch.setattr(time, "time", lambda: mock_time)

        # With 10 second timeout, both still active
        result = registry.list_active(timeout_seconds=10)
        assert result == ["agent-A", "agent-B"]

        # With 3 second timeout, both expired
        result = registry.list_active(timeout_seconds=3)
        assert result == []

    def test_heartbeat_timeout_30s(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test agent automatically removed from list_active() after 30s without heartbeat."""
        registry = AgentRegistry()

        mock_time = 1000.0
        monkeypatch.setattr(time, "time", lambda: mock_time)

        # Register agent
        registry.register("agent-A", "token-a")

        # Agent is active within 30 seconds
        mock_time = 1015.0
        monkeypatch.setattr(time, "time", lambda: mock_time)
        result = registry.list_active(timeout_seconds=30)
        assert "agent-A" in result

        # Agent expires after 30 seconds
        mock_time = 1031.0
        monkeypatch.setattr(time, "time", lambda: mock_time)
        result = registry.list_active(timeout_seconds=30)
        assert "agent-A" not in result

    def test_list_active_removes_expired_agents(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test list_active() has side effect of removing expired agents."""
        registry = AgentRegistry()

        mock_time = 1000.0
        monkeypatch.setattr(time, "time", lambda: mock_time)

        registry.register("agent-A", "token-a")
        registry.register("agent-B", "token-b")

        # Both agents exist
        result = registry.list_active(timeout_seconds=30)
        assert len(result) == 2

        # Advance time by 40 seconds
        mock_time = 1040.0
        monkeypatch.setattr(time, "time", lambda: mock_time)

        # Call list_active - should remove both
        result = registry.list_active(timeout_seconds=30)
        assert len(result) == 0

        # Verify they're actually removed from internal state
        # by heartbeating one - should fail
        with pytest.raises(ValueError):
            registry.heartbeat("agent-A")


class TestDeregister:
    """Tests for AgentRegistry.deregister()."""

    def test_deregister_removes_agent(self) -> None:
        """Test deregister removes agent and returns True."""
        registry = AgentRegistry()
        registry.register("agent-A", "token-123")
        result = registry.deregister("agent-A")
        assert result is True

    def test_deregister_idempotent(self) -> None:
        """Test deregister is idempotent - second call returns False."""
        registry = AgentRegistry()
        registry.register("agent-A", "token-123")
        registry.deregister("agent-A")
        result = registry.deregister("agent-A")
        assert result is False

    def test_deregister_unknown_agent_returns_false(self) -> None:
        """Test deregister on unknown agent returns False."""
        registry = AgentRegistry()
        result = registry.deregister("agent-unknown")
        assert result is False

    def test_deregister_empty_agent_id_raises(self) -> None:
        """Test deregister with empty agent_id raises ValueError."""
        registry = AgentRegistry()
        with pytest.raises(ValueError, match="agent_id cannot be empty"):
            registry.deregister("")

    def test_deregister_none_agent_id_raises(self) -> None:
        """Test deregister with None agent_id raises ValueError."""
        registry = AgentRegistry()
        with pytest.raises(ValueError, match="agent_id cannot be empty"):
            registry.deregister(None)  # type: ignore

    def test_deregister_prevents_heartbeat(self) -> None:
        """Test agent cannot heartbeat after deregister."""
        registry = AgentRegistry()
        registry.register("agent-A", "token-123")
        registry.deregister("agent-A")
        with pytest.raises(ValueError, match="is not registered"):
            registry.heartbeat("agent-A")


class TestConcurrency:
    """Tests for thread safety."""

    def test_concurrent_heartbeats(self) -> None:
        """Test concurrent heartbeats from multiple threads."""
        registry = AgentRegistry()

        # Register multiple agents
        num_agents = 5
        for i in range(num_agents):
            registry.register(f"agent-{i}", f"token-{i}")

        # Track results
        errors: List[Exception] = []
        success_count = 0
        success_lock = threading.Lock()

        def heartbeat_worker(agent_id: str, duration_seconds: float = 2.0) -> None:
            """Worker thread that sends heartbeats."""
            nonlocal success_count
            start = time.time()
            local_count = 0
            try:
                while time.time() - start < duration_seconds:
                    registry.heartbeat(agent_id)
                    local_count += 1
                    time.sleep(0.01)
                with success_lock:
                    success_count += local_count
            except Exception as e:
                errors.append(e)

        # Start heartbeat threads
        threads = []
        for i in range(num_agents):
            thread = threading.Thread(
                target=heartbeat_worker,
                args=(f"agent-{i}",),
                daemon=True
            )
            thread.start()
            threads.append(thread)

        # Also have another thread calling list_active concurrently
        def list_active_worker(duration_seconds: float = 2.0) -> None:
            """Worker thread that lists active agents."""
            start = time.time()
            try:
                while time.time() - start < duration_seconds:
                    result = registry.list_active(timeout_seconds=30)
                    assert len(result) == num_agents
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        list_thread = threading.Thread(
            target=list_active_worker,
            daemon=True
        )
        list_thread.start()
        threads.append(list_thread)

        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=5.0)

        # Verify no errors occurred
        assert len(errors) == 0
        assert success_count > 0

    def test_concurrent_register_heartbeat_deregister(self) -> None:
        """Test concurrent register, heartbeat, and deregister operations."""
        registry = AgentRegistry()
        errors: List[Exception] = []

        def worker(agent_id: str) -> None:
            """Worker that registers, heartbeats, and deregisters."""
            try:
                # Register
                registry.register(agent_id, f"token-{agent_id}")

                # Heartbeat multiple times
                for _ in range(10):
                    registry.heartbeat(agent_id)
                    time.sleep(0.001)

                # Deregister
                result = registry.deregister(agent_id)
                assert result is True

                # Second deregister should return False
                result = registry.deregister(agent_id)
                assert result is False
            except Exception as e:
                errors.append(e)

        # Start multiple worker threads
        threads = []
        for i in range(10):
            thread = threading.Thread(
                target=worker,
                args=(f"agent-{i}",),
                daemon=True
            )
            thread.start()
            threads.append(thread)

        # Wait for all threads
        for thread in threads:
            thread.join(timeout=5.0)

        # Verify no errors
        assert len(errors) == 0

        # Verify all agents are deregistered
        result = registry.list_active()
        assert result == []

    def test_concurrent_heartbeat_timeout_expiry(self) -> None:
        """Test that timeout expiry works correctly under concurrent access."""
        registry = AgentRegistry()

        # Register agents
        registry.register("agent-A", "token-a")
        registry.register("agent-B", "token-b")

        # Start thread that keeps agent-A alive with heartbeats
        shutdown_event = threading.Event()
        errors: List[Exception] = []

        def keep_alive_worker() -> None:
            """Keep agent-A alive."""
            try:
                while not shutdown_event.is_set():
                    registry.heartbeat("agent-A")
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        thread = threading.Thread(target=keep_alive_worker, daemon=True)
        thread.start()

        # Let agent-B expire
        time.sleep(0.5)

        # List active - agent-B should be gone, agent-A should still be active
        result = registry.list_active(timeout_seconds=0.3)
        assert "agent-A" in result
        assert "agent-B" not in result

        # Shutdown keep-alive thread
        shutdown_event.set()
        thread.join(timeout=1.0)

        # Verify no errors
        assert len(errors) == 0

    def test_concurrent_list_active_removes_expired(self) -> None:
        """Test that concurrent list_active calls properly remove expired agents."""
        registry = AgentRegistry()

        # Register many agents
        for i in range(20):
            registry.register(f"agent-{i}", f"token-{i}")

        results: List[List[str]] = []
        results_lock = threading.Lock()
        errors: List[Exception] = []

        def list_worker() -> None:
            """Call list_active concurrently."""
            try:
                for _ in range(20):
                    result = registry.list_active(timeout_seconds=0.05)
                    with results_lock:
                        results.append(result)
                    time.sleep(0.02)
            except Exception as e:
                errors.append(e)

        # Start multiple threads
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=list_worker, daemon=True)
            thread.start()
            threads.append(thread)

        # Wait for threads
        for thread in threads:
            thread.join(timeout=5.0)

        # Verify no errors
        assert len(errors) == 0

        # Verify that at some point all agents expire (last result should be empty)
        assert results[-1] == []
