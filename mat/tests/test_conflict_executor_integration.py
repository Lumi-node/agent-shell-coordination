"""Integration tests for ConflictDetector + CommandExecutor interaction.

These tests verify that ConflictDetector correctly identifies conflicts
between commands that would be executed by CommandExecutor, and that
the safe_order recommendations align with lock acquisition requirements.
"""

import os
import tempfile
from unittest.mock import Mock, patch
import time

import pytest

from mat.analysis.command_analyzer import CommandDependencyAnalyzer
from mat.coordination.conflict_detector import ConflictDetector
from mat.execution.command_executor import CommandExecutor
from mat.core.file_lock_manager import FileLockManager, LockToken
from mat.exceptions import LockTimeoutError, CommandTimeoutError


@pytest.fixture
def analyzer() -> CommandDependencyAnalyzer:
    """Create a CommandDependencyAnalyzer instance."""
    return CommandDependencyAnalyzer()


@pytest.fixture
def detector(analyzer: CommandDependencyAnalyzer) -> ConflictDetector:
    """Create a ConflictDetector instance."""
    return ConflictDetector(analyzer)


@pytest.fixture
def lock_manager() -> FileLockManager:
    """Create a FileLockManager instance."""
    return FileLockManager()


@pytest.fixture
def executor(
    lock_manager: FileLockManager,
    analyzer: CommandDependencyAnalyzer
) -> CommandExecutor:
    """Create a CommandExecutor instance."""
    env_registry: dict[str, str] = {}
    return CommandExecutor(lock_manager, analyzer, env_registry)


class TestConflictDetectionWithExecutionOrder:
    """Test that ConflictDetector's safe_order matches execution lock requirements."""

    def test_write_write_conflict_safe_order_prevents_lock_conflict(
        self, detector: ConflictDetector, lock_manager: FileLockManager
    ) -> None:
        """Test that write_write safe_order prevents simultaneous write locks."""
        cmd1 = "python gen1.py --output result.txt"
        cmd2 = "python gen2.py --output result.txt"

        # Detect conflict
        conflict = detector.check_conflict(cmd1, cmd2, "cmd1", "cmd2")
        assert conflict is not None
        assert conflict.conflict_type == "write_write"
        assert conflict.safe_order == ["cmd1", "cmd2"]

        # Create a temp file for testing
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("test")
            file_path = f.name

        try:
            # cmd1 should be able to acquire write lock first
            token1 = lock_manager.acquire_write(
                "agent1", file_path, timeout_seconds=5
            )
            assert token1 is not None

            # cmd2 should NOT be able to acquire write lock while cmd1 holds it
            with pytest.raises(LockTimeoutError):
                lock_manager.acquire_write("agent2", file_path, timeout_seconds=1)

            # After cmd1 releases, cmd2 can acquire
            lock_manager.release_write(token1)
            token2 = lock_manager.acquire_write("agent2", file_path, timeout_seconds=1)
            assert token2 is not None
            lock_manager.release_write(token2)

        finally:
            os.unlink(file_path)

    def test_read_write_conflict_safe_order_requires_writer_first(
        self, detector: ConflictDetector, lock_manager: FileLockManager
    ) -> None:
        """Test that read_write safe_order puts writer first as required by locks."""
        cmd1 = "python generate.py --output data.csv"
        cmd2 = "mypy data.csv"

        # Detect conflict
        conflict = detector.check_conflict(cmd1, cmd2, "gen", "check")
        assert conflict is not None
        assert conflict.conflict_type == "read_write"
        # Writer (gen) must be first, reader (check) second
        assert conflict.safe_order == ["gen", "check"]

        # Create a temp file for testing
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("old data")
            file_path = f.name

        try:
            # Reader acquires lock first
            token_read = lock_manager.acquire_read(
                "agent_check", file_path, timeout_seconds=1
            )
            assert token_read is not None

            # Writer should NOT be able to acquire while reader holds lock
            with pytest.raises(LockTimeoutError):
                lock_manager.acquire_write("agent_gen", file_path, timeout_seconds=1)

            # When reader releases, writer can acquire
            lock_manager.release_read(token_read)
            token_write = lock_manager.acquire_write(
                "agent_gen", file_path, timeout_seconds=1
            )
            assert token_write is not None
            lock_manager.release_write(token_write)

        finally:
            os.unlink(file_path)

    def test_delete_any_conflict_safe_order_writer_first(
        self, detector: ConflictDetector, lock_manager: FileLockManager
    ) -> None:
        """Test that delete_any safe_order puts deleter last as required by locks."""
        cmd1 = "rm file.txt"
        cmd2 = "python gen.py --output file.txt"

        # Detect conflict
        conflict = detector.check_conflict(cmd1, cmd2, "deleter", "writer")
        assert conflict is not None
        assert conflict.conflict_type == "delete_any"
        # Writer must be first, deleter second
        assert conflict.safe_order == ["writer", "deleter"]

        # Create a temp file for testing
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("test")
            file_path = f.name

        try:
            # Writer acquires write lock
            token_write = lock_manager.acquire_write(
                "agent_writer", file_path, timeout_seconds=1
            )
            assert token_write is not None

            # Another agent cannot acquire lock while writer holds it
            # (deleter would need exclusive access)
            with pytest.raises(LockTimeoutError):
                lock_manager.acquire_write("agent_deleter", file_path, timeout_seconds=1)

            # When writer releases, deleter can acquire
            lock_manager.release_write(token_write)
            token_delete = lock_manager.acquire_write(
                "agent_deleter", file_path, timeout_seconds=1
            )
            assert token_delete is not None
            lock_manager.release_write(token_delete)

        finally:
            if os.path.exists(file_path):
                os.unlink(file_path)


