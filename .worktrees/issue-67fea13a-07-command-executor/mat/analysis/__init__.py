"""Analysis modules for multi-agent-terminal.

This package contains command dependency analysis:
- CommandDependencyAnalyzer: Extract file and environment dependencies from shell commands
"""

from mat.analysis.command_analyzer import CommandDependencies, CommandDependencyAnalyzer

__all__ = [
    "CommandDependencies",
    "CommandDependencyAnalyzer",
]
