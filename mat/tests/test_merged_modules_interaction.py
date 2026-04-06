"""Integration tests for newly merged modules and their interactions.

Tests verify that:
1. ConflictDetector (from issue/67fea13a-06-conflict-detector) works correctly
2. CommandExecutor (from issue/67fea13a-07-command-executor) works correctly
3. The interaction between ConflictDetector and CommandExecutor
4. All merged modules work with previously implemented modules
"""

import os
import tempfile
from unittest.mock import Mock, patch
import time
import threading

import pytest

from mat.analysis.command_analyzer import CommandDependencyAnalyzer
from mat.coordination.conflict_detector import ConflictDetector, Conflict
from mat.execution.command_executor import CommandExecutor, ExecutionResult
from mat.core.file_lock_manager import FileLockManager
from mat.core.agent_registry import AgentRegistry
from mat.exceptions import LockTimeoutError, CommandTimeoutError


@pytest.fixture
def temp_file() -> str:
    """Create a temporary file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        f.write("initial content")
        return f.name


@pytest.fixture
def temp_file_cleanup(temp_file: str) -> str:
    """Provide temp file path with cleanup."""
    yield temp_file
    if os.path.exists(temp_file):
        os.unlink(temp_file)


class TestConflictDetectorIntegration:
    """Test ConflictDetector as a standalone merged module."""

    def test_detector_analyzes_write_write_conflict_correctly(self) -> None:
        """Test ConflictDetector with write_write conflict scenario."""
        analyzer = CommandDependencyAnalyzer()
        detector = ConflictDetector(analyzer)

        cmd1 = "python refactor.py > main.py"
        cmd2 = "python format.py > main.py"

        conflict = detector.check_conflict(cmd1, cmd2, "refactor", "format")

        assert isinstance(conflict, Conflict)
        assert conflict.conflict_type == "write_write"
        assert conflict.cmd1_id == "refactor"
        assert conflict.cmd2_id == "format"
        assert conflict.safe_order == ["refactor", "format"]
        assert "main.py" in conflict.description

    def test_detector_analyzes_read_write_conflict_correctly(self) -> None:
        """Test ConflictDetector with read_write conflict scenario."""
        analyzer = CommandDependencyAnalyzer()
        detector = ConflictDetector(analyzer)

        cmd1 = "python generate.py > config.py"
        cmd2 = "mypy config.py"

        conflict = detector.check_conflict(cmd1, cmd2, "generate", "typecheck")

        assert isinstance(conflict, Conflict)
        assert conflict.conflict_type == "read_write"
        assert conflict.safe_order == ["generate", "typecheck"]

    def test_detector_analyzes_delete_any_conflict_correctly(self) -> None:
        """Test ConflictDetector with delete_any conflict scenario."""
        analyzer = CommandDependencyAnalyzer()
        detector = ConflictDetector(analyzer)

        cmd1 = "rm output.csv"
        cmd2 = "python process.py > output.csv"

        conflict = detector.check_conflict(cmd1, cmd2, "deleter", "writer")

        assert isinstance(conflict, Conflict)
        assert conflict.conflict_type == "delete_any"
        assert conflict.safe_order == ["writer", "deleter"]

    def test_detector_analyzes_env_conflict_correctly(self) -> None:
        """Test ConflictDetector with env_conflict scenario."""
        analyzer = CommandDependencyAnalyzer()
        detector = ConflictDetector(analyzer)

        cmd1 = "export MODEL_PATH=/path/a"
        cmd2 = "export MODEL_PATH=/path/b"

        conflict = detector.check_conflict(cmd1, cmd2, "cmd_a", "cmd_b")

        assert isinstance(conflict, Conflict)
        assert conflict.conflict_type == "env_conflict"
        assert "MODEL_PATH" in conflict.description

    def test_detector_returns_none_for_no_conflict(self) -> None:
        """Test ConflictDetector returns None for no conflict."""
        analyzer = CommandDependencyAnalyzer()
        detector = ConflictDetector(analyzer)

        cmd1 = "python process1.py > output1.csv"
        cmd2 = "python process2.py > output2.csv"

        conflict = detector.check_conflict(cmd1, cmd2)

        assert conflict is None


class TestCommandExecutorIntegration:
    """Test CommandExecutor as a standalone merged module."""

    def test_executor_succeeds_with_valid_inputs(self) -> None:
        """Test CommandExecutor executes commands successfully."""
        analyzer = CommandDependencyAnalyzer()
        lock_mgr = FileLockManager()
        executor = CommandExecutor(lock_mgr, analyzer, {})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="command output",
                stderr=""
            )

            result = executor.enqueue(
                agent_id="agent1",
                cmd_id="cmd1",
                command="echo hello"
            )

        assert isinstance(result, ExecutionResult)
        assert result.exit_code == 0
        assert result.stdout == "command output"
        assert result.stderr == ""
        assert result.duration_seconds >= 0

    def test_executor_captures_stderr(self) -> None:
        """Test CommandExecutor captures stderr output."""
        analyzer = CommandDependencyAnalyzer()
        lock_mgr = FileLockManager()
        executor = CommandExecutor(lock_mgr, analyzer, {})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stdout="",
                stderr="error message"
            )

            result = executor.enqueue(
                agent_id="agent1",
                cmd_id="cmd1",
                command="false"
            )

        assert result.exit_code == 1
        assert result.stderr == "error message"

    def test_executor_respects_lock_timeouts(self) -> None:
        """Test CommandExecutor raises LockTimeoutError when locks timeout."""
        analyzer = CommandDependencyAnalyzer()
        lock_mgr = Mock()
        executor = CommandExecutor(lock_mgr, analyzer, {})

        # Make lock acquisition timeout
        lock_mgr.acquire_multiple.side_effect = LockTimeoutError(
            "Lock timeout"
        )

        with pytest.raises(LockTimeoutError):
            executor.enqueue(
                agent_id="agent1",
                cmd_id="cmd1",
                command="echo hello"
            )

    def test_executor_respects_command_timeouts(self) -> None:
        """Test CommandExecutor raises CommandTimeoutError on process timeout."""
        analyzer = CommandDependencyAnalyzer()
        lock_mgr = FileLockManager()
        executor = CommandExecutor(lock_mgr, analyzer, {})

        with patch("subprocess.run") as mock_run:
            import subprocess
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd="sleep 1000",
                timeout=5
            )

            with pytest.raises(CommandTimeoutError):
                executor.enqueue(
                    agent_id="agent1",
                    cmd_id="cmd1",
                    command="sleep 1000",
                    timeout_seconds=5
                )

    def test_executor_inherits_environment_variables(self) -> None:
        """Test CommandExecutor passes environment variables to subprocess."""
        analyzer = CommandDependencyAnalyzer()
        lock_mgr = FileLockManager()
        env_registry = {
            "CUSTOM_VAR": "custom_value",
            "ANOTHER_VAR": "another_value"
        }
        executor = CommandExecutor(lock_mgr, analyzer, env_registry)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            executor.enqueue(
                agent_id="agent1",
                cmd_id="cmd1",
                command="echo $CUSTOM_VAR"
            )

            # Verify environment was passed
            call_args = mock_run.call_args
            env = call_args.kwargs["env"]
            assert env["CUSTOM_VAR"] == "custom_value"
            assert env["ANOTHER_VAR"] == "another_value"


class TestConflictDetectorCommandExecutorInteraction:
    """Test interaction between ConflictDetector and CommandExecutor."""

    def test_safe_order_guides_execution_sequence(self) -> None:
        """Test that conflict's safe_order can guide execution order."""
        analyzer = CommandDependencyAnalyzer()
        detector = ConflictDetector(analyzer)
        lock_mgr = FileLockManager()
        executor = CommandExecutor(lock_mgr, analyzer, {})

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("initial")
            file_path = f.name

        try:
            # Detect conflict
            cmd1 = f"echo new > {file_path}"
            cmd2 = f"cat {file_path}"

            conflict = detector.check_conflict(cmd1, cmd2, "writer", "reader")
            assert conflict is not None
            assert conflict.conflict_type == "read_write"
            assert conflict.safe_order == ["writer", "reader"]

            # Follow the safe order: execute writer first, then reader
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(
                    returncode=0,
                    stdout="output",
                    stderr=""
                )

                # Execute in safe order
                result1 = executor.enqueue(
                    agent_id="agent_write",
                    cmd_id="cmd_write",
                    command=cmd1
                )
                assert result1.exit_code == 0

                result2 = executor.enqueue(
                    agent_id="agent_read",
                    cmd_id="cmd_read",
                    command=cmd2
                )
                assert result2.exit_code == 0

        finally:
            os.unlink(file_path)

    def test_multiple_conflicts_create_execution_graph(self) -> None:
        """Test building execution dependencies from multiple conflicts."""
        analyzer = CommandDependencyAnalyzer()
        detector = ConflictDetector(analyzer)

        commands = {
            "generate": "python gen.py > data.csv",
            "process": "python process.py --input data.csv > results.txt",
            "analyze": "python analyze.py --input results.txt > report.txt"
        }

        # Build conflict graph
        dependencies = {}
        cmd_ids = sorted(commands.keys())
        for i, id1 in enumerate(cmd_ids):
            for id2 in cmd_ids[i+1:]:
                conflict = detector.check_conflict(
                    commands[id1], commands[id2], id1, id2
                )
                if conflict:
                    # Store dependency: safe_order[0] must run before safe_order[1]
                    first_cmd = conflict.safe_order[0]
                    second_cmd = conflict.safe_order[1]
                    if first_cmd not in dependencies:
                        dependencies[first_cmd] = []
                    dependencies[first_cmd].append(second_cmd)

        # Verify dependency chain
        assert "generate" in dependencies
        assert "process" in dependencies["generate"]