class TestCommandExecutorRespectingConflictSafeOrder:
    """Test that CommandExecutor's lock acquisition respects ConflictDetector's safe_order."""

    def test_executor_respects_write_write_safe_order(
        self, executor: CommandExecutor, lock_manager: FileLockManager
    ) -> None:
        """Test that CommandExecutor properly handles write_write conflicts via locks."""
        # Create temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("initial")
            file_path = f.name

        try:
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(
                    returncode=0,
                    stdout="",
                    stderr=""
                )

                # First command acquires write lock
                result1 = executor.enqueue(
                    agent_id="agent1",
                    cmd_id="cmd1",
                    command=f"python gen1.py --output {file_path}",
                    lock_timeout_seconds=1
                )
                assert result1.exit_code == 0
                # Lock should be released after execution
                assert len(result1.locks_held) > 0

                # Second command should also succeed (lock was released)
                result2 = executor.enqueue(
                    agent_id="agent2",
                    cmd_id="cmd2",
                    command=f"python gen2.py --output {file_path}",
                    lock_timeout_seconds=1
                )
                assert result2.exit_code == 0

        finally:
            os.unlink(file_path)

    def test_executor_respects_read_write_safe_order(
        self, executor: CommandExecutor
    ) -> None:
        """Test that CommandExecutor handles read_write conflicts via locks."""
        # Create temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("data")
            file_path = f.name

        try:
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(
                    returncode=0,
                    stdout="output",
                    stderr=""
                )

                # Writer executes first
                result_write = executor.enqueue(
                    agent_id="agent_write",
                    cmd_id="cmd_write",
                    command=f"python gen.py --output {file_path}",
                    lock_timeout_seconds=5
                )
                assert result_write.exit_code == 0

                # Reader can execute after writer (lock was released)
                result_read = executor.enqueue(
                    agent_id="agent_read",
                    cmd_id="cmd_read",
                    command=f"mypy {file_path}",
                    lock_timeout_seconds=5
                )
                assert result_read.exit_code == 0

        finally:
            os.unlink(file_path)


