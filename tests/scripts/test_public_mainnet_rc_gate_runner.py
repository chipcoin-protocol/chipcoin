from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/run-public-mainnet-rc-gates.py"
runner_spec = importlib.util.spec_from_file_location("rc_gate_runner", RUNNER)
runner_module = importlib.util.module_from_spec(runner_spec)
runner_spec.loader.exec_module(runner_module)
SOURCE_COMMIT, SOURCE_TREE, WORKTREE_CLEAN = runner_module.source_snapshot(ROOT)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(tmp_path: Path, *, include_evidence: bool = True, bad_hash: bool = False,
             exit_code: int = 0, test_only_identity: bool = False, pre_freeze: bool = True) -> list[str]:
    evidence = tmp_path / "evidence"
    output = evidence / "gate.json"
    if include_evidence:
        _write_json(output, {"network": "mainnet", "chain_id": "chipcoin-mainnet-1", "genesis_hash": None if pre_freeze else "a" * 64,
                             "source_commit": SOURCE_COMMIT, "source_tree_sha256": SOURCE_TREE, "working_tree_clean": WORKTREE_CLEAN,
                             "environment": "test-only" if test_only_identity else ("mainnet-source-review" if pre_freeze else "mainnet-public-rc"), "ok": True})
    requirements = [
        {"id": "GATE-A", "blocking": "RC_BLOCKING", "dependencies": [], "required_evidence": ["E-A"]},
        {"id": "GATE-B", "blocking": "RC_BLOCKING", "dependencies": ["GATE-A"], "required_evidence": ["E-B"]},
    ]
    requirements.extend({"id": f"GATE-{index:03d}", "blocking": "RC_BLOCKING", "dependencies": [], "required_evidence": ["E-X"]} for index in range(96))
    matrix = {"chain_id": "chipcoin-mainnet-1", "requirements": requirements}
    identity = {"network": "mainnet", "chain_id": "chipcoin-mainnet-1", "genesis_hash": None if pre_freeze else "a" * 64}
    gates = {"GATE-A": {
        "command": [sys.executable, "-c", f"raise SystemExit({exit_code})"],
        "cwd": str(tmp_path), "evidence_refs": ["E-A"], "identity_evidence": "gate.json",
        "evidence": [{"path": "gate.json", **({"sha256": "0" * 64} if bad_hash else {})}],
        "assertions": [{"evidence_path": "gate.json", "pointer": "/network", "equals": "mainnet"},
                       {"evidence_path": "gate.json", "pointer": "/ok", "equals": True}],
    }}
    if pre_freeze:
        matrix["requirements"][0]["revalidation_class"] = "SOURCE_REVALIDATION"
        gates["GATE-A"]["assertions"][0]["equals"] = "mainnet"
    _write_json(tmp_path / "matrix.json", matrix)
    plan = {"source_commit": SOURCE_COMMIT, "source_tree_sha256": SOURCE_TREE, "working_tree_clean": WORKTREE_CLEAN,
            "identity": identity, "event_journal": "events.jsonl", "gates": gates}
    if pre_freeze:
        plan["scope"] = "PRE_FREEZE_SOURCE"
    _write_json(tmp_path / "plan.json", plan)
    return [sys.executable, str(RUNNER), "--matrix", str(tmp_path / "matrix.json"), "--plan", str(tmp_path / "plan.json"),
            "--evidence-dir", str(evidence), "--report-json", str(tmp_path / "report.json"),
            "--report-markdown", str(tmp_path / "report.md")]


def test_runner_requires_canonical_98_gate_matrix(tmp_path: Path) -> None:
    command = _fixture(tmp_path)
    matrix = json.loads((tmp_path / "matrix.json").read_text())
    assert subprocess.run(command, check=False).returncode == 0
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["counts"]["NOT_RUN"] == 97
    assert report["counts"]["PASS"] == 1


def test_canonical_release_matrix_is_read_without_status_promotion() -> None:
    matrix = json.loads((ROOT / "public-mainnet-rc-revalidation.json").read_text(encoding="utf-8"))
    plan = {"scope": "PRE_FREEZE_SOURCE", "source_commit": SOURCE_COMMIT, "source_tree_sha256": SOURCE_TREE,
            "working_tree_clean": WORKTREE_CLEAN,
            "identity": {"network": "mainnet", "chain_id": "chipcoin-mainnet-1", "genesis_hash": None}, "gates": {}}
    requirements, configured = runner_module.validate_inputs(matrix, plan)
    assert len(requirements) == 98
    assert configured == {}
    assert {gate["status"] for gate in matrix["requirements"]} == {"NOT_RUN"}
    assert not any(gate.get("_runner_dependency_cycle") for gate in requirements.values())


