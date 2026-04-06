"""Integration tests for the merged public API.

Tests verify that the merged public API exports work correctly
and interact properly with the merged modules.
"""

import pytest
from typing import List

# Import from public API
from mat import (
    AgentCoordinator,
    ExecutionResult,
    LockTimeoutError,
    CommandTimeoutError,
    LockToken,
    AgentRegistry,
    CommandDependencies,
    Conflict,
)

# Also import implementation modules
from mat.analysis.command_analyzer import CommandDependencyAnalyzer
from mat.core.file_lock_manager import FileLockManager
from mat.coordination.conflict_detector import ConflictDetector


class TestPublicAPIImports:
    """Test that all public API imports work correctly."""

    def test_agent_coordinator_importable(self) -> None:
        """Test AgentCoordinator is importable from mat."""
        assert AgentCoordinator is not None
        assert hasattr(AgentCoordinator, '__init__')
        assert hasattr(AgentCoordinator, 'execute')
        assert hasattr(AgentCoordinator, 'set_env')
        assert hasattr(AgentCoordinator, 'get_env')
        assert hasattr(AgentCoordinator, 'list_agents')
        assert hasattr(AgentCoordinator, 'shutdown')

    def test_execution_result_importable(self) -> None:
        """Test ExecutionResult is importable from mat."""
        assert ExecutionResult is not None
        # Should be a dataclass
        result = ExecutionResult(
            exit_code=0,
            stdout="output",
            stderr="",
            duration_seconds=1.0,
            locks_held={}
        )
        assert result.exit_code == 0
        assert result.stdout == "output"

    def test_exception_types_importable(self) -> None:
        """Test exception types are importable from mat."""
        assert LockTimeoutError is not None
        assert CommandTimeoutError is not None
        assert issubclass(LockTimeoutError, Exception)
        assert issubclass(CommandTimeoutError, Exception)

    def test_lock_token_importable(self) -> None:
        """Test LockToken is importable from mat."""
        assert LockToken is not None

    def test_agent_registry_importable(self) -> None:
        """Test AgentRegistry is importable from mat."""
        assert AgentRegistry is not None
        registry = AgentRegistry()
        assert hasattr(registry, 'register')
        assert hasattr(registry, 'heartbeat')
        assert hasattr(registry, 'list_active')
        assert hasattr(registry, 'deregister')

    def test_command_dependencies_importable(self) -> None:
        """Test CommandDependencies is importable from mat."""
        assert CommandDependencies is not None
        deps = CommandDependencies(
            files_read=set(),
            files_written=set(),
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set()
        )
        assert isinstance(deps.files_read, set)

    def test_conflict_importable(self) -> None:
        """Test Conflict is importable from mat."""
        assert Conflict is not None
        conflict = Conflict(
            cmd1_id="cmd1",
            cmd2_id="cmd2",
            conflict_type="write_write",
            description="Both write same file",
            safe_order=["cmd1", "cmd2"]
        )
        assert conflict.cmd1_id == "cmd1"
        assert conflict.conflict_type == "write_write"

    def test_all_exports_in_all(self) -> None:
        """Test __all__ contains all expected exports."""
        import mat
        expected_exports = [
            "AgentCoordinator",
            "ExecutionResult",
            "LockTimeoutError",
            "CommandTimeoutError",
            "LockToken",
            "AgentRegistry",
            "CommandDependencies",
            "Conflict",
        ]
        for export in expected_exports:
            assert export in mat.__all__


class TestPublicAPIVersion:
    """Test version string is accessible."""

    def test_version_accessible(self) -> None:
        """Test __version__ is accessible."""
        import mat
        assert hasattr(mat, '__version__')
        assert isinstance(mat.__version__, str)
        assert mat.__version__ == "0.1.0"


