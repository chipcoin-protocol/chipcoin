"""Phase 1 reporting helpers for observer-only reward tracking."""

from __future__ import annotations

from collections import Counter

from .models import (
    BroadcastPreflight,
    NodeEpochSummary,
    NodeObservation,
    PayoutBatch,
    PayoutBatchItem,
    TransactionPlan,
    TransactionPlanInput,
    TransactionPlanOutput,
    TransactionArtifact,
)


def build_epoch_summary(epoch_index: int, summaries: list[NodeEpochSummary]) -> dict[str, object]:
    """Return a compact epoch-level summary."""

    rejection_counter = Counter(
        summary.rejection_reason for summary in summaries if summary.rejection_reason is not None
    )
    return {
        "epoch_index": epoch_index,
        "node_count": len(summaries),
        "eligible_node_count": sum(1 for summary in summaries if summary.final_eligible),
        "rejected_node_count": sum(1 for summary in summaries if not summary.final_eligible),
        "top_rejection_codes": dict(sorted(rejection_counter.items())),
        "epoch_reason_code": "no_eligible_nodes" if summaries and not any(summary.final_eligible for summary in summaries) else None,
    }


def eligible_nodes_report(summaries: list[NodeEpochSummary]) -> list[dict[str, object]]:
    """Return eligible nodes in stable order."""

    return [
        {
            "epoch_index": summary.epoch_index,
            "node_id": summary.node_id,
            "payout_address": summary.payout_address,
            "observed_facts": {
                "host": summary.host,
                "port": summary.port,
                "success_count": summary.success_count,
                "failure_count": summary.failure_count,
                "checked_observation_count": summary.checked_observation_count,
                "observation_count": summary.observation_count,
                "public_ip": summary.public_ip,
                "subnet_key": summary.subnet_key,
                "handshake_ok": summary.handshake_ok,
                "network_ok": summary.network_ok,
            },
            "derived_eligibility": {
                "registration_status": summary.registration_status,
                "warmup_status": summary.warmup_status,
                "concentration_status": summary.concentration_status,
                "final_eligible": summary.final_eligible,
                "rejection_reason": summary.rejection_reason,
            },
            "provisional_fields": _provisional_fields(summary),
        }
        for summary in sorted(summaries, key=lambda item: (item.node_id, item.payout_address))
        if summary.final_eligible
    ]


def rejected_nodes_report(summaries: list[NodeEpochSummary]) -> list[dict[str, object]]:
    """Return rejected nodes with stable reason codes."""

    return [
        {
            "epoch_index": summary.epoch_index,
            "node_id": summary.node_id,
            "payout_address": summary.payout_address,
            "observed_facts": {
                "host": summary.host,
                "port": summary.port,
                "success_count": summary.success_count,
                "failure_count": summary.failure_count,
                "checked_observation_count": summary.checked_observation_count,
                "observation_count": summary.observation_count,
                "public_ip": summary.public_ip,
                "subnet_key": summary.subnet_key,
                "handshake_ok": summary.handshake_ok,
                "network_ok": summary.network_ok,
            },
            "derived_eligibility": {
                "registration_status": summary.registration_status,
                "warmup_status": summary.warmup_status,
                "concentration_status": summary.concentration_status,
                "final_eligible": summary.final_eligible,
                "rejection_reason": summary.rejection_reason,
            },
            "provisional_fields": _provisional_fields(summary),
        }
        for summary in sorted(summaries, key=lambda item: (item.node_id, item.payout_address))
        if not summary.final_eligible
    ]


def concentration_report(summaries: list[NodeEpochSummary]) -> dict[str, object]:
    """Return concentration counts by deterministic grouping keys."""

    by_ip = Counter(summary.public_ip for summary in summaries if summary.public_ip is not None)
    by_subnet = Counter(summary.subnet_key for summary in summaries if summary.subnet_key is not None)
    by_fingerprint = Counter(summary.fingerprint for summary in summaries if summary.fingerprint is not None)
    return {
        "public_ip_counts": dict(sorted(by_ip.items())),
        "subnet_counts": dict(sorted(by_subnet.items())),
        "fingerprint_counts": dict(sorted(by_fingerprint.items())),
    }


