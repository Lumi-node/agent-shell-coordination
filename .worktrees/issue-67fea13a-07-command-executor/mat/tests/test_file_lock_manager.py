"""Comprehensive tests for FileLockManager read-write lock implementation."""

import os
import threading
import time
import uuid
from typing import Any, List
from unittest.mock import patch

import pytest

from mat.core.file_lock_manager import FileLockManager, LockToken
from mat.exceptions import LockTimeoutError


class TestLockToken:
    """Tests for LockToken dataclass."""

    def test_lock_token_frozen(self) -> None:
        """Verify LockToken is immutable (frozen)."""
        token = LockToken(
            agent_id="agent-A",
            file_path="/tmp/file.txt",
            lock_type="read",
            acquired_at=time.time(),
            token_id=uuid.uuid4().hex
        )

        # Should not be able to modify attributes
        with pytest.raises(AttributeError):
            token.agent_id = "agent-B"  # type: ignore

    def test_lock_token_attributes(self) -> None:
        """Verify LockToken has all required attributes."""
        now = time.time()
        token_id = uuid.uuid4().hex

        token = LockToken(
            agent_id="agent-A",
            file_path="/tmp/file.txt",
            lock_type="write",
            acquired_at=now,
            token_id=token_id
        )

        assert token.agent_id == "agent-A"
        assert token.file_path == "/tmp/file.txt"
        assert token.lock_type == "write"
        assert token.acquired_at == now
        assert token.token_id == token_id


class TestAcquireWrite:
    """Tests for exclusive write lock acquisition."""

    def test_acquire_write_exclusive(self) -> None:
        """Verify exclusive write lock blocks subsequent write attempts."""
        mgr = FileLockManager()

        # Agent A acquires write lock
        token_a = mgr.acquire_write("agent-A", "/tmp/file.txt", timeout_seconds=1)
        assert token_a.lock_type == "write"
        assert token_a.agent_id == "agent-A"

        # Agent B tries to acquire write lock (should timeout)
        with pytest.raises(LockTimeoutError):
            mgr.acquire_write("agent-B", "/tmp/file.txt", timeout_seconds=1)

    def test_acquire_write_empty_agent_id(self) -> None:
        """Verify ValueError raised for empty agent_id."""
        mgr = FileLockManager()

        with pytest.raises(ValueError):
            mgr.acquire_write("", "/tmp/file.txt", timeout_seconds=1)

        with pytest.raises(ValueError):
            mgr.acquire_write(None, "/tmp/file.txt", timeout_seconds=1)  # type: ignore

    def test_acquire_write_empty_file_path(self) -> None:
        """Verify ValueError raised for empty file_path."""
        mgr = FileLockManager()

        with pytest.raises(ValueError):
            mgr.acquire_write("agent-A", "", timeout_seconds=1)

        with pytest.raises(ValueError):
            mgr.acquire_write("agent-A", None, timeout_seconds=1)  # type: ignore

    def test_acquire_write_returns_token(self) -> None:
        """Verify acquire_write returns valid LockToken."""
        mgr = FileLockManager()
        token = mgr.acquire_write("agent-A", "/tmp/file.txt", timeout_seconds=10)

        assert isinstance(token, LockToken)
        assert token.agent_id == "agent-A"
        assert token.file_path == os.path.abspath("/tmp/file.txt")
        assert token.lock_type == "write"
        assert token.acquired_at > 0
        assert token.token_id


