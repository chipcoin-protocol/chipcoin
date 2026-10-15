#!/usr/bin/env python3
"""Persistent state machine for the isolated mainnet fault-injection harness."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path


PHASES = (
    "BASELINE",
    "RESTART_TEST",
    "FULLSYNC_TEST",
    "PARTITION_PREPARED",
    "PARTITION_ACTIVE",
    "FORK_CONFIRMED",
    "ORPHAN_TX_CONFIRMED",
    "WINNING_BRANCH_CONFIRMED",
    "SCENARIO_A_TX_CONFIRMED",
    "SCENARIO_A_B_WINNING",
    "RECONNECTING",
    "ORPHAN_TX_REENTERED_MEMPOOL",
    "SCENARIO_A_COMPLETE",
    "SCENARIO_B_PREPARED",
    "SCENARIO_B_PARTITION_ACTIVE",
    "SCENARIO_B_FORK_CONFIRMED",
    "SCENARIO_B_TX_A2_CONFIRMED",
    "SCENARIO_B_TX_B2_CONFIRMED",
    "SCENARIO_B_B_WINNING",
    "SCENARIO_B_RECONNECTING",
    "RECOVERY_REQUIRED",
    "CONFLICTING_ORPHAN_TX_REJECTED",
    "REORG_COMPLETE",
    "FINAL_CONVERGENCE",
)

TRANSITIONS = {
    None: {"BASELINE"},
    "BASELINE": {"BASELINE", "RESTART_TEST", "SCENARIO_B_PREPARED"},
    "RESTART_TEST": {"RESTART_TEST", "FULLSYNC_TEST"},
    "FULLSYNC_TEST": {"FULLSYNC_TEST", "PARTITION_PREPARED"},
    "PARTITION_PREPARED": {"PARTITION_PREPARED", "PARTITION_ACTIVE", "RECONNECTING", "FINAL_CONVERGENCE", "RECOVERY_REQUIRED"},
    "PARTITION_ACTIVE": {"PARTITION_ACTIVE", "FORK_CONFIRMED", "RECONNECTING"},
    "FORK_CONFIRMED": {"FORK_CONFIRMED", "ORPHAN_TX_CONFIRMED", "SCENARIO_A_TX_CONFIRMED", "WINNING_BRANCH_CONFIRMED", "RECONNECTING"},
    "ORPHAN_TX_CONFIRMED": {"ORPHAN_TX_CONFIRMED", "SCENARIO_A_TX_CONFIRMED", "WINNING_BRANCH_CONFIRMED", "RECONNECTING"},
    "SCENARIO_A_TX_CONFIRMED": {"SCENARIO_A_TX_CONFIRMED", "SCENARIO_A_B_WINNING", "RECONNECTING"},
    "SCENARIO_A_B_WINNING": {"SCENARIO_A_B_WINNING", "WINNING_BRANCH_CONFIRMED", "RECONNECTING"},
    "WINNING_BRANCH_CONFIRMED": {"WINNING_BRANCH_CONFIRMED", "RECONNECTING"},
    "RECONNECTING": {"RECONNECTING", "REORG_COMPLETE", "RECOVERY_REQUIRED"},
    "REORG_COMPLETE": {"REORG_COMPLETE", "ORPHAN_TX_REENTERED_MEMPOOL", "CONFLICTING_ORPHAN_TX_REJECTED", "FINAL_CONVERGENCE"},
    "ORPHAN_TX_REENTERED_MEMPOOL": {"ORPHAN_TX_REENTERED_MEMPOOL", "SCENARIO_A_COMPLETE", "FINAL_CONVERGENCE"},
    "SCENARIO_A_COMPLETE": {"SCENARIO_A_COMPLETE", "SCENARIO_B_PREPARED", "FINAL_CONVERGENCE"},
    "SCENARIO_B_PREPARED": {"SCENARIO_B_PREPARED", "SCENARIO_B_PARTITION_ACTIVE", "RECONNECTING", "FINAL_CONVERGENCE", "BASELINE", "RECOVERY_REQUIRED"},
    "SCENARIO_B_PARTITION_ACTIVE": {"SCENARIO_B_PARTITION_ACTIVE", "SCENARIO_B_FORK_CONFIRMED", "RECONNECTING"},
    "SCENARIO_B_FORK_CONFIRMED": {"SCENARIO_B_FORK_CONFIRMED", "SCENARIO_B_TX_A2_CONFIRMED", "RECONNECTING"},
    "SCENARIO_B_TX_A2_CONFIRMED": {"SCENARIO_B_TX_A2_CONFIRMED", "SCENARIO_B_TX_B2_CONFIRMED", "RECONNECTING"},
    "SCENARIO_B_TX_B2_CONFIRMED": {"SCENARIO_B_TX_B2_CONFIRMED", "SCENARIO_B_B_WINNING", "RECONNECTING"},
    "SCENARIO_B_B_WINNING": {"SCENARIO_B_B_WINNING", "SCENARIO_B_RECONNECTING", "RECONNECTING"},
    "SCENARIO_B_RECONNECTING": {"SCENARIO_B_RECONNECTING", "REORG_COMPLETE", "RECOVERY_REQUIRED"},
    "CONFLICTING_ORPHAN_TX_REJECTED": {"CONFLICTING_ORPHAN_TX_REJECTED", "FINAL_CONVERGENCE"},
    "FINAL_CONVERGENCE": {"FINAL_CONVERGENCE", "BASELINE", "PARTITION_PREPARED", "SCENARIO_B_PREPARED", "SCENARIO_B_PARTITION_ACTIVE", "RECOVERY_REQUIRED"},
    "RECOVERY_REQUIRED": {"RECOVERY_REQUIRED", "RECONNECTING", "FINAL_CONVERGENCE"},
}


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"phase": None, "history": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("phase") not in {None, *PHASES} or not isinstance(value.get("history"), list):
        raise ValueError("invalid fault harness state file")
    return value


def transition(path: Path, phase: str, evidence: str) -> dict:
    state = load_state(path)
    current = state["phase"]
    recovery_transition = phase == "RECONNECTING" and current not in {None, "FINAL_CONVERGENCE"}
    if phase not in TRANSITIONS[current] and not recovery_transition:
        raise ValueError(f"invalid phase transition: {current or 'NONE'} -> {phase}")
    event = {
        "from": current,
        "to": phase,
        "at": datetime.now(timezone.utc).isoformat(),
        "evidence": evidence,
    }
    state = {"phase": phase, "history": [*state["history"], event]}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(state, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", required=True, type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("show")
    update = subparsers.add_parser("transition")
    update.add_argument("phase", choices=PHASES)
    update.add_argument("--evidence", required=True)
    args = parser.parse_args()
    if args.command == "show":
        state = load_state(args.state_file)
    else:
        state = transition(args.state_file, args.phase, args.evidence)
    print(json.dumps(state, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