def test_runner_dry_run_of_canonical_matrix_preserves_all_unrun_gate_statuses(tmp_path: Path) -> None:
    source = ROOT / "public-mainnet-rc-revalidation.json"
    matrix = json.loads(source.read_text(encoding="utf-8"))
    plan = {"schema_version": 1, "scope": "PRE_FREEZE_SOURCE", "source_commit": SOURCE_COMMIT,
            "source_tree_sha256": SOURCE_TREE, "working_tree_clean": WORKTREE_CLEAN,
            "identity": {"network": "mainnet", "chain_id": "chipcoin-mainnet-1", "genesis_hash": None},
            "event_journal": "events.jsonl", "gates": {}}
    _write_json(tmp_path / "matrix.json", matrix)
    _write_json(tmp_path / "plan.json", plan)
    command = [sys.executable, str(RUNNER), "--matrix", str(tmp_path / "matrix.json"), "--plan", str(tmp_path / "plan.json"),
               "--evidence-dir", str(tmp_path / "evidence"), "--report-json", str(tmp_path / "report.json"),
               "--report-markdown", str(tmp_path / "report.md")]
    assert subprocess.run(command, check=False).returncode == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["counts"]["PASS"] == 0
    assert report["counts"]["NOT_RUN"] + report["counts"]["BLOCKED"] == 98
    assert report["dependency_cycle_gate_ids"] == []
    assert {gate["status"] for gate in json.loads(source.read_text(encoding="utf-8"))["requirements"]} == {"NOT_RUN"}


def test_dependency_cycle_is_rejected_before_execution(tmp_path: Path) -> None:
    command = _fixture(tmp_path)
    matrix = json.loads((tmp_path / "matrix.json").read_text())
    matrix["requirements"][0]["dependencies"] = ["GATE-B"]
    _write_json(tmp_path / "matrix.json", matrix)
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    assert completed.returncode == 2
    assert "dependency cycle" in completed.stderr


def test_missing_evidence_blocks_and_blocks_dependents(tmp_path: Path) -> None:
    command = _fixture(tmp_path, include_evidence=False)
    assert subprocess.run(command, check=False).returncode == 0
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["gate_results"]["GATE-A"]["status"] == "BLOCKED"
    assert report["gate_results"]["GATE-B"]["status"] == "BLOCKED"


def test_evidence_hash_mismatch_blocks_pass(tmp_path: Path) -> None:
    command = _fixture(tmp_path, bad_hash=True)
    subprocess.run(command, check=False)
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["gate_results"]["GATE-A"]["status"] == "BLOCKED"


def test_nonzero_gate_command_fails_and_blocks_dependents(tmp_path: Path) -> None:
    command = _fixture(tmp_path, exit_code=7)
    assert subprocess.run(command, check=False).returncode == 1
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["gate_results"]["GATE-A"]["status"] == "FAIL"
    assert report["gate_results"]["GATE-B"]["status"] == "BLOCKED"


def test_test_only_identity_evidence_never_passes_mainnet_gate(tmp_path: Path) -> None:
    command = _fixture(tmp_path, test_only_identity=True)
    subprocess.run(command, check=False)
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["gate_results"]["GATE-A"]["status"] == "BLOCKED"


def test_resume_blocks_tampered_evidence(tmp_path: Path) -> None:
    command = _fixture(tmp_path)
    subprocess.run(command, check=False)
    (tmp_path / "evidence/gate.json").write_text(json.dumps({"network": "mainnet", "chain_id": "chipcoin-mainnet-1",
                                                             "genesis_hash": "a" * 64, "source_commit": SOURCE_COMMIT,
                                                             "source_tree_sha256": SOURCE_TREE, "working_tree_clean": WORKTREE_CLEAN,
                                                             "environment": "mainnet-public-rc", "ok": False}), encoding="utf-8")
    subprocess.run(command, check=False)
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["gate_results"]["GATE-A"]["status"] == "BLOCKED"


def test_resume_detects_tampered_journal(tmp_path: Path) -> None:
    command = _fixture(tmp_path)
    subprocess.run(command, check=False)
    journal = tmp_path / "evidence/events.jsonl"
    journal.write_text(journal.read_text().replace("GATE-A", "GATE-X", 1), encoding="utf-8")
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    assert completed.returncode == 2
    assert "journal integrity failure" in completed.stderr


def test_pending_or_candidate_genesis_is_rejected_before_running(tmp_path: Path) -> None:
    command = _fixture(tmp_path)
    plan = json.loads((tmp_path / "plan.json").read_text())
    plan["identity"]["genesis_hash"] = "PENDING_FINALIZATION"
    _write_json(tmp_path / "plan.json", plan)
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    assert completed.returncode == 2
    assert "pre-freeze source scope must not assert or use a genesis hash" in completed.stderr
    assert not (tmp_path / "evidence/events.jsonl").exists()


def test_plan_cannot_omit_canonical_evidence_reference(tmp_path: Path) -> None:
    command = _fixture(tmp_path)
    plan = json.loads((tmp_path / "plan.json").read_text())
    plan["gates"]["GATE-A"]["evidence_refs"] = []
    _write_json(tmp_path / "plan.json", plan)
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    assert completed.returncode == 2
    assert "does not cover all canonical evidence references" in completed.stderr


def test_pre_freeze_source_gate_can_run_without_genesis(tmp_path: Path) -> None:
    command = _fixture(tmp_path, pre_freeze=True)
    assert subprocess.run(command, check=False).returncode == 0
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["genesis_hash"] is None
    assert report["gate_results"]["GATE-A"]["status"] == "PASS"


def test_pre_freeze_scope_rejects_runtime_gate(tmp_path: Path) -> None:
    command = _fixture(tmp_path, pre_freeze=True)
    matrix = json.loads((tmp_path / "matrix.json").read_text())
    matrix["requirements"][0]["revalidation_class"] = "ISOLATED_CHAIN_RUNTIME"
    _write_json(tmp_path / "matrix.json", matrix)
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    assert completed.returncode == 2
    assert "only SOURCE_REVALIDATION gates" in completed.stderr