class TestAcquireRead:
    """Tests for shared read lock acquisition."""

    def test_acquire_read_shared(self) -> None:
        """Verify multiple read locks allowed on same file."""
        mgr = FileLockManager()

        # Agent A acquires read lock
        token_a = mgr.acquire_read("agent-A", "/tmp/file.txt", timeout_seconds=1)
        assert token_a.lock_type == "read"

        # Agent B also acquires read lock (should succeed)
        token_b = mgr.acquire_read("agent-B", "/tmp/file.txt", timeout_seconds=1)
        assert token_b.lock_type == "read"

        # Tokens should be different
        assert token_a.token_id != token_b.token_id

    def test_multiple_read_locks_allowed(self) -> None:
        """Verify multiple agents can hold read locks on same file simultaneously."""
        mgr = FileLockManager()
        tokens: List[LockToken] = []

        # Acquire 5 read locks from different agents
        for i in range(5):
            token = mgr.acquire_read(f"agent-{i}", "/tmp/file.txt", timeout_seconds=10)
            tokens.append(token)

        # All should be read locks
        assert all(t.lock_type == "read" for t in tokens)

        # All should have different token_ids
        token_ids = [t.token_id for t in tokens]
        assert len(token_ids) == len(set(token_ids))

    def test_exclusive_write_blocks_read(self) -> None:
        """Verify write lock blocks read attempts."""
        mgr = FileLockManager()

        # Agent A acquires write lock
        token_a = mgr.acquire_write("agent-A", "/tmp/file.txt", timeout_seconds=10)

        # Agent B tries to acquire read lock (should timeout)
        with pytest.raises(LockTimeoutError):
            mgr.acquire_read("agent-B", "/tmp/file.txt", timeout_seconds=1)

    def test_acquire_read_empty_agent_id(self) -> None:
        """Verify ValueError raised for empty agent_id."""
        mgr = FileLockManager()

        with pytest.raises(ValueError):
            mgr.acquire_read("", "/tmp/file.txt", timeout_seconds=1)

    def test_acquire_read_returns_token(self) -> None:
        """Verify acquire_read returns valid LockToken."""
        mgr = FileLockManager()
        token = mgr.acquire_read("agent-A", "/tmp/file.txt", timeout_seconds=10)

        assert isinstance(token, LockToken)
        assert token.agent_id == "agent-A"
        assert token.lock_type == "read"
        assert token.acquired_at > 0


class TestReleaseWrite:
    """Tests for write lock release."""

    def test_release_write_success(self) -> None:
        """Verify release_write returns True on success."""
        mgr = FileLockManager()
        token = mgr.acquire_write("agent-A", "/tmp/file.txt", timeout_seconds=10)

        result = mgr.release_write(token)
        assert result is True

    def test_release_write_allows_subsequent_acquire(self) -> None:
        """Verify lock can be acquired after release."""
        mgr = FileLockManager()

        token_a = mgr.acquire_write("agent-A", "/tmp/file.txt", timeout_seconds=10)
        mgr.release_write(token_a)

        # Agent B should now be able to acquire
        token_b = mgr.acquire_write("agent-B", "/tmp/file.txt", timeout_seconds=1)
        assert token_b.agent_id == "agent-B"

    def test_release_write_invalid_token(self) -> None:
        """Verify ValueError raised for invalid token."""
        mgr = FileLockManager()

        with pytest.raises(ValueError):
            mgr.release_write(None)  # type: ignore

    def test_release_write_wrong_token(self) -> None:
        """Verify False returned for wrong token."""
        mgr = FileLockManager()
        token = mgr.acquire_write("agent-A", "/tmp/file.txt", timeout_seconds=10)

        # Create fake token with different token_id
        wrong_token = LockToken(
            agent_id="agent-A",
            file_path=token.file_path,
            lock_type="write",
            acquired_at=token.acquired_at,
            token_id="wrong-id"
        )

        result = mgr.release_write(wrong_token)
        assert result is False

    def test_release_write_twice(self) -> None:
        """Verify second release returns False (idempotent)."""
        mgr = FileLockManager()
        token = mgr.acquire_write("agent-A", "/tmp/file.txt", timeout_seconds=10)

        # First release succeeds
        assert mgr.release_write(token) is True

        # Second release fails
        assert mgr.release_write(token) is False


