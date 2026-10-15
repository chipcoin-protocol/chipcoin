#!/usr/bin/env python3
"""Atomic, immutable-identity state for mainnet fault-harness sessions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid


SCHEMA_VERSION = 1
STATES = {
    "PREPARING",
    "MONITOR_STARTING",
    "MONITOR_HEALTHY",
    "CUTOVER",
    "PARTITION_ACTIVE",
    "FORK_ACTIVE",
    "RECONNECTING",
    "REORG_VALIDATING",
    "RECOVERING",
    "FINAL_CONVERGENCE",
    "RECOVERY_REQUIRED",
}
TRANSITIONS = {
    "PREPARING": {"PREPARING", "MONITOR_STARTING", "RECOVERING", "RECOVERY_REQUIRED"},
    "MONITOR_STARTING": {"MONITOR_HEALTHY", "RECOVERING", "RECOVERY_REQUIRED"},
    "MONITOR_HEALTHY": {"CUTOVER", "RECOVERING", "RECOVERY_REQUIRED"},
    "CUTOVER": {"CUTOVER", "PARTITION_ACTIVE", "RECOVERING", "RECOVERY_REQUIRED"},
    "PARTITION_ACTIVE": {"FORK_ACTIVE", "RECONNECTING", "RECOVERING", "RECOVERY_REQUIRED"},
    "FORK_ACTIVE": {"FORK_ACTIVE", "RECONNECTING", "RECOVERING", "RECOVERY_REQUIRED"},
    "RECONNECTING": {"REORG_VALIDATING", "RECOVERING", "RECOVERY_REQUIRED"},
    "REORG_VALIDATING": {"FINAL_CONVERGENCE", "RECOVERING", "RECOVERY_REQUIRED"},
    "RECOVERING": {"RECOVERING", "FINAL_CONVERGENCE", "RECOVERY_REQUIRED"},
    "RECOVERY_REQUIRED": {"RECOVERING", "RECOVERY_REQUIRED"},
    "FINAL_CONVERGENCE": {"FINAL_CONVERGENCE", "RECOVERING"},
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "fault_session_id",
        "created_at",
        "current_phase",
        "monitor_unit",
        "monitor_main_pid",
        "monitor_session_id",
        "recovery_state",
        "recovery_attempt_id",
        "topology_state",
        "last_completed_step",
    }
    if value.get("schema_version") != SCHEMA_VERSION or not required.issubset(value):
        raise ValueError("invalid fault session lock schema")
    if value["current_phase"] not in STATES:
        raise ValueError("invalid fault session phase")
    return value


def atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def create(path: Path, *, session_id: str | None = None) -> dict:
    if path.exists():
        raise FileExistsError("fault session already exists")
    identity = session_id or f"fault-{uuid.uuid4()}"
    value = {
        "schema_version": SCHEMA_VERSION,
        "fault_session_id": identity,
        "created_at": now(),
        "current_phase": "PREPARING",
        "monitor_unit": None,
        "monitor_main_pid": None,
        "monitor_session_id": None,
        "recovery_state": "NONE",
        "recovery_attempt_id": None,
        "topology_state": "SHARED",
        "last_completed_step": "SESSION_CREATED",
        "updated_at": now(),
    }
    atomic_write(path, value)
    return value


def update(path: Path, *, expected_id: str, changes: dict) -> dict:
    value = load(path)
    identity = value["fault_session_id"]
    if identity != expected_id:
        raise ValueError(f"fault session identity mismatch: expected={expected_id} actual={identity}")
    if "fault_session_id" in changes and changes["fault_session_id"] != identity:
        raise ValueError("FAULT_SESSION_ID_IMMUTABLE")
    target = changes.get("current_phase", value["current_phase"])
    if target not in STATES:
        raise ValueError(f"invalid target phase: {target}")
    if target != value["current_phase"] and target not in TRANSITIONS[value["current_phase"]]:
        raise ValueError(f"invalid fault session transition: {value['current_phase']} -> {target}")
    value.update(changes)
    if value["fault_session_id"] != identity:
        raise ValueError("FAULT_SESSION_ID_IMMUTABLE")
    value["updated_at"] = now()
    atomic_write(path, value)
    return value


def begin_recovery(path: Path, *, expected_id: str, attempt_id: str | None = None) -> dict:
    return update(
        path,
        expected_id=expected_id,
        changes={
            "current_phase": "RECOVERING",
            "recovery_state": "IN_PROGRESS",
            "recovery_attempt_id": attempt_id or f"recovery-{uuid.uuid4()}",
            "last_completed_step": "RECOVERY_STARTED",
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock-file", required=True, type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--session-id")
    subparsers.add_parser("show")
    assert_parser = subparsers.add_parser("assert-id")
    assert_parser.add_argument("--session-id", required=True)
    update_parser = subparsers.add_parser("update")
    update_parser.add_argument("--session-id", required=True)
    update_parser.add_argument("--changes-json", required=True)
    recovery_parser = subparsers.add_parser("begin-recovery")
    recovery_parser.add_argument("--session-id", required=True)
    recovery_parser.add_argument("--attempt-id")
    args = parser.parse_args()

    if args.command == "create":
        value = create(args.lock_file, session_id=args.session_id)
    elif args.command == "show":
        value = load(args.lock_file)
    elif args.command == "assert-id":
        value = load(args.lock_file)
        if value["fault_session_id"] != args.session_id:
            raise SystemExit("FAULT_SESSION_ID_IMMUTABLE assertion failed")
    elif args.command == "update":
        changes = json.loads(args.changes_json)
        if not isinstance(changes, dict):
            raise SystemExit("changes-json must contain an object")
        value = update(args.lock_file, expected_id=args.session_id, changes=changes)
    else:
        value = begin_recovery(args.lock_file, expected_id=args.session_id, attempt_id=args.attempt_id)
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
