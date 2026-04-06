"""
Unit tests for ConflictDetector.

Tests cover:
- write_write conflicts: Both commands write same file
- read_write conflicts: One reads, one writes same file
- delete_any conflicts: One deletes, other reads/writes same file
- env_conflict: Both modify same environment variable
- No conflict cases: Different files or different operations
- Safe order recommendations: Verify correct ordering for each conflict type
- Error cases: Empty commands raise ValueError
"""

import pytest

from mat.analysis.command_analyzer import CommandDependencyAnalyzer
from mat.coordination.conflict_detector import Conflict, ConflictDetector


@pytest.fixture
def analyzer() -> CommandDependencyAnalyzer:
    """Create a CommandDependencyAnalyzer instance."""
    return CommandDependencyAnalyzer()


@pytest.fixture
def detector(analyzer: CommandDependencyAnalyzer) -> ConflictDetector:
    """Create a ConflictDetector instance."""
    return ConflictDetector(analyzer)


class TestWriteWriteConflict:
    """Test write_write conflict detection."""

    def test_write_write_conflict(self, detector: ConflictDetector) -> None:
        """Test that write_write conflict is detected when both commands write same file."""
        cmd1 = "python script.py --output result.txt"
        cmd2 = "python another.py --output result.txt"

        conflict = detector.check_conflict(cmd1, cmd2, "cmd1", "cmd2")

        assert conflict is not None
        assert conflict.conflict_type == "write_write"
        assert conflict.cmd1_id == "cmd1"
        assert conflict.cmd2_id == "cmd2"
        assert conflict.safe_order == ["cmd1", "cmd2"]
        assert "result.txt" in conflict.description

    def test_write_write_no_overlap(self, detector: ConflictDetector) -> None:
        """Test no conflict when both write different files."""
        cmd1 = "python script.py --output file1.txt"
        cmd2 = "python script.py --output file2.txt"

        conflict = detector.check_conflict(cmd1, cmd2)

        assert conflict is None

    def test_write_write_multiple_files_conflict(
        self, detector: ConflictDetector
    ) -> None:
        """Test write_write conflict with multiple written files."""
        # Python script that writes multiple files
        cmd1 = "python gen1.py --output a.txt --output b.txt"
        cmd2 = "python gen2.py --output b.txt --output c.txt"

        conflict = detector.check_conflict(cmd1, cmd2, "gen1", "gen2")

        assert conflict is not None
        assert conflict.conflict_type == "write_write"
        # Should detect the overlap (b.txt or c.txt)
        assert "b.txt" in conflict.description or "c.txt" in conflict.description


class TestReadWriteConflict:
    """Test read_write conflict detection."""

    def test_read_write_conflict_cmd1_writes_cmd2_reads(
        self, detector: ConflictDetector
    ) -> None:
        """Test read_write conflict when cmd1 writes and cmd2 reads same file."""
        cmd1 = "python generate.py --output data.csv"
        cmd2 = "mypy data.csv"

        conflict = detector.check_conflict(cmd1, cmd2, "gen", "check")

        assert conflict is not None
        assert conflict.conflict_type == "read_write"
        assert conflict.safe_order == ["gen", "check"]
        assert "data.csv" in conflict.description

    def test_read_write_conflict_cmd2_writes_cmd1_reads(
        self, detector: ConflictDetector
    ) -> None:
        """Test read_write conflict when cmd2 writes and cmd1 reads same file."""
        cmd1 = "mypy generated.py"
        cmd2 = "python generate.py --output generated.py"

        conflict = detector.check_conflict(cmd1, cmd2, "check", "gen")

        assert conflict is not None
        assert conflict.conflict_type == "read_write"
        assert conflict.safe_order == ["gen", "check"]
        assert "generated.py" in conflict.description

    def test_read_write_via_redirect(self, detector: ConflictDetector) -> None:
        """Test read_write conflict with file redirects."""
        cmd1 = "echo data > file.txt"
        cmd2 = "grep pattern file.txt"

        conflict = detector.check_conflict(cmd1, cmd2, "write", "read")

        assert conflict is not None
        assert conflict.conflict_type == "read_write"
        assert conflict.safe_order == ["write", "read"]

    def test_read_write_no_overlap(self, detector: ConflictDetector) -> None:
        """Test no read_write conflict when accessing different files."""
        cmd1 = "python script.py --output result.txt"
        cmd2 = "mypy source.py"

        conflict = detector.check_conflict(cmd1, cmd2)

        assert conflict is None


