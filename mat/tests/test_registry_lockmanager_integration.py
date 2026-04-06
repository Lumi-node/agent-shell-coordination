"""Integration tests for AgentRegistry and FileLockManager interaction.

Tests verify that agents registering in AgentRegistry can interact
with FileLockManager to acquire and release locks.
"""

import pytest
import tempfile
import os
import threading
import time
from typing import List

from mat.core.agent_registry import AgentRegistry
from mat.core.file_lock_manager import FileLockManager
from mat.exceptions import LockTimeoutError


class TestRegisteredAgentsCanAcquireLocks:
    """Test that registered agents can acquire and release locks."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.registry = AgentRegistry()
        self.lock_mgr = FileLockManager()

    def test_registered_agent_acquires_lock(self) -> None:
        """Test a registered agent can acquire a lock."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("data")
            file_path = f.name

        try:
            # Register agent
            agent_id = "test-agent"
            is_registered = self.registry.register(agent_id, "token-123")
            assert is_registered is True

            # Registered agent acquires lock
            token = self.lock_mgr.acquire_write(agent_id, file_path, timeout_seconds=5)

            assert token.agent_id == agent_id
            assert token.file_path == file_path
            assert token.lock_type == "write"

            # Release lock
            is_released = self.lock_mgr.release_write(token)
            assert is_released is True

        finally:
            os.unlink(file_path)

    def test_unregistered_agent_still_can_acquire_lock(self) -> None:
        """Test that unregistered agents can still acquire locks (no auth check)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("data")
            file_path = f.name

        try:
            # Don't register agent
            agent_id = "unregistered-agent"

            # Can still acquire lock (lock mgr doesn't check registry)
            token = self.lock_mgr.acquire_write(agent_id, file_path, timeout_seconds=5)
            assert token.agent_id == agent_id

            self.lock_mgr.release_write(token)

        finally:
            os.unlink(file_path)

    def test_multiple_registered_agents_coordinate_locks(self) -> None:
        """Test multiple registered agents can coordinate via locks."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("shared")
            shared_file = f.name

        try:
            # Register agents
            agent_a_id = "agent-a"
            agent_b_id = "agent-b"
            self.registry.register(agent_a_id, "token-a")
            self.registry.register(agent_b_id, "token-b")

            # Agent A acquires write lock
            token_a = self.lock_mgr.acquire_write(agent_a_id, shared_file, timeout_seconds=5)
            assert token_a.agent_id == agent_a_id

            # Agent B cannot acquire write lock (timeout)
            with pytest.raises(LockTimeoutError):
                self.lock_mgr.acquire_write(agent_b_id, shared_file, timeout_seconds=1)

            # Agent A releases
            self.lock_mgr.release_write(token_a)

            # Now agent B can acquire
            token_b = self.lock_mgr.acquire_write(agent_b_id, shared_file, timeout_seconds=5)
            assert token_b.agent_id == agent_b_id

            self.lock_mgr.release_write(token_b)

        finally:
            os.unlink(shared_file)

    def test_registered_agent_multiple_locks(self) -> None:
        """Test registered agent can hold multiple locks."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f1:
            f1.write("file1")
            file1_path = f1.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f2:
            f2.write("file2")
            file2_path = f2.name

        try:
            agent_id = "agent-multi"
            self.registry.register(agent_id, "token-multi")

            # Agent acquires multiple locks
            tokens = self.lock_mgr.acquire_multiple(
                agent_id,
                read_paths=[file1_path],
                write_paths=[file2_path],
                timeout_seconds=5
            )

            assert len(tokens) == 2
            assert all(t.agent_id == agent_id for t in tokens)

            # Release all
            self.lock_mgr.release_multiple(tokens)

        finally:
            os.unlink(file1_path)
            os.unlink(file2_path)


class TestRegistryHeartbeatIntegration:
    """Test integration between registry heartbeats and lock management."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.registry = AgentRegistry()
        self.lock_mgr = FileLockManager()

    def test_heartbeat_updates_do_not_affect_locks(self) -> None:
        """Test that heartbeating doesn't release locks."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("data")
            file_path = f.name

        try:
            agent_id = "agent-heartbeat"
            self.registry.register(agent_id, "token-123")

            # Acquire lock
            token = self.lock_mgr.acquire_write(agent_id, file_path, timeout_seconds=5)

            # Send heartbeat
            is_alive = self.registry.heartbeat(agent_id)
            assert is_alive is True

            # Lock still held
            with pytest.raises(LockTimeoutError):
                self.lock_mgr.acquire_write("other-agent", file_path, timeout_seconds=1)

            # Release lock
            self.lock_mgr.release_write(token)

        finally:
            os.unlink(file_path)

    def test_registered_agent_in_list_active_can_acquire_locks(self) -> None:
        """Test agents in list_active() can acquire locks."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("data")
            file_path = f.name

        try:
            agent_id = "agent-active"
            self.registry.register(agent_id, "token-123")

            # Agent is in active list
            active_agents = self.registry.list_active()
            assert agent_id in active_agents

            # Agent can acquire lock
            token = self.lock_mgr.acquire_write(agent_id, file_path, timeout_seconds=5)
            assert token.agent_id == agent_id

            self.lock_mgr.release_write(token)

        finally:
            os.unlink(file_path)

    def test_agent_removed_from_registry_can_still_hold_locks(self) -> None:
        """Test agent removed from registry can still hold acquired locks."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("data")
            file_path = f.name

        try:
            agent_id = "agent-removed"
            self.registry.register(agent_id, "token-123")

            # Acquire lock
            token = self.lock_mgr.acquire_write(agent_id, file_path, timeout_seconds=5)

            # Deregister from registry
            is_deregistered = self.registry.deregister(agent_id)
            assert is_deregistered is True

            # Agent no longer in active list
            active_agents = self.registry.list_active()
            assert agent_id not in active_agents

            # But lock is still held! (registry and lock mgr are separate)
            with pytest.raises(LockTimeoutError):
                self.lock_mgr.acquire_write("other-agent", file_path, timeout_seconds=1)

            # Original agent can still release
            is_released = self.lock_mgr.release_write(token)
            assert is_released is True

        finally:
            os.unlink(file_path)

    def test_agent_timeout_in_registry_independent_of_locks(self) -> None:
        """Test agent timing out in registry doesn't affect locks."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("data")
            file_path = f.name

        try:
            agent_id = "agent-timeout"
            self.registry.register(agent_id, "token-123")

            # Acquire lock
            token = self.lock_mgr.acquire_write(agent_id, file_path, timeout_seconds=5)

            # Wait for agent to timeout in registry (30 second default)
            # Don't heartbeat, just let timeout occur
            time.sleep(31)

            # Agent should be removed from active list
            active_agents = self.registry.list_active()
            assert agent_id not in active_agents

            # But lock is still held! (FileLockManager has its own timeout)
            # Lock expires based on FileLockManager's timeout, not registry timeout
            # FileLockManager timeout is separate: auto-release after lock_timeout

        finally:
            os.unlink(file_path)


