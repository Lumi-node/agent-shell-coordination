"""
CommandDependencyAnalyzer for parsing shell commands and extracting file/environment dependencies.

This module provides quote-aware tokenization and pattern-based analysis of shell commands
to determine which files are read, written, or deleted, and which environment variables are
accessed or modified.
"""

import re
from dataclasses import dataclass


@dataclass
class CommandDependencies:
    """
    Extracted dependencies from a shell command.

    Attributes:
        files_read: Set of file paths the command reads (e.g., input files)
        files_written: Set of file paths the command writes/creates
        files_deleted: Set of file paths the command deletes
        env_vars_read: Set of environment variables the command reads
        env_vars_written: Set of environment variables the command modifies

    Conservative parsing:
        If command format is ambiguous, assumes worst case.
        E.g., if can't parse `python -c '...'`, assumes files_read={'*'}
    """

    files_read: set[str]
    files_written: set[str]
    files_deleted: set[str]
    env_vars_read: set[str]
    env_vars_written: set[str]


class CommandDependencyAnalyzer:
    """
    Parse shell commands to extract file and environment dependencies.

    Design:
    - Tokenizes command respecting quotes and special characters
    - Uses regex patterns for common tools (python, mypy, mv, rm, etc.)
    - Handles pipes, redirects, output substitutions
    - Conservative: unknown commands → files_read={'*'}
    - No external parser; ~300-400 lines of patterns and logic

    Limitations (by design):
    - Does NOT execute code to determine side effects
    - Does NOT handle complex shell syntax (IFS, globbing with ** patterns)
    - Does NOT track indirect dependencies (file A imports file B)
    - Does NOT handle binary commands (only shell scripts)
    """

    def __init__(self) -> None:
        """Initialize the command dependency analyzer."""
        pass

    def analyze(self, command: str) -> CommandDependencies:
        """
        Parse a shell command and extract file/env dependencies.

        Args:
            command: Shell command string (e.g., "python3 refactor.py --in src/module.py --out src/module.py")

        Returns:
            CommandDependencies object with files_read, files_written, files_deleted,
            env_vars_read, env_vars_written

        Raises:
            ValueError: If command is None or empty string

        Algorithm:
        1. Tokenize command into tokens (respecting quotes and escapes)
        2. Identify tool (first token: python, mypy, mv, rm, etc.)
        3. Apply tool-specific patterns:
           - python <script> <args>: reads <script> and any file args
           - mypy <file>: reads <file>
           - mv <src> <dst>: reads <src>, writes <dst>
           - rm <file>: deletes <file>
           - grep <pattern> <file>: reads <file>
           - sed -i <file>: reads and writes <file>
           - export FOO=bar: writes FOO
           - $VAR or ${VAR}: reads VAR
        4. Handle pipes and redirects:
           - cmd1 | cmd2: pipe, combine dependencies
           - cmd > file: redirect write, add to files_written
           - cmd < file: redirect read, add to files_read
           - cmd >> file: append, add to files_written
        5. Fallback: If tool unknown or parsing fails, return files_read={'*'}

        Conservative fallback:
        - Unknown tool → assume it reads all files
        - Ambiguous syntax → assume worst case (files_read={'*'})
        - Shell substitutions we can't parse → assume files_read={'*'}

        Returns:
            CommandDependencies with extracted files and env vars
        """
        if not command:
            raise ValueError("Command cannot be empty")

        # Handle pipes: split by | and analyze each part
        if "|" in command:
            return self._analyze_piped(command)

        # Remove redirects from command for tokenization
        cmd_without_redirects = self._remove_redirects(command)

        # Tokenize the command
        tokens = self._tokenize(cmd_without_redirects)
        if not tokens:
            raise ValueError("Command is empty after tokenization")

        tool = tokens[0]

        # Initialize dependencies
        deps = CommandDependencies(
            files_read=set(),
            files_written=set(),
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set(),
        )

        # Try tool-specific extractors
        try:
            if self._is_python_cmd(tool):
                deps = self._extract_python_deps(tokens)
            elif self._is_mypy_cmd(tool):
                deps = self._extract_mypy_deps(tokens)
            elif self._is_mv_cmd(tool):
                deps = self._extract_mv_deps(tokens)
            elif self._is_rm_cmd(tool):
                deps = self._extract_rm_deps(tokens)
            elif self._is_grep_cmd(tool):
                deps = self._extract_grep_deps(tokens)
            elif self._is_sed_cmd(tool):
                deps = self._extract_sed_deps(tokens)
            elif self._is_export_cmd(tool):
                deps = self._extract_export_deps(tokens)
            elif self._is_cat_cmd(tool):
                deps = self._extract_cat_deps(tokens)
            else:
                # Unknown tool - conservative fallback
                deps = CommandDependencies(
                    files_read={"*"},
                    files_written=set(),
                    files_deleted=set(),
                    env_vars_read=set(),
                    env_vars_written=set(),
                )
        except Exception:
            # Pattern extraction failed, use conservative fallback
            deps = CommandDependencies(
                files_read={"*"},
                files_written=set(),
                files_deleted=set(),
                env_vars_read=set(),
                env_vars_written=set(),
            )

        # Always extract env vars from the entire command
        env_vars = self._extract_all_env_vars(command)
        deps.env_vars_read.update(env_vars["read"])
        deps.env_vars_written.update(env_vars["written"])

        # Handle redirects
        deps = self._merge_redirect_deps(command, deps)

        return deps

    def _tokenize(self, command: str) -> list[str]:
        """
        Split command into tokens, respecting quotes and escapes.

        Internal helper method.

        Args:
            command: Raw command string

        Returns:
            List of tokens. Quoted strings are single tokens with quotes removed.

        Examples:
            "python 'file with spaces.py'" → ["python", "file with spaces.py"]
            "echo \"hello world\"" → ["echo", "hello world"]
            "grep 'pattern' file.txt" → ["grep", "pattern", "file.txt"]

        Algorithm:
        - Iterate through command character by character
        - Track quote state (none, single, double)
        - Track escape state (backslash escapes next char)
        - Accumulate characters into current token
        - Split on whitespace when not in quotes
        - Strip quotes from final tokens
        """
        tokens = []
        current_token = []
        in_quote = None  # None, "'", or '"'
        escape_next = False

        for char in command:
            if escape_next:
                current_token.append(char)
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            if char in ("'", '"'):
                if in_quote == char:
                    # End quote
                    in_quote = None
                elif in_quote is None:
                    # Start quote
                    in_quote = char
                else:
                    # Different quote type, treat as literal
                    current_token.append(char)
                continue

            if char.isspace() and in_quote is None:
                # Token boundary
                if current_token:
                    tokens.append("".join(current_token))
                    current_token = []
                continue

            current_token.append(char)

        if current_token:
            tokens.append("".join(current_token))

        return tokens

    def _is_python_cmd(self, tool: str) -> bool:
        """Check if tool is a Python command."""
        return re.match(r"^python\d*(\.\d+)?$", tool) is not None

    def _is_mypy_cmd(self, tool: str) -> bool:
        """Check if tool is mypy."""
        return tool == "mypy"

    def _is_mv_cmd(self, tool: str) -> bool:
        """Check if tool is mv."""
        return tool == "mv"

    def _is_rm_cmd(self, tool: str) -> bool:
        """Check if tool is rm."""
        return tool == "rm"

    def _is_grep_cmd(self, tool: str) -> bool:
        """Check if tool is grep."""
        return tool == "grep"

    def _is_sed_cmd(self, tool: str) -> bool:
        """Check if tool is sed."""
        return tool == "sed"

    def _is_export_cmd(self, tool: str) -> bool:
        """Check if tool is export."""
        return tool == "export"

    def _is_cat_cmd(self, tool: str) -> bool:
        """Check if tool is cat."""
        return tool == "cat"

    def _remove_redirects(self, command: str) -> str:
        """Remove redirects from command before tokenization."""
        # Remove redirect operators and their arguments
        result = re.sub(r"\s*[<>]+\s*[^\s|]+", "", command)
        return result

    def _extract_python_deps(self, tokens: list[str]) -> CommandDependencies:
        """Extract dependencies from python command."""
        files_read = set()
        files_written = set()

        # First token after python is the script
        if len(tokens) > 1:
            script = tokens[1]
            files_read.add(script)

        # Look for --in, --input, and other input indicators
        i = 1
        while i < len(tokens):
            token = tokens[i]
            if token in ("--in", "--input", "--input-file"):
                if i + 1 < len(tokens):
                    files_read.add(tokens[i + 1])
                    i += 2
                else:
                    i += 1
            elif token in ("--out", "--output", "--output-file"):
                if i + 1 < len(tokens):
                    files_written.add(tokens[i + 1])
                    i += 2
                else:
                    i += 1
            else:
                i += 1

        return CommandDependencies(
            files_read=files_read,
            files_written=files_written,
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set(),
        )

    def _extract_mypy_deps(self, tokens: list[str]) -> CommandDependencies:
        """Extract dependencies from mypy command."""
        files_read = set()

        # All arguments after mypy are files to check
        for token in tokens[1:]:
            if not token.startswith("-"):
                files_read.add(token)

        return CommandDependencies(
            files_read=files_read,
            files_written=set(),
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set(),
        )

    def _extract_mv_deps(self, tokens: list[str]) -> CommandDependencies:
        """Extract dependencies from mv command."""
        files_read = set()
        files_written = set()

        # Format: mv [options] source dest
        if len(tokens) >= 3:
            files_read.add(tokens[1])
            files_written.add(tokens[2])

        return CommandDependencies(
            files_read=files_read,
            files_written=files_written,
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set(),
        )

    def _extract_rm_deps(self, tokens: list[str]) -> CommandDependencies:
        """Extract dependencies from rm command."""
        files_deleted = set()

        # All arguments after rm are files to delete (skip flags)
        for token in tokens[1:]:
            if not token.startswith("-"):
                files_deleted.add(token)

        return CommandDependencies(
            files_read=set(),
            files_written=set(),
            files_deleted=files_deleted,
            env_vars_read=set(),
            env_vars_written=set(),
        )

    def _extract_grep_deps(self, tokens: list[str]) -> CommandDependencies:
        """Extract dependencies from grep command."""
        files_read = set()

        # Last token is usually the file (if present)
        for token in tokens[1:]:
            if not token.startswith("-") and not token.startswith("-"):
                files_read.add(token)

        return CommandDependencies(
            files_read=files_read,
            files_written=set(),
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set(),
        )

    def _extract_cat_deps(self, tokens: list[str]) -> CommandDependencies:
        """Extract dependencies from cat command."""
        files_read = set()

        # All arguments after cat are files to read
        for token in tokens[1:]:
            if not token.startswith("-"):
                files_read.add(token)

        return CommandDependencies(
            files_read=files_read,
            files_written=set(),
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set(),
        )

    def _extract_sed_deps(self, tokens: list[str]) -> CommandDependencies:
        """Extract dependencies from sed command."""
        files_read = set()
        files_written = set()

        # Check for -i flag (in-place edit)
        if "-i" in tokens:
            # Find the file argument after -i or in the remaining tokens
            i = 0
            while i < len(tokens):
                if tokens[i] == "-i":
                    if i + 1 < len(tokens):
                        # Next token might be suffix or file
                        next_token = tokens[i + 1]
                        if not next_token.startswith("-"):
                            # Could be suffix or file
                            # Assume it's the file if it's the last non-flag token
                            files_read.add(next_token)
                            files_written.add(next_token)
                    i += 1
                else:
                    if not tokens[i].startswith("-"):
                        # Non-flag token, assume it's a file
                        files_read.add(tokens[i])
                        if "-i" in tokens:
                            files_written.add(tokens[i])
                    i += 1
        else:
            # Without -i, only read
            for token in tokens[1:]:
                if not token.startswith("-"):
                    files_read.add(token)

        return CommandDependencies(
            files_read=files_read,
            files_written=files_written,
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set(),
        )

    def _extract_export_deps(self, tokens: list[str]) -> CommandDependencies:
        """Extract dependencies from export command."""
        env_vars_written = set()

        # Format: export VAR=value or export VAR
        for token in tokens[1:]:
            if "=" in token:
                var_name = token.split("=")[0]
                env_vars_written.add(var_name)
            else:
                env_vars_written.add(token)

        return CommandDependencies(
            files_read=set(),
            files_written=set(),
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=env_vars_written,
        )

    def _extract_all_env_vars(self, command: str) -> dict[str, set[str]]:
        """Extract all environment variables from command."""
        env_vars_read = set()
        env_vars_written = set()

        # Extract $VAR and ${VAR} references
        var_pattern = r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?"
        matches = re.findall(var_pattern, command)
        env_vars_read.update(matches)

        # Extract $(...) command substitutions
        cmd_sub_pattern = r"\$\(([^)]+)\)"
        cmd_matches = re.findall(cmd_sub_pattern, command)
        # Extract vars from command substitutions
        for cmd_sub in cmd_matches:
            var_matches = re.findall(var_pattern, cmd_sub)
            env_vars_read.update(var_matches)

        # Extract export FOO=bar
        export_pattern = r"\bexport\s+([A-Za-z_][A-Za-z0-9_]*)"
        export_matches = re.findall(export_pattern, command)
        env_vars_written.update(export_matches)

        return {"read": env_vars_read, "written": env_vars_written}

    def _merge_redirect_deps(
        self, command: str, deps: CommandDependencies
    ) -> CommandDependencies:
        """Handle redirects and pipes in command."""
        # Handle output redirect: cmd > file
        output_redirect = re.search(r">\s*([^\s|]+)", command)
        if output_redirect:
            deps.files_written.add(output_redirect.group(1))

        # Handle append redirect: cmd >> file
        append_redirect = re.search(r">>\s*([^\s|]+)", command)
        if append_redirect:
            deps.files_written.add(append_redirect.group(1))

        # Handle input redirect: cmd < file
        input_redirect = re.search(r"<\s*([^\s|]+)", command)
        if input_redirect:
            deps.files_read.add(input_redirect.group(1))

        return deps

    def _analyze_piped(self, command: str) -> CommandDependencies:
        """Analyze a piped command (cmd1 | cmd2)."""
        parts = command.split("|")
        all_deps = CommandDependencies(
            files_read=set(),
            files_written=set(),
            files_deleted=set(),
            env_vars_read=set(),
            env_vars_written=set(),
        )

        for part in parts:
            part = part.strip()
            if part:
                try:
                    part_deps = self.analyze(part)
                    all_deps.files_read.update(part_deps.files_read)
                    all_deps.files_written.update(part_deps.files_written)
                    all_deps.files_deleted.update(part_deps.files_deleted)
                    all_deps.env_vars_read.update(part_deps.env_vars_read)
                    all_deps.env_vars_written.update(part_deps.env_vars_written)
                except Exception:
                    # If analysis fails, assume conservative
                    all_deps.files_read.add("*")

        return all_deps
