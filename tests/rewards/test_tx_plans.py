from pathlib import Path

from chipcoin.rewards.batches import build_dry_run_batch
from chipcoin.rewards.models import NodeEpochSummary, PlanningUtxo, PayoutBatch, PayoutBatchItem
from chipcoin.rewards.store import RewardObserverStore
from chipcoin.rewards.tx_plans import build_transaction_plan, estimate_fee_chipbits, validate_transaction_plan


def _summary(node_id: str, payout_address: str, *, amount_chipbits: int = 2_500_000_000) -> NodeEpochSummary:
    return NodeEpochSummary(
        epoch_index=0,
        node_id=node_id,
        payout_address=payout_address,
        host=f"{node_id}.example",
        port=18444,
        first_seen=1,
        last_success=2,
        success_count=100,
        failure_count=0,
        consecutive_failures=0,
        handshake_ok=True,
        network_ok=True,
        registration_status="registered",
        warmup_status=True,
        concentration_status="ok",
        final_eligible=True,
        rejection_reason=None,
        registration_source="node_registry",
        warmup_source="derived",
        ban_source="peer_state",
        endpoint_source="peer_state",
        public_ip="203.0.113.10",
        subnet_key="203.0.113.0/24",
        fingerprint=None,
        checked_observation_count=100,
        observation_count=100,
    )


def _batch(amounts: list[int] | None = None):
    if amounts is None:
        amounts = [2_500_000_000, 2_500_000_000]
    summaries = [
        _summary("node-a", "CHCa", amount_chipbits=amounts[0]),
        _summary("node-b", "CHCb", amount_chipbits=amounts[1] if len(amounts) > 1 else amounts[0]),
    ]
    batch, items = build_dry_run_batch(
        epoch_index=0,
        network="devnet",
        summaries=summaries[: len(amounts)],
        created_at=1_700_000_000,
    )
    approved = batch.__class__(**{**batch.__dict__, "status": "approved"})
    return approved, items[: len(amounts)]


def _manual_batch(item_amounts: list[tuple[str, str, int]]) -> tuple[PayoutBatch, list[PayoutBatchItem]]:
    batch = PayoutBatch(
        batch_id="dryrun-devnet-epoch-000000-1700000000",
        epoch_index=0,
        network="devnet",
        status="approved",
        scheduled_node_reward_chipbits=sum(amount for _node_id, _address, amount in item_amounts),
        eligible_node_count=len(item_amounts),
        rejected_node_count=0,
        allocated_total_chipbits=sum(amount for _node_id, _address, amount in item_amounts),
        unallocated_total_chipbits=0,
        zero_allocation_reason=None,
        provisional_evidence_count=len(item_amounts),
        created_at=1_700_000_000,
        approved_at=1_700_000_001,
        reviewed_at=1_700_000_001,
        created_by="tester",
        reviewed_by="tester",
        operator_note=None,
        review_result="pass",
        review_reason=None,
        review_snapshot_hash="snapshot",
        command_version="reward-observer-cli/v1",
    )
    items = [
        PayoutBatchItem(
            batch_id=batch.batch_id,
            allocation_rank=index + 1,
            node_id=node_id,
            payout_address=payout_address,
            allocated_chipbits=amount,
            remainder_assigned=False,
            provisional_fields=("fingerprint",),
        )
        for index, (node_id, payout_address, amount) in enumerate(item_amounts)
    ]
    return batch, items


def _utxo(txid: str, index: int, amount: int, *, confirmations: int = 10, recipient: str = "funding") -> PlanningUtxo:
    return PlanningUtxo(
        txid=txid,
        index=index,
        amount_chipbits=amount,
        recipient=recipient,
        confirmations=confirmations,
    )


def test_transaction_plan_generation_is_deterministic() -> None:
    batch, items = _batch()
    utxos = [_utxo("b", 0, 3_000_000_000), _utxo("a", 0, 2_500_001_000)]

    plan1 = build_transaction_plan(
        batch=batch,
        items=items,
        funding_utxos=utxos,
        funding_assumption="manual",
        change_address="CHCchange",
        fee_rate_chipbits_per_weight_unit=1,
        dust_threshold_chipbits=546,
        min_input_confirmations=1,
        created_at=1_700_000_100,
    )
    plan2 = build_transaction_plan(
        batch=batch,
        items=items,
        funding_utxos=utxos,
        funding_assumption="manual",
        change_address="CHCchange",
        fee_rate_chipbits_per_weight_unit=1,
        dust_threshold_chipbits=546,
        min_input_confirmations=1,
        created_at=1_700_000_100,
    )

    assert plan1[0].plan_snapshot_hash == plan2[0].plan_snapshot_hash
    assert [item.txid for item in plan1[1]] == ["a", "b"]


def test_transaction_plan_reports_insufficient_funds() -> None:
    batch, items = _batch()
    plan, inputs, outputs = build_transaction_plan(
        batch=batch,
        items=items,
        funding_utxos=[_utxo("a", 0, 1_000_000_000)],
        funding_assumption="manual",
        change_address="CHCchange",
        fee_rate_chipbits_per_weight_unit=1,
        dust_threshold_chipbits=546,
        min_input_confirmations=1,
        created_at=1_700_000_100,
    )

    assert plan.status == "invalid"
    assert plan.insufficient_funds is True
    assert plan.invalid_reason == "insufficient_funds"
    assert inputs == []
    assert outputs == []