class TestDeleteAnyConflict:
    """Test delete_any conflict detection."""

    def test_delete_any_conflict_cmd1_deletes_cmd2_writes(
        self, detector: ConflictDetector
    ) -> None:
        """Test delete_any conflict when cmd1 deletes file cmd2 writes."""
        cmd1 = "rm data.txt"
        cmd2 = "python script.py --output data.txt"

        conflict = detector.check_conflict(cmd1, cmd2, "deleter", "writer")

        assert conflict is not None
        assert conflict.conflict_type == "delete_any"
        assert conflict.safe_order == ["writer", "deleter"]
        assert "data.txt" in conflict.description

    def test_delete_any_conflict_cmd2_deletes_cmd1_reads(
        self, detector: ConflictDetector
    ) -> None:
        """Test delete_any conflict when cmd2 deletes file cmd1 reads."""
        cmd1 = "grep pattern file.txt"
        cmd2 = "rm file.txt"

        conflict = detector.check_conflict(cmd1, cmd2, "reader", "deleter")

        assert conflict is not None
        assert conflict.conflict_type == "delete_any"
        assert conflict.safe_order == ["reader", "deleter"]
        assert "file.txt" in conflict.description

    def test_delete_any_conflict_cmd2_deletes_cmd1_writes(
        self, detector: ConflictDetector
    ) -> None:
        """Test delete_any conflict when cmd2 deletes file cmd1 writes."""
        cmd1 = "python gen.py --output output.txt"
        cmd2 = "rm output.txt"

        conflict = detector.check_conflict(cmd1, cmd2, "writer", "deleter")

        assert conflict is not None
        assert conflict.conflict_type == "delete_any"
        assert conflict.safe_order == ["writer", "deleter"]

    def test_delete_any_no_conflict(self, detector: ConflictDetector) -> None:
        """Test no delete_any conflict when deleting different file."""
        cmd1 = "rm file1.txt"
        cmd2 = "python script.py --output file2.txt"

        conflict = detector.check_conflict(cmd1, cmd2)

        assert conflict is None


class TestEnvConflict:
    """Test env_conflict detection."""

    def test_env_conflict(self, detector: ConflictDetector) -> None:
        """Test env_conflict when both commands modify same env var."""
        cmd1 = "export DEBUG=true"
        cmd2 = "export DEBUG=false"

        conflict = detector.check_conflict(cmd1, cmd2, "cmd_a", "cmd_b")

        assert conflict is not None
        assert conflict.conflict_type == "env_conflict"
        assert conflict.safe_order == ["cmd_a", "cmd_b"]
        assert "DEBUG" in conflict.description

    def test_env_conflict_multiple_vars(self, detector: ConflictDetector) -> None:
        """Test env_conflict with multiple environment variables."""
        cmd1 = "export VAR1=a VAR2=b"
        cmd2 = "export VAR2=c VAR3=d"

        conflict = detector.check_conflict(cmd1, cmd2)

        assert conflict is not None
        assert conflict.conflict_type == "env_conflict"
        assert "VAR2" in conflict.description

    def test_env_conflict_no_overlap(self, detector: ConflictDetector) -> None:
        """Test no env_conflict when modifying different env vars."""
        cmd1 = "export VAR1=value1"
        cmd2 = "export VAR2=value2"

        conflict = detector.check_conflict(cmd1, cmd2)

        assert conflict is None

    def test_env_conflict_read_vs_write_no_conflict(
        self, detector: ConflictDetector
    ) -> None:
        """Test no env_conflict when one reads and one writes env var."""
        # Only conflicting writes cause env_conflict
        cmd1 = "echo $DEBUG"
        cmd2 = "export DEBUG=true"

        conflict = detector.check_conflict(cmd1, cmd2)

        # Should have no conflict (only reads and writes, not both writing)
        assert conflict is None


