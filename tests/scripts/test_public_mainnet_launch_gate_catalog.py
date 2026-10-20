from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts/build-public-mainnet-launch-gate-catalog.py"


def test_public_launch_catalog_covers_seven_gates_with_verifiable_manual_criteria(tmp_path: Path) -> None:
    output = tmp_path / "catalog.json"
    subprocess.run([sys.executable, str(BUILDER), "--output", str(output)], check=True)
    catalog = json.loads(output.read_text(encoding="utf-8"))
    assert len(catalog["gates"]) == 7
    assert catalog["source_matrix_sha256"] == hashlib.sha256((ROOT / "mainnet-release-gate.json").read_bytes()).hexdigest()
    for gate in catalog["gates"]:
        assert gate["procedure"]
        assert gate["assertions"]
        assert gate["required_evidence"]
        assert gate["pass_criteria"]
        assert gate["fail_criteria"]
        assert gate["blocker_criteria"]
        assert gate["status"] == "NOT_RUN"
        assert gate["runner_auto_pass"] is False


def test_public_catalog_refuses_missing_or_extra_canonical_gates(tmp_path: Path) -> None:
    matrix = json.loads((ROOT / "mainnet-release-gate.json").read_text(encoding="utf-8"))
    matrix["requirements"] = [gate for gate in matrix["requirements"] if gate["id"] != "PUB-006"]
    matrix_path = tmp_path / "incomplete.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    completed = subprocess.run([sys.executable, str(BUILDER), "--matrix", str(matrix_path),
                                "--output", str(tmp_path / "catalog.json")], check=False, capture_output=True, text=True)
    assert completed.returncode != 0
    assert "canonical seven public-launch gate IDs" in completed.stderr
