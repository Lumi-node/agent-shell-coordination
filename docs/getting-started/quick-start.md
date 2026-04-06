# 🚀 AgentShell Quick Start Guide

Welcome to AgentShell, a distributed multi-agent terminal coordination system designed to allow autonomous AI agents to collaborate on shared computational environments. AgentShell leverages advanced concepts like Conflict-Free Replicated Data Types (CRDTs) and distributed consensus to ensure robust, conflict-free execution of shell commands across multiple agents.

This guide will walk you through setting up and using the core components, focusing specifically on the **TerminalStateManager**.

## 🎯 Goal Overview

The primary goal of AgentShell is to build a system where multiple AI agents can interact with a single, shared terminal session concurrently without data corruption or race conditions. We achieve this by implementing the `TerminalStateManager` using **Vector Clocks** and **Operational Transformation (OT)** to guarantee causally-consistent terminal buffer states. Lamport timestamps are used to establish a total ordering for terminal operations.

## 📦 Installation & Setup

Assuming you have the necessary environment set up, AgentShell is packaged as `agent_shell_coordination`.

**Prerequisites:** Python 3.8+

**Installation (Conceptual):**
```bash
pip install agent_shell_coordination
```

**Key Modules:**
The core logic resides within the `mat` directory:
*   `mat.core.agent_registry`: Manages registered agents.
*   `mat.core.file_lock_manager`: Handles resource locking.
*   `mat.coordination.conflict_detector`: Detects potential state conflicts.
*   `mat.coordinator.Coordinator`: Orchestrates agent interactions.
*   **`mat.terminal_state_manager` (Conceptual Implementation Focus):** Manages the terminal buffer state using Vector Clocks and OT.

---

## 🧠 Deep Dive: TerminalStateManager Implementation

The `TerminalStateManager` is the heart of the shared terminal experience. It ensures that when Agent A sends a command, and Agent B simultaneously sends an output, the resulting terminal buffer state is consistent and reflects the causal order of events.

**Mechanism:**
1.  **Vector Clocks:** Each state update carries a vector clock, tracking the causality across all participating agents.
2.  **Lamport Timestamps:** Used alongside vector clocks to provide a total ordering for operations that are concurrent (i.e., not causally related).
3.  **Operational Transformation (OT):** When two agents attempt to apply operations that conflict (e.g., both try to insert text at the same index), OT transforms one operation against the other to ensure both operations are applied correctly to the resulting state without losing information.

*(Note: Since the specific implementation of `TerminalStateManager` was not provided in the module list, the examples below demonstrate how you would interact with the *interface* of such a manager, assuming it resides in a logical location like `mat.terminal_state_manager`.)*

---

## 🛠️ Usage Examples

Here are 2-3 examples demonstrating how agents would interact with the coordination system, specifically focusing on state management.

### Example 1: Agent Submitting a Command (State Mutation)

An agent decides to execute a command (`ls -l`) and submits the operation to the coordinator, which passes it to the `TerminalStateManager` for validation and application.

```python
from agent_shell_coordination.mat.coordinator import Coordinator
from agent_shell_coordination.mat.terminal_state_manager import TerminalStateManager
from typing import Dict

# Setup (In a real system, this would be initialized across the network)
coordinator = Coordinator()
state_manager: TerminalStateManager = TerminalStateManager()

# Agent A wants to execute 'ls -l'
command_operation = {
    "type": "COMMAND_EXECUTE",
    "command": "ls -l",
    "agent_id": "Agent_Alpha",
    "lamport_ts": 101,
    "vector_clock": {"Agent_Alpha": 5, "Agent_Beta": 2}
}

print("--- Submitting Command Operation ---")
# The state manager applies the operation, transforming it if necessary
new_state, success = state_manager.apply_operation(command_operation)

if success:
    print(f"✅ Command applied successfully. New state reflects execution.")
    print(f"Current Terminal Buffer Snippet: {new_state['buffer'][:50]}...")
else:
    print("❌ Operation failed due to conflict resolution.")
```

### Example 2: Agent Receiving Remote Output (Causal Update)

Agent Beta receives output from the shell execution initiated by Agent Alpha. This output must be merged into the local state while respecting causality.

```python
from agent_shell_coordination.mat.terminal_state_manager import TerminalStateManager

# Assume state_manager is already initialized and holds the current state
# (e.g., from Example 1)

# Agent Beta receives output from the remote shell process
output_operation = {
    "type": "OUTPUT_APPEND",
    "content": "total 8\n-rw-r--r-- 1 user user 1024 Jan 1 10:00 file1.txt\n",
    "agent_id": "Shell_Process",
    "lamport_ts": 102,
    # This vector clock indicates the state it is based upon
    "vector_clock": {"Agent_Alpha": 5, "Agent_Beta": 2} 
}

print("\n--- Merging Remote Output Operation ---")
# The state manager uses OT to merge this output into the current buffer
merged_state, success = state_manager.merge_remote_operation(output_operation)

if success:
    print("✅ Remote output merged successfully, maintaining causal order.")
    print(f"Total buffer length after merge: {len(merged_state['buffer'])}")
else:
    print("❌ Failed to merge remote operation; state divergence detected.")
```

### Example 3: Conflict Detection and Resolution (Simulated)

This example simulates a scenario where two agents try to modify the same line simultaneously, forcing the conflict detector and OT mechanism to resolve the ambiguity.

```python
from agent_shell_coordination.mat.coordination.conflict_detector import ConflictDetector
from agent_shell_coordination.mat.terminal_state_manager import TerminalStateManager

# Setup
state_manager: TerminalStateManager = TerminalStateManager()
detector = ConflictDetector()

# Operation 1: Agent Alpha tries to overwrite line 5
op_alpha = {"type": "OVERWRITE", "line_index": 5, "new_content": "Alpha's Edit", "agent_id": "Agent_Alpha"}

# Operation 2: Agent Beta tries to append to line 5 concurrently
op_beta = {"type": "APPEND", "line_index": 5, "append_text": " | Beta's Note", "agent_id": "Agent_Beta"}

print("\n---