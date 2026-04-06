# AgentShell API Reference

AgentShell is a distributed multi-agent terminal coordination system designed to allow autonomous AI agents to collaboratively execute shell commands on shared computational environments. It leverages Conflict-Free Replicated Data Types (CRDTs) and distributed consensus algorithms to ensure conflict-free execution.

---

## Core Modules

### `.worktrees/issue-67fea13a-06-conflict-detector/mat/core/agent_registry.py`

Manages the registration, discovery, and state tracking of all active agents within the system.

**Key Classes/Functions:**

*   **`AgentRegistry`**
    *   **Signature:** `AgentRegistry()`
    *   **Description:** Singleton class responsible for maintaining a global map of registered agents, their capabilities, and current connection statuses.
    *   **Example Usage:**
        ```python
        registry = AgentRegistry()
        registry.register_agent("AgentA", {"role": "executor"})
        print(registry.get_agent_details("AgentA"))
        ```

### `.worktrees/issue-67fea13a-06-conflict-detector/mat/core/file_lock_manager.py`

Handles distributed locking mechanisms to prevent simultaneous, conflicting writes to shared resources (files, terminal sessions).

**Key Classes/Functions:**

*   **`FileLockManager`**
    *   **Signature:** `FileLockManager(resource_id: str, consensus_client)`
    *   **Description:** Manages the acquisition and release of locks for specific shared resources using an underlying consensus mechanism.
    *   **Example Usage:**
        ```python
        lock_manager = FileLockManager("/shared/log.txt", consensus_client)
        if lock_manager.acquire_lock("/shared/log.txt", timeout=5):
            try:
                # Perform critical section operations
                pass
            finally:
                lock_manager.release_lock("/shared/log.txt")
        ```

---

## Coordination Modules

### `.worktrees/issue-67fea13a-06-conflict-detector/mat/coordination/conflict_detector.py`

Implements the logic for detecting potential conflicts arising from concurrent operations across different agents.

**Key Classes/Functions:**

*   **`ConflictDetector`**
    *   **Signature:** `ConflictDetector(history_log: list)`
    *   **Description:** Analyzes sequences of operations against a shared history log to determine if a new proposed operation would lead to a state conflict.
    *   **Example Usage:**
        ```python
        detector = ConflictDetector(initial_history)
        is_conflict = detector.check_conflict(proposed_operation, current_state)
        if is_conflict:
            print("Conflict detected! Requires resolution.")
        ```

### `.worktrees/issue-67fea13a-06-conflict-detector/mat/coordination/coordinator.py`

The central orchestration component that mediates requests between agents, applies conflict resolution strategies, and drives the execution workflow.

**Key Classes/Functions:**

*   **`Coordinator`**
    *   **Signature:** `Coordinator(registry: AgentRegistry, detector: ConflictDetector)`
    *   **Description:** Coordinates the execution flow. It receives requests, consults the conflict detector, and manages the state transition across agents.
    *   **Example Usage:**
        ```python
        coordinator = Coordinator(registry, detector)
        result = coordinator.submit_task(agent_id="AgentB", command="ls -l")
        print(f"Task result: {result}")
        ```

---

## Analysis Modules

### `.worktrees/issue-67fea13a-06-conflict-detector/mat/analysis/command_analyzer.py`

Parses and semantically analyzes shell commands to determine their potential side effects, resource dependencies, and execution complexity.

**Key Classes/Functions:**

*   **`CommandAnalyzer`**
    *   **Signature:** `CommandAnalyzer()`
    *   **Description:** Takes a raw shell string and returns a structured representation detailing expected I/O, required permissions, and potential resource locks.
    *   **Example Usage:**
        ```python
        analyzer = CommandAnalyzer()
        analysis = analyzer.analyze("grep 'error' /var/log/sys.log | wc -l")
        print(f"Dependencies: {analysis.dependencies}")
        # Output: Dependencies: ['/var/log/sys.log']
        ```

### `.worktrees/issue-67fea13a-06-conflict-detector/mat/cli.py`

Provides the command-line interface for interacting with the AgentShell system (e.g., starting the coordinator, submitting manual tasks).

**Key Classes/Functions:**

*   **`AgentShellCLI`**
    *   **Signature:** `AgentShellCLI(coordinator_instance)`
    *   **Description:** Handles command-line parsing and routes user input to the appropriate internal system components.
    *   **Example Usage:**
        ```python
        cli = AgentShellCLI(coordinator)
        cli.run(["submit", "AgentC", "echo Hello World"])
        ```

---

## Terminal State Management (Advanced)

### `.worktrees/issue-67fea13a-06-conflict-detector/mat/analysis/command_analyzer.py` (Conceptual Extension)

*Note: While the primary focus of this module is command parsing, the TerminalStateManager functionality is conceptually integrated here or within a dedicated state module, utilizing Lamport Timestamps and Vector Clocks.*

**Key Classes/Functions (Conceptual):**

*   **`TerminalStateManager`**
    *   **Signature:** `TerminalStateManager(initial_state: str)`
    *   **Description:** Maintains the causally-consistent state of the terminal buffer across all agents using Vector Clocks for causality tracking and Operational Transformation (OT) for merging concurrent edits.
    *   **Methods:**
        *   `apply_operation(op: dict, vector_clock: dict) -> tuple[str, dict]`: Applies an incoming operation, transforms it against local changes if necessary, and returns the new state and updated vector clock.
        *   `generate_timestamp(agent_id: str) -> dict`: Generates a Lamport timestamp structure for a new event.
    *   **Example Usage:**
        ```python
        tsm = TerminalStateManager("Welcome to AgentShell")
        # Agent A sends an input operation
        new_state, new_vc = tsm.apply_operation(
            {"type": "insert", "data": "Hello"}, 
            {"AgentA": 1}
        )
        print(f"New Terminal State: {new_state}")
        ```