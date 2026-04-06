"""Conflict detection for multi-agent command coordination.

This module provides ConflictDetector that analyzes two commands for conflicts
based on their file dependencies and environment variable modifications.

Conflict types:
- write_write: Both commands write to the same file
- read_write: One command reads while another writes the same file
- delete_any: One command deletes a file another reads or writes
- env_conflict: Both commands modify the same environment variable
"""

from dataclasses import dataclass
from typing import Literal

from mat.analysis.command_analyzer import CommandDependencyAnalyzer, CommandDependencies


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

    Conflict types:
    1. write_write: Both commands write to same file
       - Safe order: Either can run first (same result)
       - Recommendation: cmd1 first (arbitrary, but deterministic)

    2. read_write: One command reads while other writes same file
       - Safe order: writer must run first, then reader
       - (If cmd1 writes and cmd2 reads, order is [cmd1, cmd2])

    3. delete_any: One command deletes file another reads/writes
       - Safe order: writer/reader must run first, then deleter
       - (Deleter always runs last)

    4. env_conflict: Both commands modify same environment variable
       - Safe order: Arbitrary (but deterministic in output)

    No conflict: Return None
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
            cmd1_id: Identifier for first command (default "cmd1", used in Conflict.safe_order)
            cmd2_id: Identifier for second command (default "cmd2", used in Conflict.safe_order)

        Returns:
            Conflict object if conflict detected, None if no conflict

        Raises:
            ValueError: If cmd1 or cmd2 is None or empty string

        Algorithm:
        1. Analyze both commands using CommandDependencyAnalyzer
        2. Check for overlaps:
           a. Both write same file → write_write conflict
           b. One reads, one writes same file → read_write conflict
           c. One deletes, other reads/writes same file → delete_any conflict
           d. Both modify same env var → env_conflict conflict
        3. If no overlap → return None
        4. If conflict found → determine safe_order and return Conflict

        Safe Order Logic:
        - write_write: [cmd1, cmd2] (arbitrary, both valid)
        - read_write: [writer, reader]
        - delete_any: [reader/writer, deleter]
        - env_conflict: [cmd1, cmd2] (arbitrary)
        """
        if not cmd1 or not cmd2:
            raise ValueError("Commands cannot be empty")

        # Analyze both commands
        deps1 = self._analyzer.analyze(cmd1)
        deps2 = self._analyzer.analyze(cmd2)

        # Check for delete_any conflict (must be checked before read_write)
        delete_conflict = self._check_delete_any_conflict(
            deps1, deps2, cmd1_id, cmd2_id
        )
        if delete_conflict is not None:
            return delete_conflict

        # Check for write_write conflict
        write_write_conflict = self._check_write_write_conflict(
            deps1, deps2, cmd1_id, cmd2_id
        )
        if write_write_conflict is not None:
            return write_write_conflict

        # Check for read_write conflict
        read_write_conflict = self._check_read_write_conflict(
            deps1, deps2, cmd1_id, cmd2_id
        )
        if read_write_conflict is not None:
            return read_write_conflict

        # Check for env_conflict
        env_conflict = self._check_env_conflict(deps1, deps2, cmd1_id, cmd2_id)
        if env_conflict is not None:
            return env_conflict

        return None

    def _check_write_write_conflict(
        self,
        deps1: CommandDependencies,
        deps2: CommandDependencies,
        cmd1_id: str,
        cmd2_id: str
    ) -> Conflict | None:
        """Check if both commands write to the same file."""
        # Find files both commands write
        overlapping_files = deps1.files_written & deps2.files_written

        if overlapping_files:
            # Pick first overlapping file (sorted for determinism)
            conflict_file = sorted(overlapping_files)[0]
            description = f"Both commands write to {conflict_file}"
            return Conflict(
                cmd1_id=cmd1_id,
                cmd2_id=cmd2_id,
                conflict_type="write_write",
                description=description,
                safe_order=[cmd1_id, cmd2_id]
            )

        return None

    def _check_read_write_conflict(
        self,
        deps1: CommandDependencies,
        deps2: CommandDependencies,
        cmd1_id: str,
        cmd2_id: str
    ) -> Conflict | None:
        """Check if one reads while other writes the same file."""
        # Check if cmd1 writes and cmd2 reads same file
        overlapping_1w_2r = deps1.files_written & deps2.files_read
        if overlapping_1w_2r:
            conflict_file = sorted(overlapping_1w_2r)[0]
            description = (
                f"{cmd1_id} writes {conflict_file}, {cmd2_id} reads it: "
                f"{cmd1_id} must run first"
            )
            return Conflict(
                cmd1_id=cmd1_id,
                cmd2_id=cmd2_id,
                conflict_type="read_write",
                description=description,
                safe_order=[cmd1_id, cmd2_id]
            )

        # Check if cmd2 writes and cmd1 reads same file
        overlapping_2w_1r = deps2.files_written & deps1.files_read
        if overlapping_2w_1r:
            conflict_file = sorted(overlapping_2w_1r)[0]
            description = (
                f"{cmd2_id} writes {conflict_file}, {cmd1_id} reads it: "
                f"{cmd2_id} must run first"
            )
            return Conflict(
                cmd1_id=cmd1_id,
                cmd2_id=cmd2_id,
                conflict_type="read_write",
                description=description,
                safe_order=[cmd2_id, cmd1_id]
            )

        return None

    def _check_delete_any_conflict(
        self,
        deps1: CommandDependencies,
        deps2: CommandDependencies,
        cmd1_id: str,
        cmd2_id: str
    ) -> Conflict | None:
        """Check if one deletes file another reads or writes."""
        # Check if cmd1 deletes and cmd2 reads/writes same file
        files_cmd2_accesses = deps2.files_read | deps2.files_written
        overlapping_1d_2a = deps1.files_deleted & files_cmd2_accesses
        if overlapping_1d_2a:
            conflict_file = sorted(overlapping_1d_2a)[0]
            description = (
                f"{cmd1_id} deletes {conflict_file}, {cmd2_id} accesses it: "
                f"{cmd2_id} must run first"
            )
            return Conflict(
                cmd1_id=cmd1_id,
                cmd2_id=cmd2_id,
                conflict_type="delete_any",
                description=description,
                safe_order=[cmd2_id, cmd1_id]
            )

        # Check if cmd2 deletes and cmd1 reads/writes same file
        files_cmd1_accesses = deps1.files_read | deps1.files_written
        overlapping_2d_1a = deps2.files_deleted & files_cmd1_accesses
        if overlapping_2d_1a:
            conflict_file = sorted(overlapping_2d_1a)[0]
            description = (
                f"{cmd2_id} deletes {conflict_file}, {cmd1_id} accesses it: "
                f"{cmd1_id} must run first"
            )
            return Conflict(
                cmd1_id=cmd1_id,
                cmd2_id=cmd2_id,
                conflict_type="delete_any",
                description=description,
                safe_order=[cmd1_id, cmd2_id]
            )

        return None

    def _check_env_conflict(
        self,
        deps1: CommandDependencies,
        deps2: CommandDependencies,
        cmd1_id: str,
        cmd2_id: str
    ) -> Conflict | None:
        """Check if both commands modify the same environment variable."""
        overlapping_env_vars = deps1.env_vars_written & deps2.env_vars_written

        if overlapping_env_vars:
            # Pick first overlapping env var (sorted for determinism)
            conflict_var = sorted(overlapping_env_vars)[0]
            description = f"Both commands modify environment variable {conflict_var}"
            return Conflict(
                cmd1_id=cmd1_id,
                cmd2_id=cmd2_id,
                conflict_type="env_conflict",
                description=description,
                safe_order=[cmd1_id, cmd2_id]
            )

        return None
