from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
import shutil
import base64
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

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


def test_manual_attestation_gate_cannot_be_configured_as_automated_command() -> None:
    matrix = json.loads((ROOT / "public-mainnet-rc-revalidation.json").read_text(encoding="utf-8"))
    plan = {"scope": "MAINNET_RC", "source_commit": SOURCE_COMMIT, "source_tree_sha256": SOURCE_TREE,
            "working_tree_clean": True,
            "identity": {"network": "mainnet", "chain_id": "chipcoin-mainnet-1", "genesis_hash": "a" * 64},
            "gates": {"SEC-DEP-002": {"command": [sys.executable, "-c", "pass"],
                "evidence_refs": ["E"], "identity_evidence": "e.json",
                "evidence": [{"path": "e.json"}],
                "assertions": [{"evidence_path": "e.json", "pointer": "/ok", "equals": True}]}}}
    with pytest.raises(ValueError, match="manual-attestation gates cannot be configured"):
        runner_module.validate_inputs(matrix, plan)


def test_public_gates_require_hash_bound_current_rc_report_and_never_auto_pass(tmp_path: Path) -> None:
    repo = tmp_path / "clean-source"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "scripts").mkdir()
    shutil.copy2(RUNNER, repo / "scripts/run-public-mainnet-rc-gates.py")
    subprocess.run(["git", "-C", str(repo), "add", "scripts/run-public-mainnet-rc-gates.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture source"], check=True)
    commit, tree_hash, clean = runner_module.source_snapshot(repo)

    matrix = json.loads((ROOT / "mainnet-release-gate.json").read_text(encoding="utf-8"))
    plan = {"scope": "MAINNET_RC", "source_commit": commit, "source_tree_sha256": tree_hash,
            "working_tree_clean": clean,
            "identity": {"network": "mainnet", "chain_id": "chipcoin-mainnet-1",
                         "genesis_hash": "0" * 63 + "1"}, "event_journal": "events.jsonl", "gates": {}}
    matrix_path = tmp_path / "public-matrix.json"
    plan_path = tmp_path / "public-plan.json"
    _write_json(matrix_path, matrix)
    _write_json(plan_path, plan)
    rc_matrix = json.loads((ROOT / "public-mainnet-rc-revalidation.json").read_text(encoding="utf-8"))
    rc_ids = [gate["id"] for gate in rc_matrix["requirements"]]
    rc_report = {"scope": "MAINNET_RC", "blocking_class": "RC_BLOCKING", "network": "mainnet",
                 "chain_id": "chipcoin-mainnet-1", "genesis_hash": "0" * 63 + "1",
                 "source_commit": commit, "source_tree_sha256": tree_hash, "working_tree_clean": clean,
                 "counts": {"PASS": 98, "FAIL": 0, "BLOCKED": 0, "NOT_RUN": 0},
                 "gate_results": {gate_id: {"status": "PASS"} for gate_id in rc_ids}}
    prerequisite_evidence = tmp_path / "rc-evidence"
    prerequisite_evidence.mkdir()
    artifact = prerequisite_evidence / "gate-evidence.json"
    _write_json(artifact, {"identity": "bound-to-source-and-mainnet"})
    artifact_record = {"path": artifact.name, "sha256": runner_module.sha256(artifact)}
    identity = {"network": "mainnet", "chain_id": "chipcoin-mainnet-1", "genesis_hash": "0" * 63 + "1"}
    matrix_digest = "a" * 64
    rc_report["source_matrix_sha256"] = matrix_digest
    for gate_id in rc_ids:
        rc_report["gate_results"][gate_id] = {"status": "PASS", "evidence": [artifact_record]}
        event = {"recorded_at": "2026-10-19T00:00:00Z", "gate_id": gate_id,
                 "source_commit": commit, "source_tree_sha256": tree_hash, "working_tree_clean": clean,
                 "matrix_sha256": matrix_digest, "plan_sha256": "b" * 64,
                 "identity": identity, "result": rc_report["gate_results"][gate_id]}
        previous = runner_module.append_event(prerequisite_evidence / "events.jsonl", event,
                                              "0" * 64 if gate_id == rc_ids[0] else previous)
    rc_report["event_journal_sha256"] = runner_module.sha256(prerequisite_evidence / "events.jsonl")
    rc_report_path = tmp_path / "rc-report.json"
    _write_json(rc_report_path, rc_report)
    rc_report_hash = runner_module.sha256(rc_report_path)
    report_json = tmp_path / "public-report.json"
    report_md = tmp_path / "public-report.md"
    evidence = tmp_path / "public-evidence"
    command = [sys.executable, str(repo / "scripts/run-public-mainnet-rc-gates.py"),
               "--matrix", str(matrix_path), "--plan", str(plan_path), "--evidence-dir", str(evidence),
               "--report-json", str(report_json), "--report-markdown", str(report_md),
               "--blocking-class", "PUBLIC_LAUNCH_BLOCKING", "--prerequisite-report", str(rc_report_path),
               "--prerequisite-report-sha256", rc_report_hash,
               "--prerequisite-evidence-dir", str(prerequisite_evidence)]
    assert subprocess.run(command, check=False).returncode == 0
    report = json.loads(report_json.read_text(encoding="utf-8"))
    assert report["blocking_class"] == "PUBLIC_LAUNCH_BLOCKING"
    assert report["counts"]["PASS"] == 0
    assert report["counts"]["NOT_RUN"] + report["counts"]["BLOCKED"] == 7

    plan["gates"] = {"PUB-005": {"command": [sys.executable, "-c", "pass"],
        "evidence_refs": [], "identity_evidence": "public.json", "evidence": [{"path": "public.json"}],
        "assertions": [{"evidence_path": "public.json", "pointer": "/ok", "equals": True}]}}
    with pytest.raises(ValueError, match="public-launch gates require signed human review"):
        runner_module.validate_inputs(matrix, plan, "PUBLIC_LAUNCH_BLOCKING")

    command[command.index("--prerequisite-report-sha256") + 1] = "f" * 64
    invalid = subprocess.run(command, check=False, capture_output=True, text=True)
    assert invalid.returncode == 2
    assert "SHA-256 mismatch" in invalid.stderr


