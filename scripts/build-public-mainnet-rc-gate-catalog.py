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
       for gate in ("CONS-CFG-003", "CONS-CFG-004", "CONS-CFG-005", "CONS-CFG-006",
                    "CONS-CFG-007", "CONS-CFG-008", "PQ-CFG-001", "PQ-CFG-002", "REWARD-CFG-001")},
    "CONS-CFG-002": [PYTEST, "-q", "tests/consensus/test_mainnet_profile.py", "tests/config/test_network_config.py", "tests/consensus/test_network_identity.py"],
    "PQ-CFG-003": [PYTEST, "-q", "tests/consensus/test_mainnet_profile.py", "tests/config/test_network_config.py", "tests/node/test_mainnet_pq_end_to_end.py"],
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
SOURCE_COMMANDS["PQ-CFG-002"] = [PYTEST, "-q", "tests/consensus/test_mainnet_profile.py", "tests/config/test_network_config.py", "tests/node/test_mainnet_pq_end_to_end.py"]

EXTERNAL_EVIDENCE: dict[str, list[str]] = {
    "CONS-CFG-002": ["E-PREFLIGHT"],
    "PQ-CFG-001": ["E-PREFLIGHT"],
    "PQ-CFG-002": ["E-PREFLIGHT"],
    "PQ-CFG-003": ["E-PREFLIGHT", "E-MATURITY-PQ"],
    "SEC-CONF-001": ["E-PREFLIGHT", "E-BROWSER", "E-EXPLORER"],
    "SEC-DEP-001": ["E-EXPLORER"],
}

SOURCE_CWD = {
    gate: "apps/browser-wallet"
    for gate in ("BW-BUILD-001", "BW-BUILD-002", "BW-NET-001", "BW-NET-002", "BW-SEC-002")
}

MANUAL_SOURCE = {
    "SEC-DEP-002", "SEC-SECRET-001", "SEC-SECRET-002", "RUNBOOK-001", "RUNBOOK-002", "RUNBOOK-003",
    "RUNBOOK-004", "RUNBOOK-005",
}

