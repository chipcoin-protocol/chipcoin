#!/usr/bin/env python3
"""Build the complete execution/evidence catalog for the 98 RC gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PYTEST = ".venv/bin/pytest"

SOURCE_COMMANDS: dict[str, list[str]] = {
    **{gate: [PYTEST, "-q", "tests/consensus/test_mainnet_profile.py", "tests/config/test_network_config.py"]
       for gate in ("CONS-CFG-002", "CONS-CFG-003", "CONS-CFG-004", "CONS-CFG-005", "CONS-CFG-006",
                    "CONS-CFG-007", "CONS-CFG-008", "PQ-CFG-001", "PQ-CFG-002", "PQ-CFG-003", "REWARD-CFG-001")},
    "SNAP-CFG-001": [PYTEST, "-q", "tests/node/test_snapshots.py"],
    "SNAP-CFG-002": [PYTEST, "-q", "tests/node/test_snapshots.py"],
    "BW-BUILD-001": ["npm", "run", "build:chrome"],
    "BW-BUILD-002": ["npm", "run", "build:firefox"],
    "BW-NET-001": ["npm", "test", "--", "tests/unit/cross_network_isolation.test.ts", "tests/unit/network_support.test.ts"],
    "BW-NET-002": ["npm", "test", "--", "tests/unit/network_support.test.ts"],
    "BW-SEC-002": ["npm", "test", "--", "tests/unit/provider_manifest.test.ts"],
    "SEC-CONF-001": [PYTEST, "-q", "tests/config/test_network_config.py", "tests/consensus/test_network_identity.py"],
    "SEC-DEP-001": [".venv/bin/python", "scripts/audit-public-mainnet-npm-production.py"],
}

SOURCE_CWD = {
    gate: "apps/browser-wallet"
    for gate in ("BW-BUILD-001", "BW-BUILD-002", "BW-NET-001", "BW-NET-002", "BW-SEC-002")
}

MANUAL_SOURCE = {
    "SEC-DEP-002", "SEC-SECRET-001", "SEC-SECRET-002", "RUNBOOK-001", "RUNBOOK-002", "RUNBOOK-003",
    "RUNBOOK-004", "RUNBOOK-005",
}

PHASE_BY_PREFIX = {
    "CONS-RUN-": "canonical-chain-consensus",
    "PQ-RUN-": "canonical-chain-pq",
    "PQ-OPS-": "canonical-chain-wallet-operations",
    "PQ-NEG-": "canonical-chain-negative",
    "PQ-BW-": "canonical-chain-browser",
    "TX-RUN-": "canonical-chain-transactions",
    "TX-EXP-": "canonical-chain-explorer",
    "FAULT-": "canonical-chain-fault-recovery",
    "SNAP-NEG-": "canonical-chain-snapshot",
    "SNAP-RUN-": "canonical-chain-snapshot",
    "SNAP-OPS-": "canonical-chain-snapshot",
    "REWARD-RUN-": "canonical-chain-rewards",
    "FINAL-RUN-": "canonical-chain-final-convergence",
    "BW-OPS-": "canonical-chain-browser-operations",
    "EXP-INT-": "canonical-chain-explorer",
}


def phase(gate_id: str) -> str:
    return next((value for prefix, value in PHASE_BY_PREFIX.items() if gate_id.startswith(prefix)), "release-finalization")


def entry(gate: dict[str, Any]) -> dict[str, Any]:
    gate_id = gate["id"]
    gate_class = gate["revalidation_class"]
    if gate_id == "CONS-CFG-001":
        mode = "BLOCKED_FINAL_GENESIS"
        command = None
        cwd = "."
        blocker = "canonical genesis bytes/hash are intentionally pending"
    elif gate_id == "BW-SEC-001":
        mode = "BLOCKED_RUNTIME_DEPENDENCIES"
        command = None
        cwd = "apps/browser-wallet"
        blocker = "depends on PQ-BW-001 and PQ-BW-002 runtime evidence"
    elif gate_id in MANUAL_SOURCE:
        mode = "MANUAL_ATTESTATION"
        command = None
        cwd = "."
        blocker = "human review and signed attestation required; runner must not auto-PASS"
    elif gate_id in SOURCE_COMMANDS:
        mode = "AUTOMATED_PRE_FREEZE"
        command = SOURCE_COMMANDS[gate_id]
        cwd = SOURCE_CWD.get(gate_id, ".")
        blocker = None
    elif gate_class == "RELEASE_FINALIZATION":
        mode = "BLOCKED_SOURCE_FREEZE"
        command = None
        cwd = "."
        blocker = "requires clean frozen commit, final genesis, and immutable release artifacts"
    else:
        mode = "BLOCKED_FINAL_CHAIN"
        command = None
        cwd = "."
        blocker = "requires the isolated definitive-mainnet chain and reviewed production orchestrator"

    needs_explorer = gate["category"] == "explorer_integration" or gate_id in {"SEC-CONF-001", "SEC-DEP-001", "SEC-DEP-002"}
    return {
        "id": gate_id,
        "description": gate["description"],
        "category": gate["category"],
        "revalidation_class": gate_class,
        "dependencies": gate["dependencies"],
        "required_evidence_refs": gate["required_evidence"],
        "execution_mode": mode,
        "phase": phase(gate_id),
        "command": command,
        "cwd": cwd,
        "prerequisites": {
            "final_genesis": gate_class != "SOURCE_REVALIDATION" or gate_id == "CONS-CFG-001",
            "isolated_chain": gate_class == "ISOLATED_CHAIN_RUNTIME",
            "explorer_repository": needs_explorer,
            "public_infrastructure": False,
            "clean_frozen_source": gate_class == "RELEASE_FINALIZATION",
        },
        "evidence_schema": {
            "required_fields": [
                "gate_id", "network", "chain_id", "genesis_hash", "source_commit", "source_tree_sha256",
                "environment", "command", "exit_code", "started_at", "finished_at", "checks", "artifacts",
            ],
            "artifact_fields": ["path", "sha256"],
            "identity_must_match_run": True,
            "test_only_evidence_forbidden": True,
        },
        "pass_criteria": [
            "all dependencies have verified PASS evidence",
            "command exits zero when an automated command exists",
            "all canonical evidence references are present and hash-verified",
            "all gate-specific checks in the evidence are true",
            "network, chain, genesis, source commit and tree identity match this run",
        ],
        "fail_criteria": [
            "the tested property is demonstrably false or command exits nonzero",
            "identity mismatch or TEST-ONLY evidence can never produce PASS",
            "missing/incomplete evidence produces BLOCKED, not PASS",
        ],
        "manual_attestation": {
            "required": mode == "MANUAL_ATTESTATION",
            "runner_auto_pass": False,
            "required_fields": ["gate_id", "reviewer", "role", "signed_at", "statement", "statement_sha256", "evidence_sha256", "outcome"],
        },
        "blocker": blocker,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=Path("public-mainnet-rc-revalidation.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/releases/public-mainnet-rc1-gate-catalog.json"))
    args = parser.parse_args()
    matrix = json.loads(args.matrix.read_text(encoding="utf-8"))
    gates = [entry(gate) for gate in matrix["requirements"]]
    if len(gates) != 98 or len({gate["id"] for gate in gates}) != 98:
        raise SystemExit("catalog must contain exactly 98 unique gates")
    payload = {
        "schema_version": 1,
        "matrix_sha256_required_at_execution": True,
        "automatic_pass_requires_runner_evidence": True,
        "manual_attestations_never_auto_pass": True,
        "counts": {
            mode: sum(gate["execution_mode"] == mode for gate in gates)
            for mode in sorted({gate["execution_mode"] for gate in gates})
        },
        "gates": gates,
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