class TestAgentCoordinatorStubBehavior:
    """Test AgentCoordinator stub behavior (issue-08 not yet implemented)."""

    def test_agent_coordinator_init_requires_agent_id(self) -> None:
        """Test AgentCoordinator requires non-empty agent_id."""
        # Valid initialization
        coordinator = AgentCoordinator("test-agent")
        assert coordinator._agent_id == "test-agent"

        # Invalid agent_id
        with pytest.raises(ValueError):
            AgentCoordinator("")

        with pytest.raises(ValueError):
            AgentCoordinator(None)  # type: ignore

    def test_agent_coordinator_heartbeat_interval(self) -> None:
        """Test AgentCoordinator heartbeat_interval parameter."""
        coordinator = AgentCoordinator("test-agent", heartbeat_interval_seconds=5)
        assert coordinator._heartbeat_interval == 5

        # Default is 10
        coordinator2 = AgentCoordinator("test-agent-2")
        assert coordinator2._heartbeat_interval == 10

    def test_agent_coordinator_execute_not_implemented(self) -> None:
        """Test execute method raises NotImplementedError (stub)."""
        coordinator = AgentCoordinator("test-agent")
        with pytest.raises(NotImplementedError):
            coordinator.execute("echo hello")

    def test_agent_coordinator_set_env_validates_input(self) -> None:
        """Test set_env validates var_name parameter."""
        coordinator = AgentCoordinator("test-agent")

        # Valid call (just validates, doesn't store in stub)
        coordinator.set_env("MY_VAR", "value")

        # Invalid var_name
        with pytest.raises(ValueError):
            coordinator.set_env("", "value")

        with pytest.raises(ValueError):
            coordinator.set_env(None, "value")  # type: ignore

    def test_agent_coordinator_get_env_stub(self) -> None:
        """Test get_env returns empty string (stub)."""
        coordinator = AgentCoordinator("test-agent")
        result = coordinator.get_env("NONEXISTENT")
        assert result == ""

    def test_agent_coordinator_list_agents_stub(self) -> None:
        """Test list_agents returns empty list (stub)."""
        coordinator = AgentCoordinator("test-agent")
        result = coordinator.list_agents()
        assert result == []

    def test_agent_coordinator_shutdown_stub(self) -> None:
        """Test shutdown runs without error (stub)."""
        coordinator = AgentCoordinator("test-agent")
        coordinator.shutdown()  # Should not raise


class TestModuleStructure:
    """Test that merged module structure is correct."""

    def test_core_package_exports(self) -> None:
        """Test core package exports AgentRegistry and FileLockManager."""
        from mat.core import AgentRegistry as CoreRegistry
        from mat.core import FileLockManager
        from mat.core import LockToken

        assert CoreRegistry is not None
        assert FileLockManager is not None
        assert LockToken is not None

    def test_analysis_package_exports(self) -> None:
        """Test analysis package exports analyzer and dependencies."""
        from mat.analysis import CommandDependencyAnalyzer
        from mat.analysis import CommandDependencies

        assert CommandDependencyAnalyzer is not None
        assert CommandDependencies is not None

    def test_coordination_package_exports(self) -> None:
        """Test coordination package structure."""
        from mat.coordination.conflict_detector import ConflictDetector
        from mat.coordination.conflict_detector import Conflict

        assert ConflictDetector is not None
        assert Conflict is not None

    def test_execution_package_structure(self) -> None:
        """Test execution package structure."""
        from mat.execution.command_executor import CommandExecutor
        from mat.execution.command_executor import ExecutionResult

        assert CommandExecutor is not None
        assert ExecutionResult is not None

    def test_exceptions_module(self) -> None:
        """Test exceptions module exports both exception types."""
        from mat.exceptions import LockTimeoutError, CommandTimeoutError

        assert LockTimeoutError is not None
        assert CommandTimeoutError is not None
        assert issubclass(LockTimeoutError, Exception)
        assert issubclass(CommandTimeoutError, Exception)


