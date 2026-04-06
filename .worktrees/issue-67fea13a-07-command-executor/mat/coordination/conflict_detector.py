"""Conflict detection for multi-agent command coordination.

This module will be fully implemented in issue-06-conflict-detector.
For now, it provides stub types for the public API.
"""

from dataclasses import dataclass
from typing import Literal
from mat.analysis.command_analyzer import CommandDependencyAnalyzer


@dataclass
class Conflict:
    """Represents a conflict between two commands.

    Attributes:
        cmd1_id: Identifier for first command
        cmd2_id: Identifier for second command
        conflict_type: One of "write_write", "read_write", "delete_any", "env_conflict"
        description: Human-readable explanation of conflict
        safe_order: List[str] = [cmd_that_runs_first, cmd_that_runs_second]
    """

    cmd1_id: str
    cmd2_id: str
    conflict_type: Literal["write_write", "read_write", "delete_any", "env_conflict"]
    description: str
    safe_order: list[str]


class ConflictDetector:
    """Detects conflicts between two commands based on file dependencies.

    Placeholder implementation for issue-01-project-setup.
    Full implementation in issue-06-conflict-detector.
    """

    def __init__(self, command_analyzer: CommandDependencyAnalyzer) -> None:
        """Initialize conflict detector with command analyzer.

        Args:
            command_analyzer: Instance to extract command dependencies
        """
        self._analyzer = command_analyzer

    def check_conflict(
        self,
        cmd1: str,
        cmd2: str,
        cmd1_id: str = "cmd1",
        cmd2_id: str = "cmd2"
    ) -> Conflict | None:
        """Analyze two commands for conflicts.

        Args:
            cmd1: First command string
            cmd2: Second command string
            cmd1_id: Identifier for first command (default "cmd1")
            cmd2_id: Identifier for second command (default "cmd2")

        Returns:
            Conflict object if conflict detected, None if no conflict

        Raises:
            ValueError: If cmd1 or cmd2 is None or empty string
        """
        if not cmd1 or not cmd2:
            raise ValueError("Commands cannot be empty")
        raise NotImplementedError("Full implementation in issue-06")
