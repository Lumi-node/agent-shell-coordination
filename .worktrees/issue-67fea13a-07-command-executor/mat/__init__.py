"""Multi-Agent Terminal Coordination System.

A distributed system enabling autonomous AI agents to collaboratively execute
shell commands on shared computational environments while maintaining
consistency guarantees.

Public API:
    - AgentCoordinator: High-level API for agents
    - ExecutionResult: Result of command execution
    - LockTimeoutError: Raised when lock acquisition times out
    - CommandTimeoutError: Raised when command execution times out
    - LockToken: Opaque token representing a held lock
    - CommandDependencies: Extracted dependencies from a shell command
    - Conflict: Represents a conflict between two commands
    - AgentRegistry: Live agent membership tracking
"""

from mat.coordinator import AgentCoordinator
from mat.execution.command_executor import ExecutionResult
from mat.exceptions import LockTimeoutError, CommandTimeoutError
from mat.core.file_lock_manager import LockToken
from mat.core.agent_registry import AgentRegistry
from mat.analysis.command_analyzer import CommandDependencies
from mat.coordination.conflict_detector import Conflict

__all__ = [
    "AgentCoordinator",
    "ExecutionResult",
    "LockTimeoutError",
    "CommandTimeoutError",
    "LockToken",
    "AgentRegistry",
    "CommandDependencies",
    "Conflict",
]

__version__ = "0.1.0"
