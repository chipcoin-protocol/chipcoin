"""Dry transaction planning on top of approved reward batches."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json

from .models import (
    PlanningUtxo,
    PayoutBatch,
    PayoutBatchItem,
    TransactionPlan,
    TransactionPlanInput,
    TransactionPlanOutput,
)


PLAN_BASE_WEIGHT_UNITS = 40
PLAN_INPUT_WEIGHT_UNITS = 272
PLAN_OUTPUT_WEIGHT_UNITS = 136
DEFAULT_DUST_POLICY = "reject"
SUPPORTED_DUST_POLICIES = frozenset({"reject"})


def build_transaction_plan(
    *,
    batch: PayoutBatch,
    items: list[PayoutBatchItem],
    funding_utxos: list[PlanningUtxo],
    funding_assumption: str,
    change_address: str,
    fee_rate_chipbits_per_weight_unit: int,
    dust_threshold_chipbits: int,
    min_input_confirmations: int,
    created_at: int,
    created_by: str | None = None,
    dust_policy: str = DEFAULT_DUST_POLICY,
) -> tuple[TransactionPlan, list[TransactionPlanInput], list[TransactionPlanOutput]]:
    """Build one unsigned, unbroadcastable transaction plan from an approved batch."""

    if batch.status != "approved":
        raise ValueError("transaction planning requires an approved batch")
    if fee_rate_chipbits_per_weight_unit <= 0:
        raise ValueError("fee_rate_chipbits_per_weight_unit must be positive")
    if dust_threshold_chipbits < 0:
        raise ValueError("dust_threshold_chipbits must be non-negative")
    if min_input_confirmations < 0:
        raise ValueError("min_input_confirmations must be non-negative")
    if dust_policy not in SUPPORTED_DUST_POLICIES:
        raise ValueError(f"unsupported dust policy: {dust_policy}")

    plan_id = f"txplan-{batch.batch_id}-{created_at}"
    recipient_items = sorted(items, key=lambda item: item.allocation_rank)
    dust_outputs = [item for item in recipient_items if item.allocated_chipbits < dust_threshold_chipbits]
    if dust_outputs:
        plan = TransactionPlan(
            plan_id=plan_id,
            batch_id=batch.batch_id,
            status="invalid",
            funding_assumption=funding_assumption,
            input_count=0,
            output_count=0,
            estimated_fee_chipbits=0,
            total_input_chipbits=0,
            total_recipient_chipbits=sum(item.allocated_chipbits for item in recipient_items),
            change_chipbits=0,
            dust_dropped_chipbits=0,
            insufficient_funds=False,
            created_at=created_at,
            created_by=created_by,
            plan_snapshot_hash=None,
            fee_rate_chipbits_per_weight_unit=fee_rate_chipbits_per_weight_unit,
            dust_threshold_chipbits=dust_threshold_chipbits,
            min_input_confirmations=min_input_confirmations,
            change_address=change_address,
            dust_policy=dust_policy,
            provisional_warning_inherited=batch.provisional_evidence_count > 0,
            invalid_reason="dust_recipient_output",
            command_version="reward-observer-cli/v1",
        )
        return _finalize_plan(plan, [], [])

    eligible_utxos = sorted(
        [utxo for utxo in funding_utxos if utxo.confirmations >= min_input_confirmations],
        key=lambda item: (item.amount_chipbits, item.txid, item.index),
    )
    selected: list[PlanningUtxo] = []
    total_input = 0
    target_recipients = sum(item.allocated_chipbits for item in recipient_items)

    for utxo in eligible_utxos:
        selected.append(utxo)
        total_input += utxo.amount_chipbits

        fee_without_change = estimate_fee_chipbits(
            input_count=len(selected),
            output_count=len(recipient_items),
            fee_rate_chipbits_per_weight_unit=fee_rate_chipbits_per_weight_unit,
        )
        if total_input < target_recipients + fee_without_change:
            continue

        fee_with_change = estimate_fee_chipbits(
            input_count=len(selected),
            output_count=len(recipient_items) + 1,
            fee_rate_chipbits_per_weight_unit=fee_rate_chipbits_per_weight_unit,
        )
        change_candidate = total_input - target_recipients - fee_with_change
        if change_candidate >= dust_threshold_chipbits:
            return _finalize_valid_plan(
                plan_id=plan_id,
                batch=batch,
                recipient_items=recipient_items,
                selected=selected,
                total_input=total_input,
                fee_chipbits=fee_with_change,
                change_chipbits=change_candidate,
                funding_assumption=funding_assumption,
                change_address=change_address,
                fee_rate_chipbits_per_weight_unit=fee_rate_chipbits_per_weight_unit,
                dust_threshold_chipbits=dust_threshold_chipbits,
                min_input_confirmations=min_input_confirmations,
                created_at=created_at,
                created_by=created_by,
                dust_policy=dust_policy,
            )

        fee_effective = total_input - target_recipients
        if fee_effective >= fee_without_change:
            return _finalize_valid_plan(
                plan_id=plan_id,
                batch=batch,
                recipient_items=recipient_items,
                selected=selected,
                total_input=total_input,
                fee_chipbits=fee_effective,
                change_chipbits=0,
                funding_assumption=funding_assumption,
                change_address=change_address,
                fee_rate_chipbits_per_weight_unit=fee_rate_chipbits_per_weight_unit,
                dust_threshold_chipbits=dust_threshold_chipbits,
                min_input_confirmations=min_input_confirmations,
                created_at=created_at,
                created_by=created_by,
                dust_policy=dust_policy,
            )

    plan = TransactionPlan(
        plan_id=plan_id,
        batch_id=batch.batch_id,
        status="invalid",
        funding_assumption=funding_assumption,
        input_count=0,
        output_count=0,
        estimated_fee_chipbits=0,
        total_input_chipbits=sum(utxo.amount_chipbits for utxo in eligible_utxos),
        total_recipient_chipbits=target_recipients,
        change_chipbits=0,
        dust_dropped_chipbits=0,
        insufficient_funds=True,
        created_at=created_at,
        created_by=created_by,
        plan_snapshot_hash=None,
        fee_rate_chipbits_per_weight_unit=fee_rate_chipbits_per_weight_unit,
        dust_threshold_chipbits=dust_threshold_chipbits,
        min_input_confirmations=min_input_confirmations,
        change_address=change_address,
        dust_policy=dust_policy,
        provisional_warning_inherited=batch.provisional_evidence_count > 0,
        invalid_reason="insufficient_funds",
        command_version="reward-observer-cli/v1",
    )
    return _finalize_plan(plan, [], [])


def estimate_fee_chipbits(*, input_count: int, output_count: int, fee_rate_chipbits_per_weight_unit: int) -> int:
    """Estimate fee from fixed planning weights."""

    total_weight = PLAN_BASE_WEIGHT_UNITS + (input_count * PLAN_INPUT_WEIGHT_UNITS) + (
        output_count * PLAN_OUTPUT_WEIGHT_UNITS
    )
    return total_weight * fee_rate_chipbits_per_weight_unit


def plan_snapshot_hash(
    plan: TransactionPlan,
    inputs: list[TransactionPlanInput],
    outputs: list[TransactionPlanOutput],
) -> str:
    """Return a deterministic content digest for one plan."""

    payload = {
        "plan": {
            "plan_id": plan.plan_id,
            "batch_id": plan.batch_id,
            "status": plan.status,
            "funding_assumption": plan.funding_assumption,
            "estimated_fee_chipbits": plan.estimated_fee_chipbits,
            "total_input_chipbits": plan.total_input_chipbits,
            "total_recipient_chipbits": plan.total_recipient_chipbits,
            "change_chipbits": plan.change_chipbits,
            "dust_dropped_chipbits": plan.dust_dropped_chipbits,
            "insufficient_funds": plan.insufficient_funds,
            "fee_rate_chipbits_per_weight_unit": plan.fee_rate_chipbits_per_weight_unit,
            "dust_threshold_chipbits": plan.dust_threshold_chipbits,
            "min_input_confirmations": plan.min_input_confirmations,
            "change_address": plan.change_address,
            "dust_policy": plan.dust_policy,
        },
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
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_transaction_plan(
    *,
    batch: PayoutBatch,
    batch_items: list[PayoutBatchItem],
    plan: TransactionPlan,
    inputs: list[TransactionPlanInput],
    outputs: list[TransactionPlanOutput],
) -> dict[str, object]:
    """Validate one dry transaction plan against its batch linkage and policy."""

    recipient_outputs = [output for output in outputs if output.output_kind == "recipient"]
    duplicate_recipients = [
        recipient
        for recipient, count in _counter(output.recipient for output in recipient_outputs).items()
        if count > 1
    ]
    expected_recipient_keys = [(item.node_id, item.payout_address) for item in sorted(batch_items, key=lambda item: item.allocation_rank)]
    actual_recipient_keys = [(output.batch_node_id, output.recipient) for output in recipient_outputs]
    expected_fee = estimate_fee_chipbits(
        input_count=len(inputs),
        output_count=len(outputs),
        fee_rate_chipbits_per_weight_unit=plan.fee_rate_chipbits_per_weight_unit,
    )
    fee_consistent = plan.estimated_fee_chipbits >= expected_fee if plan.change_chipbits == 0 else plan.estimated_fee_chipbits == expected_fee
    checks = {
        "batch_linkage_exact": plan.batch_id == batch.batch_id,
        "inputs_cover_outputs_and_fee": plan.total_input_chipbits == (plan.total_recipient_chipbits + plan.change_chipbits + plan.estimated_fee_chipbits),
        "no_duplicate_payout_outputs": not duplicate_recipients,
        "output_ordering_deterministic": actual_recipient_keys == expected_recipient_keys and _change_output_last(outputs),
        "fee_consistent": fee_consistent,
        "dust_policy_consistent": (plan.invalid_reason == "dust_recipient_output") if plan.status == "invalid" and plan.total_recipient_chipbits > 0 and not outputs and not inputs and not plan.insufficient_funds else True,
        "provisional_warning_inherited": plan.provisional_warning_inherited == (batch.provisional_evidence_count > 0),
    }
    errors = [name for name, ok in checks.items() if not ok]
    return {
        "checks": checks,
        "errors": errors,
        "duplicate_recipients": duplicate_recipients,
        "expected_fee_chipbits": expected_fee,
    }


def _finalize_valid_plan(
    *,
    plan_id: str,
    batch: PayoutBatch,
    recipient_items: list[PayoutBatchItem],
    selected: list[PlanningUtxo],
    total_input: int,
    fee_chipbits: int,
    change_chipbits: int,
    funding_assumption: str,
    change_address: str,
    fee_rate_chipbits_per_weight_unit: int,
    dust_threshold_chipbits: int,
    min_input_confirmations: int,
    created_at: int,
    created_by: str | None,
    dust_policy: str,
) -> tuple[TransactionPlan, list[TransactionPlanInput], list[TransactionPlanOutput]]:
    inputs = [
        TransactionPlanInput(
            plan_id=plan_id,
            input_index=index,
            txid=utxo.txid,
            vout=utxo.index,
            amount_chipbits=utxo.amount_chipbits,
            recipient=utxo.recipient,
            confirmations=utxo.confirmations,
        )
        for index, utxo in enumerate(selected)
    ]
    outputs = [
        TransactionPlanOutput(
            plan_id=plan_id,
            output_index=index,
            output_kind="recipient",
            recipient=item.payout_address,
            amount_chipbits=item.allocated_chipbits,
            batch_node_id=item.node_id,
        )
        for index, item in enumerate(recipient_items)
    ]
    if change_chipbits > 0:
        outputs.append(
            TransactionPlanOutput(
                plan_id=plan_id,
                output_index=len(outputs),
                output_kind="change",
                recipient=change_address,
                amount_chipbits=change_chipbits,
                batch_node_id=None,
            )
        )
    plan = TransactionPlan(
        plan_id=plan_id,
        batch_id=batch.batch_id,
        status="planned",
        funding_assumption=funding_assumption,
        input_count=len(inputs),
        output_count=len(outputs),
        estimated_fee_chipbits=fee_chipbits,
        total_input_chipbits=total_input,
        total_recipient_chipbits=sum(item.allocated_chipbits for item in recipient_items),
        change_chipbits=change_chipbits,
        dust_dropped_chipbits=0,
        insufficient_funds=False,
        created_at=created_at,
        created_by=created_by,
        plan_snapshot_hash=None,
        fee_rate_chipbits_per_weight_unit=fee_rate_chipbits_per_weight_unit,
        dust_threshold_chipbits=dust_threshold_chipbits,
        min_input_confirmations=min_input_confirmations,
        change_address=change_address,
        dust_policy=dust_policy,
        provisional_warning_inherited=batch.provisional_evidence_count > 0,
        invalid_reason=None,
        command_version="reward-observer-cli/v1",
    )
    return _finalize_plan(plan, inputs, outputs)


def _finalize_plan(
    plan: TransactionPlan,
    inputs: list[TransactionPlanInput],
    outputs: list[TransactionPlanOutput],
) -> tuple[TransactionPlan, list[TransactionPlanInput], list[TransactionPlanOutput]]:
    return replace(plan, plan_snapshot_hash=plan_snapshot_hash(plan, inputs, outputs)), inputs, outputs


def _counter(values):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _change_output_last(outputs: list[TransactionPlanOutput]) -> bool:
    change_indexes = [output.output_index for output in outputs if output.output_kind == "change"]
    if not change_indexes:
        return True
    return change_indexes == [len(outputs) - 1]