def observation_stats_report(epoch_index: int, observations: list[NodeObservation]) -> dict[str, object]:
    """Return one compact observation counter report."""

    filtered = [observation for observation in observations if observation.epoch_index == epoch_index]
    by_outcome = Counter(observation.outcome for observation in filtered)
    by_reason = Counter(observation.reason_code for observation in filtered if observation.reason_code is not None)
    return {
        "epoch_index": epoch_index,
        "observation_count": len(filtered),
        "outcome_counts": dict(sorted(by_outcome.items())),
        "reason_code_counts": dict(sorted(by_reason.items())),
    }


def payout_batch_report(batch: PayoutBatch, items: list[PayoutBatchItem]) -> dict[str, object]:
    """Return one dry-run payout batch report."""

    return {
        "batch_id": batch.batch_id,
        "epoch_index": batch.epoch_index,
        "network": batch.network,
        "status": batch.status,
        "dry_run": True,
        "funds_moved": False,
        "transaction_created": False,
        "warning": "allocation is based on current observer evidence only",
        "scheduled_node_reward_chipbits": batch.scheduled_node_reward_chipbits,
        "eligible_node_count": batch.eligible_node_count,
        "rejected_node_count": batch.rejected_node_count,
        "allocated_total_chipbits": batch.allocated_total_chipbits,
        "unallocated_total_chipbits": batch.unallocated_total_chipbits,
        "zero_allocation_reason": batch.zero_allocation_reason,
        "provisional_evidence_present": batch.provisional_evidence_count > 0,
        "provisional_evidence_count": batch.provisional_evidence_count,
        "created_at": batch.created_at,
        "approved_at": batch.approved_at,
        "reviewed_at": batch.reviewed_at,
        "created_by": batch.created_by,
        "reviewed_by": batch.reviewed_by,
        "operator_note": batch.operator_note,
        "items": [
            {
                "allocation_rank": item.allocation_rank,
                "node_id": item.node_id,
                "payout_address": item.payout_address,
                "allocated_chipbits": item.allocated_chipbits,
                "remainder_assigned": item.remainder_assigned,
                "provisional_fields": list(item.provisional_fields),
            }
            for item in items
        ],
    }


def payout_batch_list_report(batches: list[PayoutBatch]) -> list[dict[str, object]]:
    """Return a compact list view of persisted dry-run payout batches."""

    return [
        {
            "batch_id": batch.batch_id,
            "epoch_index": batch.epoch_index,
            "network": batch.network,
            "status": batch.status,
            "scheduled_node_reward_chipbits": batch.scheduled_node_reward_chipbits,
            "eligible_node_count": batch.eligible_node_count,
            "allocated_total_chipbits": batch.allocated_total_chipbits,
            "unallocated_total_chipbits": batch.unallocated_total_chipbits,
            "zero_allocation_reason": batch.zero_allocation_reason,
            "provisional_evidence_present": batch.provisional_evidence_count > 0,
            "created_at": batch.created_at,
            "approved_at": batch.approved_at,
            "reviewed_at": batch.reviewed_at,
        }
        for batch in batches
    ]


def batch_items_report(items: list[PayoutBatchItem]) -> list[dict[str, object]]:
    """Return one compact item list for dry-run review."""

    return [
        {
            "allocation_rank": item.allocation_rank,
            "node_id": item.node_id,
            "payout_address": item.payout_address,
            "allocated_chipbits": item.allocated_chipbits,
            "remainder_assigned": item.remainder_assigned,
            "provisional_fields": list(item.provisional_fields),
        }
        for item in items
    ]


def batch_review_report(
    batch: PayoutBatch,
    items: list[PayoutBatchItem],
    *,
    epoch_summaries: list[NodeEpochSummary],
    validation: dict[str, object],
) -> dict[str, object]:
    """Return one operator-facing dry-run review summary."""

    rejection_counter = Counter(
        summary.rejection_reason for summary in epoch_summaries if summary.rejection_reason is not None
    )
    concentration_counter = Counter(
        summary.concentration_status
        for summary in epoch_summaries
        if summary.concentration_status != "ok"
    )
    provisional_counter = Counter()
    for summary in epoch_summaries:
        for field in _provisional_fields(summary):
            provisional_counter[field] += 1
    return {
        "batch_id": batch.batch_id,
        "epoch_index": batch.epoch_index,
        "status": batch.status,
        "dry_run": True,
        "review_result": validation["review_result"],
        "review_reason": batch.review_reason,
        "review_snapshot_hash": batch.review_snapshot_hash,
        "operator_note": batch.operator_note,
        "decision_summary": {
            "scheduled_node_reward_chipbits": batch.scheduled_node_reward_chipbits,
            "eligible_node_count": batch.eligible_node_count,
            "rejected_node_count": batch.rejected_node_count,
            "allocated_total_chipbits": batch.allocated_total_chipbits,
            "unallocated_total_chipbits": batch.unallocated_total_chipbits,
            "zero_allocation_reason": batch.zero_allocation_reason,
        },
        "eligibility_summary_by_reason_code": dict(sorted(rejection_counter.items())),
        "provisional_evidence_summary": dict(sorted(provisional_counter.items())),
        "concentration_summary": dict(sorted(concentration_counter.items())),
        "allocation_summary": {
            "item_count": len(items),
            "remainder_assigned_count": sum(1 for item in items if item.remainder_assigned),
            "provisional_item_count": sum(1 for item in items if item.provisional_fields),
        },
        "validation_checks": validation["checks"],
    }