class TestConflictDetectorMultipleCommands:
    """Test ConflictDetector analyzing multiple command sequences."""

    def test_sequence_of_three_commands_conflict_detection(
        self, detector: ConflictDetector
    ) -> None:
        """Test detecting conflicts in a sequence of three commands."""
        cmd_refactor = "python refactor.py --input main.py --output main.py"
        cmd_typecheck = "mypy main.py"
        cmd_train = "python train.py --input main.py"

        # Check refactor vs typecheck
        conflict_1 = detector.check_conflict(
            cmd_refactor, cmd_typecheck, "refactor", "typecheck"
        )
        assert conflict_1 is not None
        assert conflict_1.conflict_type == "read_write"
        assert conflict_1.safe_order == ["refactor", "typecheck"]

        # Check typecheck vs train (both read, no conflict)
        conflict_2 = detector.check_conflict(
            cmd_typecheck, cmd_train, "typecheck", "train"
        )
        assert conflict_2 is None

        # Check refactor vs train
        conflict_3 = detector.check_conflict(
            cmd_refactor, cmd_train, "refactor", "train"
        )
        assert conflict_3 is not None
        assert conflict_3.conflict_type == "read_write"
        assert conflict_3.safe_order == ["refactor", "train"]

    def test_conflict_graph_with_custom_ids(self, detector: ConflictDetector) -> None:
        """Test using custom command IDs for conflict detection."""
        commands = {
            "A": "python script_a.py --output shared.txt",
            "B": "python script_b.py --output shared.txt",
            "C": "grep pattern shared.txt"
        }

        # Build conflict graph
        conflicts = {}
        for id1 in commands:
            for id2 in commands:
                if id1 < id2:
                    conflict = detector.check_conflict(
                        commands[id1], commands[id2], id1, id2
                    )
                    if conflict:
                        conflicts[f"{id1}-{id2}"] = conflict

        # Should detect conflicts: A-B (write_write), A-C (read_write), B-C (read_write)
        assert "A-B" in conflicts
        assert conflicts["A-B"].conflict_type == "write_write"

        assert "A-C" in conflicts
        assert conflicts["A-C"].conflict_type == "read_write"
        assert conflicts["A-C"].safe_order[0] == "A"  # Writer first

        assert "B-C" in conflicts
        assert conflicts["B-C"].conflict_type == "read_write"
        assert conflicts["B-C"].safe_order[0] == "B"  # Writer first


class TestExecutorWithAnalyzerAndLockManager:
    """Test CommandExecutor with actual CommandDependencyAnalyzer and FileLockManager."""

    def test_executor_analyzes_dependencies_correctly(
        self, analyzer: CommandDependencyAnalyzer, executor: CommandExecutor
    ) -> None:
        """Test that executor uses analyzer to extract dependencies correctly."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("test")
            file_path = f.name

        try:
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(
                    returncode=0,
                    stdout="result",
                    stderr=""
                )

                # Analyze the command first
                cmd = f"python script.py --input {file_path} --output output.txt"
                deps = analyzer.analyze(cmd)
                assert file_path in deps.files_read or len(deps.files_read) == 1

                # Execute through executor
                result = executor.enqueue(
                    agent_id="agent1",
                    cmd_id="cmd1",
                    command=cmd,
                    lock_timeout_seconds=5
                )
                assert result.exit_code == 0

        finally:
            os.unlink(file_path)

    def test_executor_acquires_correct_lock_types(
        self, executor: CommandExecutor
    ) -> None:
        """Test that executor acquires correct lock types for read vs write."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("test")
            file_path = f.name

        try:
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(
                    returncode=0,
                    stdout="",
                    stderr=""
                )

                # Read-only command
                result_read = executor.enqueue(
                    agent_id="agent1",
                    cmd_id="cmd_read",
                    command=f"grep pattern {file_path}",
                    lock_timeout_seconds=5
                )
                assert result_read.exit_code == 0
                # Should have acquired read lock
                if file_path in result_read.locks_held:
                    assert result_read.locks_held[file_path] == "read"

                # Write command
                result_write = executor.enqueue(
                    agent_id="agent2",
                    cmd_id="cmd_write",
                    command=f"python gen.py --output {file_path}",
                    lock_timeout_seconds=5
                )
                assert result_write.exit_code == 0
                # Should have acquired write lock
                if file_path in result_write.locks_held:
                    assert result_write.locks_held[file_path] == "write"

        finally:
            os.unlink(file_path)


