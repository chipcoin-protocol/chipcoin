"""Local-only broadcast preparation for signed transaction artifacts."""

from __future__ import annotations

import hashlib
import json

from ..consensus.serialization import deserialize_transaction, serialize_transaction
from .models import BroadcastPreflight, PayoutBatch, TransactionArtifact, TransactionPlan, TransactionPlanInput, TransactionPlanOutput
from .signing import validate_signed_transaction_artifact


def export_signed_transaction_artifact(artifact: TransactionArtifact) -> dict[str, object]:
    """Return deterministic local export data for one signed artifact."""

    transaction = deserialize_signed_transaction_artifact(artifact)
    serialized = serialize_transaction(transaction)
    return {
        "artifact_id": artifact.artifact_id,
        "plan_id": artifact.plan_id,
        "batch_id": artifact.batch_id,
        "txid": transaction.txid(),
        "tx_hex": serialized.hex(),
        "serialization_hash": hashlib.sha256(serialized).hexdigest(),
        "broadcasted": False,
        "submitted": False,
        "auto_send": False,
        "manual_broadcast_required": True,
    }


def deserialize_signed_transaction_artifact(artifact: TransactionArtifact):
    """Decode and verify a signed transaction artifact from stored hex."""

    if artifact.status != "signed":
        raise ValueError("artifact is not signed")
    payload = bytes.fromhex(artifact.tx_hex)
    transaction, offset = deserialize_transaction(payload)
    if offset != len(payload):
        raise ValueError("artifact transaction payload has trailing bytes")
    return transaction


