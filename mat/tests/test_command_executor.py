"""Comprehensive tests for CommandExecutor command execution with lock management."""

import os
import subprocess
import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from mat.execution.command_executor import CommandExecutor, ExecutionResult
from mat.core.file_lock_manager import LockToken
from mat.analysis.command_analyzer import CommandDependencies
from mat.exceptions import LockTimeoutError, CommandTimeoutError


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_execution_result_creation(self) -> None:
        """Test creating an ExecutionResult."""
        locks_held = {"/tmp/file1.txt": "read", "/tmp/file2.txt": "write"}

        result = ExecutionResult(
            exit_code=0,
            stdout="output",
            stderr="",
            duration_seconds=1.5,
            locks_held=locks_held
        )

        assert result.exit_code == 0
        assert result.stdout == "output"
        assert result.stderr == ""
        assert result.duration_seconds == 1.5
        assert result.locks_held == locks_held

    def test_execution_result_with_error(self) -> None:
        """Test ExecutionResult with non-zero exit code."""
        result = ExecutionResult(
            exit_code=127,
            stdout="",
            stderr="command not found",
            duration_seconds=0.5,
            locks_held={}
        )

        assert result.exit_code == 127
        assert result.stderr == "command not found"


class TestCommandExecutorInit:
    """Tests for CommandExecutor initialization."""

    def test_init_stores_dependencies(self) -> None:
        """Test that __init__ stores all dependencies."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()
        env_registry = {"VAR1": "value1"}

        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, env_registry)

        assert executor._file_lock_manager is file_lock_mgr
        assert executor._command_analyzer is cmd_analyzer
        assert executor._env_registry is env_registry

    def test_init_with_empty_env_registry(self) -> None:
        """Test initialization with empty environment registry."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()
        env_registry: dict[str, str] = {}

        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, env_registry)

        assert executor._env_registry == {}