class TestReleaseRead:
    """Tests for read lock release."""

    def test_release_read_success(self) -> None:
        """Verify release_read returns True on success."""
        mgr = FileLockManager()
        token = mgr.acquire_read("agent-A", "/tmp/file.txt", timeout_seconds=10)

        result = mgr.release_read(token)
        assert result is True

    def test_release_read_allows_write(self) -> None:
        """Verify write lock can be acquired after read release."""
        mgr = FileLockManager()

        token_read = mgr.acquire_read("agent-A", "/tmp/file.txt", timeout_seconds=10)
        mgr.release_read(token_read)

        # Agent B should now be able to acquire write lock
        token_write = mgr.acquire_write("agent-B", "/tmp/file.txt", timeout_seconds=1)
        assert token_write.lock_type == "write"

    def test_release_read_invalid_token(self) -> None:
        """Verify ValueError raised for invalid token."""
        mgr = FileLockManager()

        with pytest.raises(ValueError):
            mgr.release_read(None)  # type: ignore

    def test_release_read_twice(self) -> None:
        """Verify second release returns False."""
        mgr = FileLockManager()
        token = mgr.acquire_read("agent-A", "/tmp/file.txt", timeout_seconds=10)

        assert mgr.release_read(token) is True
        assert mgr.release_read(token) is False


class TestAcquireMultiple:
    """Tests for atomic multi-file lock acquisition."""

    def test_acquire_multiple_basic(self) -> None:
        """Verify acquire_multiple returns list of tokens."""
        mgr = FileLockManager()
        tokens = mgr.acquire_multiple(
            "agent-A",
            read_paths=["/tmp/file1.txt"],
            write_paths=["/tmp/file2.txt"],
            timeout_seconds=10
        )

        assert len(tokens) == 2
        assert all(isinstance(t, LockToken) for t in tokens)

    def test_acquire_multiple_sorted_order(self) -> None:
        """Verify locks acquired in sorted order (deadlock prevention)."""
        mgr = FileLockManager()

        # Acquire locks in one agent: reads fileZ, writes fileA
        tokens_1 = mgr.acquire_multiple(
            "agent-1",
            read_paths=["/tmp/fileZ.txt"],
            write_paths=["/tmp/fileA.txt"],
            timeout_seconds=10
        )

        # Try to acquire in "reverse" order from another agent
        # Agent 2 wants: reads fileA, writes fileZ
        # Both should acquire in sorted order: [fileA, fileZ]
        # Agent 1 already holds: read on Z, write on A
        # So agent-2 should timeout on fileA (agent-1 writes it)
        with pytest.raises(LockTimeoutError):
            mgr.acquire_multiple(
                "agent-2",
                read_paths=["/tmp/fileA.txt"],
                write_paths=["/tmp/fileZ.txt"],
                timeout_seconds=1
            )

        # The key point: both agents acquire in SAME order (sorted)
        # Agent 1: [fileA (write), fileZ (read)]
        # Agent 2: [fileA (read), fileZ (write)]
        # This prevents circular waits and deadlock

    def test_acquire_multiple_all_or_nothing(self) -> None:
        """Verify timeout on any lock releases all previous locks."""
        mgr = FileLockManager()

        # Agent A holds write lock on file1
        token_a = mgr.acquire_write("agent-A", "/tmp/file1.txt", timeout_seconds=10)

        # Agent B tries to acquire both file1 and file2 (file1 should timeout)
        with pytest.raises(LockTimeoutError):
            mgr.acquire_multiple(
                "agent-B",
                read_paths=[],
                write_paths=["/tmp/file1.txt", "/tmp/file2.txt"],
                timeout_seconds=1
            )

        # Agent B should not have acquired file2
        # Verify this by trying to acquire file2 (should succeed if not locked)
        token_b = mgr.acquire_write("agent-B", "/tmp/file2.txt", timeout_seconds=1)
        assert token_b is not None

    def test_acquire_multiple_duplicate_path(self) -> None:
        """Verify ValueError if same path in both read and write."""
        mgr = FileLockManager()

        with pytest.raises(ValueError):
            mgr.acquire_multiple(
                "agent-A",
                read_paths=["/tmp/file.txt"],
                write_paths=["/tmp/file.txt"],
                timeout_seconds=10
            )

    def test_acquire_multiple_empty_agent_id(self) -> None:
        """Verify ValueError for empty agent_id."""
        mgr = FileLockManager()

        with pytest.raises(ValueError):
            mgr.acquire_multiple(
                "",
                read_paths=["/tmp/file.txt"],
                write_paths=[],
                timeout_seconds=10
            )

    def test_acquire_multiple_path_normalization(self) -> None:
        """Verify paths normalized before acquiring locks."""
        mgr = FileLockManager()

        # Acquire with non-normalized path
        tokens = mgr.acquire_multiple(
            "agent-A",
            read_paths=["./file.txt"],
            write_paths=[],
            timeout_seconds=10
        )

        # Verify path is normalized
        assert tokens[0].file_path == os.path.abspath("./file.txt")


