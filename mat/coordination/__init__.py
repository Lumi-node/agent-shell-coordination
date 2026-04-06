"""Coordination modules for multi-agent-terminal.

This package contains conflict detection and resolution:
- ConflictDetector: Detect and recommend safe ordering for conflicting commands
"""

from .conflict_detector import Conflict, ConflictDetector

__all__ = ["Conflict", "ConflictDetector"]