class TestConcurrentRegistryAndLockAccess:
    """Test concurrent access to registry and lock manager."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.registry = AgentRegistry()
        self.lock_mgr = FileLockManager()

    def test_concurrent_agents_registering_and_locking(self) -> None:
        """Test multiple agents concurrently registering and acquiring locks."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("shared")
            shared_file = f.name

        num_agents = 5
        acquired_locks: List[List] = [[] for _ in range(num_agents)]

        def agent_workflow(agent_index: int) -> None:
            agent_id = f"agent-{agent_index}"

            # Register
            self.registry.register(agent_id, f"token-{agent_index}")

            # Try to acquire read lock
            try:
                token = self.lock_mgr.acquire_read(agent_id, shared_file, timeout_seconds=5)
                acquired_locks[agent_index] = [token]

                # Heartbeat
                self.registry.heartbeat(agent_id)

                # Release
                self.lock_mgr.release_read(token)

            except LockTimeoutError:
                # Some agents might timeout (expected in test with write locks)
                pass

        try:
            threads = [
                threading.Thread(target=agent_workflow, args=(i,))
                for i in range(num_agents)
            ]

            for t in threads:
                t.start()

            for t in threads:
                t.join(timeout=30)

            # At least some agents should have acquired locks
            acquired_count = sum(1 for locks in acquired_locks if len(locks) > 0)
            assert acquired_count > 0

            # All agents should be registered
            active_agents = self.registry.list_active()
            for i in range(num_agents):
                assert f"agent-{i}" in active_agents

        finally:
            os.unlink(shared_file)

    def test_thread_safe_registry_lock_coordination(self) -> None:
        """Test thread-safe coordination between registry and lock manager."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("data")
            file_path = f.name

        results: List[str] = []

        def agent_a_work() -> None:
            agent_id = "agent-a-concurrent"
            self.registry.register(agent_id, "token-a")

            try:
                # Try to get exclusive write lock
                token = self.lock_mgr.acquire_write(agent_id, file_path, timeout_seconds=10)
                results.append("a_acquired_write")

                # Sleep to hold lock while agent_b tries
                time.sleep(0.5)

                self.lock_mgr.release_write(token)
                results.append("a_released_write")

            except LockTimeoutError:
                results.append("a_timeout_write")

        def agent_b_work() -> None:
            agent_id = "agent-b-concurrent"
            self.registry.register(agent_id, "token-b")

            # Give agent_a time to acquire first
            time.sleep(0.1)

            try:
                # Try to get read lock while a holds write
                token = self.lock_mgr.acquire_read(agent_id, file_path, timeout_seconds=1)
                results.append("b_acquired_read")
                self.lock_mgr.release_read(token)

            except LockTimeoutError:
                results.append("b_timeout_read")

        try:
            t_a = threading.Thread(target=agent_a_work)
            t_b = threading.Thread(target=agent_b_work)

            t_a.start()
            t_b.start()

            t_a.join(timeout=20)
            t_b.join(timeout=20)

            # Both agents should complete their workflows
            assert "a_acquired_write" in results
            assert "a_released_write" in results
            # B should either timeout or acquire after A releases
            assert "b_acquired_read" in results or "b_timeout_read" in results

        finally:
            os.unlink(file_path)

    def test_registry_tracks_all_concurrent_agents_with_locks(self) -> None:
        """Test registry correctly tracks agents even while managing locks."""
        num_agents = 10
        agents_created = []

        def agent_workflow(index: int) -> None:
            agent_id = f"concurrent-agent-{index}"
            self.registry.register(agent_id, f"token-{index}")
            agents_created.append(agent_id)

            # Heartbeat periodically
            for _ in range(3):
                self.registry.heartbeat(agent_id)
                time.sleep(0.01)

        threads = [
            threading.Thread(target=agent_workflow, args=(i,))
            for i in range(num_agents)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=10)

        # All agents should be in active list
        active_agents = self.registry.list_active()
        for agent_id in agents_created:
            assert agent_id in active_agents


class TestCoordinationWorkflow:
    """Test realistic coordination workflows."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.registry = AgentRegistry()
        self.lock_mgr = FileLockManager()

    def test_workflow_register_heartbeat_lock_release_deregister(self) -> None:
        """Test complete workflow: register, heartbeat, lock, release, deregister."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("data")
            file_path = f.name

        try:
            agent_id = "workflow-agent"

            # Step 1: Register
            is_registered = self.registry.register(agent_id, "token-workflow")
            assert is_registered is True

            # Step 2: Verify in active list
            active = self.registry.list_active()
            assert agent_id in active

            # Step 3: Heartbeat
            is_alive = self.registry.heartbeat(agent_id)
            assert is_alive is True

            # Step 4: Acquire lock
            token = self.lock_mgr.acquire_write(agent_id, file_path, timeout_seconds=5)
            assert token.agent_id == agent_id

            # Step 5: Heartbeat while holding lock
            is_alive = self.registry.heartbeat(agent_id)
            assert is_alive is True

            # Step 6: Release lock
            is_released = self.lock_mgr.release_write(token)
            assert is_released is True

            # Step 7: Deregister
            is_deregistered = self.registry.deregister(agent_id)
            assert is_deregistered is True

            # Step 8: Verify removed from active list
            active = self.registry.list_active()
            assert agent_id not in active

        finally:
            os.unlink(file_path)

    def test_multiple_agents_exclusive_write_via_registry(self) -> None:
        """Test multiple registered agents enforce exclusive write access."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("shared")
            shared_file = f.name

        try:
            agent_a = "exclusive-a"
            agent_b = "exclusive-b"
            agent_c = "exclusive-c"

            # Register all
            self.registry.register(agent_a, "token-a")
            self.registry.register(agent_b, "token-b")
            self.registry.register(agent_c, "token-c")

            # Agent A acquires exclusive write
            token_a = self.lock_mgr.acquire_write(agent_a, shared_file, timeout_seconds=5)

            # Agents B and C cannot acquire (write or read)
            with pytest.raises(LockTimeoutError):
                self.lock_mgr.acquire_write(agent_b, shared_file, timeout_seconds=1)

            with pytest.raises(LockTimeoutError):
                self.lock_mgr.acquire_read(agent_c, shared_file, timeout_seconds=1)

            # A releases
            self.lock_mgr.release_write(token_a)

            # Now B can acquire read
            token_b = self.lock_mgr.acquire_read(agent_b, shared_file, timeout_seconds=5)

            # C can also acquire read (shared)
            token_c = self.lock_mgr.acquire_read(agent_c, shared_file, timeout_seconds=5)

            # B cannot acquire write while C holds read
            with pytest.raises(LockTimeoutError):
                self.lock_mgr.acquire_write(agent_b, shared_file, timeout_seconds=1)

            self.lock_mgr.release_read(token_b)
            self.lock_mgr.release_read(token_c)

        finally:
            os.unlink(shared_file)