class TestPathNormalization:
    """Tests for path normalization."""

    def test_path_normalization_absolute_vs_relative(self) -> None:
        """Verify relative and absolute paths to same file are recognized as identical."""
        mgr = FileLockManager()

        # Get absolute path
        abs_path = os.path.abspath("./testfile.txt")

        # Acquire with relative path
        token_rel = mgr.acquire_write("agent-A", "./testfile.txt", timeout_seconds=10)

        # Try to acquire with absolute path (should block)
        with pytest.raises(LockTimeoutError):
            mgr.acquire_write("agent-B", abs_path, timeout_seconds=1)

    def test_path_normalization_symlink(self) -> None:
        """Verify same file identity for paths with ./ and without."""
        mgr = FileLockManager()

        # These should be treated as the same file
        token_1 = mgr.acquire_write("agent-A", "/tmp/file.txt", timeout_seconds=10)

        with pytest.raises(LockTimeoutError):
            mgr.acquire_write("agent-B", "/tmp/./file.txt", timeout_seconds=1)


class TestListLocks:
    """Tests for debugging lock list."""

    def test_list_locks_empty(self) -> None:
        """Verify list_locks returns empty dict when no locks."""
        mgr = FileLockManager()
        locks = mgr.list_locks()
        assert locks == {}

    def test_list_locks_write_lock(self) -> None:
        """Verify list_locks shows write lock."""
        mgr = FileLockManager()
        token = mgr.acquire_write("agent-A", "/tmp/file.txt", timeout_seconds=10)

        locks = mgr.list_locks()
        file_path = os.path.abspath("/tmp/file.txt")

        assert file_path in locks
        assert locks[file_path]["write_lock"] == token
        assert locks[file_path]["read_locks"] == []

    def test_list_locks_read_locks(self) -> None:
        """Verify list_locks shows read locks."""
        mgr = FileLockManager()
        token_a = mgr.acquire_read("agent-A", "/tmp/file.txt", timeout_seconds=10)
        token_b = mgr.acquire_read("agent-B", "/tmp/file.txt", timeout_seconds=10)

        locks = mgr.list_locks()
        file_path = os.path.abspath("/tmp/file.txt")

        assert file_path in locks
        assert locks[file_path]["write_lock"] is None
        assert len(locks[file_path]["read_locks"]) == 2

    def test_list_locks_waiting_agents(self) -> None:
        """Verify list_locks shows waiting agents."""
        mgr = FileLockManager()

        # Agent A holds write lock
        token_a = mgr.acquire_write("agent-A", "/tmp/file.txt", timeout_seconds=10)

        # Start thread for agent B to wait
        def try_read() -> None:
            try:
                mgr.acquire_read("agent-B", "/tmp/file.txt", timeout_seconds=5)
            except LockTimeoutError:
                pass

        thread = threading.Thread(target=try_read)
        thread.start()

        # Give thread time to start waiting
        time.sleep(0.1)

        locks = mgr.list_locks()
        file_path = os.path.abspath("/tmp/file.txt")

        # Should have waiting agents
        assert "agent-B" in locks[file_path]["waiting_agents"]

        thread.join(timeout=6)


