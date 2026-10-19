#!/usr/bin/env python3
"""Fail-closed, resumable evidence runner for the public-mainnet RC matrix.

The matrix is never edited. Only gates explicitly described in a reviewed plan
can run; PASS requires a successful command and matching, identity-bound
evidence assertions. Commands are argv arrays and are never run through a shell.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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
        "source_commit": plan["source_commit"],
        "source_tree_sha256": plan["source_tree_sha256"],
        "working_tree_clean": plan["working_tree_clean"],
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


def validate_inputs(matrix: dict[str, Any], plan: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    raw_requirements = matrix.get("requirements", [])
    requirements = {gate["id"]: gate for gate in raw_requirements if gate.get("blocking") == "RC_BLOCKING"}
    if len(requirements) != 98 or len(raw_requirements) != 98:
        raise ValueError(f"expected 98 unique blocking requirements, found {len(requirements)}")
    if any(dep not in requirements for gate in requirements.values() for dep in gate.get("dependencies", [])):
        raise ValueError("canonical matrix has an unknown dependency")
    ordered: dict[str, dict[str, Any]] = {}
    remaining = dict(requirements)
    while remaining:
        ready = [gate_id for gate_id, gate in remaining.items() if set(gate.get("dependencies", [])).issubset(ordered)]
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
    if identity.get("network") != "mainnet" or identity.get("chain_id") != matrix.get("chain_id"):
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
    unknown = sorted(set(plans) - set(requirements))
    if unknown:
        raise ValueError(f"plan includes unknown gate ids: {unknown}")
    for gate_id, spec in plans.items():
        gate_class = requirements[gate_id].get("revalidation_class")
        if scope == "PRE_FREEZE_SOURCE" and gate_class != "SOURCE_REVALIDATION":
            raise ValueError(f"{gate_id}: only SOURCE_REVALIDATION gates may run before genesis freeze")
        argv = spec.get("command")
        if not isinstance(argv, list) or not argv or not all(isinstance(part, str) for part in argv):
            raise ValueError(f"{gate_id}: command must be a non-empty argv array")
        if not spec.get("evidence") or not spec.get("assertions"):
            raise ValueError(f"{gate_id}: evidence and explicit JSON assertions are required for PASS")
        required_refs = set(requirements[gate_id].get("required_evidence", []))
        if not required_refs.issubset(set(spec.get("evidence_refs", []))):
            raise ValueError(f"{gate_id}: plan does not cover all canonical evidence references")
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
    requirements, gate_plans = validate_inputs(matrix, plan)
    root = args.evidence_dir.resolve()
    plan["evidence_root"] = str(root)
    root.mkdir(parents=True, exist_ok=True)
    journal = safe_path(root, plan.get("event_journal", "events.jsonl"))
    events = load_events(journal)
    latest: dict[str, dict[str, Any]] = {}
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
        elif gate_id not in gate_plans:
            result = latest.get(gate_id, {"status": "NOT_RUN", "detail": "no reviewed executable plan", "evidence": []})
        else:
            spec = gate_plans[gate_id]
            cwd = Path(spec.get("cwd", ".")).resolve()
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
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"gate runner: BLOCKED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
