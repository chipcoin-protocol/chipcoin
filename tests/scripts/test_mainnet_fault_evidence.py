from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[2] / "scripts" / "mainnet-fault-evidence.py"
SPEC = importlib.util.spec_from_file_location("mainnet_fault_evidence", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_transaction_manifest_separates_raw_and_public_metadata(tmp_path: Path) -> None:
    source = tmp_path / "built.json"
    source.write_text(json.dumps({"txid": "aa" * 32, "raw_hex": "0102", "inputs": [], "outputs": []}))
    manifest = MODULE.write_transaction_evidence(source, tmp_path / "evidence")
    assert "raw_hex" not in manifest
    assert (tmp_path / "evidence/transaction.raw.hex").read_text() == "0102\n"
    assert (tmp_path / "evidence/transaction.raw.hex").stat().st_mode & 0o777 == 0o600


def test_fork_requires_two_different_blocks_after_common_ancestor(tmp_path: Path) -> None:
    a = [{"height": 0, "block_hash": "00", "cumulative_work": 1}, {"height": 1, "block_hash": "aa", "cumulative_work": 2}]
    b = [{"height": 0, "block_hash": "00", "cumulative_work": 1}, {"height": 1, "block_hash": "bb", "cumulative_work": 3}]
    pa, pb = tmp_path / "a.json", tmp_path / "b.json"
    pa.write_text(json.dumps(a)); pb.write_text(json.dumps(b))
    evidence = MODULE.fork_evidence(pa, pb)
    assert evidence["common_ancestor"]["height"] == 0
    assert evidence["first_divergent_a"]["block_hash"] == "aa"
    assert evidence["first_divergent_b"]["block_hash"] == "bb"
    assert evidence["branch_b_winning"] is True


def test_fork_rejects_identical_paths(tmp_path: Path) -> None:
    path = [{"height": 0, "block_hash": "00", "cumulative_work": 1}, {"height": 1, "block_hash": "aa", "cumulative_work": 2}]
    pa, pb = tmp_path / "a.json", tmp_path / "b.json"
    pa.write_text(json.dumps(path)); pb.write_text(json.dumps(path))
    with pytest.raises(ValueError, match="divergent"):
        MODULE.fork_evidence(pa, pb)