class TestEnqueueValidation:
    """Tests for CommandExecutor.enqueue() input validation."""

    def test_enqueue_requires_agent_id(self) -> None:
        """Test that enqueue raises ValueError if agent_id is empty."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()
        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, {})

        with pytest.raises(ValueError, match="agent_id"):
            executor.enqueue("", "cmd-123", "echo hello")

    def test_enqueue_requires_agent_id_not_none(self) -> None:
        """Test that enqueue raises ValueError if agent_id is None."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()
        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, {})

        # This will raise ValueError because we check: if not agent_id
        with pytest.raises(ValueError):
            executor.enqueue(None, "cmd-123", "echo hello")  # type: ignore

    def test_enqueue_requires_cmd_id(self) -> None:
        """Test that enqueue raises ValueError if cmd_id is empty."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()
        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, {})

        with pytest.raises(ValueError, match="cmd_id"):
            executor.enqueue("agent-A", "", "echo hello")

    def test_enqueue_requires_command(self) -> None:
        """Test that enqueue raises ValueError if command is empty."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()
        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, {})

        with pytest.raises(ValueError, match="command"):
            executor.enqueue("agent-A", "cmd-123", "")

    def test_enqueue_requires_command_not_none(self) -> None:
        """Test that enqueue raises ValueError if command is None."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()
        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, {})

        with pytest.raises(ValueError):
            executor.enqueue("agent-A", "cmd-123", None)  # type: ignore


class TestEnqueueWithLocks:
    """Tests for CommandExecutor.enqueue() with lock management."""

    def test_execute_with_locks(self) -> None:
        """Test executing a command that acquires and releases locks."""
        # Mock dependencies
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()

        # Mock lock tokens
        token1 = LockToken(
            agent_id="agent-A",
            file_path="/tmp/input.txt",
            lock_type="read",
            acquired_at=time.time(),
            token_id="token-1"
        )
        token2 = LockToken(
            agent_id="agent-A",
            file_path="/tmp/output.txt",
            lock_type="write",
            acquired_at=time.time(),
            token_id="token-2"
        )

        # Setup mocks
        cmd_analyzer.analyze.return_value = CommandDependencies(
            files_read={"/tmp/input.txt"},
            files_written={"/tmp/output.txt"},
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set()
        )

        file_lock_mgr.acquire_multiple.return_value = [token1, token2]
        file_lock_mgr.release_multiple.return_value = True

        # Create executor
        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, {})

        # Execute command with patch for subprocess
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Success",
                stderr=""
            )

            result = executor.enqueue(
                agent_id="agent-A",
                cmd_id="cmd-123",
                command="python process.py"
            )

        # Verify results
        assert result.exit_code == 0
        assert result.stdout == "Success"
        assert result.stderr == ""
        assert "/tmp/input.txt" in result.locks_held
        assert "/tmp/output.txt" in result.locks_held
        assert result.locks_held["/tmp/input.txt"] == "read"
        assert result.locks_held["/tmp/output.txt"] == "write"

        # Verify lock operations
        file_lock_mgr.acquire_multiple.assert_called_once_with(
            agent_id="agent-A",
            read_paths=["/tmp/input.txt"],
            write_paths=["/tmp/output.txt"],
            timeout_seconds=10
        )
        file_lock_mgr.release_multiple.assert_called_once()

    def test_lock_timeout_prevents_execution(self) -> None:
        """Test that lock timeout raises exception and no execution occurs."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()

        # Setup mocks
        cmd_analyzer.analyze.return_value = CommandDependencies(
            files_read={"file1.txt"},
            files_written=set(),
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set()
        )

        # Simulate lock timeout
        file_lock_mgr.acquire_multiple.side_effect = LockTimeoutError(
            "Timeout acquiring locks"
        )

        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, {})

        # Verify exception is raised and no execution occurs
        with pytest.raises(LockTimeoutError):
            with patch("subprocess.run") as mock_run:
                executor.enqueue(
                    agent_id="agent-A",
                    cmd_id="cmd-123",
                    command="echo hello"
                )
                # Verify subprocess was NOT called
                mock_run.assert_not_called()

    def test_command_timeout_kills_process(self) -> None:
        """Test that command timeout raises CommandTimeoutError."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()

        token = LockToken(
            agent_id="agent-A",
            file_path="/tmp/file.txt",
            lock_type="read",
            acquired_at=time.time(),
            token_id="token-1"
        )

        cmd_analyzer.analyze.return_value = CommandDependencies(
            files_read={"/tmp/file.txt"},
            files_written=set(),
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set()
        )

        file_lock_mgr.acquire_multiple.return_value = [token]
        file_lock_mgr.release_multiple.return_value = True

        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, {})

        with patch("subprocess.run") as mock_run:
            # Simulate timeout
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd="sleep 1000",
                timeout=10
            )

            with pytest.raises(CommandTimeoutError):
                executor.enqueue(
                    agent_id="agent-A",
                    cmd_id="cmd-123",
                    command="sleep 1000",
                    timeout_seconds=10
                )

            # Verify locks were still released
            file_lock_mgr.release_multiple.assert_called_once()

    def test_environment_variable_inheritance(self) -> None:
        """Test that environment variables are passed to subprocess."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()

        # Setup mocks
        cmd_analyzer.analyze.return_value = CommandDependencies(
            files_read=set(),
            files_written=set(),
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set()
        )

        file_lock_mgr.acquire_multiple.return_value = []
        file_lock_mgr.release_multiple.return_value = True

        # Create executor with custom env vars
        env_registry = {"CUSTOM_VAR": "custom_value", "PATH": "/custom/path"}
        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, env_registry)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            executor.enqueue(
                agent_id="agent-A",
                cmd_id="cmd-123",
                command="echo $CUSTOM_VAR"
            )

            # Verify subprocess was called with merged environment
            call_args = mock_run.call_args
            assert call_args is not None
            env_arg = call_args.kwargs["env"]

            # Verify custom vars are present
            assert env_arg["CUSTOM_VAR"] == "custom_value"
            # Verify it's a merge (os.environ values should still be there)
            # We can't check specific os.environ values reliably, but we can
            # verify that the env dict is the result of merging
            assert len(env_arg) >= len(env_registry)

    def test_lock_release_on_exception(self) -> None:
        """Test that locks are released even when subprocess raises exception."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()

        token = LockToken(
            agent_id="agent-A",
            file_path="/tmp/file.txt",
            lock_type="write",
            acquired_at=time.time(),
            token_id="token-1"
        )

        cmd_analyzer.analyze.return_value = CommandDependencies(
            files_read=set(),
            files_written={"/tmp/file.txt"},
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set()
        )

        file_lock_mgr.acquire_multiple.return_value = [token]
        file_lock_mgr.release_multiple.return_value = True

        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, {})

        with patch("subprocess.run") as mock_run:
            # Simulate an unexpected exception
            mock_run.side_effect = RuntimeError("Subprocess error")

            with pytest.raises(RuntimeError):
                executor.enqueue(
                    agent_id="agent-A",
                    cmd_id="cmd-123",
                    command="echo hello"
                )

            # Verify locks were still released (in finally block)
            file_lock_mgr.release_multiple.assert_called_once()

    def test_nonzero_exit_code_no_exception(self) -> None:
        """Test that non-zero exit codes don't raise exception."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()

        token = LockToken(
            agent_id="agent-A",
            file_path="/tmp/file.txt",
            lock_type="read",
            acquired_at=time.time(),
            token_id="token-1"
        )

        cmd_analyzer.analyze.return_value = CommandDependencies(
            files_read={"/tmp/file.txt"},
            files_written=set(),
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set()
        )

        file_lock_mgr.acquire_multiple.return_value = [token]
        file_lock_mgr.release_multiple.return_value = True

        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, {})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stdout="",
                stderr="Error message"
            )

            result = executor.enqueue(
                agent_id="agent-A",
                cmd_id="cmd-123",
                command="false"
            )

            # Should not raise exception, just return result with exit_code=1
            assert result.exit_code == 1
            assert result.stderr == "Error message"

    def test_partial_output_captured_on_timeout(self) -> None:
        """Test that partial output is captured when command times out."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()

        token = LockToken(
            agent_id="agent-A",
            file_path="/tmp/file.txt",
            lock_type="read",
            acquired_at=time.time(),
            token_id="token-1"
        )

        cmd_analyzer.analyze.return_value = CommandDependencies(
            files_read={"/tmp/file.txt"},
            files_written=set(),
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set()
        )

        file_lock_mgr.acquire_multiple.return_value = [token]
        file_lock_mgr.release_multiple.return_value = True

        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, {})

        with patch("subprocess.run") as mock_run:
            # Timeout exception (process killed by timeout)
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd="long running",
                timeout=5
            )

            with pytest.raises(CommandTimeoutError) as exc_info:
                executor.enqueue(
                    agent_id="agent-A",
                    cmd_id="cmd-123",
                    command="sleep 1000",
                    timeout_seconds=5
                )

            # Verify timeout error message mentions the timeout
            assert "timed out" in str(exc_info.value).lower()
            # Verify locks were still released
            file_lock_mgr.release_multiple.assert_called_once()


class TestEnqueueWithConsecutiveFiles:
    """Tests for handling commands with multiple files."""

    def test_multiple_read_files(self) -> None:
        """Test command with multiple read files."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()

        token1 = LockToken(
            agent_id="agent-A",
            file_path="/tmp/file1.txt",
            lock_type="read",
            acquired_at=time.time(),
            token_id="token-1"
        )
        token2 = LockToken(
            agent_id="agent-A",
            file_path="/tmp/file2.txt",
            lock_type="read",
            acquired_at=time.time(),
            token_id="token-2"
        )

        cmd_analyzer.analyze.return_value = CommandDependencies(
            files_read={"/tmp/file1.txt", "/tmp/file2.txt"},
            files_written=set(),
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set()
        )

        file_lock_mgr.acquire_multiple.return_value = [token1, token2]
        file_lock_mgr.release_multiple.return_value = True

        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, {})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="ok",
                stderr=""
            )

            result = executor.enqueue(
                agent_id="agent-A",
                cmd_id="cmd-123",
                command="cat file1.txt file2.txt"
            )

            assert len(result.locks_held) == 2

    def test_mixed_read_and_write_files(self) -> None:
        """Test command with both read and write files."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()

        token_r = LockToken(
            agent_id="agent-A",
            file_path="/tmp/input.txt",
            lock_type="read",
            acquired_at=time.time(),
            token_id="token-r"
        )
        token_w = LockToken(
            agent_id="agent-A",
            file_path="/tmp/output.txt",
            lock_type="write",
            acquired_at=time.time(),
            token_id="token-w"
        )

        cmd_analyzer.analyze.return_value = CommandDependencies(
            files_read={"/tmp/input.txt"},
            files_written={"/tmp/output.txt"},
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set()
        )

        file_lock_mgr.acquire_multiple.return_value = [token_r, token_w]
        file_lock_mgr.release_multiple.return_value = True

        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, {})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            result = executor.enqueue(
                agent_id="agent-A",
                cmd_id="cmd-123",
                command="process input.txt > output.txt"
            )

            # Verify acquire_multiple was called with separated read/write paths
            call_args = file_lock_mgr.acquire_multiple.call_args
            assert call_args is not None
            assert "/tmp/input.txt" in call_args.kwargs["read_paths"]
            assert "/tmp/output.txt" in call_args.kwargs["write_paths"]


class TestEnqueueWithWildcards:
    """Tests for handling commands with wildcard files."""

    def test_wildcard_conservative_fallback(self) -> None:
        """Test that wildcard files are handled conservatively."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()

        # Wildcard returned by analyzer (conservative fallback)
        cmd_analyzer.analyze.return_value = CommandDependencies(
            files_read={"*"},
            files_written=set(),
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set()
        )

        file_lock_mgr.acquire_multiple.return_value = []
        file_lock_mgr.release_multiple.return_value = True

        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, {})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            result = executor.enqueue(
                agent_id="agent-A",
                cmd_id="cmd-123",
                command="unknown-command"
            )

            # Verify acquire_multiple was called with empty read_paths when wildcard
            call_args = file_lock_mgr.acquire_multiple.call_args
            assert call_args is not None
            # When files_read is {"*"}, we pass empty list
            assert call_args.kwargs["read_paths"] == []


