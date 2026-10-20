#!/usr/bin/env python3
"""Create an exact-command plan for the 20 catalogued pre-freeze RC gates."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

RUNNER_SPEC = importlib.util.spec_from_file_location(
    "rc_gate_runner", Path(__file__).resolve().parent / "run-public-mainnet-rc-gates.py"
)
if RUNNER_SPEC is None or RUNNER_SPEC.loader is None:
    raise RuntimeError("gate runner module is unavailable")
RUNNER = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(RUNNER)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--genesis-hash", help="approved canonical genesis hash; required for MAINNET_RC")
    parser.add_argument("--release-tag", help="approved immutable release tag; required for MAINNET_RC")
    parser.add_argument("--scope", choices=("MAINNET_RC", "PRE_FREEZE_SOURCE"), default="MAINNET_RC")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    root = args.source_root.resolve()
    commit, tree_hash, clean = RUNNER.source_snapshot(root)
    if args.scope == "MAINNET_RC":
        if not clean or not args.genesis_hash or len(args.genesis_hash) != 64 or not args.release_tag:
            parser.error("MAINNET_RC requires a clean frozen tree, canonical genesis hash, and release tag")
    elif args.genesis_hash or args.release_tag:
        parser.error("PRE_FREEZE_SOURCE must not bind a genesis or release tag")
    catalog = json.loads((root / "docs/releases/public-mainnet-rc1-gate-catalog.json").read_text(encoding="utf-8"))
    gates = {}
    for item in catalog["gates"]:
        if item["execution_mode"] != "AUTOMATED_PRE_FREEZE":
            continue
        gates[item["id"]] = {"evidence_mode": "COMMAND_CONTRACT", "command": item["command"], "cwd": item["cwd"],
                              "evidence_refs": item["required_evidence_refs"],
                              "command_evidence_refs": item["command_evidence_refs"],
                              "check_ids": [check["check_id"] for check in item["automated_contract"]],
                              "external_evidence_refs": item["external_evidence_refs"],
                              "external_evidence": [{"ref": ref, "path": f"external/{ref}.json"}
                                                    for ref in item["external_evidence_refs"]],
                              "timeout_seconds": 3600}
    if len(gates) != 20:
        parser.error(f"catalog must define 20 executable pre-freeze gates, found {len(gates)}")
    plan = {"schema_version": 1, "scope": args.scope, "source_commit": commit,
            "source_tree_sha256": tree_hash, "working_tree_clean": clean,
            "identity": {"network": "mainnet", "chain_id": "chipcoin-mainnet-1",
                         "genesis_hash": args.genesis_hash if args.scope == "MAINNET_RC" else None},
            "release_tag": args.release_tag, "event_journal": "events.jsonl", "gates": gates}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