def build_broadcast_preflight(
    *,
    artifact: TransactionArtifact,
    plan: TransactionPlan,
    batch: PayoutBatch,
    inputs: list[TransactionPlanInput],
    outputs: list[TransactionPlanOutput],
    network: str,
    created_at: int,
    created_by: str | None = None,
    existing_ready_input_conflicts: dict[tuple[str, int], list[str]] | None = None,
) -> tuple[BroadcastPreflight, dict[str, object], list[tuple[int, str, int]]]:
    """Build one local preflight record without submitting anything."""

    warnings: list[str] = []
    blocking_reason = None
    transaction = None

    if artifact.status != "signed":
        blocking_reason = "artifact_not_signed"
    elif artifact.validation_result != "pass":
        blocking_reason = "artifact_validation_failed"
    elif artifact.invalid_reason is not None:
        blocking_reason = artifact.invalid_reason
    elif artifact.broadcasted:
        blocking_reason = "artifact_already_marked_broadcasted"
    elif artifact.sent:
        blocking_reason = "artifact_already_marked_sent"
    elif artifact.plan_id != plan.plan_id or artifact.batch_id != batch.batch_id:
        blocking_reason = "artifact_linkage_mismatch"
    elif batch.network != network:
        blocking_reason = "network_mismatch"
    else:
        transaction = deserialize_signed_transaction_artifact(artifact)
        validation = validate_signed_transaction_artifact(
            plan=plan,
            transaction=transaction,
            inputs=inputs,
            outputs=outputs,
        )
        if not validation["valid"]:
            blocking_reason = str(validation["invalid_reason"])

    if transaction is not None and blocking_reason is None:
        serialized = serialize_transaction(transaction)
        txid = transaction.txid()
        serialization_hash = hashlib.sha256(serialized).hexdigest()
        expected_inputs = [(entry.txid, entry.vout) for entry in sorted(inputs, key=lambda item: item.input_index)]
        actual_inputs = [(item.previous_output.txid, item.previous_output.index) for item in transaction.inputs]
        expected_outputs = [(entry.recipient, entry.amount_chipbits) for entry in sorted(outputs, key=lambda item: item.output_index)]
        actual_outputs = [(item.recipient, int(item.value)) for item in transaction.outputs]
        conflict_map = existing_ready_input_conflicts or {}
        duplicate_input_conflicts = {
            f"{txid_hex}:{vout}": preflight_ids
            for (txid_hex, vout), preflight_ids in conflict_map.items()
            if (txid_hex, vout) in actual_inputs
        }
        if expected_inputs != actual_inputs:
            blocking_reason = "signed_input_mismatch"
        elif expected_outputs != actual_outputs:
            blocking_reason = "signed_output_mismatch"
        elif artifact.tx_hex != serialized.hex():
            blocking_reason = "artifact_serialization_mismatch"
        elif duplicate_input_conflicts:
            blocking_reason = "duplicate_input_preflight_conflict"
        if blocking_reason is None:
            warnings.append("stale_utxo_detection_unverified")
            if artifact.signer_type == "stub":
                warnings.append("stub_signature_artifact")
        checks = {
            "artifact_status_valid": artifact.status == "signed",
            "artifact_not_terminal": not artifact.broadcasted and not artifact.sent,
            "artifact_plan_batch_linkage_exact": artifact.plan_id == plan.plan_id and artifact.batch_id == batch.batch_id,
            "network_matches_target": batch.network == network,
            "tx_ready_for_serialization": True,
            "txid_reproducible": txid == transaction.txid(),
            "fee_and_output_totals_consistent": (
                plan.total_input_chipbits == plan.total_recipient_chipbits + plan.change_chipbits + plan.estimated_fee_chipbits
            ),
            "signed_inputs_match_plan": expected_inputs == actual_inputs,
            "signed_outputs_match_plan": expected_outputs == actual_outputs,
            "duplicate_inputs_not_prepared_locally": not duplicate_input_conflicts,
            "stale_utxo_detection_authoritative": False,
        }
    else:
        txid = ""
        serialization_hash = ""
        duplicate_input_conflicts = {}
        checks = {
            "artifact_status_valid": artifact.status == "signed",
            "artifact_not_terminal": not artifact.broadcasted and not artifact.sent,
            "artifact_plan_batch_linkage_exact": artifact.plan_id == plan.plan_id and artifact.batch_id == batch.batch_id,
            "network_matches_target": batch.network == network,
            "tx_ready_for_serialization": False,
            "txid_reproducible": False,
            "fee_and_output_totals_consistent": False,
            "signed_inputs_match_plan": False,
            "signed_outputs_match_plan": False,
            "duplicate_inputs_not_prepared_locally": True,
            "stale_utxo_detection_authoritative": False,
        }

    ready = blocking_reason is None
    preflight = BroadcastPreflight(
        preflight_id=f"preflight-{artifact.artifact_id}-{created_at}",
        artifact_id=artifact.artifact_id,
        batch_id=artifact.batch_id,
        plan_id=artifact.plan_id,
        txid=txid,
        serialization_hash=serialization_hash,
        status="prepared" if ready else "blocked",
        preflight_result="warn" if ready and warnings else "pass" if ready else "fail",
        blocking_reason=blocking_reason,
        warning_count=len(warnings),
        created_at=created_at,
        created_by=created_by,
        network=network,
        ready_for_manual_broadcast=ready,
        warnings_json=json.dumps(warnings, sort_keys=True),
    )
    report = {
        "preflight_id": preflight.preflight_id,
        "artifact_id": artifact.artifact_id,
        "plan_id": plan.plan_id,
        "batch_id": batch.batch_id,
        "txid": txid,
        "serialization_hash": serialization_hash,
        "status": preflight.status,
        "preflight_result": preflight.preflight_result,
        "blocking_reason": blocking_reason,
        "warnings": warnings,
        "warning_count": len(warnings),
        "duplicate_input_conflicts": duplicate_input_conflicts,
        "checks": checks,
        "broadcasted": False,
        "submitted": False,
        "auto_send": False,
        "manual_broadcast_required": True,
        "ready_for_manual_broadcast": ready,
    }
    indexed_inputs = [
        (index, entry.txid, entry.vout) for index, entry in enumerate(sorted(inputs, key=lambda item: item.input_index))
    ]
    return preflight, report, indexed_inputs