def test_transaction_plan_with_exact_funds_has_no_change() -> None:
    batch, items = _batch([5_000_000_000])
    fee = estimate_fee_chipbits(input_count=1, output_count=1, fee_rate_chipbits_per_weight_unit=1)
    plan, inputs, outputs = build_transaction_plan(
        batch=batch,
        items=items,
        funding_utxos=[_utxo("a", 0, 5_000_000_000 + fee)],
        funding_assumption="manual",
        change_address="CHCchange",
        fee_rate_chipbits_per_weight_unit=1,
        dust_threshold_chipbits=546,
        min_input_confirmations=1,
        created_at=1_700_000_100,
    )

    assert plan.status == "planned"
    assert plan.change_chipbits == 0
    assert len(inputs) == 1
    assert len(outputs) == 1


def test_transaction_plan_generates_change_when_large_enough() -> None:
    batch, items = _batch([5_000_000_000])
    fee = estimate_fee_chipbits(input_count=1, output_count=2, fee_rate_chipbits_per_weight_unit=1)
    total = 5_000_000_000 + fee + 10_000
    plan, inputs, outputs = build_transaction_plan(
        batch=batch,
        items=items,
        funding_utxos=[_utxo("a", 0, total)],
        funding_assumption="manual",
        change_address="CHCchange",
        fee_rate_chipbits_per_weight_unit=1,
        dust_threshold_chipbits=546,
        min_input_confirmations=1,
        created_at=1_700_000_100,
    )

    assert plan.status == "planned"
    assert plan.change_chipbits == 10_000
    assert outputs[-1].output_kind == "change"
    assert outputs[-1].recipient == "CHCchange"


def test_transaction_plan_rejects_dust_recipient_outputs() -> None:
    batch, items = _manual_batch([("node-a", "CHCa", 100)])
    plan, inputs, outputs = build_transaction_plan(
        batch=batch,
        items=items,
        funding_utxos=[_utxo("a", 0, 10_000)],
        funding_assumption="manual",
        change_address="CHCchange",
        fee_rate_chipbits_per_weight_unit=1,
        dust_threshold_chipbits=546,
        min_input_confirmations=1,
        created_at=1_700_000_100,
    )

    assert plan.status == "invalid"
    assert plan.invalid_reason == "dust_recipient_output"
    assert inputs == []
    assert outputs == []


def test_transaction_plan_validation_is_consistent() -> None:
    batch, items = _batch([5_000_000_000])
    fee = estimate_fee_chipbits(input_count=1, output_count=2, fee_rate_chipbits_per_weight_unit=1)
    plan, inputs, outputs = build_transaction_plan(
        batch=batch,
        items=items,
        funding_utxos=[_utxo("a", 0, 5_000_000_000 + fee + 1_000)],
        funding_assumption="manual",
        change_address="CHCchange",
        fee_rate_chipbits_per_weight_unit=1,
        dust_threshold_chipbits=546,
        min_input_confirmations=1,
        created_at=1_700_000_100,
    )
    validation = validate_transaction_plan(batch=batch, batch_items=items, plan=plan, inputs=inputs, outputs=outputs)

    assert validation["checks"]["batch_linkage_exact"] is True
    assert validation["checks"]["inputs_cover_outputs_and_fee"] is True
    assert validation["checks"]["no_duplicate_payout_outputs"] is True
    assert validation["checks"]["output_ordering_deterministic"] is True
    assert validation["checks"]["fee_consistent"] is True
    assert validation["checks"]["provisional_warning_inherited"] is True


def test_transaction_plan_persistence(tmp_path: Path) -> None:
    store = RewardObserverStore(tmp_path / "observer.sqlite3")
    store.init_schema()
    batch, items = _batch([5_000_000_000])
    fee = estimate_fee_chipbits(input_count=1, output_count=1, fee_rate_chipbits_per_weight_unit=1)
    plan, inputs, outputs = build_transaction_plan(
        batch=batch,
        items=items,
        funding_utxos=[_utxo("a", 0, 5_000_000_000 + fee)],
        funding_assumption="manual",
        change_address="CHCchange",
        fee_rate_chipbits_per_weight_unit=1,
        dust_threshold_chipbits=546,
        min_input_confirmations=1,
        created_at=1_700_000_100,
    )
    store.insert_transaction_plan(plan, inputs, outputs)

    loaded = store.get_transaction_plan(plan.plan_id)
    assert loaded is not None
    loaded_plan, loaded_inputs, loaded_outputs = loaded
    assert loaded_plan.batch_id == batch.batch_id
    assert loaded_plan.plan_snapshot_hash == plan.plan_snapshot_hash
    assert [item.txid for item in loaded_inputs] == ["a"]
    assert [item.output_kind for item in loaded_outputs] == ["recipient"]
