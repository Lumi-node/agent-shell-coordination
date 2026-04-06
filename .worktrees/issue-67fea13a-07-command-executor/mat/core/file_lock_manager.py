"""
File-level read-write lock manager with deadlock prevention via atomic multi-file acquisition.

This module implements FileLockManager, a thread-safe lock manager providing:
- Shared read locks: multiple agents can hold read locks on same file
- Exclusive write locks: only one agent can hold write lock at a time
- Cross-blocking: write blocks reads and vice versa
- Atomic multi-file acquisition: acquire_multiple() prevents deadlock by sorting paths
- Auto-release: background cleanup thread releases expired locks
- Path normalization: all paths normalized via os.path.abspath()
"""

import os
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Literal, Tuple


@dataclass(frozen=True)
class LockToken:
    """
    Opaque token representing a held lock.

    Attributes:
        agent_id: Agent that holds this lock
        file_path: Absolute normalized file path this lock protects
        lock_type: "read" (shared) or "write" (exclusive)
        acquired_at: Unix timestamp when lock was acquired
        token_id: Unique identifier for this lock grant (prevents confusion
                 if same agent acquires same lock twice)
    """
    agent_id: str
    file_path: str
    lock_type: Literal["read", "write"]
    acquired_at: float  # time.time()
    token_id: str       # uuid.uuid4().hex for uniqueness


