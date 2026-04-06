"""CLI tool for multi-agent-terminal: mat-coordinate.

This module provides command-line interface for the coordination system.
"""

import sys
from typing import List


def main(argv: List[str] | None = None) -> int:
    """Main entry point for mat-coordinate CLI.

    Args:
        argv: Command line arguments (default: sys.argv[1:])

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] in ("--help", "-h"):
        print("mat-coordinate - Multi-Agent Terminal Coordinator")
        print()
        print("Usage: mat-coordinate [COMMAND] [OPTIONS]")
        print()
        print("Commands:")
        print("  --version         Show version and exit")
        print("  --help            Show this help and exit")
        print("  serve             Start lock manager server (Phase 2)")
        print("  test              Run integration tests")
        return 0

    if argv[0] in ("--version", "-v"):
        print("multi-agent-terminal 0.1.0")
        return 0

    if argv[0] == "serve":
        print("Lock manager server starting on localhost:5050...")
        print("(Phase 1: placeholder implementation)")
        return 0

    if argv[0] == "test":
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "-m", "pytest",
                 "mat/tests/integration/test_three_agent_coordination.py", "-v"],
                cwd="."
            )
            return result.returncode
        except ImportError:
            print("Error: pytest not installed. Run: pip install pytest")
            return 1

    print(f"Unknown command: {argv[0]}")
    print("Use --help for usage information")
    return 1


if __name__ == "__main__":
    sys.exit(main())
