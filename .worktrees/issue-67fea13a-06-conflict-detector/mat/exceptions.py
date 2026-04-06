"""
Custom exception types for multi-agent terminal coordination.

This module defines exceptions used throughout the coordination system
to indicate specific failure modes during lock acquisition and command execution.
"""


class LockTimeoutError(Exception):
    """
    Raised when a lock cannot be acquired within the specified timeout period.

    This exception is raised by FileLockManager when:
    - An acquire_read() or acquire_write() call times out waiting for a lock
    - An acquire_multiple() call times out on any lock in the batch

    When LockTimeoutError is raised during acquire_multiple(), no locks are acquired
    (all-or-nothing semantics), so no cleanup is necessary.
    """

    pass


class CommandTimeoutError(Exception):
    """
    Raised when a command execution exceeds the specified timeout period.

    This exception is raised by CommandExecutor when:
    - A subprocess.run() call exceeds the timeout_seconds parameter
    - The process is killed and execution is terminated

    Locks are released after CommandTimeoutError is raised.
    """

    pass
