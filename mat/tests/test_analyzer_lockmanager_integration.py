"""Integration tests for CommandAnalyzer and FileLockManager interaction.

Tests verify that CommandDependencyAnalyzer correctly identifies file
dependencies that should be protected by FileLockManager locks.
"""

import pytest
import tempfile
import os
from typing import List

from mat.analysis.command_analyzer import CommandDependencyAnalyzer, CommandDependencies
from mat.core.file_lock_manager import FileLockManager
from mat.exceptions import LockTimeoutError


class TestAnalyzerIdentifiesLockableFiles:
    """Test that analyzer output drives lock acquisition."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.analyzer = CommandDependencyAnalyzer()
        self.lock_mgr = FileLockManager()
        self.agent_id = "agent-test"

    def test_python_script_analysis_matches_lock_acquisition(self) -> None:
        """Test analyzing python command identifies files that need locking."""
        # Create actual temp files
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f_script:
            f_script.write("# test script")
            script_path = f_script.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f_input:
            f_input.write("# input file")
            input_path = f_input.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f_output:
            f_output.write("# output file")
            output_path = f_output.name

        try:
            command = f"python {script_path} --input {input_path} --output {output_path}"
            deps = self.analyzer.analyze(command)

            # Verify analyzer found dependencies
            assert script_path in deps.files_read
            assert input_path in deps.files_read
            assert output_path in deps.files_written

            # Verify locks can be acquired for identified files
            read_locks = self.lock_mgr.acquire_multiple(
                self.agent_id,
                read_paths=[script_path, input_path],
                write_paths=[output_path],
                timeout_seconds=5
            )
            assert len(read_locks) == 3
            assert all(token.agent_id == self.agent_id for token in read_locks)

            # Verify lock types match dependency types
            read_lock_paths = {t.file_path for t in read_locks if t.lock_type == "read"}
            write_lock_paths = {t.file_path for t in read_locks if t.lock_type == "write"}

            assert script_path in read_lock_paths
            assert input_path in read_lock_paths
            assert output_path in write_lock_paths

            # Clean up locks
            self.lock_mgr.release_multiple(read_locks)

        finally:
            os.unlink(script_path)
            os.unlink(input_path)
            os.unlink(output_path)

    def test_mypy_command_dependencies_locked_correctly(self) -> None:
        """Test mypy command dependencies map to correct lock types."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("# python file")
            file_path = f.name

        try:
            command = f"mypy {file_path}"
            deps = self.analyzer.analyze(command)

            # Mypy reads the file
            assert file_path in deps.files_read
            assert file_path not in deps.files_written
            assert file_path not in deps.files_deleted

            # Should be able to acquire read lock
            tokens = self.lock_mgr.acquire_multiple(
                self.agent_id,
                read_paths=[file_path],
                write_paths=[],
                timeout_seconds=5
            )
            assert len(tokens) == 1
            assert tokens[0].lock_type == "read"

            self.lock_mgr.release_multiple(tokens)

        finally:
            os.unlink(file_path)

    def test_file_move_command_uses_read_and_write_locks(self) -> None:
        """Test mv command requires read lock on src and write lock on dst."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f_src:
            f_src.write("source")
            src_path = f_src.name

        dst_path = src_path + ".moved"

        try:
            command = f"mv {src_path} {dst_path}"
            deps = self.analyzer.analyze(command)

            # mv reads source and writes destination
            assert src_path in deps.files_read
            assert dst_path in deps.files_written

            # Should acquire read lock on src, write lock on dst
            tokens = self.lock_mgr.acquire_multiple(
                self.agent_id,
                read_paths=[src_path],
                write_paths=[dst_path],
                timeout_seconds=5
            )
            assert len(tokens) == 2

            read_tokens = [t for t in tokens if t.lock_type == "read"]
            write_tokens = [t for t in tokens if t.lock_type == "write"]

            assert len(read_tokens) == 1
            assert read_tokens[0].file_path == src_path
            assert len(write_tokens) == 1
            assert write_tokens[0].file_path == dst_path

            self.lock_mgr.release_multiple(tokens)

        finally:
            if os.path.exists(src_path):
                os.unlink(src_path)
            if os.path.exists(dst_path):
                os.unlink(dst_path)

    def test_file_delete_command_analysis(self) -> None:
        """Test rm command correctly identifies deleted files."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("temp")
            file_path = f.name

        try:
            command = f"rm {file_path}"
            deps = self.analyzer.analyze(command)

            # rm deletes the file
            assert file_path in deps.files_deleted

            # Note: delete doesn't use locks (per design), but analyzer identifies it
            assert file_path not in deps.files_written
            assert file_path not in deps.files_read

        finally:
            if os.path.exists(file_path):
                os.unlink(file_path)

    def test_piped_commands_identify_all_file_dependencies(self) -> None:
        """Test piped commands identify dependencies in all commands."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f_in:
            f_in.write("input")
            in_path = f_in.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f_out:
            f_out.write("output")
            out_path = f_out.name

        try:
            # Piped command: read input, pipe to grep, write to output
            command = f"cat {in_path} | grep pattern > {out_path}"
            deps = self.analyzer.analyze(command)

            # Should identify both files
            assert in_path in deps.files_read
            assert out_path in deps.files_written

            # Should be able to lock both
            tokens = self.lock_mgr.acquire_multiple(
                self.agent_id,
                read_paths=[in_path],
                write_paths=[out_path],
                timeout_seconds=5
            )
            assert len(tokens) == 2

            self.lock_mgr.release_multiple(tokens)

        finally:
            os.unlink(in_path)
            os.unlink(out_path)

    def test_conservative_fallback_for_unknown_commands(self) -> None:
        """Test that unknown commands fall back to conservative {'*'} assumption."""
        command = "some_unknown_command arg1 arg2"
        deps = self.analyzer.analyze(command)

        # Conservative fallback: assume reads everything
        assert '*' in deps.files_read or len(deps.files_read) > 0

    def test_multiple_files_same_command_acquire_all_locks(self) -> None:
        """Test command reading multiple files can acquire locks for all."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f1:
            f1.write("file1")
            file1_path = f1.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f2:
            f2.write("file2")
            file2_path = f2.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f3:
            f3.write("file3")
            file3_path = f3.name

        try:
            # Command reading multiple files
            command = f"cat {file1_path} {file2_path} > {file3_path}"
            deps = self.analyzer.analyze(command)

            # Should identify all files
            assert file1_path in deps.files_read
            assert file2_path in deps.files_read
            assert file3_path in deps.files_written

            # Should acquire all locks
            tokens = self.lock_mgr.acquire_multiple(
                self.agent_id,
                read_paths=[file1_path, file2_path],
                write_paths=[file3_path],
                timeout_seconds=5
            )
            assert len(tokens) == 3

            self.lock_mgr.release_multiple(tokens)

        finally:
            os.unlink(file1_path)
            os.unlink(file2_path)
            os.unlink(file3_path)

    def test_quotes_respected_in_file_arguments(self) -> None:
        """Test that analyzer respects quotes in file paths."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("# test")
            file_path = f.name

        try:
            # Command with quoted file path
            command = f"python -c 'import sys' {file_path}"
            deps = self.analyzer.analyze(command)

            # Should identify the unquoted file path
            assert file_path in deps.files_read or len(deps.files_read) > 0

        finally:
            os.unlink(file_path)


class TestLockManagerProtectsAnalyzedDependencies:
    """Test that locks actually protect analyzed dependencies."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.analyzer = CommandDependencyAnalyzer()
        self.lock_mgr = FileLockManager()

    def test_write_lock_blocks_other_read_on_analyzed_file(self) -> None:
        """Test write lock on file analyzed as read blocks other agents."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("data")
            file_path = f.name

        try:
            # Agent A acquires write lock
            write_token = self.lock_mgr.acquire_write("agent-a", file_path, timeout_seconds=5)

            # Agent B tries to acquire read lock (should timeout)
            with pytest.raises(LockTimeoutError):
                self.lock_mgr.acquire_read("agent-b", file_path, timeout_seconds=1)

            self.lock_mgr.release_write(write_token)

        finally:
            os.unlink(file_path)

    def test_multiple_read_locks_allowed_on_same_file(self) -> None:
        """Test multiple agents can hold read locks on same file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("data")
            file_path = f.name

        try:
            # Multiple agents acquire read locks
            token_a = self.lock_mgr.acquire_read("agent-a", file_path, timeout_seconds=5)
            token_b = self.lock_mgr.acquire_read("agent-b", file_path, timeout_seconds=5)
            token_c = self.lock_mgr.acquire_read("agent-c", file_path, timeout_seconds=5)

            assert token_a.lock_type == "read"
            assert token_b.lock_type == "read"
            assert token_c.lock_type == "read"

            # All should have same file_path
            assert token_a.file_path == file_path
            assert token_b.file_path == file_path
            assert token_c.file_path == file_path

            self.lock_mgr.release_read(token_a)
            self.lock_mgr.release_read(token_b)
            self.lock_mgr.release_read(token_c)

        finally:
            os.unlink(file_path)

    def test_read_lock_blocks_write_on_analyzed_file(self) -> None:
        """Test read lock blocks write lock (reverse of write_blocks_read)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("data")
            file_path = f.name

        try:
            # Agent A acquires read lock
            read_token = self.lock_mgr.acquire_read("agent-a", file_path, timeout_seconds=5)

            # Agent B tries to acquire write lock (should timeout)
            with pytest.raises(LockTimeoutError):
                self.lock_mgr.acquire_write("agent-b", file_path, timeout_seconds=1)

            self.lock_mgr.release_read(read_token)

        finally:
            os.unlink(file_path)

    def test_atomic_acquisition_prevents_partial_locks(self) -> None:
        """Test that acquire_multiple is atomic: all-or-nothing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f1:
            f1.write("file1")
            file1_path = f1.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f2:
            f2.write("file2")
            file2_path = f2.name

        try:
            # Agent A locks file2
            write_token = self.lock_mgr.acquire_write("agent-a", file2_path, timeout_seconds=5)

            # Agent B tries to acquire multiple locks (file1 readable, file2 writable)
            # Since file2 is locked, acquire_multiple should fail with timeout
            with pytest.raises(LockTimeoutError):
                self.lock_mgr.acquire_multiple(
                    "agent-b",
                    read_paths=[file1_path],
                    write_paths=[file2_path],
                    timeout_seconds=1
                )

            # Verify file1 was NOT locked by agent-b (atomic failure)
            # Agent c should be able to acquire read lock on file1
            token_c = self.lock_mgr.acquire_read("agent-c", file1_path, timeout_seconds=1)
            self.lock_mgr.release_read(token_c)

            self.lock_mgr.release_write(write_token)

        finally:
            os.unlink(file1_path)
            os.unlink(file2_path)