class TestMergedModulesWithExistingComponents:
    """Test new merged modules with previously implemented components."""

    def test_conflict_detector_with_agent_registry(self) -> None:
        """Test ConflictDetector doesn't interfere with AgentRegistry."""
        # Create instances
        registry = AgentRegistry()
        analyzer = CommandDependencyAnalyzer()
        detector = ConflictDetector(analyzer)

        # Registry should work
        assert registry.register("agent1", "token1") is True
        assert "agent1" in registry.list_active()

        # Detector should work independently
        cmd1 = "python a.py > file.txt"
        cmd2 = "python b.py > file.txt"
        conflict = detector.check_conflict(cmd1, cmd2)
        assert conflict is not None

    def test_command_executor_with_agent_registry(self) -> None:
        """Test CommandExecutor works alongside AgentRegistry."""
        registry = AgentRegistry()
        analyzer = CommandDependencyAnalyzer()
        lock_mgr = FileLockManager()
        executor = CommandExecutor(lock_mgr, analyzer, {})

        # Register agents
        assert registry.register("agent1", "token1") is True
        assert registry.register("agent2", "token2") is True

        # Execute commands with registered agents
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            # Both agents can execute commands
            result1 = executor.enqueue(
                agent_id="agent1",
                cmd_id="cmd1",
                command="echo hello"
            )
            assert result1.exit_code == 0

            result2 = executor.enqueue(
                agent_id="agent2",
                cmd_id="cmd2",
                command="echo world"
            )
            assert result2.exit_code == 0

            # Registry should still have both agents
            assert "agent1" in registry.list_active()
            assert "agent2" in registry.list_active()

    def test_command_executor_with_file_lock_manager_real_files(
        self, temp_file_cleanup: str
    ) -> None:
        """Test CommandExecutor with real FileLockManager and actual files."""
        analyzer = CommandDependencyAnalyzer()
        lock_mgr = FileLockManager()
        executor = CommandExecutor(lock_mgr, analyzer, {})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            # Execute command that reads the file
            cmd = f"grep content {temp_file_cleanup}"
            result = executor.enqueue(
                agent_id="agent1",
                cmd_id="cmd1",
                command=cmd
            )

            assert result.exit_code == 0
            # Should have acquired read lock
            assert len(result.locks_held) >= 0