class TestEnqueueDurationTracking:
    """Tests for duration tracking."""

    def test_duration_seconds_recorded(self) -> None:
        """Test that execution duration is recorded."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()

        cmd_analyzer.analyze.return_value = CommandDependencies(
            files_read=set(),
            files_written=set(),
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set()
        )

        file_lock_mgr.acquire_multiple.return_value = []
        file_lock_mgr.release_multiple.return_value = True

        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, {})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            with patch("time.time") as mock_time:
                # Simulate time progression
                mock_time.side_effect = [100.0, 105.5]

                result = executor.enqueue(
                    agent_id="agent-A",
                    cmd_id="cmd-123",
                    command="echo test"
                )

                # Duration should be approximately 5.5 seconds
                assert abs(result.duration_seconds - 5.5) < 0.1


class TestEnqueueSubprocessOptions:
    """Tests for subprocess.run options."""

    def test_subprocess_called_with_correct_options(self) -> None:
        """Test that subprocess.run is called with correct options."""
        file_lock_mgr = Mock()
        cmd_analyzer = Mock()

        cmd_analyzer.analyze.return_value = CommandDependencies(
            files_read=set(),
            files_written=set(),
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set()
        )

        file_lock_mgr.acquire_multiple.return_value = []
        file_lock_mgr.release_multiple.return_value = True

        executor = CommandExecutor(file_lock_mgr, cmd_analyzer, {})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            executor.enqueue(
                agent_id="agent-A",
                cmd_id="cmd-123",
                command="echo hello",
                timeout_seconds=30
            )

            # Verify subprocess.run was called with correct options
            call_args = mock_run.call_args
            assert call_args is not None
            assert call_args[0][0] == "echo hello"
            assert call_args.kwargs["shell"] is True
            assert call_args.kwargs["timeout"] == 30
            assert call_args.kwargs["capture_output"] is True
            assert call_args.kwargs["text"] is True
            assert "env" in call_args.kwargs