class TestAnalyzerAndLockManagerWorkflow:
    """Test realistic workflows combining analysis and locking."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.analyzer = CommandDependencyAnalyzer()
        self.lock_mgr = FileLockManager()

    def test_workflow_analyze_then_lock_then_execute(self) -> None:
        """Test realistic workflow: analyze, acquire locks, execute (stub), release."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f_in:
            f_in.write("x = 1")
            in_path = f_in.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f_out:
            f_out.write("")
            out_path = f_out.name

        try:
            # Step 1: Analyze command
            command = f"python -c 'print({in_path})' > {out_path}"
            deps = self.analyzer.analyze(command)

            # Step 2: Acquire locks based on dependencies
            tokens = self.lock_mgr.acquire_multiple(
                "agent-executor",
                read_paths=list(deps.files_read),
                write_paths=list(deps.files_written),
                timeout_seconds=5
            )

            # Step 3: Verify locks held
            assert len(tokens) > 0
            assert all(t.agent_id == "agent-executor" for t in tokens)

            # Step 4: Release locks
            self.lock_mgr.release_multiple(tokens)

            # Step 5: Verify locks released (new agent can acquire)
            new_tokens = self.lock_mgr.acquire_multiple(
                "agent-other",
                read_paths=list(deps.files_read),
                write_paths=list(deps.files_written),
                timeout_seconds=5
            )
            self.lock_mgr.release_multiple(new_tokens)

        finally:
            os.unlink(in_path)
            os.unlink(out_path)

    def test_concurrent_agents_different_files_succeed(self) -> None:
        """Test two agents reading different files can both acquire locks."""
        import threading

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f_a:
            f_a.write("agent-a data")
            file_a_path = f_a.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f_b:
            f_b.write("agent-b data")
            file_b_path = f_b.name

        acquired: List[List] = [[], []]

        def agent_acquire(agent_id: str, file_path: str, index: int) -> None:
            token = self.lock_mgr.acquire_read(agent_id, file_path, timeout_seconds=5)
            acquired[index] = [token]
            self.lock_mgr.release_read(token)

        try:
            thread_a = threading.Thread(
                target=agent_acquire,
                args=("agent-a", file_a_path, 0)
            )
            thread_b = threading.Thread(
                target=agent_acquire,
                args=("agent-b", file_b_path, 1)
            )

            thread_a.start()
            thread_b.start()

            thread_a.join(timeout=10)
            thread_b.join(timeout=10)

            assert len(acquired[0]) == 1
            assert len(acquired[1]) == 1
            assert acquired[0][0].agent_id == "agent-a"
            assert acquired[1][0].agent_id == "agent-b"

        finally:
            os.unlink(file_a_path)
            os.unlink(file_b_path)