def batch_audit_report(
    batch: PayoutBatch,
    items: list[PayoutBatchItem],
    *,
    validation: dict[str, object],
) -> dict[str, object]:
    """Return a formal dry-run audit payload."""

    return {
        "batch_id": batch.batch_id,
        "epoch_index": batch.epoch_index,
        "dry_run": True,
        "review_result": validation["review_result"],
        "checks": validation["checks"],
        "errors": validation["errors"],
        "scheduled_reward_chipbits": validation["scheduled_reward_chipbits"],
        "expected_remainder_count": validation["expected_remainder_count"],
        "actual_remainder_count": validation["actual_remainder_count"],
        "expected_provisional_evidence_count": validation["expected_provisional_evidence_count"],
        "expected_item_provisional_flag_count": validation["expected_item_provisional_flag_count"],
        "actual_item_provisional_flag_count": validation["actual_item_provisional_flag_count"],
        "duplicate_node_ids": validation["duplicate_node_ids"],
        "duplicate_payout_addresses": validation["duplicate_payout_addresses"],
        "item_count": len(items),
        "review_snapshot_hash": batch.review_snapshot_hash,
    }


def transaction_plan_report(
    plan: TransactionPlan,
    inputs: list[TransactionPlanInput],
    outputs: list[TransactionPlanOutput],
) -> dict[str, object]:
    """Return one dry transaction plan report."""

    return {
        "plan_id": plan.plan_id,
        "batch_id": plan.batch_id,
        "status": plan.status,
        "dry_run": True,
        "signed": False,
        "broadcasted": False,
        "wallet_mutation": False,
        "funding_assumption": plan.funding_assumption,
        "input_count": plan.input_count,
        "output_count": plan.output_count,
        "estimated_fee_chipbits": plan.estimated_fee_chipbits,
        "total_input_chipbits": plan.total_input_chipbits,
        "total_recipient_chipbits": plan.total_recipient_chipbits,
        "change_chipbits": plan.change_chipbits,
        "dust_dropped_chipbits": plan.dust_dropped_chipbits,
        "insufficient_funds": plan.insufficient_funds,
        "created_at": plan.created_at,
        "created_by": plan.created_by,
        "plan_snapshot_hash": plan.plan_snapshot_hash,
        "fee_rate_chipbits_per_weight_unit": plan.fee_rate_chipbits_per_weight_unit,
        "dust_threshold_chipbits": plan.dust_threshold_chipbits,
        "min_input_confirmations": plan.min_input_confirmations,
        "change_address": plan.change_address,
        "dust_policy": plan.dust_policy,
        "provisional_warning_inherited": plan.provisional_warning_inherited,
        "invalid_reason": plan.invalid_reason,
        "inputs": [
            {
                "input_index": item.input_index,
                "txid": item.txid,
                "vout": item.vout,
                "amount_chipbits": item.amount_chipbits,
                "recipient": item.recipient,
                "confirmations": item.confirmations,
            }
            for item in inputs
        ],
        "outputs": [
            {
                "output_index": item.output_index,
                "output_kind": item.output_kind,
                "recipient": item.recipient,
                "amount_chipbits": item.amount_chipbits,
                "batch_node_id": item.batch_node_id,
            }
            for item in outputs
        ],
    }


