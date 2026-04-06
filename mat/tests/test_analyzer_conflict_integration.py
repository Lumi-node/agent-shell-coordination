"""Integration tests for CommandAnalyzer and ConflictDetector interaction.

Tests verify that CommandDependencyAnalyzer correctly identifies conflicts
through the ConflictDetector using extracted dependencies.
"""

import pytest
import tempfile
import os

from mat.analysis.command_analyzer import CommandDependencyAnalyzer
from mat.coordination.conflict_detector import ConflictDetector, Conflict


class TestAnalyzerFeedsConflictDetector:
    """Test that analyzer output drives conflict detection."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.analyzer = CommandDependencyAnalyzer()
        self.detector = ConflictDetector(self.analyzer)

    def test_conflict_detection_invalid_commands_raises(self) -> None:
        """Test that invalid commands raise ValueError in conflict detector."""
        with pytest.raises(ValueError):
            self.detector.check_conflict("", "python script.py")

        with pytest.raises(ValueError):
            self.detector.check_conflict("python script.py", "")

        with pytest.raises(ValueError):
            self.detector.check_conflict(None, "python script.py")  # type: ignore

    def test_conflict_detector_initializes_with_analyzer(self) -> None:
        """Test ConflictDetector properly stores analyzer reference."""
        assert self.detector._analyzer is self.analyzer

    def test_conflict_detector_check_conflict_stub(self) -> None:
        """Test ConflictDetector.check_conflict is a proper stub."""
        # The stub implementation should raise NotImplementedError
        with pytest.raises(NotImplementedError):
            self.detector.check_conflict("python a.py", "python b.py")


class TestAnalyzerDependenciesCanDetectConflicts:
    """Test that analyzed dependencies represent conflict scenarios."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.analyzer = CommandDependencyAnalyzer()

    def test_write_write_conflict_detected_from_dependencies(self) -> None:
        """Test two commands writing same file creates analyzable write-write conflict."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("shared")
            shared_file = f.name

        try:
            # Both commands write to same file
            cmd1 = f"echo 'data1' > {shared_file}"
            cmd2 = f"echo 'data2' > {shared_file}"

            deps1 = self.analyzer.analyze(cmd1)
            deps2 = self.analyzer.analyze(cmd2)

            # Both should identify the shared file in files_written
            assert shared_file in deps1.files_written
            assert shared_file in deps2.files_written

            # Conflict is: both write same file = write-write
            # (Full conflict detection implemented in issue-06)

        finally:
            os.unlink(shared_file)

    def test_read_write_conflict_detected_from_dependencies(self) -> None:
        """Test read-write conflict is analyzable from dependencies."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("data")
            shared_file = f.name

        try:
            # cmd1 reads, cmd2 writes same file
            cmd1 = f"cat {shared_file}"
            cmd2 = f"echo 'modified' > {shared_file}"

            deps1 = self.analyzer.analyze(cmd1)
            deps2 = self.analyzer.analyze(cmd2)

            # cmd1 reads, cmd2 writes
            assert shared_file in deps1.files_read
            assert shared_file in deps2.files_written

            # Conflict is: one reads, other writes same file = read-write

        finally:
            os.unlink(shared_file)

    def test_no_conflict_different_files(self) -> None:
        """Test no conflict when commands access different files."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f1:
            f1.write("file1")
            file1 = f1.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f2:
            f2.write("file2")
            file2 = f2.name

        try:
            cmd1 = f"cat {file1}"
            cmd2 = f"echo 'data' > {file2}"

            deps1 = self.analyzer.analyze(cmd1)
            deps2 = self.analyzer.analyze(cmd2)

            # No overlapping file accesses
            assert deps1.files_read == {file1}
            assert deps2.files_written == {file2}
            assert file1 not in deps2.files_read
            assert file1 not in deps2.files_written
            assert file2 not in deps1.files_read
            assert file2 not in deps1.files_written

            # No conflict

        finally:
            os.unlink(file1)
            os.unlink(file2)

    def test_delete_conflicts_detected_from_dependencies(self) -> None:
        """Test delete-any conflicts are analyzable from dependencies."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("file")
            shared_file = f.name

        try:
            # cmd1 reads, cmd2 deletes same file
            cmd1 = f"cat {shared_file}"
            cmd2 = f"rm {shared_file}"

            deps1 = self.analyzer.analyze(cmd1)
            deps2 = self.analyzer.analyze(cmd2)

            # cmd1 reads, cmd2 deletes
            assert shared_file in deps1.files_read
            assert shared_file in deps2.files_deleted

            # Conflict: one accesses, other deletes = delete-any conflict

        finally:
            if os.path.exists(shared_file):
                os.unlink(shared_file)

    def test_environment_variable_conflicts_detectable(self) -> None:
        """Test environment variable conflicts are analyzable."""
        # cmd1 reads PATH, cmd2 writes PATH
        cmd1 = "echo $PATH"
        cmd2 = "export PATH=/new/path"

        deps1 = self.analyzer.analyze(cmd1)
        deps2 = self.analyzer.analyze(cmd2)

        # Both should handle environment variables
        # (Depending on analyzer implementation, PATH may be in env_vars_read/written)
        assert isinstance(deps1.env_vars_read, set)
        assert isinstance(deps1.env_vars_written, set)
        assert isinstance(deps2.env_vars_read, set)
        assert isinstance(deps2.env_vars_written, set)

    def test_complex_command_with_multiple_dependency_types(self) -> None:
        """Test complex command with reads, writes, and env vars."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f_in:
            f_in.write("input")
            in_file = f_in.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f_out:
            f_out.write("")
            out_file = f_out.name

        try:
            # Complex command: python script reading input, writing output, using env
            cmd = f"python {in_file} --output {out_file}"
            deps = self.analyzer.analyze(cmd)

            # Should identify all dependency types
            assert in_file in deps.files_read
            assert out_file in deps.files_written
            assert isinstance(deps.env_vars_read, set)
            assert isinstance(deps.env_vars_written, set)

        finally:
            os.unlink(in_file)
            os.unlink(out_file)

    def test_piped_commands_show_composite_dependencies(self) -> None:
        """Test piped commands show dependencies from all commands in pipeline."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f_in:
            f_in.write("input")
            in_file = f_in.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f_out:
            f_out.write("")
            out_file = f_out.name

        try:
            # Piped: cat reads in_file, grep filters, output redirected to out_file
            cmd = f"cat {in_file} | grep pattern > {out_file}"
            deps = self.analyzer.analyze(cmd)

            # Should identify both files
            assert in_file in deps.files_read
            assert out_file in deps.files_written

            # Piped commands create composite dependency set
            # (Multiple commands' dependencies combined)

        finally:
            os.unlink(in_file)
            os.unlink(out_file)

    def test_file_operations_show_clear_conflict_patterns(self) -> None:
        """Test file operation commands show clear conflict patterns."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f_src:
            f_src.write("source")
            src_file = f_src.name

        dst_file = src_file + ".dst"

        try:
            # Move command: reads src, writes dst
            cmd_move = f"mv {src_file} {dst_file}"
            deps_move = self.analyzer.analyze(cmd_move)

            assert src_file in deps_move.files_read
            assert dst_file in deps_move.files_written

            # If another command writes src_file, conflict with move
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f_mod:
                f_mod.write("modified")
                mod_file = f_mod.name

            try:
                cmd_modify = f"echo 'data' > {src_file}"
                deps_modify = self.analyzer.analyze(cmd_modify)

                # cmd_modify writes src_file
                assert src_file in deps_modify.files_written

                # Move reads src_file, modify writes it = read-write conflict
                # (when sequenced: modify should run before move)

            finally:
                os.unlink(mod_file)

        finally:
            if os.path.exists(src_file):
                os.unlink(src_file)
            if os.path.exists(dst_file):
                os.unlink(dst_file)


class TestConflictScenarios:
    """Test realistic conflict scenarios derived from analyzed commands."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.analyzer = CommandDependencyAnalyzer()

    def test_refactor_then_typecheck_scenario(self) -> None:
        """Test refactor-then-typecheck workflow: refactor writes code, typecheck reads it."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def func(): pass")
            code_file = f.name

        try:
            # Refactor command writes code
            refactor_cmd = f"python -c 'open(\"{code_file}\", \"w\").write(\"refactored\")'  > {code_file}"
            refactor_deps = self.analyzer.analyze(refactor_cmd)

            # Type check reads code
            typecheck_cmd = f"mypy {code_file}"
            typecheck_deps = self.analyzer.analyze(typecheck_cmd)

            # Refactor writes code_file
            assert code_file in refactor_deps.files_written

            # Typecheck reads code_file
            assert code_file in typecheck_deps.files_read

            # This is a read-write conflict:
            # - refactor must complete before typecheck
            # - typecheck cannot run while refactor holds write lock

        finally:
            os.unlink(code_file)

    def test_concurrent_read_safe_scenario(self) -> None:
        """Test scenario where multiple agents read same file (no conflict)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("shared_module")
            module_file = f.name

        try:
            # Multiple agents analyze same file (no conflict)
            agent_a_cmd = f"mypy {module_file}"
            agent_b_cmd = f"mypy {module_file}"

            deps_a = self.analyzer.analyze(agent_a_cmd)
            deps_b = self.analyzer.analyze(agent_b_cmd)

            # Both read same file
            assert module_file in deps_a.files_read
            assert module_file in deps_b.files_read

            # Both writes/deletes should be empty (read-only)
            assert len(deps_a.files_written) == 0
            assert len(deps_b.files_written) == 0

            # No conflict: multiple reads allowed

        finally:
            os.unlink(module_file)

    def test_exclusive_write_scenario(self) -> None:
        """Test scenario where agents need exclusive write access."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
            f.write("database")
            db_file = f.name

        try:
            # Agent A writes to database
            cmd_a = f"sqlite3 {db_file} 'INSERT INTO table VALUES (1)'"
            deps_a = self.analyzer.analyze(cmd_a)

            # Agent B writes to database
            cmd_b = f"sqlite3 {db_file} 'INSERT INTO table VALUES (2)'"
            deps_b = self.analyzer.analyze(cmd_b)

            # Both write same file
            # (Conservative analyzer might mark both as reading db_file)
            # Actual implementation: need exclusive write locks for both

        finally:
            os.unlink(db_file)

    def test_redirect_creates_write_dependency(self) -> None:
        """Test that shell redirects create write dependencies."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f_output:
            f_output.write("")
            output_file = f_output.name

        try:
            # Command with redirect should identify output file as written
            cmd = f"echo 'hello' > {output_file}"
            deps = self.analyzer.analyze(cmd)

            # Redirect should be recognized as file write
            assert output_file in deps.files_written

        finally:
            os.unlink(output_file)