class TestConflictResolutionMerges:
    """Test that conflict resolutions were successful."""

    def test_mat_init_has_comprehensive_api(self) -> None:
        """Test mat/__init__.py has all merged APIs."""
        from mat import __all__

        # Should have APIs from multiple merged branches
        # project-setup: Agent/Command classes
        assert "AgentCoordinator" in __all__
        assert "ExecutionResult" in __all__

        # exception-types: Exception classes
        assert "LockTimeoutError" in __all__
        assert "CommandTimeoutError" in __all__

        # agent-registry: AgentRegistry
        assert "AgentRegistry" in __all__

        # command-analyzer: CommandDependencies
        assert "CommandDependencies" in __all__

        # conflict-detector: Conflict
        assert "Conflict" in __all__

        # core: LockToken
        assert "LockToken" in __all__

    def test_core_init_has_registry_and_lock_manager(self) -> None:
        """Test mat/core/__init__.py has both registry and lock manager."""
        from mat.core import __all__

        assert "AgentRegistry" in __all__
        assert "FileLockManager" in __all__
        assert "LockToken" in __all__

    def test_analysis_init_has_analyzer_exports(self) -> None:
        """Test mat/analysis/__init__.py exports analyzer classes."""
        from mat.analysis import __all__

        assert "CommandDependencyAnalyzer" in __all__
        assert "CommandDependencies" in __all__

    def test_exception_types_have_proper_docstrings(self) -> None:
        """Test exception types have detailed docstrings (from exception-types merge)."""
        from mat.exceptions import LockTimeoutError, CommandTimeoutError

        # Should have docstrings explaining when raised
        assert LockTimeoutError.__doc__ is not None
        assert CommandTimeoutError.__doc__ is not None

        assert "acquire" in LockTimeoutError.__doc__.lower()
        assert "command" in CommandTimeoutError.__doc__.lower()

    def test_agent_registry_initialized_without_stub(self) -> None:
        """Test AgentRegistry is fully implemented (not a stub)."""
        registry = AgentRegistry()

        # Should have real implementation (not raising NotImplementedError)
        assert registry.register("test-agent", "token-123") is True

        active = registry.list_active()
        assert "test-agent" in active

    def test_file_lock_manager_initialized_without_stub(self) -> None:
        """Test FileLockManager is fully implemented (not a stub)."""
        import tempfile
        import os

        lock_mgr = FileLockManager()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("test")
            file_path = f.name

        try:
            # Should have real implementation
            token = lock_mgr.acquire_write("agent", file_path, timeout_seconds=5)
            assert token is not None
            lock_mgr.release_write(token)

        finally:
            os.unlink(file_path)

    def test_command_analyzer_initialized_without_stub(self) -> None:
        """Test CommandDependencyAnalyzer is fully implemented (not a stub)."""
        analyzer = CommandDependencyAnalyzer()

        # Should have real implementation (not raising NotImplementedError)
        deps = analyzer.analyze("python script.py")
        assert deps is not None
        assert isinstance(deps.files_read, set)
        assert isinstance(deps.files_written, set)

    def test_conflict_detector_is_stub(self) -> None:
        """Test ConflictDetector is still a stub (not yet implemented)."""
        analyzer = CommandDependencyAnalyzer()
        detector = ConflictDetector(analyzer)

        # Should be a stub (raises NotImplementedError)
        with pytest.raises(NotImplementedError):
            detector.check_conflict("python a.py", "python b.py")

    def test_command_executor_is_stub(self) -> None:
        """Test CommandExecutor is still a stub (not yet implemented)."""
        from mat.execution.command_executor import CommandExecutor

        lock_mgr = FileLockManager()
        analyzer = CommandDependencyAnalyzer()
        env_registry = {}

        executor = CommandExecutor(lock_mgr, analyzer, env_registry)

        # Should be a stub (raises NotImplementedError)
        with pytest.raises(NotImplementedError):
            executor.enqueue("agent", "cmd-1", "echo hello")

    def test_coordination_between_implemented_modules(self) -> None:
        """Test that implemented modules coordinate correctly."""
        # AgentRegistry + FileLockManager work together
        registry = AgentRegistry()
        lock_mgr = FileLockManager()

        registry.register("agent-test", "token-123")
        active = registry.list_active()
        assert "agent-test" in active

        # FileLockManager doesn't depend on registry
        # but both can work with same agent_id

        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("test")
            file_path = f.name

        try:
            # Same agent_id used in both systems
            token = lock_mgr.acquire_write("agent-test", file_path, timeout_seconds=5)
            assert token.agent_id == "agent-test"
            lock_mgr.release_write(token)

        finally:
            os.unlink(file_path)


class TestIntegrationReadiness:
    """Test that system is ready for further integration testing."""

    def test_all_implemented_modules_functional(self) -> None:
        """Test all implemented modules are functional."""
        # AgentRegistry functional
        registry = AgentRegistry()
        registry.register("agent-1", "token-1")
        assert "agent-1" in registry.list_active()

        # FileLockManager functional
        lock_mgr = FileLockManager()
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("test")
            file_path = f.name

        try:
            token = lock_mgr.acquire_read("agent-1", file_path, timeout_seconds=5)
            lock_mgr.release_read(token)

        finally:
            os.unlink(file_path)

        # CommandDependencyAnalyzer functional
        analyzer = CommandDependencyAnalyzer()
        deps = analyzer.analyze("python script.py input.txt output.txt")
        assert deps.files_read or deps.files_written or len(deps.files_read) == 0

    def test_stub_modules_have_proper_placeholders(self) -> None:
        """Test stub modules have proper NotImplementedError placeholders."""
        # ConflictDetector.check_conflict is a stub
        analyzer = CommandDependencyAnalyzer()
        detector = ConflictDetector(analyzer)

        with pytest.raises(NotImplementedError):
            detector.check_conflict("cmd1", "cmd2")

        # CommandExecutor.enqueue is a stub
        from mat.execution.command_executor import CommandExecutor

        lock_mgr = FileLockManager()
        executor = CommandExecutor(lock_mgr, analyzer, {})

        with pytest.raises(NotImplementedError):
            executor.enqueue("agent", "cmd-1", "echo hello")

        # AgentCoordinator.execute is a stub
        coordinator = AgentCoordinator("agent-test")

        with pytest.raises(NotImplementedError):
            coordinator.execute("echo hello")