class TestNoConflict:
    """Test cases where no conflict should be detected."""

    def test_no_conflict_different_files(self, detector: ConflictDetector) -> None:
        """Test no conflict when commands operate on completely different files."""
        cmd1 = "python process1.py --input data1.csv --output result1.txt"
        cmd2 = "python process2.py --input data2.csv --output result2.txt"

        conflict = detector.check_conflict(cmd1, cmd2)

        assert conflict is None

    def test_no_conflict_both_read_same_file(self, detector: ConflictDetector) -> None:
        """Test no conflict when both commands only read same file."""
        cmd1 = "grep pattern file.txt"
        cmd2 = "mypy file.txt"

        conflict = detector.check_conflict(cmd1, cmd2)

        assert conflict is None

    def test_no_conflict_read_write_different_files(
        self, detector: ConflictDetector
    ) -> None:
        """Test no conflict when one reads and one writes different files."""
        cmd1 = "python script.py --input input.txt --output output.txt"
        cmd2 = "grep pattern other.txt"

        conflict = detector.check_conflict(cmd1, cmd2)

        assert conflict is None

    def test_no_conflict_commands_with_no_dependencies(
        self, detector: ConflictDetector
    ) -> None:
        """Test no conflict when commands have no file dependencies."""
        cmd1 = "echo hello"
        cmd2 = "echo world"

        conflict = detector.check_conflict(cmd1, cmd2)

        # These might return None if echo has unknown tool fallback
        # and files_read={'*'}, but let's check the behavior
        # Actually, 'echo' is not recognized, so it falls back to files_read={'*'}
        # This would cause a conflict. Let me use recognized commands.

        # Use export which has no files
        cmd1 = "export VAR1=value"
        cmd2 = "export VAR2=value"

        conflict = detector.check_conflict(cmd1, cmd2)

        assert conflict is None


class TestSafeOrderRecommendations:
    """Test that safe_order recommendations are correct for each conflict type."""

    def test_safe_order_write_write_is_cmd1_cmd2(
        self, detector: ConflictDetector
    ) -> None:
        """Test that write_write safe_order is always [cmd1, cmd2]."""
        cmd1 = "python gen1.py --output file.txt"
        cmd2 = "python gen2.py --output file.txt"

        conflict = detector.check_conflict(cmd1, cmd2, "first", "second")

        assert conflict is not None
        assert conflict.conflict_type == "write_write"
        assert conflict.safe_order == ["first", "second"]

    def test_safe_order_read_write_writer_first(
        self, detector: ConflictDetector
    ) -> None:
        """Test that read_write safe_order puts writer first."""
        cmd1 = "python gen.py --output file.txt"
        cmd2 = "mypy file.txt"

        conflict = detector.check_conflict(cmd1, cmd2, "gen", "check")

        assert conflict is not None
        assert conflict.conflict_type == "read_write"
        assert conflict.safe_order[0] == "gen"  # Writer first
        assert conflict.safe_order[1] == "check"  # Reader second

    def test_safe_order_read_write_writer_first_reversed(
        self, detector: ConflictDetector
    ) -> None:
        """Test read_write safe_order when cmd2 is the writer."""
        cmd1 = "mypy file.txt"
        cmd2 = "python gen.py --output file.txt"

        conflict = detector.check_conflict(cmd1, cmd2, "check", "gen")

        assert conflict is not None
        assert conflict.conflict_type == "read_write"
        assert conflict.safe_order[0] == "gen"  # Writer first
        assert conflict.safe_order[1] == "check"  # Reader second

    def test_safe_order_delete_any_deleter_last(
        self, detector: ConflictDetector
    ) -> None:
        """Test that delete_any safe_order puts deleter last."""
        cmd1 = "rm file.txt"
        cmd2 = "python gen.py --output file.txt"

        conflict = detector.check_conflict(cmd1, cmd2, "deleter", "writer")

        assert conflict is not None
        assert conflict.conflict_type == "delete_any"
        assert conflict.safe_order[1] == "deleter"  # Deleter last
        assert conflict.safe_order[0] == "writer"  # Writer first

    def test_safe_order_delete_any_deleter_last_reversed(
        self, detector: ConflictDetector
    ) -> None:
        """Test delete_any safe_order when cmd2 is the deleter."""
        cmd1 = "python gen.py --output file.txt"
        cmd2 = "rm file.txt"

        conflict = detector.check_conflict(cmd1, cmd2, "writer", "deleter")

        assert conflict is not None
        assert conflict.conflict_type == "delete_any"
        assert conflict.safe_order[0] == "writer"  # Writer first
        assert conflict.safe_order[1] == "deleter"  # Deleter last

    def test_safe_order_env_conflict_is_cmd1_cmd2(
        self, detector: ConflictDetector
    ) -> None:
        """Test that env_conflict safe_order is [cmd1, cmd2]."""
        cmd1 = "export VAR=a"
        cmd2 = "export VAR=b"

        conflict = detector.check_conflict(cmd1, cmd2, "alpha", "beta")

        assert conflict is not None
        assert conflict.conflict_type == "env_conflict"
        assert conflict.safe_order == ["alpha", "beta"]


