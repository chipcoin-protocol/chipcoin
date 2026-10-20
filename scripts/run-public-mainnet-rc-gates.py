#!/usr/bin/env python3
"""Fail-closed, resumable evidence runner for the public-mainnet RC matrix.

The matrix is never edited. Only gates explicitly described in a reviewed plan
can run; PASS requires a successful command and matching, identity-bound
evidence assertions. Commands are argv arrays and are never run through a shell.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ZERO_HASH = "0" * 64


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_snapshot(root: Path) -> tuple[str, str, bool]:
    commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
                            check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    paths = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.split(b"\0")
    digest = hashlib.sha256()
    for raw_path in sorted(set(path for path in paths if path)):
        path = root / os.fsdecode(raw_path)
        digest.update(len(raw_path).to_bytes(8, "big"))
        digest.update(raw_path)
        if not path.exists() and not path.is_symlink():
            digest.update(b"MISSING")
            continue
        info = path.lstat()
        digest.update(stat.S_IMODE(info.st_mode).to_bytes(4, "big"))
        if path.is_symlink():
            digest.update(b"LINK" + os.fsencode(os.readlink(path)))
        elif path.is_file():
            digest.update(b"FILE" + bytes.fromhex(sha256(path)))
        else:
            digest.update(b"OTHER")
    return commit, digest.hexdigest(), not bool(status)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if candidate != root.resolve() and root.resolve() not in candidate.parents:
        raise ValueError(f"path escapes evidence directory: {relative}")
    return candidate


def json_pointer(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise ValueError(f"invalid JSON pointer: {pointer}")
    current = value
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be RFC3339 UTC ending in Z")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include UTC timezone")
    return parsed.astimezone(timezone.utc)


def verify_manual_attestation(attestation: dict[str, Any], trust_store: dict[str, Any], *,
                              gate_id: str, plan: dict[str, Any], evidence_root: Path) -> list[dict[str, str]]:
    """Verify one human decision against an explicit public-key allowlist."""
    if not isinstance(attestation, dict):
        raise ValueError("attestation must be a JSON object")
    if not isinstance(trust_store, dict):
        raise ValueError("trust store must be a JSON object")
    if trust_store.get("schema_version") != 1 or trust_store.get("signature_algorithm") != "Ed25519":
        raise ValueError("trust store schema or signature algorithm is unsupported")
    if set(trust_store) != {"schema_version", "signature_algorithm", "max_age_seconds", "authorized_signers"}:
        raise ValueError("trust store contains missing or unknown fields")
    required = {"schema_version", "gate_id", "signer_key_id", "signer_identity", "role", "signed_at",
                "source_commit", "source_tree_sha256", "release_tag", "genesis_hash", "evidence", "outcome", "statement", "signature"}
    if set(attestation) != required or attestation.get("schema_version") != 1:
        raise ValueError("attestation fields/schema are incomplete or unknown")
    if attestation["gate_id"] != gate_id:
        raise ValueError("attestation gate id mismatch")
    expected = {"source_commit": plan["source_commit"], "release_tag": plan.get("release_tag"),
                "genesis_hash": plan["identity"].get("genesis_hash"),
                "source_tree_sha256": plan["source_tree_sha256"]}
    if any(not expected[key] or attestation.get(key) != value for key, value in expected.items()):
        raise ValueError("attestation release identity mismatch")
    if attestation.get("outcome") not in {"PASS", "FAIL", "BLOCKED"} or not isinstance(attestation.get("statement"), str) or not attestation["statement"].strip():
        raise ValueError("attestation outcome/statement is invalid")
    signed_at = parse_utc(attestation["signed_at"])
    now = datetime.now(timezone.utc)
    if signed_at > now:
        raise ValueError("attestation timestamp is in the future")
    max_age = trust_store.get("max_age_seconds")
    if type(max_age) is not int or max_age <= 0 or (now - signed_at).total_seconds() > max_age:
        raise ValueError("attestation is stale")
    keys = trust_store.get("authorized_signers", [])
    if not isinstance(keys, list):
        raise ValueError("trust store authorized_signers must be an explicit list")
    key_fields = {"key_id", "identity", "roles", "gate_ids", "public_key_hex", "valid_from", "valid_until"}
    for key in keys:
        if not isinstance(key, dict) or set(key) != key_fields:
            raise ValueError("authorized signer record is incomplete or has unknown fields")
        if (not isinstance(key["key_id"], str) or not key["key_id"]
                or not isinstance(key["roles"], list) or not key["roles"]
                or not isinstance(key["gate_ids"], list) or not key["gate_ids"]
                or any(not isinstance(value, str) or not value for value in key["roles"] + key["gate_ids"])
                or not isinstance(key["public_key_hex"], str)
                or re.fullmatch(r"[0-9a-f]{64}", key["public_key_hex"]) is None):
            raise ValueError("authorized signer key/role/gate fields are invalid")
    matches = [item for item in keys if isinstance(item, dict) and item.get("key_id") == attestation["signer_key_id"]]
    if len(matches) != 1:
        raise ValueError("signer key is absent or ambiguous in the trust store")
    signer = matches[0]
    if not isinstance(signer, dict) or not isinstance(signer.get("identity"), str) or not signer["identity"].strip():
        raise ValueError("authorized signer record is incomplete")
    if (signer.get("identity") != attestation["signer_identity"] or attestation["role"] not in signer.get("roles", [])
            or gate_id not in signer.get("gate_ids", [])):
        raise ValueError("signer identity, role, or gate authorization mismatch")
    if parse_utc(signer["valid_from"]) > signed_at or parse_utc(signer["valid_until"]) < signed_at:
        raise ValueError("signing key was not valid at signed_at")
    try:
        public_bytes = bytes.fromhex(signer["public_key_hex"])
        signature = base64.b64decode(attestation["signature"], validate=True)
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(public_bytes).verify(signature, canonical({k: v for k, v in attestation.items() if k != "signature"}))
    except (ValueError, TypeError, KeyError, binascii.Error, ImportError) as error:
        raise ValueError(f"Ed25519 signature material invalid: {error}") from error
    except Exception as error:
        # cryptography's InvalidSignature intentionally stays behind a stable fail-closed error.
        raise ValueError("Ed25519 signature verification failed") from error
    records: list[dict[str, str]] = []
    evidence_items = attestation["evidence"]
    if not isinstance(evidence_items, list) or not evidence_items:
        raise ValueError("attestation must bind at least one evidence artifact")
    expected_evidence_fields = {"path", "sha256", "network", "chain_id", "genesis_hash", "source_commit",
                                "source_tree_sha256", "release_tag", "environment"}
    for item in evidence_items:
        if not isinstance(item, dict) or set(item) != expected_evidence_fields:
            raise ValueError("attestation evidence entry must bind artifact hash and release provenance")
        if (not isinstance(item.get("path"), str) or not item["path"]
                or not isinstance(item.get("sha256"), str) or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None):
            raise ValueError("attestation evidence path/hash is invalid")
        provenance = {"network": "mainnet", "chain_id": plan["identity"]["chain_id"],
                      "genesis_hash": plan["identity"]["genesis_hash"], "source_commit": plan["source_commit"],
                      "source_tree_sha256": plan["source_tree_sha256"], "release_tag": plan["release_tag"],
                      "environment": "mainnet-public-rc"}
        if any(item.get(key) != value for key, value in provenance.items()):
            raise ValueError("TEST-ONLY, historical, or other-release evidence is not admissible")
        path = safe_path(evidence_root, item["path"])
        if not path.is_file() or sha256(path) != item["sha256"]:
            raise ValueError(f"attestation evidence missing or hash mismatch: {item['path']}")
        records.append({"path": item["path"], "sha256": item["sha256"]})
    return records


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    previous = ZERO_HASH
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        event = json.loads(line)
        supplied = event.pop("event_sha256", None)
        if event.get("previous_event_sha256") != previous or supplied != hashlib.sha256(canonical(event)).hexdigest():
            raise ValueError(f"event journal integrity failure at line {number}")
        event["event_sha256"] = supplied
        events.append(event)
        previous = supplied
    return events


def append_event(path: Path, event: dict[str, Any], previous: str) -> str:
    event["previous_event_sha256"] = previous
    event_hash = hashlib.sha256(canonical(event)).hexdigest()
    record = {**event, "event_sha256": event_hash}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return event_hash


def counts(results: dict[str, dict[str, Any]]) -> dict[str, int]:
    return {status: sum(item["status"] == status for item in results.values()) for status in ("PASS", "FAIL", "BLOCKED", "NOT_RUN")}


def render_report(matrix: dict[str, Any], plan: dict[str, Any], results: dict[str, dict[str, Any]], events: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    journal_path = safe_path(Path(plan["evidence_root"]), plan.get("event_journal", "events.jsonl"))
    report = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "source_matrix_sha256": plan["matrix_sha256"],
        "release_tag": plan.get("release_tag"),
        "source_commit": plan["source_commit"],
        "source_tree_sha256": plan["source_tree_sha256"],
        "working_tree_clean": plan["working_tree_clean"],
        "scope": plan.get("scope", "MAINNET_RC"),
        "blocking_class": plan.get("blocking_class", "RC_BLOCKING"),
        "prerequisite_report_sha256": plan.get("prerequisite_report_sha256"),
        "network": plan["identity"]["network"],
        "chain_id": plan["identity"]["chain_id"],
        "genesis_hash": plan["identity"]["genesis_hash"],
        "counts": counts(results),
        "dependency_cycle_gate_ids": [],
        "gate_results": results,
        "event_count": len(events),
        "event_journal_sha256": sha256(journal_path) if journal_path.exists() else None,
    }
    lines = ["# Public Mainnet RC Gate Run", "", f"Generated: {report['generated_at']}",
             f"Source commit: `{report['source_commit']}`", f"Identity: `{report['network']}` / `{report['chain_id']}` / `{report['genesis_hash']}", "",
             "| Status | Count |", "|---|---:|"]
    lines.extend(f"| {status} | {number} |" for status, number in report["counts"].items())
    lines += ["", "| Gate | Status | Evidence | Detail |", "|---|---|---|---|"]
    for gate_id in sorted(results):
        item = results[gate_id]
        evidence = ", ".join(f"`{record['path']}` ({record.get('sha256', 'missing')})" for record in item.get("evidence", []))
        detail = str(item.get("detail", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {gate_id} | {item['status']} | {evidence} | {detail} |")
    return report, "\n".join(lines) + "\n"


def validate_inputs(matrix: dict[str, Any], plan: dict[str, Any], blocking_class: str = "RC_BLOCKING") -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    raw_requirements = matrix.get("requirements", [])
    requirements = {gate["id"]: gate for gate in raw_requirements if gate.get("blocking") == blocking_class}
    expected_count = 98 if blocking_class == "RC_BLOCKING" else 7 if blocking_class == "PUBLIC_LAUNCH_BLOCKING" else None
    if expected_count is None or len(requirements) != expected_count or len(raw_requirements) not in (expected_count, 105):
        raise ValueError(f"expected {expected_count} unique {blocking_class} requirements, found {len(requirements)}")
    all_ids = {gate["id"] for gate in raw_requirements}
    if len(all_ids) != len(raw_requirements):
        raise ValueError("matrix contains duplicate gate ids")
    if any(dep not in all_ids for gate in requirements.values() for dep in gate.get("dependencies", [])):
        raise ValueError("canonical matrix has an unknown dependency")
    ordered: dict[str, dict[str, Any]] = {}
    remaining = dict(requirements)
    while remaining:
        ready = [gate_id for gate_id, gate in remaining.items()
                 if set(dep for dep in gate.get("dependencies", []) if dep in requirements).issubset(ordered)]
        if not ready:
            raise ValueError(f"canonical matrix has a dependency cycle: {sorted(remaining)}")
        for gate_id in ready:
            ordered[gate_id] = remaining.pop(gate_id)
    requirements = ordered
    identity = plan.get("identity", {})
    genesis = identity.get("genesis_hash", "")
    commit = plan.get("source_commit", "")
    tree_hash = plan.get("source_tree_sha256", "")
    clean = plan.get("working_tree_clean")
    scope = plan.get("scope", "MAINNET_RC")
    expected_chain_id = matrix.get("chain_id", "chipcoin-mainnet-1" if blocking_class == "PUBLIC_LAUNCH_BLOCKING" else None)
    if identity.get("network") != "mainnet" or identity.get("chain_id") != expected_chain_id:
        raise ValueError("plan identity must match the canonical mainnet and chain id")
    if scope == "MAINNET_RC":
        if not isinstance(genesis, str) or len(genesis) != 64 or any(char not in "0123456789abcdef" for char in genesis):
            raise ValueError("final mainnet genesis hash is required; candidate/pending identities cannot run gates")
    elif scope == "PRE_FREEZE_SOURCE":
        if genesis is not None:
            raise ValueError("pre-freeze source scope must not assert or use a genesis hash")
    else:
        raise ValueError("scope must be MAINNET_RC or PRE_FREEZE_SOURCE")
    if not isinstance(commit, str) or len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise ValueError("a frozen source commit is required")
    if not isinstance(tree_hash, str) or len(tree_hash) != 64 or any(char not in "0123456789abcdef" for char in tree_hash):
        raise ValueError("a frozen source tree SHA-256 is required")
    if not isinstance(clean, bool):
        raise ValueError("working_tree_clean must be an explicit boolean")
    if scope == "MAINNET_RC" and not clean:
        raise ValueError("MAINNET_RC gate runs require a clean frozen source tree")
    plans = plan.get("gates", {})
    if not isinstance(plans, dict):
        raise ValueError("plan gates must be an object")
    unknown = sorted(set(plans) - set(requirements))
    if unknown:
        raise ValueError(f"plan includes unknown gate ids: {unknown}")
    catalog_path = Path(__file__).resolve().parents[1] / "docs/releases/public-mainnet-rc4-gate-catalog.json"
    catalog = read_json(catalog_path) if catalog_path.is_file() else {"gates": []}
    catalog_gates = {item["id"]: item for item in catalog.get("gates", [])}
    manual_ids = {gate_id for gate_id, item in catalog_gates.items()
                  if item.get("execution_mode") == "MANUAL_ATTESTATION"}
    manual_plan_ids = sorted(set(plans) & manual_ids)
    if manual_plan_ids:
        raise ValueError(f"manual-attestation gates cannot be configured as automated commands: {manual_plan_ids}")
    if blocking_class == "PUBLIC_LAUNCH_BLOCKING" and plans:
        raise ValueError("public-launch gates require signed human review; this runner cannot auto-PASS them")
    for gate_id, spec in plans.items():
        if not isinstance(spec, dict):
            raise ValueError(f"{gate_id}: gate plan must be an object")
        gate_class = requirements[gate_id].get("revalidation_class")
        canonical_gate = catalog_gates.get(gate_id, {})
        if scope == "PRE_FREEZE_SOURCE" and gate_class != "SOURCE_REVALIDATION":
            raise ValueError(f"{gate_id}: only SOURCE_REVALIDATION gates may run before genesis freeze")
        argv = spec.get("command")
        if not isinstance(argv, list) or not argv or not all(isinstance(part, str) for part in argv):
            raise ValueError(f"{gate_id}: command must be a non-empty argv array")
        if canonical_gate.get("execution_mode") == "AUTOMATED_PRE_FREEZE" and (argv != canonical_gate.get("command") or spec.get("cwd", ".") != canonical_gate.get("cwd")):
            raise ValueError(f"{gate_id}: command and cwd must exactly match the canonical catalog")
        required_refs = set(requirements[gate_id].get("required_evidence", requirements[gate_id].get("evidence", [])))
        declared_refs = spec.get("evidence_refs", [])
        if not isinstance(declared_refs, list) or any(not isinstance(ref, str) for ref in declared_refs):
            raise ValueError(f"{gate_id}: evidence_refs must be a string array")
        if not required_refs.issubset(set(declared_refs)):
            raise ValueError(f"{gate_id}: plan does not cover all canonical evidence references")
        if not spec.get("evidence") or not spec.get("assertions"):
            if spec.get("evidence_mode") != "COMMAND_CONTRACT":
                raise ValueError(f"{gate_id}: evidence/assertions or COMMAND_CONTRACT are required for PASS")
        if spec.get("evidence_mode") == "COMMAND_CONTRACT":
            contract = catalog_gates.get(gate_id, {})
            if plan.get("scope") == "MAINNET_RC" and (not isinstance(plan.get("release_tag"), str) or not plan["release_tag"].strip()):
                raise ValueError(f"{gate_id}: MAINNET_RC command evidence requires a frozen release tag")
            if (contract.get("execution_mode") != "AUTOMATED_PRE_FREEZE"
                    or argv != contract.get("command") or spec.get("cwd", ".") != contract.get("cwd")
                    or spec.get("check_ids") != [item["check_id"] for item in contract.get("automated_contract", [])]):
                raise ValueError(f"{gate_id}: command/check contract must exactly match the canonical catalog")
            external_refs = contract.get("external_evidence_refs", [])
            external_entries = spec.get("external_evidence", [])
            if (not isinstance(external_entries, list)
                    or any(not isinstance(item, dict) or set(item) != {"ref", "path"}
                           or not isinstance(item.get("ref"), str) or not isinstance(item.get("path"), str)
                           for item in external_entries)):
                raise ValueError(f"{gate_id}: external evidence entries must be objects")
            if (spec.get("external_evidence_refs") != external_refs
                    or spec.get("command_evidence_refs") != contract.get("command_evidence_refs")
                    or set(declared_refs) != set(requirements[gate_id].get("required_evidence", []))
                    or [item.get("ref") for item in external_entries] != external_refs):
                raise ValueError(f"{gate_id}: external evidence references must exactly match the canonical catalog")
            continue
        if spec.get("evidence_mode") is not None:
            raise ValueError(f"{gate_id}: unsupported evidence mode")
        identity_path = spec.get("identity_evidence")
        if not identity_path or identity_path not in {item.get("path") for item in spec["evidence"]}:
            raise ValueError(f"{gate_id}: identity_evidence must be one of the hashed evidence files")
        if any(assertion.get("evidence_path") not in {item.get("path") for item in spec["evidence"]} for assertion in spec["assertions"]):
            raise ValueError(f"{gate_id}: assertions must target hashed evidence files")
        deps = requirements[gate_id].get("dependencies", [])
        if any(dep not in requirements for dep in deps):
            raise ValueError(f"{gate_id}: dependency references an unknown gate")
    return requirements, plans


def run(args: argparse.Namespace) -> int:
    matrix_path = args.matrix.resolve()
    plan_path = args.plan.resolve()
    matrix = read_json(matrix_path)
    plan = read_json(plan_path)
    plan["matrix_sha256"] = sha256(matrix_path)
    plan["plan_sha256"] = hashlib.sha256(canonical(plan)).hexdigest()
    actual_commit, actual_tree_hash, actual_clean = source_snapshot(Path(__file__).resolve().parents[1])
    if (plan.get("source_commit"), plan.get("source_tree_sha256"), plan.get("working_tree_clean")) != (actual_commit, actual_tree_hash, actual_clean):
        raise ValueError("plan source identity does not match the current repository worktree")
    requirements, gate_plans = validate_inputs(matrix, plan, args.blocking_class)
    external_dependencies = sorted({dependency for requirement in requirements.values()
                                    for dependency in requirement.get("dependencies", [])
                                    if dependency not in requirements})
    prerequisite_results: dict[str, dict[str, Any]] = {}
    if args.blocking_class == "PUBLIC_LAUNCH_BLOCKING":
        if not args.prerequisite_report or not args.prerequisite_report_sha256 or not args.prerequisite_evidence_dir:
            raise ValueError("public-launch runs require an RC report, its SHA-256, and the matching evidence directory")
        if sha256(args.prerequisite_report) != args.prerequisite_report_sha256:
            raise ValueError("RC prerequisite report SHA-256 mismatch")
        prerequisite = read_json(args.prerequisite_report)
        expected_identity = {**plan["identity"], "source_commit": plan["source_commit"],
                             "source_tree_sha256": plan["source_tree_sha256"],
                             "working_tree_clean": plan["working_tree_clean"],
                             "release_tag": plan.get("release_tag")}
        if any(prerequisite.get(key) != value for key, value in expected_identity.items()):
            raise ValueError("RC prerequisite report identity does not match public-launch run")
        if prerequisite.get("scope") != "MAINNET_RC" or prerequisite.get("blocking_class") != "RC_BLOCKING":
            raise ValueError("public-launch prerequisites must come from a MAINNET_RC report")
        if prerequisite.get("counts") != {"PASS": 98, "FAIL": 0, "BLOCKED": 0, "NOT_RUN": 0}:
            raise ValueError("all 98 current RC gates must have verified PASS before public-launch validation")
        prerequisite_results = prerequisite.get("gate_results", {})
        if len(prerequisite_results) != 98 or any(item.get("status") != "PASS" for item in prerequisite_results.values()):
            raise ValueError("RC prerequisite report does not contain 98 PASS gate results")
        journal_path = safe_path(args.prerequisite_evidence_dir.resolve(), "events.jsonl")
        if not journal_path.is_file() or sha256(journal_path) != prerequisite.get("event_journal_sha256"):
            raise ValueError("RC prerequisite journal is missing or does not match the report checksum")
        journal_events = load_events(journal_path)
        journal_results: dict[str, dict[str, Any]] = {}
        for event in journal_events:
            if (event.get("source_commit") == prerequisite["source_commit"]
                    and event.get("source_tree_sha256") == prerequisite["source_tree_sha256"]
                    and event.get("matrix_sha256") == prerequisite.get("source_matrix_sha256")
                    and event.get("identity") == {key: prerequisite[key] for key in ("network", "chain_id", "genesis_hash")}):
                journal_results[event["gate_id"]] = event["result"]
        if set(journal_results) != set(prerequisite_results):
            raise ValueError("RC prerequisite journal does not cover the report gate set")
        for gate_id, result in prerequisite_results.items():
            if result != journal_results[gate_id] or result.get("status") != "PASS":
                raise ValueError(f"RC prerequisite journal/result mismatch: {gate_id}")
            for artifact in result.get("evidence", []):
                artifact_path = safe_path(args.prerequisite_evidence_dir.resolve(), artifact["path"])
                if not artifact_path.is_file() or sha256(artifact_path) != artifact.get("sha256"):
                    raise ValueError(f"RC prerequisite evidence missing or corrupt: {gate_id}/{artifact['path']}")
        missing = [gate_id for gate_id in external_dependencies if gate_id not in prerequisite_results]
        if missing:
            raise ValueError(f"RC prerequisite report omits dependencies: {missing}")
        plan["prerequisite_report_sha256"] = args.prerequisite_report_sha256
        plan["plan_sha256"] = hashlib.sha256(canonical({key: value for key, value in plan.items() if key != "plan_sha256"})).hexdigest()
    elif args.prerequisite_report or args.prerequisite_report_sha256:
        raise ValueError("RC prerequisite report is only valid for PUBLIC_LAUNCH_BLOCKING runs")
    plan["blocking_class"] = args.blocking_class
    plan["plan_sha256"] = hashlib.sha256(canonical({key: value for key, value in plan.items() if key != "plan_sha256"})).hexdigest()
    root = args.evidence_dir.resolve()
    catalog_path = Path(__file__).resolve().parents[1] / "docs/releases/public-mainnet-rc4-gate-catalog.json"
    catalog_entries = read_json(catalog_path).get("gates", []) if catalog_path.is_file() else []
    manual_catalog_ids = {item["id"] for item in catalog_entries if item.get("execution_mode") == "MANUAL_ATTESTATION"}
    plan["evidence_root"] = str(root)
    root.mkdir(parents=True, exist_ok=True)
    journal = safe_path(root, plan.get("event_journal", "events.jsonl"))
    events = load_events(journal)
    latest: dict[str, dict[str, Any]] = {}
    latest.update({gate_id: prerequisite_results[gate_id] for gate_id in external_dependencies})
    for event in events:
        if (event.get("source_commit") != plan["source_commit"]
                or event.get("source_tree_sha256") != plan["source_tree_sha256"]
                or event.get("working_tree_clean") != plan["working_tree_clean"]
                or event.get("identity") != plan["identity"]
                or event.get("matrix_sha256") != plan["matrix_sha256"]
                or event.get("plan_sha256") != plan["plan_sha256"]):
            continue
        latest[event["gate_id"]] = event["result"]

    invalidated: list[str] = []
    for gate_id, result in list(latest.items()):
        if result.get("status") == "PASS":
            for evidence in result.get("evidence", []):
                path = safe_path(root, evidence["path"])
                if not path.is_file() or sha256(path) != evidence.get("sha256"):
                    latest[gate_id] = {"status": "BLOCKED", "detail": f"resume evidence missing or hash mismatch: {evidence['path']}", "evidence": result.get("evidence", [])}
                    invalidated.append(gate_id)
                    break
    changed = True
    while changed:
        changed = False
        for gate_id, requirement in requirements.items():
            prior = latest.get(gate_id)
            if prior and prior.get("status") == "PASS" and any(latest.get(dep, {}).get("status") != "PASS" for dep in requirement.get("dependencies", [])):
                latest[gate_id] = {"status": "BLOCKED", "detail": "a dependency no longer has verified PASS evidence", "evidence": prior.get("evidence", [])}
                invalidated.append(gate_id)
                changed = True

    previous = events[-1]["event_sha256"] if events else ZERO_HASH
    for gate_id in dict.fromkeys(invalidated):
        event = {"recorded_at": utc_now(), "gate_id": gate_id, "source_commit": plan["source_commit"],
                 "source_tree_sha256": plan["source_tree_sha256"], "working_tree_clean": plan["working_tree_clean"],
                 "matrix_sha256": plan["matrix_sha256"], "plan_sha256": plan["plan_sha256"],
                 "identity": plan["identity"], "result": latest[gate_id]}
        previous = append_event(journal, event, previous)
        events.append({**event, "event_sha256": previous})
    for gate_id, requirement in requirements.items():
        if gate_id in latest:
            continue
        deps = requirement.get("dependencies", [])
        failed_deps = [dep for dep in deps if latest.get(dep, {}).get("status") != "PASS"]
        if requirement.get("_runner_dependency_cycle"):
            result = {"status": "BLOCKED", "detail": "unresolved dependency cycle in canonical matrix", "evidence": []}
        elif failed_deps:
            result = {"status": "BLOCKED", "detail": f"dependencies not PASS: {', '.join(failed_deps)}", "evidence": []}
        elif gate_id not in gate_plans and gate_id in manual_catalog_ids:
            try:
                trust_path = args.trust_store or (Path(__file__).resolve().parents[1] / "docs/releases/rc-gate-trust-store.json")
                trust_store = read_json(trust_path)
                if not args.attestations_dir:
                    raise ValueError("attestations directory not provided")
                attestation_path = safe_path(args.attestations_dir.resolve(), f"{gate_id}.json")
                attestation = read_json(attestation_path)
                evidence_records = verify_manual_attestation(attestation, trust_store, gate_id=gate_id,
                                                             plan=plan, evidence_root=root)
                copied_attestation_rel = f"attestations/{gate_id}.json"
                copied_attestation_path = safe_path(root, copied_attestation_rel)
                copied_attestation_path.parent.mkdir(parents=True, exist_ok=True)
                copied_attestation_path.write_bytes(attestation_path.read_bytes())
                outcome = attestation["outcome"]
                result = {"status": outcome, "detail": "valid authorized Ed25519 human attestation" if outcome == "PASS" else "signed human outcome",
                          "evidence": evidence_records + [{"path": copied_attestation_rel, "sha256": sha256(copied_attestation_path)}],
                          "attestation_signer": attestation["signer_identity"], "attestation_role": attestation["role"]}
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                result = {"status": "BLOCKED", "detail": f"manual attestation unavailable or invalid: {error}", "evidence": []}
        elif gate_id not in gate_plans:
            result = latest.get(gate_id, {"status": "NOT_RUN", "detail": "no reviewed executable plan", "evidence": []})
        else:
            spec = gate_plans[gate_id]
            cwd_value = Path(spec.get("cwd", "."))
            cwd = ((Path(__file__).resolve().parents[1] / cwd_value).resolve()
                   if spec.get("evidence_mode") == "COMMAND_CONTRACT" and not cwd_value.is_absolute()
                   else cwd_value.resolve())
            if not cwd.is_dir():
                result = {"status": "BLOCKED", "detail": "command working directory is unavailable", "evidence": []}
            else:
                started = utc_now()
                try:
                    completed = subprocess.run(spec["command"], cwd=cwd, text=True, stdout=subprocess.PIPE,
                                               stderr=subprocess.STDOUT, timeout=spec.get("timeout_seconds", 3600), check=False)
                    log_rel = f"commands/{gate_id}.log"
                    log_path = safe_path(root, log_rel)
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    log_path.write_text(completed.stdout, encoding="utf-8")
                    records = [{"path": log_rel, "sha256": sha256(log_path)}]
                    problems: list[str] = []
                    if completed.returncode != 0:
                        result = {"status": "FAIL", "detail": f"command exit {completed.returncode}", "evidence": records}
                    elif spec.get("evidence_mode") == "COMMAND_CONTRACT":
                        contract = next(item for item in catalog_entries if item["id"] == gate_id)
                        evidence_rel = f"gate-results/{gate_id}.json"
                        evidence_path = safe_path(root, evidence_rel)
                        evidence_path.parent.mkdir(parents=True, exist_ok=True)
                        started_at = started
                        envelope = {"gate_id": gate_id, **plan["identity"], "source_commit": plan["source_commit"],
                                    "source_tree_sha256": plan["source_tree_sha256"],
                                    "environment": "mainnet-source-review" if plan.get("scope") == "PRE_FREEZE_SOURCE" else "mainnet-public-rc",
                                    "command": spec["command"], "exit_code": completed.returncode, "started_at": started_at,
                                    "finished_at": utc_now(), "checks": {check["check_id"]: True for check in contract["automated_contract"]},
                                    "evidence_refs": spec["evidence_refs"],
                                    "evidence_ref_sources": {ref: "command-output" for ref in contract["command_evidence_refs"]}
                                    | {item["ref"]: item["path"] for item in spec.get("external_evidence", [])},
                                    "artifacts": records}
                        evidence_path.write_text(json.dumps(envelope, sort_keys=True, indent=2) + "\n", encoding="utf-8")
                        records.append({"path": evidence_rel, "sha256": sha256(evidence_path)})
                        problems: list[str] = []
                        expected_environment = "mainnet-source-review" if plan.get("scope") == "PRE_FREEZE_SOURCE" else "mainnet-public-rc"
                        for external in spec.get("external_evidence", []):
                            rel = external["path"]
                            path = safe_path(root, rel)
                            if not path.is_file():
                                problems.append(f"missing external evidence {external['ref']}: {rel}")
                                continue
                            try:
                                observed = read_json(path)
                                expected_fields = {"evidence_ref", "gate_id", "network", "chain_id", "genesis_hash",
                                                   "source_commit", "source_tree_sha256", "release_tag", "environment", "checks"}
                                if set(observed) != expected_fields:
                                    problems.append(f"external evidence schema mismatch: {rel}")
                                    continue
                                expected = {"evidence_ref": external["ref"], "gate_id": gate_id,
                                            **plan["identity"], "source_commit": plan["source_commit"],
                                            "source_tree_sha256": plan["source_tree_sha256"],
                                            "release_tag": plan.get("release_tag"), "environment": expected_environment}
                                if any(observed.get(key) != value for key, value in expected.items()):
                                    problems.append(f"external evidence provenance mismatch: {rel}")
                                checks = observed.get("checks")
                                if not isinstance(checks, dict) or not checks or any(value is not True for value in checks.values()):
                                    problems.append(f"external evidence has missing/false checks: {rel}")
                            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                                problems.append(f"external evidence invalid: {rel} ({error})")
                            records.append({"path": rel, "sha256": sha256(path)})
                        result = {"status": "BLOCKED" if problems else "PASS",
                                  "detail": "; ".join(problems) if problems else "canonical command contract and bound external evidence passed",
                                  "evidence": records}
                    else:
                        for item in spec["evidence"]:
                            rel = item["path"]
                            path = safe_path(root, rel)
                            record: dict[str, Any] = {"path": rel, "sha256": sha256(path) if path.is_file() else None}
                            records.append(record)
                            if not path.is_file():
                                problems.append(f"missing evidence: {rel}")
                                continue
                            if item.get("sha256") and item["sha256"] != record["sha256"]:
                                problems.append(f"evidence hash mismatch: {rel}")
                        identity_rel = spec["identity_evidence"]
                        try:
                            observed_identity = read_json(safe_path(root, identity_rel))
                            for key, expected in {**plan["identity"], "source_commit": plan["source_commit"],
                                                  "source_tree_sha256": plan["source_tree_sha256"],
                                                  "working_tree_clean": plan["working_tree_clean"]}.items():
                                if observed_identity.get(key) != expected:
                                    problems.append(f"identity mismatch: {identity_rel} field {key}")
                            expected_environment = "mainnet-source-review" if plan.get("scope") == "PRE_FREEZE_SOURCE" else "mainnet-public-rc"
                            if observed_identity.get("environment") != expected_environment:
                                problems.append(f"environment is not {expected_environment}: {observed_identity.get('environment')}")
                        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                            problems.append(f"identity evidence invalid: {identity_rel} ({error})")
                        for assertion in spec["assertions"]:
                            path = safe_path(root, assertion["evidence_path"])
                            try:
                                observed = json_pointer(read_json(path), assertion["pointer"])
                                if observed != assertion["equals"]:
                                    problems.append(f"assertion mismatch: {assertion['evidence_path']}#{assertion['pointer']}")
                            except (OSError, ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
                                problems.append(f"assertion unavailable: {assertion['evidence_path']} ({error})")
                        result = {"status": "BLOCKED" if problems else "PASS", "detail": "; ".join(problems) if problems else "command and evidence assertions passed", "evidence": records}
                except subprocess.TimeoutExpired as error:
                    log_rel = f"commands/{gate_id}.log"
                    log_path = safe_path(root, log_rel)
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    output = error.stdout or ""
                    log_path.write_text(output if isinstance(output, str) else output.decode(errors="replace"), encoding="utf-8")
                    result = {"status": "FAIL", "detail": f"command timed out after {error.timeout}s", "evidence": [{"path": log_rel, "sha256": sha256(log_path)}]}
                except OSError as error:
                    result = {"status": "BLOCKED", "detail": f"command could not start: {error}", "evidence": []}
                result.update({"started_at": started, "finished_at": utc_now(), "command": spec["command"]})
        latest[gate_id] = result
        event = {"recorded_at": utc_now(), "gate_id": gate_id, "source_commit": plan["source_commit"],
                 "source_tree_sha256": plan["source_tree_sha256"], "working_tree_clean": plan["working_tree_clean"],
                 "matrix_sha256": plan["matrix_sha256"], "plan_sha256": plan["plan_sha256"],
                 "identity": plan["identity"], "result": result}
        previous = append_event(journal, event, previous)
        events.append({**event, "event_sha256": previous})

    ordered_results = {gate_id: latest.get(gate_id, {"status": "NOT_RUN", "detail": "not evaluated", "evidence": []}) for gate_id in requirements}
    report, markdown = render_report(matrix, plan, ordered_results, events)
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    args.report_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.report_markdown.write_text(markdown, encoding="utf-8")
    return 1 if any(item["status"] == "FAIL" for item in ordered_results.values()) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=Path("public-mainnet-rc-revalidation.json"))
    parser.add_argument("--plan", type=Path, required=True, help="reviewed per-gate command/evidence plan")
    parser.add_argument("--evidence-dir", type=Path, required=True, help="append-only run evidence directory")
    parser.add_argument("--report-json", type=Path, required=True)
    parser.add_argument("--report-markdown", type=Path, required=True)
    parser.add_argument("--blocking-class", choices=("RC_BLOCKING", "PUBLIC_LAUNCH_BLOCKING"), default="RC_BLOCKING")
    parser.add_argument("--trust-store", type=Path, help="explicit Ed25519 public-key allowlist for signed human attestations")
    parser.add_argument("--attestations-dir", type=Path, help="directory containing <GATE-ID>.json signed attestations")
    parser.add_argument("--prerequisite-report", type=Path, help="identity-bound RC report required by public-launch gates")
    parser.add_argument("--prerequisite-report-sha256", help="expected SHA-256 of the RC prerequisite report")
    parser.add_argument("--prerequisite-evidence-dir", type=Path, help="evidence directory whose journal/checksums back the RC prerequisite report")
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"gate runner: BLOCKED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