def transaction_plan_list_report(plans: list[TransactionPlan]) -> list[dict[str, object]]:
    """Return a compact list view of persisted transaction plans."""

    return [
        {
            "plan_id": plan.plan_id,
            "batch_id": plan.batch_id,
            "status": plan.status,
            "dry_run": True,
            "signed": False,
            "broadcasted": False,
            "wallet_mutation": False,
            "estimated_fee_chipbits": plan.estimated_fee_chipbits,
            "total_input_chipbits": plan.total_input_chipbits,
            "total_recipient_chipbits": plan.total_recipient_chipbits,
            "change_chipbits": plan.change_chipbits,
            "insufficient_funds": plan.insufficient_funds,
            "created_at": plan.created_at,
        }
        for plan in plans
    ]


def transaction_artifact_report(artifact: TransactionArtifact) -> dict[str, object]:
    """Return one unsigned or signed transaction artifact report."""

    return {
        "artifact_id": artifact.artifact_id,
        "plan_id": artifact.plan_id,
        "batch_id": artifact.batch_id,
        "status": artifact.status,
        "broadcasted": artifact.broadcasted,
        "sent": artifact.sent,
        "wallet_mutation": artifact.wallet_mutation,
        "unsigned_tx_snapshot_hash": artifact.unsigned_tx_snapshot_hash,
        "signed_tx_snapshot_hash": artifact.signed_tx_snapshot_hash,
        "signer_type": artifact.signer_type,
        "created_at": artifact.created_at,
        "created_by": artifact.created_by,
        "validation_result": artifact.validation_result,
        "invalid_reason": artifact.invalid_reason,
        "tx_hex": artifact.tx_hex,
    }


def transaction_artifact_list_report(artifacts: list[TransactionArtifact]) -> list[dict[str, object]]:
    """Return a compact list view of local transaction artifacts."""

    return [
        {
            "artifact_id": artifact.artifact_id,
            "plan_id": artifact.plan_id,
            "batch_id": artifact.batch_id,
            "status": artifact.status,
            "broadcasted": artifact.broadcasted,
            "sent": artifact.sent,
            "wallet_mutation": artifact.wallet_mutation,
            "signer_type": artifact.signer_type,
            "created_at": artifact.created_at,
            "validation_result": artifact.validation_result,
        }
        for artifact in artifacts
    ]


def broadcast_preflight_report(
    preflight: BroadcastPreflight,
    *,
    input_outpoints: list[tuple[int, str, int]],
) -> dict[str, object]:
    """Return one local-only broadcast preparation report."""

    return {
        "preflight_id": preflight.preflight_id,
        "artifact_id": preflight.artifact_id,
        "plan_id": preflight.plan_id,
        "batch_id": preflight.batch_id,
        "txid": preflight.txid,
        "serialization_hash": preflight.serialization_hash,
        "status": preflight.status,
        "preflight_result": preflight.preflight_result,
        "blocking_reason": preflight.blocking_reason,
        "warning_count": preflight.warning_count,
        "created_at": preflight.created_at,
        "created_by": preflight.created_by,
        "network": preflight.network,
        "ready_for_manual_broadcast": preflight.ready_for_manual_broadcast,
        "broadcasted": False,
        "submitted": False,
        "auto_send": False,
        "manual_broadcast_required": True,
        "warnings": [] if not preflight.warnings_json else __import__("json").loads(preflight.warnings_json),
        "input_outpoints": [
            {"input_index": index, "txid": txid, "vout": vout}
            for index, txid, vout in input_outpoints
        ],
    }


def broadcast_preflight_list_report(preflights: list[BroadcastPreflight]) -> list[dict[str, object]]:
    """Return a compact list view of broadcast-preflight records."""

    return [
        {
            "preflight_id": preflight.preflight_id,
            "artifact_id": preflight.artifact_id,
            "plan_id": preflight.plan_id,
            "batch_id": preflight.batch_id,
            "txid": preflight.txid,
            "status": preflight.status,
            "preflight_result": preflight.preflight_result,
            "blocking_reason": preflight.blocking_reason,
            "warning_count": preflight.warning_count,
            "network": preflight.network,
            "ready_for_manual_broadcast": preflight.ready_for_manual_broadcast,
            "broadcasted": False,
            "submitted": False,
            "auto_send": False,
            "manual_broadcast_required": True,
            "created_at": preflight.created_at,
        }
        for preflight in preflights
    ]


def _provisional_fields(summary: NodeEpochSummary) -> list[str]:
    provisional: list[str] = []
    if summary.endpoint_source == "provisional":
        provisional.extend(["host", "port"])
    if summary.ban_source == "provisional":
        provisional.append("banned")
    if summary.fingerprint is None:
        provisional.append("fingerprint")
    return provisional
