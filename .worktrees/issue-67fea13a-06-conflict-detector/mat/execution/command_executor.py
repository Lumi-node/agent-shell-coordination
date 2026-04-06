"""Command execution with automatic lock management.

This module will be fully implemented in issue-07-command-executor.
For now, it provides stub types for the public API.
"""

from dataclasses import dataclass
from typing import Dict
from mat.core.file_lock_manager import FileLockManager
from mat.analysis.command_analyzer import CommandDependencyAnalyzer


@dataclass
class ExecutionResult:
    """Result of executing a command through CommandExecutor.

    Attributes:
        exit_code: Process exit code (0 for success, non-zero for error)
        stdout: Standard output captured from process
        stderr: Standard error captured from process
        duration_seconds: Wall-clock time to execute command (excludes lock wait)
        locks_held: Dict mapping file_path -> lock_type (for debugging)
    """

    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    locks_held: Dict[str, str]


class CommandExecutor:
    """Execute shell commands with automatic lock management.

    Placeholder implementation for issue-01-project-setup.
    Full implementation in issue-07-command-executor.
    """

    def __init__(
        self,
        file_lock_manager: FileLockManager,
        command_analyzer: CommandDependencyAnalyzer,
        env_registry: Dict[str, str]
    ) -> None:
        """Initialize executor with dependencies.

        Args:
            file_lock_manager: Instance to manage locks
            command_analyzer: Instance to extract command dependencies
            env_registry: Shared environment variable registry (reference, not copy)
        """
        self._file_lock_manager = file_lock_manager
        self._command_analyzer = command_analyzer
        self._env_registry = env_registry

    def enqueue(
        self,
        agent_id: str,
        cmd_id: str,
        command: str,
        timeout_seconds: int = 60,
        lock_timeout_seconds: int = 10
    ) -> ExecutionResult:
        """Execute a command with automatic lock management.

        Args:
            agent_id: Agent executing this command
            cmd_id: Unique command identifier (for logging)
            command: Shell command string to execute
            timeout_seconds: Max time to execute command (default 60)
            lock_timeout_seconds: Max time to wait for locks (default 10)

        Returns:
            ExecutionResult with exit code, stdout, stderr, duration, locks_held

        Raises:
            ValueError: If agent_id, cmd_id, or command is empty/None
        """
        if not agent_id or not cmd_id or not command:
            raise ValueError("agent_id, cmd_id, and command cannot be empty")
        raise NotImplementedError("Full implementation in issue-07")