def _signed_attestation(tmp_path: Path, *, environment: str = "mainnet-public-rc"):
    private_key = Ed25519PrivateKey.generate()
    evidence = tmp_path / "evidence" / "review.json"
    _write_json(evidence, {"result": "reviewed"})
    commit, tree_hash = "a" * 40, "b" * 64
    plan = {"source_commit": commit, "source_tree_sha256": tree_hash, "release_tag": "mainnet-v0.1.2-rc.3",
            "identity": {"network": "mainnet", "chain_id": "chipcoin-mainnet-1", "genesis_hash": "c" * 64}}
    item = {"path": "review.json", "sha256": runner_module.sha256(evidence), "network": "mainnet",
            "chain_id": "chipcoin-mainnet-1", "genesis_hash": "c" * 64, "source_commit": commit,
            "source_tree_sha256": tree_hash, "release_tag": "mainnet-v0.1.2-rc.3", "environment": environment}
    attestation = {"schema_version": 1, "gate_id": "RUNBOOK-001", "signer_key_id": "reviewer-1",
                   "signer_identity": "Alice Example", "role": "release-reviewer",
                   "signed_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                   "source_commit": commit, "source_tree_sha256": tree_hash,
                   "release_tag": "mainnet-v0.1.2-rc.3", "genesis_hash": "c" * 64,
                   "evidence": [item], "outcome": "PASS", "statement": "Reviewed evidence."}
    attestation["signature"] = base64.b64encode(private_key.sign(runner_module.canonical(attestation))).decode()
    public_key = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    trust = {"schema_version": 1, "signature_algorithm": "Ed25519", "max_age_seconds": 3600, "authorized_signers": [{
        "key_id": "reviewer-1", "identity": "Alice Example", "roles": ["release-reviewer"],
        "gate_ids": ["RUNBOOK-001"], "public_key_hex": public_key.hex(),
        "valid_from": "2026-01-01T00:00:00Z", "valid_until": "2027-01-01T00:00:00Z"}]}
    return attestation, trust, plan, tmp_path / "evidence"


def test_ed25519_manual_attestation_valid_and_release_bound(tmp_path: Path) -> None:
    attestation, trust, plan, root = _signed_attestation(tmp_path)
    assert runner_module.verify_manual_attestation(attestation, trust, gate_id="RUNBOOK-001", plan=plan,
                                                  evidence_root=root) == [{"path": "review.json", "sha256": attestation["evidence"][0]["sha256"]}]


def test_manual_attestation_rejects_missing_trust_roots(tmp_path: Path) -> None:
    attestation, _, plan, root = _signed_attestation(tmp_path)
    with pytest.raises(ValueError, match="absent or ambiguous"):
        runner_module.verify_manual_attestation(attestation, {"schema_version": 1, "signature_algorithm": "Ed25519",
                                                "max_age_seconds": 3600,
                                                "authorized_signers": []}, gate_id="RUNBOOK-001",
                                                plan=plan, evidence_root=root)


def test_manual_attestation_rejects_malformed_trust_store(tmp_path: Path) -> None:
    attestation, _, plan, root = _signed_attestation(tmp_path)
    with pytest.raises(ValueError, match="trust store must be a JSON object"):
        runner_module.verify_manual_attestation(attestation, [], gate_id="RUNBOOK-001", plan=plan, evidence_root=root)