class FileLockManager:
    """
    Manages file-level read-write locks for multiple agents.

    Design:
    - Multiple agents can hold READ locks on same file simultaneously
    - Only ONE agent can hold WRITE lock on a file at a time
    - acquire_read() blocks if a WRITE lock is held
    - acquire_write() blocks if ANY READ or WRITE lock is held
    - Locks auto-release if holder doesn't release within timeout
    - All file paths normalized via os.path.abspath() before lock checks

    Lock Acquisition Ordering (CRITICAL for deadlock prevention):
    When a caller needs multiple locks, use acquire_multiple() which acquires
    all locks atomically in sorted order by file path. This total ordering
    prevents circular wait dependencies and eliminates deadlock.

    Single-file methods (acquire_read/acquire_write) are provided for simple
    cases where only one file needs locking.

    Auto-Release Mechanism:
    - Background cleanup thread runs every 15 seconds
    - Scans all locks, releases any held beyond timeout_seconds
    - Max lock hold time: timeout_seconds + 15 seconds (cleanup interval)
    - This ensures locks are released even if no other acquire() calls occur
    """

    def __init__(self) -> None:
        """
        Initialize empty lock manager with cleanup thread.

        The cleanup thread is a daemon thread that periodically checks for
        expired locks and auto-releases them. It exits when the process exits.
        """
        # Per-file lock state
        self._file_locks: Dict[str, "_FileLockState"] = {}
        # normalized_file_path -> FileLockState

        # Protects all _file_locks access (RLock allows re-entrant acquire)
        self._lock: threading.RLock = threading.RLock()

        # Signal to stop cleanup thread
        self._shutdown_event: threading.Event = threading.Event()

        # Background daemon thread for auto-release
        self._cleanup_thread: threading.Thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True
        )
        self._cleanup_thread.start()

    def _cleanup_loop(self) -> None:
        """Background thread that scans for expired locks every 15 seconds."""
        while not self._shutdown_event.wait(timeout=15):
            self._cleanup_expired_locks()

    def _cleanup_expired_locks(self) -> None:
        """Scan all locks and release any held beyond their timeout."""
        now = time.time()

        with self._lock:
            # Collect expired lock tokens
            expired_tokens: List[LockToken] = []

            for file_path, lock_state in list(self._file_locks.items()):
                # Check write lock
                if lock_state.write_lock is not None:
                    if now - lock_state.write_lock.acquired_at > lock_state.write_lock_timeout:
                        expired_tokens.append(lock_state.write_lock)

                # Check read locks
                for token in list(lock_state.read_locks.values()):
                    if now - token.acquired_at > lock_state.read_lock_timeout.get(token.token_id, 10):
                        expired_tokens.append(token)

            # Release expired locks
            for token in expired_tokens:
                if token.lock_type == "write":
                    self.release_write(token)
                else:
                    self.release_read(token)

    def acquire_multiple(
        self,
        agent_id: str,
        read_paths: List[str],
        write_paths: List[str],
        timeout_seconds: int = 10
    ) -> List[LockToken]:
        """
        Atomically acquire multiple locks in sorted order.

        This is the PRIMARY method for acquiring locks when a command needs
        multiple files. It prevents deadlock by acquiring all locks in a
        single call, sorted by file path.

        Args:
            agent_id: Agent requesting locks
            read_paths: List of file paths to acquire read locks on
            write_paths: List of file paths to acquire write locks on
            timeout_seconds: Wait at most this long for ALL locks (default 10)

        Returns:
            List[LockToken]: All acquired locks. Pass these to release_multiple().

        Raises:
            ValueError: If agent_id is empty/None or if same path appears in
                       both read_paths and write_paths
            LockTimeoutError: If any lock cannot be acquired within timeout_seconds.
                             In this case, NO locks are acquired (all-or-nothing).

        Algorithm:
        1. Normalize all paths via os.path.abspath()
        2. Combine read and write paths, remove duplicates
        3. Sort combined list alphabetically
        4. For each path in sorted order:
           a. If path in write_paths: acquire write lock
           b. Else: acquire read lock
           c. If any lock times out: release all previously acquired locks
              and raise LockTimeoutError
        5. Return all acquired lock tokens

        Deadlock Prevention:
        By always acquiring in sorted order, we ensure:
        - If cmd1 needs [fileA, fileB] and cmd2 needs [fileB, fileA],
          both acquire in order [fileA, fileB]
        - No circular wait dependency possible
        - This is the Banker's algorithm for deadlock avoidance

        Thread-safe: Multiple agents can call this concurrently; internal
                    lock ensures consistent state.

        Auto-release: If agent doesn't call release_multiple() within
                     timeout_seconds, locks are automatically released by
                     background cleanup thread (max hold time: timeout + 15s).
        """
        from mat.exceptions import LockTimeoutError

        if not agent_id:
            raise ValueError("agent_id cannot be empty or None")

        # Normalize all paths
        normalized_read = [os.path.abspath(p) for p in read_paths]
        normalized_write = [os.path.abspath(p) for p in write_paths]

        # Check for duplicates
        read_set = set(normalized_read)
        write_set = set(normalized_write)
        if read_set & write_set:
            raise ValueError("Same path cannot be in both read_paths and write_paths")

        # Combine and sort
        all_paths = sorted(read_set | write_set)

        # Try to acquire all locks with timeout
        start_time = time.time()
        acquired_tokens: List[LockToken] = []

        try:
            for path in all_paths:
                elapsed = time.time() - start_time
                remaining = timeout_seconds - elapsed

                if remaining <= 0:
                    raise LockTimeoutError(
                        f"Timeout acquiring locks for agent {agent_id}: "
                        f"exceeded {timeout_seconds}s timeout"
                    )

                if path in write_set:
                    token = self.acquire_write(agent_id, path, timeout_seconds=int(remaining) + 1)
                else:
                    token = self.acquire_read(agent_id, path, timeout_seconds=int(remaining) + 1)

                acquired_tokens.append(token)

        except LockTimeoutError:
            # All-or-nothing: release all acquired locks before raising
            for token in acquired_tokens:
                if token.lock_type == "write":
                    self.release_write(token)
                else:
                    self.release_read(token)
            raise

        return acquired_tokens

    def acquire_read(
        self,
        agent_id: str,
        file_path: str,
        timeout_seconds: int = 10
    ) -> LockToken:
        """
        Acquire a shared read lock on file_path.

        Use this for simple cases where only one file needs locking.
        For multiple files, use acquire_multiple() to prevent deadlock.

        Multiple agents can hold read locks on the same file. Read lock
        blocks if there's an active write lock. If lock cannot be acquired
        within timeout_seconds, raises LockTimeoutError.

        Args:
            agent_id: Agent requesting lock
            file_path: File to lock (will be normalized via os.path.abspath)
            timeout_seconds: Wait at most this long for lock (default 10).
                           If timeout expires, raise LockTimeoutError.

        Returns:
            LockToken: Opaque token representing this lock grant. Must be
                      passed to release_read() to release lock.

        Raises:
            ValueError: If agent_id is empty/None or file_path is empty/None
            LockTimeoutError: If write lock is held and doesn't release
                             within timeout_seconds

        Blocking: This method blocks the calling thread until lock acquired
                 or timeout expires.

        Auto-release: If agent doesn't call release_read() within
                     timeout_seconds, lock is automatically released
                     by background cleanup thread (max hold time: timeout + 15s).
        """
        from mat.exceptions import LockTimeoutError

        if not agent_id:
            raise ValueError("agent_id cannot be empty or None")
        if not file_path:
            raise ValueError("file_path cannot be empty or None")

        # Normalize path
        file_path = os.path.abspath(file_path)

        start_time = time.time()

        with self._lock:
            # Ensure lock state exists
            if file_path not in self._file_locks:
                self._file_locks[file_path] = _FileLockState()

            lock_state = self._file_locks[file_path]

            # Wait for write lock to be released
            while lock_state.write_lock is not None:
                elapsed = time.time() - start_time
                remaining = timeout_seconds - elapsed

                if remaining <= 0:
                    raise LockTimeoutError(
                        f"Timeout acquiring read lock on {file_path} for agent {agent_id}: "
                        f"write lock held by {lock_state.write_lock.agent_id}"
                    )

                # Release lock, wait, then re-acquire
                event = threading.Event()
                lock_state.waiting_queue.append((agent_id, "read", event))
                self._lock.release()

                # Wait with timeout
                event.wait(timeout=remaining)

                self._lock.acquire()

                # Remove from queue if still there
                lock_state.waiting_queue = deque([
                    item for item in lock_state.waiting_queue
                    if not (item[0] == agent_id and item[1] == "read" and item[2] is event)
                ])

            # Acquire read lock
            token = LockToken(
                agent_id=agent_id,
                file_path=file_path,
                lock_type="read",
                acquired_at=time.time(),
                token_id=uuid.uuid4().hex
            )
            lock_state.read_locks[token.token_id] = token
            lock_state.read_lock_timeout[token.token_id] = timeout_seconds

            return token

    def acquire_write(
        self,
        agent_id: str,
        file_path: str,
        timeout_seconds: int = 10
    ) -> LockToken:
        """
        Acquire an exclusive write lock on file_path.

        Use this for simple cases where only one file needs locking.
        For multiple files, use acquire_multiple() to prevent deadlock.

        Only one agent can hold a write lock at a time. Write lock
        blocks if there are any read or write locks held. If lock
        cannot be acquired within timeout_seconds, raises LockTimeoutError.

        Args:
            agent_id: Agent requesting lock
            file_path: File to lock (will be normalized via os.path.abspath)
            timeout_seconds: Wait at most this long for lock (default 10).
                           If timeout expires, raise LockTimeoutError.

        Returns:
            LockToken: Opaque token representing this lock grant. Must be
                      passed to release_write() to release lock.

        Raises:
            ValueError: If agent_id is empty/None or file_path is empty/None
            LockTimeoutError: If any read or write lock is held and doesn't
                             release within timeout_seconds

        Blocking: This method blocks the calling thread until lock acquired
                 or timeout expires.

        Auto-release: If agent doesn't call release_write() within
                     timeout_seconds, lock is automatically released
                     by background cleanup thread (max hold time: timeout + 15s).
        """
        from mat.exceptions import LockTimeoutError

        if not agent_id:
            raise ValueError("agent_id cannot be empty or None")
        if not file_path:
            raise ValueError("file_path cannot be empty or None")

        # Normalize path
        file_path = os.path.abspath(file_path)

        start_time = time.time()

        with self._lock:
            # Ensure lock state exists
            if file_path not in self._file_locks:
                self._file_locks[file_path] = _FileLockState()

            lock_state = self._file_locks[file_path]

            # Wait for all read and write locks to be released
            while lock_state.write_lock is not None or lock_state.read_locks:
                elapsed = time.time() - start_time
                remaining = timeout_seconds - elapsed

                if remaining <= 0:
                    if lock_state.write_lock is not None:
                        raise LockTimeoutError(
                            f"Timeout acquiring write lock on {file_path} for agent {agent_id}: "
                            f"write lock held by {lock_state.write_lock.agent_id}"
                        )
                    else:
                        raise LockTimeoutError(
                            f"Timeout acquiring write lock on {file_path} for agent {agent_id}: "
                            f"read locks held by {len(lock_state.read_locks)} agents"
                        )

                # Release lock, wait, then re-acquire
                event = threading.Event()
                lock_state.waiting_queue.append((agent_id, "write", event))
                self._lock.release()

                # Wait with timeout
                event.wait(timeout=remaining)

                self._lock.acquire()

                # Remove from queue if still there
                lock_state.waiting_queue = deque([
                    item for item in lock_state.waiting_queue
                    if not (item[0] == agent_id and item[1] == "write" and item[2] is event)
                ])

            # Acquire write lock
            token = LockToken(
                agent_id=agent_id,
                file_path=file_path,
                lock_type="write",
                acquired_at=time.time(),
                token_id=uuid.uuid4().hex
            )
            lock_state.write_lock = token
            lock_state.write_lock_timeout = timeout_seconds

            return token

    def release_read(self, lock_token: LockToken) -> bool:
        """
        Release a previously acquired read lock.

        Args:
            lock_token: Token returned by acquire_read()

        Returns:
            True if lock was released successfully
            False if lock_token is invalid or already released

        Raises:
            ValueError: If lock_token is malformed (None, agent_id empty, etc.)

        Note: After release, other agents waiting on this file (via acquire_write)
             may proceed.
        """
        if lock_token is None or not lock_token.agent_id:
            raise ValueError("lock_token is invalid (None or malformed)")

        with self._lock:
            file_path = lock_token.file_path

            if file_path not in self._file_locks:
                return False

            lock_state = self._file_locks[file_path]

            # Check if this token is actually held
            if lock_token.token_id not in lock_state.read_locks:
                return False

            # Verify it's the same token
            held_token = lock_state.read_locks[lock_token.token_id]
            if held_token != lock_token:
                return False

            # Release it
            del lock_state.read_locks[lock_token.token_id]
            if lock_token.token_id in lock_state.read_lock_timeout:
                del lock_state.read_lock_timeout[lock_token.token_id]

            # Notify waiting agents
            self._notify_waiters(lock_state)

            return True

    def release_write(self, lock_token: LockToken) -> bool:
        """
        Release a previously acquired write lock.

        Args:
            lock_token: Token returned by acquire_write()

        Returns:
            True if lock was released successfully
            False if lock_token is invalid or already released

        Raises:
            ValueError: If lock_token is malformed (None, agent_id empty, etc.)

        Note: After release, other agents waiting on this file
             may proceed.
        """
        if lock_token is None or not lock_token.agent_id:
            raise ValueError("lock_token is invalid (None or malformed)")

        with self._lock:
            file_path = lock_token.file_path

            if file_path not in self._file_locks:
                return False

            lock_state = self._file_locks[file_path]

            # Check if this token is actually held
            if lock_state.write_lock is None or lock_state.write_lock != lock_token:
                return False

            # Release it
            lock_state.write_lock = None

            # Notify waiting agents
            self._notify_waiters(lock_state)

            return True

    def release_multiple(self, lock_tokens: List[LockToken]) -> bool:
        """
        Release multiple locks acquired via acquire_multiple().

        Args:
            lock_tokens: List of tokens returned by acquire_multiple()

        Returns:
            True if all locks released successfully
            False if any token is invalid (partial release may occur)

        Raises:
            ValueError: If lock_tokens is None or empty

        Note: Releases locks in reverse order of acquisition for consistency.
        """
        if lock_tokens is None or len(lock_tokens) == 0:
            raise ValueError("lock_tokens cannot be None or empty")

        all_success = True

        # Release in reverse order
        for token in reversed(lock_tokens):
            if token.lock_type == "write":
                if not self.release_write(token):
                    all_success = False
            else:
                if not self.release_read(token):
                    all_success = False

        return all_success

    def list_locks(self) -> Dict[str, Dict[str, Any]]:
        """
        Debugging: List all currently held locks.

        Returns:
            Dict mapping file_path -> {
                "write_lock": LockToken or None,
                "read_locks": List[LockToken],
                "waiting_agents": List[str]
            }

        Note: This is a snapshot; useful for debugging deadlocks and
              monitoring lock contention.
        """
        with self._lock:
            result: Dict[str, Dict[str, Any]] = {}

            for file_path, lock_state in self._file_locks.items():
                waiting_agents = list(set(item[0] for item in lock_state.waiting_queue))

                result[file_path] = {
                    "write_lock": lock_state.write_lock,
                    "read_locks": list(lock_state.read_locks.values()),
                    "waiting_agents": waiting_agents
                }

            return result

    def _notify_waiters(self, lock_state: "_FileLockState") -> None:
        """Notify waiting agents that a lock may have been released."""
        # Note: this is called while holding _lock, so we just signal events
        for _agent_id, _lock_type, event in list(lock_state.waiting_queue):
            event.set()


class _FileLockState:
    """Internal state for locks on a single file."""

    def __init__(self) -> None:
        """Initialize empty lock state."""
        self.write_lock: LockToken | None = None
        self.read_locks: Dict[str, LockToken] = {}  # token_id -> LockToken
        self.read_lock_timeout: Dict[str, int] = {}  # token_id -> timeout_seconds
        self.write_lock_timeout: int = 10
        self.waiting_queue: Deque[Tuple[str, str, threading.Event]] = deque()
