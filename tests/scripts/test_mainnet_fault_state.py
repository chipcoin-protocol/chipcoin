from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
MODULE_PATH = ROOT / "scripts/mainnet-fault-state.py"


def load_module():
    spec = importlib.util.spec_from_file_location("mainnet_fault_state", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_state_machine_persists_valid_transitions(tmp_path: Path) -> None:
    module = load_module()
    state_path = tmp_path / "state.json"

    baseline = module.transition(state_path, "BASELINE", "baseline.json")
    restarted = module.transition(state_path, "RESTART_TEST", "restart.json")
    fullsync = module.transition(state_path, "FULLSYNC_TEST", "fullsync.json")

    assert baseline["phase"] == "BASELINE"
    assert restarted["phase"] == "RESTART_TEST"
    assert fullsync["phase"] == "FULLSYNC_TEST"
    assert module.load_state(state_path) == fullsync
    assert [event["to"] for event in fullsync["history"]] == ["BASELINE", "RESTART_TEST", "FULLSYNC_TEST"]


def test_state_machine_rejects_ambiguous_phase_jump(tmp_path: Path) -> None:
    module = load_module()
    state_path = tmp_path / "state.json"
    module.transition(state_path, "BASELINE", "baseline.json")

    with pytest.raises(ValueError, match="BASELINE -> PARTITION_ACTIVE"):
        module.transition(state_path, "PARTITION_ACTIVE", "invalid")


def test_clean_baseline_can_prepare_scenario_b(tmp_path: Path) -> None:
    module = load_module()
    state_path = tmp_path / "state.json"
    module.transition(state_path, "BASELINE", "baseline.json")

    prepared = module.transition(state_path, "SCENARIO_B_PREPARED", "prepared.json")

    assert prepared["phase"] == "SCENARIO_B_PREPARED"

    cancelled = module.transition(state_path, "BASELINE", "cancelled.json")
    assert cancelled["phase"] == "BASELINE"


def test_final_convergence_can_prepare_reward_reorg(tmp_path: Path) -> None:
    module = load_module()
    state_path = tmp_path / "state.json"
    state_path.write_text(__import__("json").dumps({"phase": "FINAL_CONVERGENCE", "history": []}))

    for phase in (
        "PARTITION_PREPARED",
        "PARTITION_ACTIVE",
        "FORK_CONFIRMED",
        "WINNING_BRANCH_CONFIRMED",
        "RECONNECTING",
        "REORG_COMPLETE",
        "FINAL_CONVERGENCE",
    ):
        module.transition(state_path, phase, phase)

    assert module.load_state(state_path)["phase"] == "FINAL_CONVERGENCE"


def test_reward_reorg_prepare_can_roll_back_before_cutover(tmp_path: Path) -> None:
    module = load_module()
    state_path = tmp_path / "state.json"
    state_path.write_text(__import__("json").dumps({"phase": "FINAL_CONVERGENCE", "history": []}))
    module.transition(state_path, "PARTITION_PREPARED", "prepared")

    assert module.transition(state_path, "FINAL_CONVERGENCE", "rollback")["phase"] == "FINAL_CONVERGENCE"


def test_reconnect_is_allowed_as_partition_recovery(tmp_path: Path) -> None:
    module = load_module()
    state_path = tmp_path / "state.json"
    for phase in ("BASELINE", "RESTART_TEST", "FULLSYNC_TEST", "PARTITION_PREPARED", "PARTITION_ACTIVE"):
        module.transition(state_path, phase, phase.lower())

    recovered = module.transition(state_path, "RECONNECTING", "network restored")
    assert recovered["phase"] == "RECONNECTING"


def test_scenario_b_requires_ordered_transaction_evidence(tmp_path: Path) -> None:
    module = load_module()
    state_path = tmp_path / "state.json"
    phases = (
        "BASELINE", "RESTART_TEST", "FULLSYNC_TEST", "PARTITION_PREPARED",
        "PARTITION_ACTIVE", "FORK_CONFIRMED", "SCENARIO_A_TX_CONFIRMED",
        "SCENARIO_A_B_WINNING", "WINNING_BRANCH_CONFIRMED", "RECONNECTING", "REORG_COMPLETE",
        "ORPHAN_TX_REENTERED_MEMPOOL", "SCENARIO_A_COMPLETE",
        "SCENARIO_B_PREPARED", "SCENARIO_B_PARTITION_ACTIVE",
        "SCENARIO_B_FORK_CONFIRMED", "SCENARIO_B_TX_A2_CONFIRMED", "SCENARIO_B_TX_B2_CONFIRMED",
        "SCENARIO_B_B_WINNING", "SCENARIO_B_RECONNECTING",
        "REORG_COMPLETE", "CONFLICTING_ORPHAN_TX_REJECTED", "FINAL_CONVERGENCE",
    )
    for phase in phases:
        module.transition(state_path, phase, phase)
    assert module.load_state(state_path)["phase"] == "FINAL_CONVERGENCE"


def test_recovery_transition_is_available_from_destructive_phases(tmp_path: Path) -> None:
    module = load_module()
    for target in ("PARTITION_ACTIVE", "FORK_CONFIRMED", "SCENARIO_B_TX_A2_CONFIRMED", "REORG_COMPLETE"):
        path = tmp_path / f"{target}.json"
        state = {"phase": target, "history": []}
        path.write_text(__import__("json").dumps(state))
        assert module.transition(path, "RECONNECTING", "recovery")["phase"] == "RECONNECTING"
