# Multi-Agent Terminal Coordination System

## Overview

`multi-agent-terminal` is a distributed system enabling autonomous AI agents to collaboratively execute shell commands on shared computational environments while maintaining consistency guarantees.

When multiple autonomous AI agents execute commands on the same system concurrently, conflicts arise:
- **File write conflicts**: Agent A refactors code while Agent B's type checker reads stale versions
- **Process conflicts**: Agent C's training pipeline imports code modified by Agent A
- **Environment conflicts**: Agents modify environment variables, PATH, or working directories independently
- **Ordering dependencies**: Commands have implicit dependencies that agents don't observe

This system detects, prevents, and resolves these conflicts automatically using distributed algorithms built on read-write locks and command dependency analysis.

## Core Vision

Build a **causally-consistent distributed terminal state manager** that:

1. **Tracks shared state** across agent terminals using metadata about command dependencies
2. **Prevents conflicts** using distributed mutual exclusion (read-write locks)
3. **Reorders commands** to satisfy dependencies via static analysis
4. **Syncs state** across agents without requiring constant communication
5. **Remains available** even if agents disconnect unexpectedly

## Quick Start

### Installation

```bash
pip install -e .
```

### Basic Usage

```python
from mat import AgentCoordinator

# Create a coordinator for this agent
coordinator = AgentCoordinator(agent_id="agent-A")

# Execute a command (locks are acquired automatically)
result = coordinator.execute("python refactor.py --in src/module.py --out src/module.py")

if result.exit_code == 0:
    print("Success:", result.stdout)
else:
    print("Failed:", result.stderr)

# Share environment variables across agents
coordinator.set_env("PYTHONPATH", "/path/to/lib")

# Check active agents
agents = coordinator.list_agents()
print(f"Active agents: {agents}")

# Graceful shutdown
coordinator.shutdown()
```

### CLI

```bash
# Show version
mat-coordinate --version

# Show help
mat-coordinate --help

# Run integration tests
mat-coordinate test
```

## Architecture

The system consists of 6 core modules:

1. **AgentRegistry** (`mat.core.agent_registry`)
   - Maintains live agent membership using heartbeat mechanism
   - Agents automatically expire 30 seconds after last heartbeat

2. **FileLockManager** (`mat.core.file_lock_manager`)
   - Implements read-write locks for file-level mutual exclusion
   - Multiple agents can read; only one can write

3. **CommandDependencyAnalyzer** (`mat.analysis.command_analyzer`)
   - Parses shell commands to extract file and environment dependencies
   - Conservative fallback: unknown commands assume read all files

4. **ConflictDetector** (`mat.coordination.conflict_detector`)
   - Detects conflicts between two commands
   - Recommends safe execution order

5. **CommandExecutor** (`mat.execution.command_executor`)
   - Executes commands with automatic lock management
   - Acquires read locks on files_read, write locks on files_written

6. **AgentCoordinator** (`mat.AgentCoordinator`)
   - High-level API for agents
   - Automatic heartbeat, environment variable sharing, command execution

## Design Principles

- **Deadlock Prevention by Design**: All locks acquired atomically in sorted order
- **Conservative Parsing, Aggressive Locking**: Unknown dependencies assume worst case
- **Heartbeat = Liveness Proof**: Agents prove they're alive by calling heartbeat periodically
- **Single Source of Truth**: All state in memory in one coordinator instance
- **Fail Fast, Fail Explicitly**: Every error is a specific exception type

## Phase 1 Scope

Phase 1 implements the minimal viable coordination system:
- No external dependencies (uses only Python 3.10+ stdlib)
- In-memory coordinator (no persistence)
- localhost-only (single machine)
- ~2500 lines of core code

Phase 2 will add:
- Vector clock synchronization
- Persistent operation log
- Network distribution
- Advanced conflict resolution

## Type Safety

All code is written to pass `mypy --strict`:

```bash
mypy mat/ --strict
```

## Testing

Run the integration test suite:

```bash
pytest mat/tests/integration/test_three_agent_coordination.py -v
```

Or via CLI:

```bash
mat-coordinate test
```

## License

MIT