def test_manual_attestation_rejects_tampered_signature(tmp_path: Path) -> None:
    attestation, trust, plan, root = _signed_attestation(tmp_path)
    attestation["statement"] = "altered after signature"
    with pytest.raises(ValueError, match="signature verification failed"):
        runner_module.verify_manual_attestation(attestation, trust, gate_id="RUNBOOK-001", plan=plan, evidence_root=root)


def test_manual_attestation_rejects_unauthorized_role_or_gate(tmp_path: Path) -> None:
    attestation, trust, plan, root = _signed_attestation(tmp_path)
    trust["authorized_signers"][0]["gate_ids"] = ["RUNBOOK-002"]
    with pytest.raises(ValueError, match="authorization mismatch"):
        runner_module.verify_manual_attestation(attestation, trust, gate_id="RUNBOOK-001", plan=plan, evidence_root=root)


def test_manual_attestation_rejects_wrong_release_identity(tmp_path: Path) -> None:
    attestation, trust, plan, root = _signed_attestation(tmp_path)
    plan["release_tag"] = "mainnet-v0.1.2-rc.other"
    with pytest.raises(ValueError, match="release identity mismatch"):
        runner_module.verify_manual_attestation(attestation, trust, gate_id="RUNBOOK-001", plan=plan, evidence_root=root)


def test_manual_attestation_rejects_tampered_evidence_and_test_only_provenance(tmp_path: Path) -> None:
    attestation, trust, plan, root = _signed_attestation(tmp_path)
    (root / "review.json").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        runner_module.verify_manual_attestation(attestation, trust, gate_id="RUNBOOK-001", plan=plan, evidence_root=root)
    attestation, trust, plan, root = _signed_attestation(tmp_path / "isolated", environment="test-only")
    with pytest.raises(ValueError, match="TEST-ONLY, historical"):
        runner_module.verify_manual_attestation(attestation, trust, gate_id="RUNBOOK-001", plan=plan, evidence_root=root)


def test_automated_gate_plan_must_match_canonical_command_and_assertion_contract() -> None:
    matrix = json.loads((ROOT / "public-mainnet-rc-revalidation.json").read_text(encoding="utf-8"))
    gate = next(item for item in json.loads((ROOT / "docs/releases/public-mainnet-rc1-gate-catalog.json").read_text())
                ["gates"] if item["id"] == "CONS-CFG-003")
    plan = {"scope": "PRE_FREEZE_SOURCE", "source_commit": SOURCE_COMMIT, "source_tree_sha256": SOURCE_TREE,
            "working_tree_clean": WORKTREE_CLEAN,
            "identity": {"network": "mainnet", "chain_id": "chipcoin-mainnet-1", "genesis_hash": None},
            "gates": {"CONS-CFG-003": {"evidence_mode": "COMMAND_CONTRACT", "command": gate["command"],
                "cwd": gate["cwd"], "evidence_refs": gate["required_evidence_refs"],
                "command_evidence_refs": gate["command_evidence_refs"],
                "check_ids": [item["check_id"] for item in gate["automated_contract"]],
                "external_evidence_refs": gate["external_evidence_refs"],
                "external_evidence": [{"ref": ref, "path": f"external/{ref}.json"} for ref in gate["external_evidence_refs"]]}}}
    runner_module.validate_inputs(matrix, plan)
    plan["gates"]["CONS-CFG-003"]["command"] = [sys.executable, "-c", "pass"]
    with pytest.raises(ValueError, match="command and cwd must exactly match"):
        runner_module.validate_inputs(matrix, plan)


def test_gate_plan_builder_emits_all_20_exact_catalog_contracts(tmp_path: Path) -> None:
    output = tmp_path / "plan.json"
    completed = subprocess.run([sys.executable, str(ROOT / "scripts/build-public-mainnet-rc3-gate-plan.py"),
                                "--scope", "PRE_FREEZE_SOURCE", "--source-root", str(ROOT),
                                "--output", str(output)], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    plan = json.loads(output.read_text(encoding="utf-8"))
    catalog = json.loads((ROOT / "docs/releases/public-mainnet-rc1-gate-catalog.json").read_text(encoding="utf-8"))
    expected = {item["id"]: item for item in catalog["gates"] if item["execution_mode"] == "AUTOMATED_PRE_FREEZE"}
    assert len(plan["gates"]) == 20
    assert all(plan["gates"][gate_id]["command"] == item["command"] for gate_id, item in expected.items())
    assert all(plan["gates"][gate_id]["check_ids"] == [check["check_id"] for check in item["automated_contract"]]
               for gate_id, item in expected.items())
