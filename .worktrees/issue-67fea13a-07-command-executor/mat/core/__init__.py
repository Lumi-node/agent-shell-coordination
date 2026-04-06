"""Core modules for multi-agent-terminal.

This package contains the foundational components:
- AgentRegistry: Live agent membership tracking
- FileLockManager: File-level read-write locks
"""

from .agent_registry import AgentRegistry
from .file_lock_manager import FileLockManager, LockToken

__all__ = ["AgentRegistry", "FileLockManager", "LockToken"]
