#!/usr/bin/env python3
"""Create secret-free transaction and fork evidence for the fault harness."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def write_transaction_evidence(source: Path, output_dir: Path) -> dict:
    payload = json.loads(source.read_text(encoding="utf-8"))
    raw = str(payload.pop("raw_hex"))
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "transaction.raw.hex"
    raw_path.write_text(raw + "\n", encoding="ascii")
    os.chmod(raw_path, 0o600)
    manifest = {
        **payload,
        "raw_sha256": hashlib.sha256((raw + "\n").encode()).hexdigest(),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def fork_evidence(path_a: Path, path_b: Path) -> dict:
    branch_a = json.loads(path_a.read_text(encoding="utf-8"))
    branch_b = json.loads(path_b.read_text(encoding="utf-8"))
    by_height_a = {int(row["height"]): row for row in branch_a}
    by_height_b = {int(row["height"]): row for row in branch_b}
    common = [height for height in set(by_height_a) & set(by_height_b) if by_height_a[height]["block_hash"] == by_height_b[height]["block_hash"]]
    if not common:
        raise ValueError("branches have no common ancestor")
    ancestor_height = max(common)
    first_height = ancestor_height + 1
    first_a = by_height_a.get(first_height)
    first_b = by_height_b.get(first_height)
    if first_a is None or first_b is None or first_a["block_hash"] == first_b["block_hash"]:
        raise ValueError("two divergent blocks after the common ancestor were not proven")
    tip_a, tip_b = branch_a[-1], branch_b[-1]
    return {
        "common_ancestor": by_height_a[ancestor_height],
        "first_divergent_a": first_a,
        "first_divergent_b": first_b,
        "tip_a": tip_a,
        "tip_b": tip_b,
        "branch_b_winning": int(tip_b["cumulative_work"]) > int(tip_a["cumulative_work"]),
        "path_a": branch_a[ancestor_height:],
        "path_b": branch_b[ancestor_height:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    tx = sub.add_parser("transaction")
    tx.add_argument("--source", required=True, type=Path)
    tx.add_argument("--output-dir", required=True, type=Path)
    fork = sub.add_parser("fork")
    fork.add_argument("--branch-a", required=True, type=Path)
    fork.add_argument("--branch-b", required=True, type=Path)
    fork.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "transaction":
        result = write_transaction_evidence(args.source, args.output_dir)
    else:
        result = fork_evidence(args.branch_a, args.branch_b)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
