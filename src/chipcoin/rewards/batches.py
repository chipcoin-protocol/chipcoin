"""Dry-run payout batch allocation for observer-only rewards."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
import hashlib
import json

from ..config import get_network_config
from ..consensus.economics import node_reward_pool_chipbits
from .models import NodeEpochSummary, PayoutBatch, PayoutBatchItem


def scheduled_epoch_reward_chipbits(*, epoch_index: int, network: str) -> int:
    """Return the consensus-scheduled node reward attached to one epoch."""

    params = get_network_config(network).params
    closing_height = ((epoch_index + 1) * params.epoch_length_blocks) - 1
    return node_reward_pool_chipbits(closing_height, params)


def build_dry_run_batch(
    *,
    epoch_index: int,
    network: str,
    summaries: list[NodeEpochSummary],
    created_at: int,
    created_by: str | None = None,
    operator_note: str | None = None,
) -> tuple[PayoutBatch, list[PayoutBatchItem]]:
    """Build one deterministic dry-run payout batch from stored epoch summaries."""

    batch_id = f"dryrun-{network}-epoch-{epoch_index:06d}-{created_at}"
    scheduled_reward = scheduled_epoch_reward_chipbits(epoch_index=epoch_index, network=network)
    ordered_summaries = sorted(summaries, key=lambda item: (item.node_id, item.payout_address))
    eligible_summaries = [summary for summary in ordered_summaries if summary.final_eligible]
    rejected_count = sum(1 for summary in ordered_summaries if not summary.final_eligible)
    provisional_evidence_count = sum(len(_provisional_fields(summary)) for summary in ordered_summaries)

    if not eligible_summaries:
        batch = PayoutBatch(
            batch_id=batch_id,
            epoch_index=epoch_index,
            network=network,
            status="proposed",
            scheduled_node_reward_chipbits=scheduled_reward,
            eligible_node_count=0,
            rejected_node_count=rejected_count,
            allocated_total_chipbits=0,
            unallocated_total_chipbits=scheduled_reward,
            zero_allocation_reason="no_eligible_nodes",
            provisional_evidence_count=provisional_evidence_count,
            created_at=created_at,
            approved_at=None,
            reviewed_at=None,
            created_by=created_by,
            reviewed_by=None,
            operator_note=operator_note,
            review_result="pending",
            review_reason=None,
            review_snapshot_hash=None,
            command_version="reward-observer-cli/v1",
        )
        return batch, []

    base_allocation = scheduled_reward // len(eligible_summaries)
    remainder = scheduled_reward % len(eligible_summaries)
    items: list[PayoutBatchItem] = []
    allocated_total = 0
    for index, summary in enumerate(eligible_summaries, start=1):
        provisional_fields = tuple(_provisional_fields(summary))
        remainder_assigned = index <= remainder
        allocated = base_allocation + (1 if remainder_assigned else 0)
        allocated_total += allocated
        items.append(
            PayoutBatchItem(
                batch_id=batch_id,
                allocation_rank=index,
                node_id=summary.node_id,
                payout_address=summary.payout_address,
                allocated_chipbits=allocated,
                remainder_assigned=remainder_assigned,
                provisional_fields=provisional_fields,
            )
        )

    batch = PayoutBatch(
        batch_id=batch_id,
        epoch_index=epoch_index,
        network=network,
        status="proposed",
        scheduled_node_reward_chipbits=scheduled_reward,
        eligible_node_count=len(eligible_summaries),
        rejected_node_count=rejected_count,
        allocated_total_chipbits=allocated_total,
        unallocated_total_chipbits=max(0, scheduled_reward - allocated_total),
        zero_allocation_reason=None,
        provisional_evidence_count=provisional_evidence_count,
        created_at=created_at,
        approved_at=None,
        reviewed_at=None,
        created_by=created_by,
        reviewed_by=None,
        operator_note=operator_note,
        review_result="pending",
        review_reason=None,
        review_snapshot_hash=None,
        command_version="reward-observer-cli/v1",
    )
    return batch, items


def transition_batch(
    batch: PayoutBatch,
    *,
    status: str,
    reviewed_at: int,
    reviewed_by: str | None = None,
    operator_note: str | None = None,
) -> PayoutBatch:
    """Return one updated batch state after a dry-run review action."""

    allowed = {
        "proposed": {"approved", "rejected", "simulated"},
        "approved": {"simulated", "rejected"},
        "rejected": set(),
        "simulated": set(),
    }
    if status not in allowed.get(batch.status, set()):
        raise ValueError(f"invalid batch transition: {batch.status} -> {status}")
    review_result = "pass" if status in {"approved", "simulated"} else "fail"
    return replace(
        batch,
        status=status,
        approved_at=reviewed_at if status == "approved" else batch.approved_at,
        reviewed_at=reviewed_at,
        reviewed_by=reviewed_by,
        operator_note=operator_note if operator_note is not None else batch.operator_note,
        review_result=review_result,
        review_reason=operator_note if operator_note is not None else batch.review_reason,
    )


def batch_snapshot_hash(batch: PayoutBatch, items: list[PayoutBatchItem]) -> str:
    """Return a deterministic digest for one batch header and item set."""

    payload = {
        "batch": {
            "batch_id": batch.batch_id,
            "epoch_index": batch.epoch_index,
            "network": batch.network,
            "status": batch.status,
            "scheduled_node_reward_chipbits": batch.scheduled_node_reward_chipbits,
            "eligible_node_count": batch.eligible_node_count,
            "rejected_node_count": batch.rejected_node_count,
            "allocated_total_chipbits": batch.allocated_total_chipbits,
            "unallocated_total_chipbits": batch.unallocated_total_chipbits,
            "zero_allocation_reason": batch.zero_allocation_reason,
            "provisional_evidence_count": batch.provisional_evidence_count,
        },
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
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def finalize_batch_review_snapshot(batch: PayoutBatch, items: list[PayoutBatchItem]) -> PayoutBatch:
    """Attach the deterministic content digest to one batch header."""

    return replace(batch, review_snapshot_hash=batch_snapshot_hash(batch, items))


def validate_batch(
    *,
    batch: PayoutBatch,
    items: list[PayoutBatchItem],
    epoch_summaries: list[NodeEpochSummary],
) -> dict[str, object]:
    """Validate dry-run batch integrity against one epoch summary set."""

    scheduled_reward = scheduled_epoch_reward_chipbits(epoch_index=batch.epoch_index, network=batch.network)
    final_eligible = sorted(
        [summary for summary in epoch_summaries if summary.final_eligible],
        key=lambda item: (item.node_id, item.payout_address),
    )
    eligible_keys = {(summary.node_id, summary.payout_address) for summary in final_eligible}
    item_keys = [(item.node_id, item.payout_address) for item in items]
    duplicate_node_ids = [node_id for node_id, count in Counter(item.node_id for item in items).items() if count > 1]
    duplicate_payout_addresses = [
        payout for payout, count in Counter(item.payout_address for item in items).items() if count > 1
    ]
    expected_remainder = scheduled_reward % len(final_eligible) if final_eligible else 0
    actual_remainder = sum(1 for item in items if item.remainder_assigned)
    expected_provisional_count = sum(len(_provisional_fields(summary)) for summary in epoch_summaries)
    expected_item_provisional_count = sum(len(_provisional_fields(summary)) for summary in final_eligible)
    actual_provisional_count = sum(len(item.provisional_fields) for item in items)
    stable_ordering_preserved = item_keys == [(summary.node_id, summary.payout_address) for summary in final_eligible]
    no_ineligible_items = all(key in eligible_keys for key in item_keys)
    totals_match = (batch.allocated_total_chipbits + batch.unallocated_total_chipbits) == batch.scheduled_node_reward_chipbits

    checks = {
        "scheduled_reward_matches_consensus": batch.scheduled_node_reward_chipbits == scheduled_reward,
        "totals_balance": totals_match,
        "items_are_final_eligible_only": no_ineligible_items,
        "no_duplicate_node_ids": not duplicate_node_ids,
        "no_duplicate_payout_addresses": not duplicate_payout_addresses,
        "stable_ordering_preserved": stable_ordering_preserved,
        "deterministic_remainder_assignment": actual_remainder == expected_remainder,
        "provisional_evidence_count_matches": batch.provisional_evidence_count == expected_provisional_count,
        "item_level_provisional_flags_match": actual_provisional_count == expected_item_provisional_count,
    }
    errors = [name for name, ok in checks.items() if not ok]
    if errors:
        review_result = "fail"
    elif batch.provisional_evidence_count > 0 or batch.zero_allocation_reason is not None:
        review_result = "warn"
    else:
        review_result = "pass"

    return {
        "review_result": review_result,
        "checks": checks,
        "errors": errors,
        "scheduled_reward_chipbits": scheduled_reward,
        "duplicate_node_ids": duplicate_node_ids,
        "duplicate_payout_addresses": duplicate_payout_addresses,
        "expected_remainder_count": expected_remainder,
        "actual_remainder_count": actual_remainder,
        "expected_provisional_evidence_count": expected_provisional_count,
        "expected_item_provisional_flag_count": expected_item_provisional_count,
        "actual_item_provisional_flag_count": actual_provisional_count,
    }


def compare_epoch_to_batch(
    *,
    epoch_index: int,
    batch: PayoutBatch,
    items: list[PayoutBatchItem],
    epoch_summaries: list[NodeEpochSummary],
) -> dict[str, object]:
    """Compare one batch against the stored epoch eligibility view."""

    del epoch_index
    eligible = sorted(
        [summary for summary in epoch_summaries if summary.final_eligible],
        key=lambda item: (item.node_id, item.payout_address),
    )
    rejected = [summary for summary in epoch_summaries if not summary.final_eligible]
    batch_item_keys = {(item.node_id, item.payout_address) for item in items}
    eligible_keys = {(summary.node_id, summary.payout_address) for summary in eligible}
    missing = sorted(eligible_keys - batch_item_keys)
    extra = sorted(batch_item_keys - eligible_keys)
    rejection_breakdown = Counter(summary.rejection_reason for summary in rejected if summary.rejection_reason is not None)
    return {
        "epoch_index": batch.epoch_index,
        "batch_id": batch.batch_id,
        "eligible_node_count": len(eligible),
        "rejected_node_count": len(rejected),
        "batch_item_count": len(items),
        "missing_final_eligible_items": [
            {"node_id": node_id, "payout_address": payout_address}
            for node_id, payout_address in missing
        ],
        "unexpected_batch_items": [
            {"node_id": node_id, "payout_address": payout_address}
            for node_id, payout_address in extra
        ],
        "rejection_breakdown": dict(sorted(rejection_breakdown.items())),
        "zero_allocation_reason": batch.zero_allocation_reason,
    }


def _provisional_fields(summary: NodeEpochSummary) -> list[str]:
    provisional: list[str] = []
    if summary.endpoint_source == "provisional":
        provisional.extend(["host", "port"])
    if summary.ban_source == "provisional":
        provisional.append("banned")
    if summary.fingerprint is None:
        provisional.append("fingerprint")
    return provisional
