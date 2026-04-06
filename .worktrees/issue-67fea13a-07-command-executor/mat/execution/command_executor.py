"""Command execution with automatic lock management.

This module implements CommandExecutor, which executes shell commands with:
- Automatic file lock acquisition/release via FileLockManager
- Command dependency analysis via CommandDependencyAnalyzer
- Environment variable inheritance from coordinator registry
- Subprocess timeout handling with process termination
- Lock acquisition timeout handling with all-or-nothing semantics
"""

import os
import subprocess
import time
from dataclasses import dataclass
from typing import Dict

from mat.core.file_lock_manager import FileLockManager, LockToken
from mat.analysis.command_analyzer import CommandDependencyAnalyzer
from mat.exceptions import LockTimeoutError, CommandTimeoutError


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

    Design:
    - Acquires read locks on files_read, write locks on files_written
    - Uses FileLockManager.acquire_multiple() to prevent deadlock
    - Executes command in subprocess.run() with timeout
    - Passes environment variables from coordinator to subprocess
    - Releases locks after execution (success or failure)
    - Returns ExecutionResult with exit code, stdout, stderr, duration
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
            LockTimeoutError: If lock acquisition times out (locks not acquired)
            CommandTimeoutError: If command execution times out (process killed)

        Algorithm:
        1. Analyze command to extract dependencies (files_read, files_written)
        2. Acquire all locks via acquire_multiple(agent_id, files_read, files_written, lock_timeout_seconds)
        3. (If any lock times out → raise LockTimeoutError, no execution)
        4. Construct environment dict: env_dict = {**os.environ, **self._env_registry}
        5. Execute: subprocess.run(
               command,
               shell=True,
               timeout=timeout_seconds,
               capture_output=True,
               text=True,
               env=env_dict
           )
        6. (If process timeout → kill process, raise CommandTimeoutError)
        7. Release all locks via release_multiple(lock_tokens)
        8. Return ExecutionResult with captured output and duration
        """
        # Validate inputs
        if not agent_id or not cmd_id or not command:
            raise ValueError("agent_id, cmd_id, and command cannot be empty")

        # Analyze command to extract dependencies
        deps = self._command_analyzer.analyze(command)

        # Convert files_read and files_written to lists
        files_read = list(deps.files_read) if deps.files_read != {"*"} else []
        files_written = list(deps.files_written)

        # Acquire locks (may raise LockTimeoutError)
        lock_tokens: list[LockToken] = []
        try:
            lock_tokens = self._file_lock_manager.acquire_multiple(
                agent_id=agent_id,
                read_paths=files_read,
                write_paths=files_written,
                timeout_seconds=lock_timeout_seconds
            )
        except LockTimeoutError:
            raise

        # Build locks_held dict for result (explicitly cast to str for mypy)
        locks_held: dict[str, str] = {token.file_path: token.lock_type for token in lock_tokens}

        # Execute the command
        try:
            # Construct environment dict: merge os.environ with coordinator env_registry
            env_dict = {**os.environ, **self._env_registry}

            # Record start time
            start_time = time.time()

            # Execute subprocess
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    timeout=timeout_seconds,
                    capture_output=True,
                    text=True,
                    env=env_dict
                )
                exit_code = result.returncode
                stdout = result.stdout
                stderr = result.stderr
            except subprocess.TimeoutExpired as e:
                # Command timed out - process was killed
                duration = time.time() - start_time
                raise CommandTimeoutError(
                    f"Command timed out after {timeout_seconds}s: {command}"
                )

            # Record duration
            duration = time.time() - start_time

            # Return execution result
            return ExecutionResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration,
                locks_held=locks_held
            )

        finally:
            # Always release locks
            if lock_tokens:
                self._file_lock_manager.release_multiple(lock_tokens)
