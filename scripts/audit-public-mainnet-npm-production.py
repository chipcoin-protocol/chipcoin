#!/usr/bin/env python3
"""Fail closed unless wallet and Explorer production npm graphs are clean."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def vulnerability_total(report: dict[str, Any]) -> int:
    try:
        total = report["metadata"]["vulnerabilities"]["total"]
    except (KeyError, TypeError) as exc:
        raise ValueError("npm audit report omits metadata.vulnerabilities.total") from exc
    if not isinstance(total, int) or total < 0:
        raise ValueError("npm vulnerability total must be a non-negative integer")
    return total


def audit(path: Path) -> dict[str, Any]:
    if not (path / "package-lock.json").is_file():
        raise ValueError(f"npm project is unavailable: {path}")
    result = subprocess.run(
        ["npm", "audit", "--omit=dev", "--json"],
        cwd=path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid npm audit JSON for {path}: {result.stderr.strip()}") from exc
    total = vulnerability_total(report)
    if result.returncode != 0 or total != 0:
        raise ValueError(f"production npm audit failed for {path}: exit={result.returncode}, vulnerabilities={total}")
    return {"path": str(path.resolve()), "vulnerabilities": total}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--wallet", type=Path, default=root / "apps/browser-wallet")
    parser.add_argument("--explorer", type=Path, default=root.parent / "chipcoin-central/apps/explorer")
    args = parser.parse_args()
    payload = {
        "schema_version": 1,
        "production_dependency_audits": {
            "browser_wallet": audit(args.wallet),
            "explorer": audit(args.explorer),
        },
        "result": "PASS",
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