class TestConflictAndExecutionConsistency:
    """Test that ConflictDetector predictions are consistent with execution reality."""

    def test_conflict_prediction_matches_lock_behavior(
        self, detector: ConflictDetector, lock_manager: FileLockManager
    ) -> None:
        """Test that detected conflicts correspond to lock conflicts."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("test")
            file_path = f.name

        try:
            # Create two commands that conflict
            cmd1 = f"echo data > {file_path}"
            cmd2 = f"echo other > {file_path}"

            # Detect conflict
            conflict = detector.check_conflict(cmd1, cmd2, "cmd1", "cmd2")
            assert conflict is not None

            # Verify the conflict corresponds to lock behavior
            # First agent acquires lock
            token1 = lock_manager.acquire_write(
                "agent1", file_path, timeout_seconds=1
            )
            assert token1 is not None

            # Second agent cannot acquire lock (timeout expected)
            with pytest.raises(LockTimeoutError):
                lock_manager.acquire_write("agent2", file_path, timeout_seconds=1)

            # Clean up
            lock_manager.release_write(token1)

        finally:
            os.unlink(file_path)

    def test_no_conflict_matches_no_lock_conflict(
        self, detector: ConflictDetector, lock_manager: FileLockManager
    ) -> None:
        """Test that no detected conflict means no lock conflicts."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f1:
            f1.write("test1")
            file_path1 = f1.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f2:
            f2.write("test2")
            file_path2 = f2.name

        try:
            # Create two commands that don't conflict (different files)
            cmd1 = f"echo data > {file_path1}"
            cmd2 = f"echo other > {file_path2}"

            # Detect conflict
            conflict = detector.check_conflict(cmd1, cmd2, "cmd1", "cmd2")
            assert conflict is None

            # Verify lock behavior matches: both should succeed
            token1 = lock_manager.acquire_write("agent1", file_path1, timeout_seconds=1)
            assert token1 is not None

            token2 = lock_manager.acquire_write("agent2", file_path2, timeout_seconds=1)
            assert token2 is not None

            # Clean up
            lock_manager.release_write(token1)
            lock_manager.release_write(token2)

        finally:
            os.unlink(file_path1)
            os.unlink(file_path2)


class TestEnvironmentVariableConflictViaExecutor:
    """Test environment variable conflict detection in executor context."""

    def test_executor_passes_environment_variables(
        self, executor: CommandExecutor
    ) -> None:
        """Test that CommandExecutor correctly passes environment variables."""
        # Set up executor with env vars
        executor._env_registry["CUSTOM_VAR"] = "test_value"
        executor._env_registry["DEBUG"] = "true"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            executor.enqueue(
                agent_id="agent1",
                cmd_id="cmd1",
                command="echo $CUSTOM_VAR",
                lock_timeout_seconds=5
            )

            # Verify environment was passed
            call_args = mock_run.call_args
            assert call_args is not None
            env = call_args.kwargs["env"]
            assert env["CUSTOM_VAR"] == "test_value"
            assert env["DEBUG"] == "true"

    def test_env_conflict_detection_with_custom_ids(
        self, detector: ConflictDetector
    ) -> None:
        """Test environment variable conflict detection with custom IDs."""
        cmd1 = "export DEBUG=true"
        cmd2 = "export DEBUG=false"

        conflict = detector.check_conflict(cmd1, cmd2, "cmd_a", "cmd_b")
        assert conflict is not None
        assert conflict.conflict_type == "env_conflict"
        assert "DEBUG" in conflict.description
        assert conflict.safe_order == ["cmd_a", "cmd_b"]