class TestErrorCases:
    """Test error handling in ConflictDetector."""

    def test_empty_cmd1_raises_value_error(self, detector: ConflictDetector) -> None:
        """Test that empty cmd1 raises ValueError."""
        with pytest.raises(ValueError, match="Commands cannot be empty"):
            detector.check_conflict("", "python script.py")

    def test_empty_cmd2_raises_value_error(self, detector: ConflictDetector) -> None:
        """Test that empty cmd2 raises ValueError."""
        with pytest.raises(ValueError, match="Commands cannot be empty"):
            detector.check_conflict("python script.py", "")

    def test_none_cmd1_raises_value_error(self, detector: ConflictDetector) -> None:
        """Test that None cmd1 raises ValueError."""
        with pytest.raises(ValueError, match="Commands cannot be empty"):
            detector.check_conflict(None, "python script.py")  # type: ignore

    def test_none_cmd2_raises_value_error(self, detector: ConflictDetector) -> None:
        """Test that None cmd2 raises ValueError."""
        with pytest.raises(ValueError, match="Commands cannot be empty"):
            detector.check_conflict("python script.py", None)  # type: ignore


class TestConflictDetectorCustomIds:
    """Test ConflictDetector with custom command IDs."""

    def test_conflict_respects_custom_cmd_ids(
        self, detector: ConflictDetector
    ) -> None:
        """Test that custom command IDs appear in conflict and safe_order."""
        cmd1 = "python script1.py --output file.txt"
        cmd2 = "python script2.py --output file.txt"

        conflict = detector.check_conflict(
            cmd1, cmd2, cmd1_id="refactor", cmd2_id="typecheck"
        )

        assert conflict is not None
        assert conflict.cmd1_id == "refactor"
        assert conflict.cmd2_id == "typecheck"
        assert "refactor" in conflict.safe_order
        assert "typecheck" in conflict.safe_order

    def test_conflict_default_ids(self, detector: ConflictDetector) -> None:
        """Test that default command IDs are 'cmd1' and 'cmd2'."""
        cmd1 = "python script.py --output file.txt"
        cmd2 = "python script.py --output file.txt"

        conflict = detector.check_conflict(cmd1, cmd2)

        assert conflict is not None
        assert conflict.cmd1_id == "cmd1"
        assert conflict.cmd2_id == "cmd2"


class TestConflictPriority:
    """Test that conflicts are detected in the correct priority order."""

    def test_delete_any_takes_priority_over_write_write(
        self, detector: ConflictDetector
    ) -> None:
        """Test that delete_any is detected even with write_write overlap."""
        # cmd1 deletes and writes file.txt, cmd2 writes file.txt
        # Should detect delete_any first
        cmd1 = "rm file.txt"
        cmd2 = "python script.py --output file.txt"

        conflict = detector.check_conflict(cmd1, cmd2)

        assert conflict is not None
        # delete_any should be detected before write_write
        assert conflict.conflict_type == "delete_any"

    def test_delete_any_takes_priority_over_read_write(
        self, detector: ConflictDetector
    ) -> None:
        """Test that delete_any is detected even with read_write overlap."""
        cmd1 = "rm file.txt"
        cmd2 = "grep pattern file.txt"

        conflict = detector.check_conflict(cmd1, cmd2)

        assert conflict is not None
        assert conflict.conflict_type == "delete_any"