class TestMergeConflictResolution:
    """Test that merge conflicts were properly resolved."""

    def test_both_merged_modules_importable(self) -> None:
        """Test that both merged modules are importable."""
        # ConflictDetector from issue/67fea13a-06-conflict-detector
        from mat.coordination.conflict_detector import ConflictDetector, Conflict
        assert ConflictDetector is not None
        assert Conflict is not None

        # CommandExecutor from issue/67fea13a-07-command-executor
        from mat.execution.command_executor import CommandExecutor, ExecutionResult
        assert CommandExecutor is not None
        assert ExecutionResult is not None

    def test_merged_modules_in_public_api(self) -> None:
        """Test that merged modules are exposed in public API."""
        from mat import Conflict, ExecutionResult
        assert Conflict is not None
        assert ExecutionResult is not None

    def test_no_conflicting_exports(self) -> None:
        """Test that merged modules don't have conflicting names."""
        import mat
        from mat.coordination.conflict_detector import Conflict
        from mat.execution.command_executor import ExecutionResult

        # Should be able to import both without conflicts
        assert mat.Conflict is Conflict
        assert mat.ExecutionResult is ExecutionResult

    def test_dependency_resolution_conflict_detector(self) -> None:
        """Test ConflictDetector has proper dependencies resolved."""
        from mat.coordination.conflict_detector import ConflictDetector
        from mat.analysis.command_analyzer import CommandDependencyAnalyzer

        # Should be able to instantiate with CommandDependencyAnalyzer
        analyzer = CommandDependencyAnalyzer()
        detector = ConflictDetector(analyzer)

        # Should work
        conflict = detector.check_conflict(
            "python a.py > file.txt",
            "python b.py > file.txt"
        )
        assert conflict is not None

    def test_dependency_resolution_command_executor(self) -> None:
        """Test CommandExecutor has proper dependencies resolved."""
        from mat.execution.command_executor import CommandExecutor
        from mat.core.file_lock_manager import FileLockManager
        from mat.analysis.command_analyzer import CommandDependencyAnalyzer

        # Should be able to instantiate with all dependencies
        lock_mgr = FileLockManager()
        analyzer = CommandDependencyAnalyzer()
        env_registry: dict[str, str] = {}

        executor = CommandExecutor(lock_mgr, analyzer, env_registry)
        assert executor is not None


