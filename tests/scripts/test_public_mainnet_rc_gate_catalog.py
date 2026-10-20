from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("gate_catalog", ROOT / "scripts/build-public-mainnet-rc-gate-catalog.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_catalog_covers_all_canonical_gates() -> None:
    matrix = json.loads((ROOT / "public-mainnet-rc-revalidation.json").read_text())
    gates = [MODULE.entry(gate) for gate in matrix["requirements"]]
    assert len(gates) == 98
    assert {gate["id"] for gate in gates} == {gate["id"] for gate in matrix["requirements"]}
    assert all(gate["required_evidence_refs"] for gate in gates)
    assert all(gate["pass_criteria"] and gate["fail_criteria"] for gate in gates)
    genesis_gate = next(gate for gate in gates if gate["id"] == "CONS-CFG-001")
    assert genesis_gate["execution_mode"] == "BLOCKED_SOURCE_FREEZE"
    assert "frozen source revision" in genesis_gate["blocker"]


def test_automated_entries_have_commands_and_manual_entries_do_not_auto_pass() -> None:
    matrix = json.loads((ROOT / "public-mainnet-rc-revalidation.json").read_text())
    gates = [MODULE.entry(gate) for gate in matrix["requirements"]]
    automated = [gate for gate in gates if gate["execution_mode"] == "AUTOMATED_PRE_FREEZE"]
    manual = [gate for gate in gates if gate["execution_mode"] == "MANUAL_ATTESTATION"]
    assert automated and all(gate["command"] for gate in automated)
    assert len(automated) == 20
    assert all(gate["automated_contract"] and gate["pass_criteria"] for gate in automated)
    assert all(gate["automated_contract"][0]["check_id"] in gate["pass_criteria"][2] for gate in automated)
    assert manual and all(gate["manual_attestation"]["runner_auto_pass"] is False for gate in manual)
    manifest = next(gate for gate in automated if gate["id"] == "BW-SEC-002")
    assert (ROOT / manifest["cwd"] / manifest["command"][-1]).is_file()
    dependency_risk = next(gate for gate in manual if gate["id"] == "SEC-DEP-002")
    assert dependency_risk["blocker"].startswith("human review")


def test_runtime_gates_cannot_consume_test_only_evidence() -> None:
    matrix = json.loads((ROOT / "public-mainnet-rc-revalidation.json").read_text())
    gates = [MODULE.entry(gate) for gate in matrix["requirements"]]
    runtime = [gate for gate in gates if gate["revalidation_class"] == "ISOLATED_CHAIN_RUNTIME"]
    assert len(runtime) == 63
    assert all(gate["prerequisites"]["isolated_chain"] for gate in runtime)
    assert all(gate["evidence_schema"]["test_only_evidence_forbidden"] for gate in runtime)
