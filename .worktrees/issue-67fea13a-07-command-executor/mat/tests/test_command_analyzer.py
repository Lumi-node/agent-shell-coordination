"""
Unit tests for CommandDependencyAnalyzer.

Tests cover:
- Tokenization with quotes and escapes
- Pattern matching for common tools (python, mypy, mv, rm, grep, sed)
- Redirect handling (>, >>, <)
- Pipe handling
- Environment variable extraction
- Conservative fallback for unknown tools
"""

import pytest
from mat.analysis.command_analyzer import CommandDependencies, CommandDependencyAnalyzer


@pytest.fixture
def analyzer() -> CommandDependencyAnalyzer:
    """Create a CommandDependencyAnalyzer instance."""
    return CommandDependencyAnalyzer()


class TestTokenization:
    """Test quote-aware tokenization."""

    def test_tokenize_simple_command(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test tokenization of simple command."""
        tokens = analyzer._tokenize("python script.py arg1 arg2")
        assert tokens == ["python", "script.py", "arg1", "arg2"]

    def test_tokenize_single_quoted_strings(
        self, analyzer: CommandDependencyAnalyzer
    ) -> None:
        """Test tokenization with single quotes."""
        tokens = analyzer._tokenize("python 'file with spaces.py'")
        assert tokens == ["python", "file with spaces.py"]

    def test_tokenize_double_quoted_strings(
        self, analyzer: CommandDependencyAnalyzer
    ) -> None:
        """Test tokenization with double quotes."""
        tokens = analyzer._tokenize('echo "hello world"')
        assert tokens == ["echo", "hello world"]

    def test_tokenize_mixed_quotes(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test tokenization with mixed quote types."""
        tokens = analyzer._tokenize("""grep 'pattern' "file.txt" """)
        assert tokens == ["grep", "pattern", "file.txt"]

    def test_tokenize_escaped_characters(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test tokenization with escaped characters."""
        tokens = analyzer._tokenize("echo hello\\ world")
        assert tokens == ["echo", "hello world"]

    def test_tokenize_empty_string_raises(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test that empty command raises ValueError."""
        with pytest.raises(ValueError, match="Command cannot be empty"):
            analyzer.analyze("")

    def test_tokenize_none_raises(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test that None command raises ValueError."""
        with pytest.raises(ValueError, match="Command cannot be empty"):
            analyzer.analyze(None)  # type: ignore

    def test_tokenize_quotes_in_quotes(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test tokenization with quotes inside quotes."""
        tokens = analyzer._tokenize("""echo "it's fine" """)
        assert tokens == ["echo", "it's fine"]


class TestPythonAnalysis:
    """Test Python command analysis."""

    def test_analyze_python_simple(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test simple python script analysis."""
        deps = analyzer.analyze("python script.py")
        assert "script.py" in deps.files_read
        assert deps.files_written == set()
        assert deps.files_deleted == set()

    def test_analyze_python_with_version(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test python3 command."""
        deps = analyzer.analyze("python3 script.py")
        assert "script.py" in deps.files_read

    def test_analyze_python_with_input_flag(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test python command with --input flag."""
        deps = analyzer.analyze("python train.py --input data.csv")
        assert "train.py" in deps.files_read
        assert "data.csv" in deps.files_read

    def test_analyze_python_with_output_flag(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test python command with --output flag."""
        deps = analyzer.analyze("python script.py --output result.txt")
        assert "script.py" in deps.files_read
        assert "result.txt" in deps.files_written

    def test_analyze_python_refactor(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test refactor.py command from integration test."""
        deps = analyzer.analyze(
            "python3 refactor.py --in src/module.py --out src/module.py"
        )
        assert "refactor.py" in deps.files_read
        assert "src/module.py" in deps.files_read
        assert "src/module.py" in deps.files_written

    def test_analyze_ml_training(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test ML training command."""
        deps = analyzer.analyze("python3 train.py --input data.csv --output model.pkl")
        assert "train.py" in deps.files_read
        assert "data.csv" in deps.files_read
        assert "model.pkl" in deps.files_written

    def test_analyze_python_with_multiple_input_flags(
        self, analyzer: CommandDependencyAnalyzer
    ) -> None:
        """Test python command with multiple input flags."""
        deps = analyzer.analyze(
            "python script.py --input file1.txt --input file2.txt --output out.txt"
        )
        assert "script.py" in deps.files_read
        assert "file1.txt" in deps.files_read
        assert "file2.txt" in deps.files_read
        assert "out.txt" in deps.files_written


class TestMypyAnalysis:
    """Test mypy command analysis."""

    def test_analyze_mypy_single_file(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test mypy on single file."""
        deps = analyzer.analyze("mypy script.py")
        assert "script.py" in deps.files_read
        assert deps.files_written == set()

    def test_analyze_mypy_multiple_files(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test mypy on multiple files."""
        deps = analyzer.analyze("mypy file1.py file2.py")
        assert "file1.py" in deps.files_read
        assert "file2.py" in deps.files_read

    def test_analyze_mypy_with_flags(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test mypy with flags."""
        deps = analyzer.analyze("mypy --strict module.py")
        assert "module.py" in deps.files_read

    def test_analyze_mypy_check(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test mypy check from integration test."""
        deps = analyzer.analyze("mypy src/module.py")
        assert "src/module.py" in deps.files_read
        assert deps.files_written == set()


class TestMvAnalysis:
    """Test mv command analysis."""

    def test_analyze_mv_simple(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test simple mv command."""
        deps = analyzer.analyze("mv src.py dst.py")
        assert "src.py" in deps.files_read
        assert "dst.py" in deps.files_written

    def test_analyze_mv_with_path(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test mv with paths."""
        deps = analyzer.analyze("mv src/file.py dest/file.py")
        assert "src/file.py" in deps.files_read
        assert "dest/file.py" in deps.files_written

    def test_analyze_mv_directory(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test mv with directory."""
        deps = analyzer.analyze("mv old_dir new_dir")
        assert "old_dir" in deps.files_read
        assert "new_dir" in deps.files_written


class TestRmAnalysis:
    """Test rm command analysis."""

    def test_analyze_rm_single_file(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test rm on single file."""
        deps = analyzer.analyze("rm file.py")
        assert "file.py" in deps.files_deleted
        assert deps.files_read == set()
        assert deps.files_written == set()

    def test_analyze_rm_multiple_files(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test rm on multiple files."""
        deps = analyzer.analyze("rm file1.py file2.py")
        assert "file1.py" in deps.files_deleted
        assert "file2.py" in deps.files_deleted

    def test_analyze_rm_with_flag(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test rm with flags."""
        deps = analyzer.analyze("rm -f file.py")
        assert "file.py" in deps.files_deleted


class TestGrepAnalysis:
    """Test grep command analysis."""

    def test_analyze_grep_simple(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test grep command."""
        deps = analyzer.analyze("grep pattern file.txt")
        assert "file.txt" in deps.files_read

    def test_analyze_grep_multiple_files(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test grep on multiple files."""
        deps = analyzer.analyze("grep pattern file1.txt file2.txt")
        assert "file1.txt" in deps.files_read
        assert "file2.txt" in deps.files_read

    def test_analyze_grep_with_flags(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test grep with flags."""
        deps = analyzer.analyze("grep -r pattern directory/")
        # Note: directory/ is treated as a file argument
        assert "directory/" in deps.files_read


class TestSedAnalysis:
    """Test sed command analysis."""

    def test_analyze_sed_without_inplace(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test sed without -i flag."""
        deps = analyzer.analyze("sed 's/pattern/replacement/' file.txt")
        assert "file.txt" in deps.files_read

    def test_analyze_sed_with_inplace(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test sed with -i flag."""
        deps = analyzer.analyze("sed -i 's/pattern/replacement/' file.txt")
        assert "file.txt" in deps.files_read
        assert "file.txt" in deps.files_written


class TestExportAnalysis:
    """Test export command analysis."""

    def test_analyze_export_simple(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test export command."""
        deps = analyzer.analyze("export FOO=bar")
        assert "FOO" in deps.env_vars_written

    def test_analyze_export_multiple(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test export with multiple variables."""
        deps = analyzer.analyze("export FOO=bar BAR=baz")
        assert "FOO" in deps.env_vars_written
        assert "BAR" in deps.env_vars_written


class TestEnvironmentVariables:
    """Test environment variable extraction."""

    def test_analyze_env_var_read_dollar(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test $VAR syntax."""
        deps = analyzer.analyze("echo $HOME")
        assert "HOME" in deps.env_vars_read

    def test_analyze_env_var_read_brace(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test ${VAR} syntax."""
        deps = analyzer.analyze("echo ${HOME}")
        assert "HOME" in deps.env_vars_read

    def test_analyze_env_var_in_python(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test environment variable in python command."""
        deps = analyzer.analyze("python $SCRIPT_PATH")
        assert "SCRIPT_PATH" in deps.env_vars_read

    def test_analyze_env_var_command_substitution(
        self, analyzer: CommandDependencyAnalyzer
    ) -> None:
        """Test environment variable in command substitution."""
        deps = analyzer.analyze("echo $(echo $VAR)")
        assert "VAR" in deps.env_vars_read

    def test_analyze_env_var_written(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test environment variable written."""
        deps = analyzer.analyze("export MYVAR=value")
        assert "MYVAR" in deps.env_vars_written


class TestRedirects:
    """Test redirect handling."""

    def test_analyze_output_redirect(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test > redirect."""
        deps = analyzer.analyze("cat input.txt > output.txt")
        assert "input.txt" in deps.files_read
        assert "output.txt" in deps.files_written

    def test_analyze_append_redirect(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test >> redirect."""
        deps = analyzer.analyze("echo hello >> output.txt")
        assert "output.txt" in deps.files_written

    def test_analyze_input_redirect(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test < redirect."""
        deps = analyzer.analyze("sort < input.txt")
        assert "input.txt" in deps.files_read

    def test_analyze_combined_redirects(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test combined redirects."""
        deps = analyzer.analyze("sort < input.txt > output.txt")
        assert "input.txt" in deps.files_read
        assert "output.txt" in deps.files_written


class TestPipes:
    """Test pipe handling."""

    def test_analyze_simple_pipe(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test simple pipe."""
        deps = analyzer.analyze("cat file.txt | grep pattern")
        assert "file.txt" in deps.files_read

    def test_analyze_multiple_pipes(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test multiple pipes."""
        deps = analyzer.analyze("cat input.txt | grep pattern | wc -l")
        assert "input.txt" in deps.files_read

    def test_analyze_pipe_with_redirect(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test pipe with redirect."""
        deps = analyzer.analyze("cat input.txt | grep pattern > output.txt")
        assert "input.txt" in deps.files_read
        assert "output.txt" in deps.files_written


class TestConservativeFallback:
    """Test conservative fallback for unknown tools."""

    def test_analyze_unknown_tool(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test unknown tool returns conservative fallback."""
        deps = analyzer.analyze("unknown_tool arg1 arg2")
        assert deps.files_read == {"*"}

    def test_analyze_binary_command(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test binary command (not recognized)."""
        deps = analyzer.analyze("gcc file.c -o file.o")
        assert deps.files_read == {"*"}

    def test_analyze_unknown_tool_with_redirect(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test unknown tool with redirect still captures redirect."""
        deps = analyzer.analyze("unknown_tool arg > output.txt")
        assert deps.files_read == {"*"}
        assert "output.txt" in deps.files_written


class TestQuotedFilenames:
    """Test handling of quoted filenames."""

    def test_analyze_python_quoted_filename(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test python with quoted filename containing spaces."""
        deps = analyzer.analyze('python "file with spaces.py"')
        assert "file with spaces.py" in deps.files_read

    def test_analyze_mypy_quoted_filename(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test mypy with quoted filename."""
        deps = analyzer.analyze("mypy 'my file.py'")
        assert "my file.py" in deps.files_read

    def test_analyze_mv_quoted_filenames(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test mv with quoted filenames."""
        deps = analyzer.analyze('mv "source file.py" "dest file.py"')
        assert "source file.py" in deps.files_read
        assert "dest file.py" in deps.files_written


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_analyze_command_with_extra_spaces(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test command with extra spaces."""
        deps = analyzer.analyze("python    script.py   arg1")
        assert "script.py" in deps.files_read

    def test_analyze_command_with_tabs(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test command with tabs."""
        deps = analyzer.analyze("python\tscript.py\targ1")
        assert "script.py" in deps.files_read

    def test_analyze_python_with_input_output_flags(
        self, analyzer: CommandDependencyAnalyzer
    ) -> None:
        """Test python with both --input and --output."""
        deps = analyzer.analyze("python process.py --input in.txt --output out.txt")
        assert "process.py" in deps.files_read
        assert "in.txt" in deps.files_read
        assert "out.txt" in deps.files_written

    def test_analyze_rm_with_multiple_files_and_flags(
        self, analyzer: CommandDependencyAnalyzer
    ) -> None:
        """Test rm with flags and files."""
        deps = analyzer.analyze("rm -rf file1.py file2.py")
        assert "file1.py" in deps.files_deleted
        assert "file2.py" in deps.files_deleted

    def test_analyze_grep_with_quoted_pattern(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test grep with quoted pattern."""
        deps = analyzer.analyze("grep 'pattern with spaces' file.txt")
        assert "file.txt" in deps.files_read


class TestIntegrationScenarios:
    """Test scenarios from integration tests."""

    def test_analyze_refactor_scenario(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test refactor scenario from 3-agent integration test."""
        deps = analyzer.analyze(
            "python3 refactor.py --in src/module.py --out src/module.py"
        )
        assert deps.files_read == {"refactor.py", "src/module.py"}
        assert deps.files_written == {"src/module.py"}
        assert deps.files_deleted == set()

    def test_analyze_mypy_scenario(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test mypy scenario from 3-agent integration test."""
        deps = analyzer.analyze("mypy src/module.py")
        assert deps.files_read == {"src/module.py"}
        assert deps.files_written == set()
        assert deps.files_deleted == set()

    def test_analyze_train_scenario(self, analyzer: CommandDependencyAnalyzer) -> None:
        """Test training scenario from 3-agent integration test."""
        deps = analyzer.analyze("python3 train.py --input data.csv --output model.pkl")
        assert deps.files_read == {"train.py", "data.csv"}
        assert deps.files_written == {"model.pkl"}
        assert deps.files_deleted == set()