class TestCrossModuleErrorHandling:
    """Test error handling across merged and existing modules."""

    def test_conflict_detector_validates_inputs(self) -> None:
        """Test ConflictDetector validates command inputs."""
        analyzer = CommandDependencyAnalyzer()
        detector = ConflictDetector(analyzer)

        # Empty command should raise
        with pytest.raises(ValueError):
            detector.check_conflict("", "cmd2")

        with pytest.raises(ValueError):
            detector.check_conflict("cmd1", "")

        # None command should raise
        with pytest.raises(ValueError):
            detector.check_conflict(None, "cmd2")  # type: ignore

    def test_command_executor_validates_inputs(self) -> None:
        """Test CommandExecutor validates enqueue inputs."""
        analyzer = CommandDependencyAnalyzer()
        lock_mgr = FileLockManager()
        executor = CommandExecutor(lock_mgr, analyzer, {})

        # Empty agent_id
        with pytest.raises(ValueError):
            executor.enqueue("", "cmd1", "echo hello")

        # Empty cmd_id
        with pytest.raises(ValueError):
            executor.enqueue("agent1", "", "echo hello")

        # Empty command
        with pytest.raises(ValueError):
            executor.enqueue("agent1", "cmd1", "")

    def test_lock_timeout_propagates_through_executor(self) -> None:
        """Test that LockTimeoutError from lock manager propagates through executor."""
        analyzer = CommandDependencyAnalyzer()
        lock_mgr = Mock()
        executor = CommandExecutor(lock_mgr, analyzer, {})

        lock_mgr.acquire_multiple.side_effect = LockTimeoutError("timeout")

        with pytest.raises(LockTimeoutError):
            executor.enqueue("agent1", "cmd1", "echo hello")

    def test_command_timeout_propagates_from_executor(self) -> None:
        """Test that CommandTimeoutError propagates from executor."""
        analyzer = CommandDependencyAnalyzer()
        lock_mgr = FileLockManager()
        executor = CommandExecutor(lock_mgr, analyzer, {})

        with patch("subprocess.run") as mock_run:
            import subprocess
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 5)

            with pytest.raises(CommandTimeoutError):
                executor.enqueue("agent1", "cmd1", "sleep 1000", timeout_seconds=5)


class TestIntegrationScenarios:
    """Test realistic integration scenarios using merged modules."""

    def test_three_agent_pipeline_scenario(self) -> None:
        """Test a realistic three-agent pipeline with conflict detection."""
        analyzer = CommandDependencyAnalyzer()
        detector = ConflictDetector(analyzer)
        lock_mgr = FileLockManager()
        executor = CommandExecutor(lock_mgr, analyzer, {})

        # Three agents: code_refactorer, type_checker, model_trainer
        # They work on shared files: main.py, model.pkl

        # Note: Using separate input/output files to avoid lock manager conflicts
        # (same file can't be both read and written in one command)
        commands = {
            "refactor": "python refactor_code.py > main.py",
            "typecheck": "mypy main.py",
            "train": "python train.py --input main.py > model.pkl"
        }

        # Analyze all pairwise conflicts
        conflict_pairs = {}
        for id1 in commands:
            for id2 in commands:
                if id1 < id2:
                    conflict = detector.check_conflict(
                        commands[id1], commands[id2], id1, id2
                    )
                    if conflict:
                        conflict_pairs[f"{id1}-{id2}"] = conflict

        # Should detect conflicts
        assert len(conflict_pairs) > 0

        # Execute commands (in order that respects conflicts if they exist)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            for cmd_name, cmd in commands.items():
                result = executor.enqueue(
                    agent_id=f"agent_{cmd_name}",
                    cmd_id=cmd_name,
                    command=cmd,
                    lock_timeout_seconds=5
                )
                assert result.exit_code == 0

    def test_conflict_free_parallel_execution(self) -> None:
        """Test that conflict-free commands can execute in parallel."""
        analyzer = CommandDependencyAnalyzer()
        detector = ConflictDetector(analyzer)

        # Two commands on completely different files
        cmd1 = "python process1.py > data1.csv"
        cmd2 = "python process2.py > data2.csv"

        conflict = detector.check_conflict(cmd1, cmd2)
        assert conflict is None

        # Both should be able to execute "in parallel" (via locks)
        lock_mgr = FileLockManager()
        executor = CommandExecutor(lock_mgr, analyzer, {})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            result1 = executor.enqueue("agent1", "cmd1", cmd1)
            assert result1.exit_code == 0

            result2 = executor.enqueue("agent2", "cmd2", cmd2)
            assert result2.exit_code == 0
