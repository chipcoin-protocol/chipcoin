#!/usr/bin/env python3
"""Build the review catalog for the seven public-launch gates."""

import argparse
import hashlib
import json
from pathlib import Path


PROCEDURES = {
    "EXP-PUB-001": ("Probe the deployed public Explorer over its production HTTPS origin and verify live monitoring.",
                    ["HTTP TLS chain is valid", "API reports exact mainnet chain_id, genesis_hash and network_magic_hex", "external monitor alert path is healthy"],
                    ["TLS probe output", "API identity response", "monitor status and alert test"]),
    "PUB-001": ("Resolve public DNS and probe each announced seed/bootstrap endpoint without connecting networks.",
                 ["DNS targets match approved inventory", "P2P endpoints are distinct from testnet", "handshake reports canonical mainnet identity"],
                 ["DNS answers", "port/firewall inventory", "P2P handshake transcript"]),
    "PUB-002": ("Run external TLS, firewall, API exposure and rate-limit probes against the approved public endpoints.",
                 ["TLS verification succeeds", "only approved ports are reachable", "rate limits reject excess requests", "development servers are unreachable"],
                 ["TLS scan", "port scan", "rate-limit test report", "dev-server exposure scan"]),
    "PUB-003": ("Exercise monitoring alerts and perform a documented backup restore drill.",
                 ["critical alerts reach the on-call path", "backup restore matches recorded chain identity and checkpoint", "recovery duration is within runbook limits"],
                 ["alert delivery evidence", "backup/restore checksums", "restore drill report"]),
    "PUB-004": ("Verify the published immutable snapshot and manifest using the production trusted signer and a clean bootstrap client.",
                 ["signature and trusted signer validate", "manifest identity matches canonical mainnet", "snapshot metadata matches exported chainstate", "incomplete publication is not observable"],
                 ["signed manifest", "snapshot checksum", "trusted-signer verification output", "bootstrap validation report"]),
    "PUB-005": ("Review and hash the public documentation and endpoint inventory before release.",
                 ["no mainnet faucet or unsupported funding claim is present", "all endpoint, port and chain identity values match approved inventory"],
                 ["documentation tree hash", "endpoint/port review attestation"]),
    "PUB-006": ("Conduct and record a launch/rollback/emergency tabletop or controlled production-readiness drill.",
                 ["all launch steps have named owners", "rollback and emergency stop are executable", "no unresolved critical action or unsafe dependency remains"],
                 ["signed drill report", "participant/role list", "action log and closure evidence"]),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=Path("mainnet-release-gate.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/releases/public-mainnet-launch-gate-catalog.json"))
    args = parser.parse_args()
    matrix = json.loads(args.matrix.read_text(encoding="utf-8"))
    gates = [item for item in matrix["requirements"] if item.get("blocking") == "PUBLIC_LAUNCH_BLOCKING"]
    if len(gates) != 7 or {item["id"] for item in gates} != set(PROCEDURES):
        raise SystemExit("expected the canonical seven public-launch gate IDs")
    catalog = []
    for gate in gates:
        procedure, assertions, evidence = PROCEDURES[gate["id"]]
        catalog.append({
            "id": gate["id"], "description": gate["description"], "dependencies": gate["dependencies"],
            "procedure": procedure, "assertions": assertions, "required_evidence": evidence,
            "execution_mode": "MANUAL_REVIEW", "runner_auto_pass": False,
            "pass_criteria": ["all listed assertions are supported by hashed evidence", "dependencies have current verified PASS evidence", "a named reviewer signs the evidence digest"],
            "fail_criteria": ["any required assertion fails", "identity or evidence checksum mismatch"],
            "blocker_criteria": ["missing evidence", "unavailable prerequisite", "unsigned or stale reviewer attestation"],
            "identity": ["network", "chain_id", "genesis_hash", "source_commit", "source_tree_sha256", "artifact_digest"],
            "status": "NOT_RUN",
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    matrix_hash = hashlib.sha256(args.matrix.read_bytes()).hexdigest()
    args.output.write_text(json.dumps({"schema_version": 1, "source_matrix": str(args.matrix),
                                      "source_matrix_sha256": matrix_hash,
                                      "runner_auto_pass": False, "gates": catalog}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
