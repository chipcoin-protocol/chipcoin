from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
MODULE_PATH = ROOT / "scripts/mainnet-fault-session.py"
SPEC = importlib.util.spec_from_file_location("mainnet_fault_session", MODULE_PATH)
assert SPEC and SPEC.loader
session = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(session)


def test_fault_session_schema_and_identity_are_stable(tmp_path: Path) -> None:
    lock = tmp_path / "lock.json"
    created = session.create(lock, session_id="fault-fixed")
    assert created["schema_version"] == 1
    assert created["fault_session_id"] == "fault-fixed"
    assert created["current_phase"] == "PREPARING"

    updated = session.update(
        lock,
        expected_id="fault-fixed",
        changes={"current_phase": "MONITOR_STARTING", "last_completed_step": "MONITOR_START_REQUESTED"},
    )
    assert updated["fault_session_id"] == "fault-fixed"

    with pytest.raises(ValueError, match="FAULT_SESSION_ID_IMMUTABLE"):
        session.update(lock, expected_id="fault-fixed", changes={"fault_session_id": "replacement"})


def test_recovery_attempt_does_not_replace_fault_identity(tmp_path: Path) -> None:
    lock = tmp_path / "lock.json"
    session.create(lock, session_id="fault-original")
    recovered = session.begin_recovery(lock, expected_id="fault-original", attempt_id="recovery-1")
    assert recovered["fault_session_id"] == "fault-original"
    assert recovered["recovery_attempt_id"] == "recovery-1"
    assert recovered["current_phase"] == "RECOVERING"


@pytest.mark.parametrize(
    "start,target",
    [
        ("PREPARING", "MONITOR_STARTING"),
        ("MONITOR_STARTING", "MONITOR_HEALTHY"),
        ("MONITOR_HEALTHY", "CUTOVER"),
        ("CUTOVER", "PARTITION_ACTIVE"),
        ("PARTITION_ACTIVE", "FORK_ACTIVE"),
        ("FORK_ACTIVE", "RECONNECTING"),
        ("RECONNECTING", "REORG_VALIDATING"),
        ("REORG_VALIDATING", "FINAL_CONVERGENCE"),
        ("RECOVERY_REQUIRED", "RECOVERING"),
        ("RECOVERING", "FINAL_CONVERGENCE"),
    ],
)
def test_documented_transitions_are_allowed(tmp_path: Path, start: str, target: str) -> None:
    lock = tmp_path / "lock.json"
    value = session.create(lock, session_id="fault-fixed")
    value["current_phase"] = start
    session.atomic_write(lock, value)
    assert session.update(lock, expected_id="fault-fixed", changes={"current_phase": target})["current_phase"] == target


def test_invalid_transition_is_rejected(tmp_path: Path) -> None:
    lock = tmp_path / "lock.json"
    session.create(lock, session_id="fault-fixed")
    with pytest.raises(ValueError, match="invalid fault session transition"):
        session.update(lock, expected_id="fault-fixed", changes={"current_phase": "PARTITION_ACTIVE"})


@pytest.mark.parametrize(
    "checkpoint,phase",
    [
        ("BEFORE_MONITOR_START", "PREPARING"),
        ("AFTER_MONITOR_START", "MONITOR_STARTING"),
        ("AFTER_HEALTH_HANDSHAKE", "MONITOR_HEALTHY"),
        ("DURING_FAULT_NETWORK_ATTACH", "PREPARING"),
        ("AFTER_ATTACH", "PREPARING"),
        ("DURING_SHARED_DISCONNECT", "CUTOVER"),
        ("IMMEDIATELY_AFTER_CUTOVER", "CUTOVER"),
        ("BEFORE_FINAL_PARTITION_VERIFICATION", "CUTOVER"),
        ("AFTER_VERIFICATION_BEFORE_PERSIST", "CUTOVER"),
        ("AFTER_PERSIST_BEFORE_REREAD", "PARTITION_ACTIVE"),
        ("AFTER_REREAD_BEFORE_RETURN", "PARTITION_ACTIVE"),
        ("BEFORE_PARTITION_ACTIVE_MARKER", "CUTOVER"),
        ("AFTER_PARTITION_ACTIVE", "PARTITION_ACTIVE"),
        ("DURING_RECONNECT", "RECONNECTING"),
        ("DURING_MONITOR_STOP", "RECOVERING"),
        ("DURING_CLEANUP", "RECOVERING"),
        ("DURING_LOCK_RELEASE", "FINAL_CONVERGENCE"),
    ],
)
def test_every_crash_checkpoint_recovers_with_same_identity(
    tmp_path: Path, checkpoint: str, phase: str
) -> None:
    lock = tmp_path / "lock.json"
    value = session.create(lock, session_id="fault-original")
    value.update(
        {
            "current_phase": phase,
            "last_completed_step": checkpoint,
            "topology_state": "UNKNOWN_AFTER_CRASH",
        }
    )
    session.atomic_write(lock, value)

    reloaded = session.load(lock)
    assert reloaded["fault_session_id"] == "fault-original"
    recovering = session.begin_recovery(lock, expected_id="fault-original", attempt_id="recovery-new-process")
    assert recovering["fault_session_id"] == "fault-original"
    assert recovering["recovery_attempt_id"] == "recovery-new-process"
    final = session.update(
        lock,
        expected_id="fault-original",
        changes={
            "current_phase": "FINAL_CONVERGENCE",
            "recovery_state": "COMPLETE",
            "topology_state": "SHARED",
            "last_completed_step": "FINAL_CONVERGENCE_VERIFIED",
        },
    )
    assert final["fault_session_id"] == "fault-original"
