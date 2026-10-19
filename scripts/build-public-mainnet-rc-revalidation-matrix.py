#!/usr/bin/env python3
"""Derive the 98-gate public-mainnet revalidation matrix without inheriting PASS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SOURCE_PREFIXES = ("CONS-CFG-", "PQ-CFG-", "REWARD-CFG-", "SNAP-CFG-", "BW-BUILD-", "BW-NET-", "BW-SEC-", "SEC-CONF-", "SEC-DEP-", "SEC-SECRET-", "RUNBOOK-")


def revalidation_class(gate_id: str) -> str:
    if gate_id.startswith("SEC-REL-"):
        return "RELEASE_FINALIZATION"
    if gate_id.startswith(SOURCE_PREFIXES):
        return "SOURCE_REVALIDATION"
    return "ISOLATED_CHAIN_RUNTIME"


def validate_dependency_graph(requirements: list[dict[str, object]]) -> list[str]:
    gate_ids = [str(gate["id"]) for gate in requirements]
    if len(gate_ids) != len(set(gate_ids)):
        raise ValueError("gate ids must be unique")
    known = set(gate_ids)
    dependencies = {
        str(gate["id"]): tuple(str(item) for item in gate.get("dependencies", []))
        for gate in requirements
    }
    missing = sorted({dependency for values in dependencies.values() for dependency in values if dependency not in known})
    if missing:
        raise ValueError(f"unknown gate dependencies: {missing}")
    self_dependencies = sorted(gate_id for gate_id, values in dependencies.items() if gate_id in values)
    if self_dependencies:
        raise ValueError(f"self-dependent gates: {self_dependencies}")

    ordered: list[str] = []
    remaining = dict(dependencies)
    while remaining:
        ready = sorted(gate_id for gate_id, values in remaining.items() if set(values).issubset(ordered))
        if not ready:
            raise ValueError(f"gate dependency cycle: {sorted(remaining)}")
        ordered.extend(ready)
        for gate_id in ready:
            del remaining[gate_id]
    return ordered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("mainnet-release-gate.json"))
    parser.add_argument("--output", type=Path, default=Path("public-mainnet-rc-revalidation.json"))
    args = parser.parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    requirements = []
    for gate in source["requirements"]:
        if gate["blocking"] != "RC_BLOCKING":
            continue
        requirements.append(
            {
                "id": gate["id"],
                "category": gate["category"],
                "description": gate["description"],
                "status": "NOT_RUN",
                "blocking": "RC_BLOCKING",
                "dependencies": gate.get("dependencies", []),
                "revalidation_class": revalidation_class(gate["id"]),
                "required_identity": {
                    "network": "mainnet",
                    "chain_id": "chipcoin-mainnet-1",
                    "genesis_hash": "PENDING_FINALIZATION",
                },
                "required_evidence": gate.get("evidence", []),
                "historical_reference": {
                    "status": gate["status"],
                    "evidence": gate.get("evidence", []),
                    "inherited_as_pass": False,
                },
                "notes": gate.get("notes", ""),
            }
        )
    if len(requirements) != 98:
        raise SystemExit(f"expected 98 RC gates, found {len(requirements)}")
    validate_dependency_graph(requirements)
    payload = {
        "schema_version": 1,
        "network": "mainnet",
        "chain_id": "chipcoin-mainnet-1",
        "genesis_hash": "PENDING_FINALIZATION",
        "decision_rule": "READY only when all 98 RC_BLOCKING requirements are PASS on the new canonical chain.",
        "counts": {"PASS": 0, "FAIL": 0, "NOT_RUN": 98, "PENDING_HEIGHT": 0, "BLOCKED": 0},
        "requirements": requirements,
    }
    args.output.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