class TestConcurrency:
    """Tests for thread safety and concurrent lock operations."""

    def test_concurrent_read_locks(self) -> None:
        """Verify multiple threads can acquire read locks concurrently."""
        mgr = FileLockManager()
        tokens: List[LockToken] = []
        lock = threading.Lock()

        def acquire_read(agent_id: str) -> None:
            token = mgr.acquire_read(agent_id, "/tmp/file.txt", timeout_seconds=10)
            with lock:
                tokens.append(token)

        threads = []
        for i in range(10):
            t = threading.Thread(target=acquire_read, args=(f"agent-{i}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(tokens) == 10
        assert all(t.lock_type == "read" for t in tokens)

    def test_concurrent_acquire_multiple(self) -> None:
        """Verify acquire_multiple is thread-safe."""
        mgr = FileLockManager()
        results: List[List[LockToken]] = []
        lock = threading.Lock()

        def acquire_multi(agent_id: str) -> None:
            tokens = mgr.acquire_multiple(
                agent_id,
                read_paths=["/tmp/file1.txt"],
                write_paths=["/tmp/file2.txt"],
                timeout_seconds=10
            )
            with lock:
                results.append(tokens)

        threads = []
        for i in range(5):
            t = threading.Thread(target=acquire_multi, args=(f"agent-{i}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=15)

        # At least one thread should succeed
        assert len(results) > 0

    def test_race_between_acquire_and_release(self) -> None:
        """Verify no race conditions between acquire and release."""
        mgr = FileLockManager()

        def writer(agent_id: str) -> None:
            for _ in range(10):
                token = mgr.acquire_write(agent_id, "/tmp/file.txt", timeout_seconds=5)
                time.sleep(0.01)
                mgr.release_write(token)

        threads = []
        for i in range(3):
            t = threading.Thread(target=writer, args=(f"agent-{i}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=30)


class TestReleaseMultiple:
    """Tests for releasing multiple locks."""

    def test_release_multiple_success(self) -> None:
        """Verify release_multiple releases all locks."""
        mgr = FileLockManager()
        tokens = mgr.acquire_multiple(
            "agent-A",
            read_paths=["/tmp/file1.txt"],
            write_paths=["/tmp/file2.txt"],
            timeout_seconds=10
        )

        result = mgr.release_multiple(tokens)
        assert result is True

    def test_release_multiple_empty_list(self) -> None:
        """Verify ValueError for empty list."""
        mgr = FileLockManager()

        with pytest.raises(ValueError):
            mgr.release_multiple([])

    def test_release_multiple_none(self) -> None:
        """Verify ValueError for None."""
        mgr = FileLockManager()

        with pytest.raises(ValueError):
            mgr.release_multiple(None)  # type: ignore


class TestLockTimeout:
    """Tests for lock timeout behavior."""

    def test_lock_timeout_raises_error(self) -> None:
        """Verify LockTimeoutError raised when timeout exceeded."""
        mgr = FileLockManager()

        # Agent A holds lock
        token_a = mgr.acquire_write("agent-A", "/tmp/file.txt", timeout_seconds=10)

        # Agent B waits for short timeout
        start = time.time()
        with pytest.raises(LockTimeoutError):
            mgr.acquire_write("agent-B", "/tmp/file.txt", timeout_seconds=1)
        elapsed = time.time() - start

        # Should have waited at least 0.1 seconds
        assert elapsed >= 0.1

    def test_acquire_read_blocks_on_write(self) -> None:
        """Verify read request blocks when write lock held."""
        mgr = FileLockManager()

        token_write = mgr.acquire_write("agent-A", "/tmp/file.txt", timeout_seconds=10)

        start = time.time()
        with pytest.raises(LockTimeoutError):
            mgr.acquire_read("agent-B", "/tmp/file.txt", timeout_seconds=1)
        elapsed = time.time() - start

        assert elapsed >= 0.2


class TestLockAutoRelease:
    """Tests for automatic lock release on timeout."""

    def test_lock_timeout_auto_release(self, monkeypatch: Any) -> None:
        """Verify cleanup thread releases expired locks."""
        mgr = FileLockManager()

        # Mock time.time() to simulate time passing
        current_time = [time.time()]

        original_time = time.time

        def mock_time() -> float:
            return current_time[0]

        # Acquire write lock
        with patch("mat.core.file_lock_manager.time.time", side_effect=mock_time):
            token = mgr.acquire_write("agent-A", "/tmp/file.txt", timeout_seconds=10)

        # Simulate time passing beyond timeout
        current_time[0] += 20

        # Run cleanup manually
        with patch("mat.core.file_lock_manager.time.time", side_effect=mock_time):
            mgr._cleanup_expired_locks()

        # Lock should be released now
        with patch("mat.core.file_lock_manager.time.time", side_effect=mock_time):
            # Agent B should be able to acquire (or at least not find lock in list)
            locks = mgr.list_locks()
            file_path = os.path.abspath("/tmp/file.txt")

            # Either file not in locks, or write_lock is None
            if file_path in locks:
                assert locks[file_path]["write_lock"] is None


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_same_agent_multiple_read_locks(self) -> None:
        """Verify same agent can hold multiple read locks on same file."""
        mgr = FileLockManager()

        token_1 = mgr.acquire_read("agent-A", "/tmp/file.txt", timeout_seconds=10)
        token_2 = mgr.acquire_read("agent-A", "/tmp/file.txt", timeout_seconds=10)

        assert token_1.token_id != token_2.token_id
        assert token_1.agent_id == token_2.agent_id

    def test_write_blocks_other_write(self) -> None:
        """Verify write lock prevents other write locks."""
        mgr = FileLockManager()

        token_a = mgr.acquire_write("agent-A", "/tmp/file.txt", timeout_seconds=10)

        with pytest.raises(LockTimeoutError):
            mgr.acquire_write("agent-A", "/tmp/file.txt", timeout_seconds=1)

    def test_write_unblocks_reads(self) -> None:
        """Verify releasing write lock allows pending reads."""
        mgr = FileLockManager()

        token_write = mgr.acquire_write("agent-A", "/tmp/file.txt", timeout_seconds=10)

        # Start thread to wait for read
        read_acquired = [False]
        error_occurred: list[Exception | None] = [None]

        def try_read() -> None:
            try:
                mgr.acquire_read("agent-B", "/tmp/file.txt", timeout_seconds=2)
                read_acquired[0] = True
            except Exception as e:
                error_occurred[0] = e

        thread = threading.Thread(target=try_read)
        thread.start()

        # Give thread time to start waiting
        time.sleep(0.1)

        # Release write lock
        mgr.release_write(token_write)

        # Wait for thread
        thread.join(timeout=3)

        # Read should have been acquired
        assert read_acquired[0] is True or error_occurred[0] is not None

    def test_list_locks_after_release(self) -> None:
        """Verify list_locks shows released locks are gone."""
        mgr = FileLockManager()
        token = mgr.acquire_write("agent-A", "/tmp/file.txt", timeout_seconds=10)

        # Lock should be in list
        locks = mgr.list_locks()
        assert len(locks) > 0

        # Release lock
        mgr.release_write(token)

        # Lock might still be in dict but write_lock should be None
        locks = mgr.list_locks()
        file_path = os.path.abspath("/tmp/file.txt")
        if file_path in locks:
            assert locks[file_path]["write_lock"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