AUTOMATED_CHECKS: dict[str, list[dict[str, str]]] = {
    "CONS-CFG-002": [{"id": "mainnet_identity_distinct", "assertion": "test_public_mainnet_identity_is_distinct_and_deterministic passes."}],
    "CONS-CFG-003": [{"id": "target_spacing_600", "assertion": "test_mainnet_consensus_profile_is_frozen asserts 600-second target and no legacy schedule."}],
    "CONS-CFG-004": [{"id": "genesis_bits_1e0537e7", "assertion": "test_mainnet_consensus_profile_is_frozen asserts genesis_bits=0x1e0537e7."}],
    "CONS-CFG-005": [{"id": "supply_cap_11m", "assertion": "test_mainnet_consensus_profile_is_frozen and test_mainnet_emission_ends_at_the_frozen_hard_cap assert the 11M cap."}],
    "CONS-CFG-006": [{"id": "initial_subsidy_50_chc", "assertion": "test_mainnet_consensus_profile_is_frozen asserts initial miner subsidy is 50 CHC."}],
    "CONS-CFG-007": [{"id": "halving_111000_and_cap", "assertion": "profile and hard-cap tests assert 111000 interval and exact terminal emission."}],
    "CONS-CFG-008": [{"id": "coinbase_maturity_100", "assertion": "test_mainnet_consensus_profile_is_frozen asserts maturity is 100 blocks."}],
    "PQ-CFG-001": [{"id": "pq_active_from_genesis", "assertion": "mainnet profile tests assert PQ activation height zero and standard PQ transactions required."}],
    "PQ-CFG-002": [{"id": "chcq_required", "assertion": "mainnet profile and network config tests assert canonical CHCQ output policy."}],
    "PQ-CFG-003": [{"id": "mldsa_scheme_10", "assertion": "profile tests assert ML-DSA-44 signature scheme id 10."}],
    "REWARD-CFG-001": [{"id": "reward_activation_and_warmup", "assertion": "profile tests assert reward activation 1000, warmup 2 epochs, epoch length 100 and maximum 25 nodes."}],
    "SNAP-CFG-001": [{"id": "snapshot_metadata_same_export_state", "assertion": "snapshot export metadata, anchor and UTXO state roundtrip from one consistent export."}],
    "SNAP-CFG-002": [{"id": "snapshot_signature_trust_enforced", "assertion": "tests cover signed acceptance and rejection of unsigned, invalid, unknown-signer and tampered snapshots."}],
    "BW-BUILD-001": [{"id": "chrome_locked_production_build", "assertion": "Chrome build succeeds using the checked-in lockfile."}],
    "BW-BUILD-002": [{"id": "firefox_locked_production_build", "assertion": "Firefox build succeeds using the checked-in lockfile."}],
    "BW-NET-001": [{"id": "cross_network_identity_rejected", "assertion": "cross_network_isolation and network_support test files pass."}],
    "BW-NET-002": [{"id": "no_hardcoded_testnet_api", "assertion": "network_support test file passes the mainnet endpoint selection assertions."}],
    "BW-SEC-002": [{"id": "browser_permissions_audited", "assertion": "provider_manifest tests pass for Chrome and Firefox manifests."}],
    "SEC-CONF-001": [{"id": "node_identity_separation", "assertion": "network config and identity tests pass the chain/network isolation assertions."}],
    "SEC-DEP-001": [{"id": "production_dependencies_reviewed", "assertion": "production dependency audit exits zero with no unresolved production-reachable blocker."}],
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
        mode = "BLOCKED_SOURCE_FREEZE"
        command = None
        cwd = "."
        blocker = "requires the approved canonical genesis in a clean frozen source revision"
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
        "command_evidence_refs": [ref for ref in gate["required_evidence"] if ref not in EXTERNAL_EVIDENCE.get(gate_id, [])],
        "execution_mode": mode,
        "phase": phase(gate_id),
        "command": command,
        "cwd": cwd,
        "automated_contract": ([{"check_id": check["id"], "assertion": check["assertion"]}
                                for check in AUTOMATED_CHECKS[gate_id]] if gate_id in AUTOMATED_CHECKS else []),
        "external_evidence_refs": EXTERNAL_EVIDENCE.get(gate_id, []),
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
            *(f"automated contract check {item['check_id']} is true: {item['assertion']}"
              for item in ({"check_id": check["id"], "assertion": check["assertion"]}
                           for check in AUTOMATED_CHECKS.get(gate_id, []))),
            "all canonical evidence references are present and hash-verified",
            "all gate-specific checks in the evidence are true",
            "network, chain, genesis, source commit and tree identity match this run",
        ],
        "fail_criteria": [
            "the tested property is demonstrably false or command exits nonzero",
            "any gate-specific automated contract check is false or missing",
            "identity mismatch or TEST-ONLY evidence can never produce PASS",
            "missing/incomplete evidence produces BLOCKED, not PASS",
        ],
        "manual_attestation": {
            "required": mode == "MANUAL_ATTESTATION",
            "runner_auto_pass": False,
            "signature_algorithm": "Ed25519",
            "signature_payload": "canonical-json-of-attestation-without-signature",
            "required_fields": ["schema_version", "gate_id", "signer_key_id", "signer_identity", "role", "signed_at",
                                "source_commit", "source_tree_sha256", "release_tag", "genesis_hash", "evidence", "outcome", "statement", "signature"],
        },
        "blocker": blocker,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=Path("public-mainnet-rc-revalidation.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/releases/public-mainnet-rc4-gate-catalog.json"))
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
        "manual_attestation_signature": "Ed25519",
        "manual_attestation_trust_store": "docs/releases/rc-gate-trust-store.json",
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
