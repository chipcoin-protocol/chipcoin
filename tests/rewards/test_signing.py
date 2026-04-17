from pathlib import Path

from chipcoin.rewards.models import PlanningUtxo, PayoutBatch, PayoutBatchItem
from chipcoin.rewards.signing import (
    ExplicitPrivateKeySigner,
    StubTransactionSigner,
    build_unsigned_transaction_artifact,
    sign_transaction_artifact,
    transaction_snapshot_hash,
    validate_signed_transaction_artifact,
)
from chipcoin.rewards.store import RewardObserverStore
from chipcoin.rewards.tx_plans import build_transaction_plan
from tests.helpers import wallet_key


def _approved_batch() -> tuple[PayoutBatch, list[PayoutBatchItem]]:
    recipient = wallet_key(1).address
    batch = PayoutBatch(
        batch_id="dryrun-devnet-epoch-000123-1700000000",
        epoch_index=123,
        network="devnet",
        status="approved",
        scheduled_node_reward_chipbits=5_000_000_000,
        eligible_node_count=1,
        rejected_node_count=0,
        allocated_total_chipbits=5_000_000_000,
        unallocated_total_chipbits=0,
        zero_allocation_reason=None,
        provisional_evidence_count=0,
        created_at=1_700_000_000,
        approved_at=1_700_000_001,
        reviewed_at=1_700_000_001,
        created_by="tester",
        reviewed_by="tester",
        operator_note="approved dry-run batch",
        review_result="pass",
        review_reason=None,
        review_snapshot_hash="review-snapshot",
        command_version="reward-observer-cli/v1",
    )
    items = [
        PayoutBatchItem(
            batch_id=batch.batch_id,
            allocation_rank=1,
            node_id="node-a",
            payout_address=recipient,
            allocated_chipbits=5_000_000_000,
            remainder_assigned=False,
            provisional_fields=(),
        )
    ]
    return batch, items


def _funding_utxo(*, amount_chipbits: int) -> PlanningUtxo:
    return PlanningUtxo(
        txid="11" * 32,
        index=0,
        amount_chipbits=amount_chipbits,
        recipient=wallet_key(0).address,
        confirmations=50,
    )


def _planned_transaction():
    batch, items = _approved_batch()
    plan, inputs, outputs = build_transaction_plan(
        batch=batch,
        items=items,
        funding_utxos=[_funding_utxo(amount_chipbits=5_000_000_500)],
        funding_assumption="manual",
        change_address=wallet_key(0).address,
        fee_rate_chipbits_per_weight_unit=1,
        dust_threshold_chipbits=546,
        min_input_confirmations=1,
        created_at=1_700_000_100,
        created_by="tester",
    )
    assert plan.status == "planned"
    return batch, items, plan, inputs, outputs


def test_unsigned_transaction_construction_is_deterministic() -> None:
    _batch, _items, plan, inputs, outputs = _planned_transaction()

    artifact_a, unsigned_a = build_unsigned_transaction_artifact(
        plan=plan,
        inputs=inputs,
        outputs=outputs,
        created_at=1_700_000_200,
        created_by="tester",
    )
    artifact_b, unsigned_b = build_unsigned_transaction_artifact(
        plan=plan,
        inputs=inputs,
        outputs=outputs,
        created_at=1_700_000_201,
        created_by="tester",
    )

    assert artifact_a.status == "unsigned"
    assert artifact_b.status == "unsigned"
    assert artifact_a.unsigned_tx_snapshot_hash == artifact_b.unsigned_tx_snapshot_hash
    assert transaction_snapshot_hash(unsigned_a) == transaction_snapshot_hash(unsigned_b)
    assert artifact_a.broadcasted is False
    assert artifact_a.sent is False
    assert artifact_a.wallet_mutation is False


def test_plan_to_unsigned_mapping_is_exact() -> None:
    _batch, _items, plan, inputs, outputs = _planned_transaction()
    artifact, unsigned_tx = build_unsigned_transaction_artifact(
        plan=plan,
        inputs=inputs,
        outputs=outputs,
        created_at=1_700_000_200,
    )

    assert artifact.validation_result == "pass"
    assert unsigned_tx.metadata == {
        "kind": "reward_payout_batch",
        "batch_id": plan.batch_id,
        "plan_id": plan.plan_id,
    }
    assert [(item.previous_output.txid, item.previous_output.index) for item in unsigned_tx.inputs] == [
        (entry.txid, entry.vout) for entry in inputs
    ]
    assert [(output.recipient, int(output.value)) for output in unsigned_tx.outputs] == [
        (entry.recipient, entry.amount_chipbits) for entry in outputs
    ]


def test_invalid_recipient_address_is_rejected() -> None:
    _batch, _items, plan, inputs, outputs = _planned_transaction()
    invalid_outputs = [
        outputs[0].__class__(
            plan_id=outputs[0].plan_id,
            output_index=outputs[0].output_index,
            output_kind=outputs[0].output_kind,
            recipient="not-a-valid-chipcoin-address",
            amount_chipbits=outputs[0].amount_chipbits,
            batch_node_id=outputs[0].batch_node_id,
        ),
        *outputs[1:],
    ]

    artifact, _unsigned_tx = build_unsigned_transaction_artifact(
        plan=plan,
        inputs=inputs,
        outputs=invalid_outputs,
        created_at=1_700_000_200,
    )

    assert artifact.status == "invalid"
    assert artifact.invalid_reason == "invalid_recipient_address"
    assert artifact.broadcasted is False
    assert artifact.sent is False
    assert artifact.wallet_mutation is False


def test_stub_signer_signs_without_side_effects() -> None:
    _batch, _items, plan, inputs, outputs = _planned_transaction()
    artifact, _unsigned_tx = build_unsigned_transaction_artifact(
        plan=plan,
        inputs=inputs,
        outputs=outputs,
        created_at=1_700_000_200,
    )

    signed_artifact, signed_tx = sign_transaction_artifact(
        artifact=artifact,
        plan=plan,
        inputs=inputs,
        outputs=outputs,
        signer=StubTransactionSigner(),
        created_at=1_700_000_300,
        created_by="tester",
    )
    validation = validate_signed_transaction_artifact(
        plan=plan,
        transaction=signed_tx,
        inputs=inputs,
        outputs=outputs,
    )

    assert signed_artifact.status == "signed"
    assert signed_artifact.signer_type == "stub"
    assert signed_artifact.validation_result == "pass"
    assert signed_artifact.signed_tx_snapshot_hash == transaction_snapshot_hash(signed_tx)
    assert validation == {"valid": True, "invalid_reason": None}
    assert all(item.signature for item in signed_tx.inputs)
    assert all(item.public_key for item in signed_tx.inputs)
    assert signed_artifact.broadcasted is False
    assert signed_artifact.sent is False
    assert signed_artifact.wallet_mutation is False


def test_explicit_signer_requires_matching_funding_address() -> None:
    _batch, _items, plan, inputs, outputs = _planned_transaction()
    artifact, _unsigned_tx = build_unsigned_transaction_artifact(
        plan=plan,
        inputs=inputs,
        outputs=outputs,
        created_at=1_700_000_200,
    )
    signer = ExplicitPrivateKeySigner("0000000000000000000000000000000000000000000000000000000000000002")

    try:
        sign_transaction_artifact(
            artifact=artifact,
            plan=plan,
            inputs=inputs,
            outputs=outputs,
            signer=signer,
            created_at=1_700_000_300,
        )
    except ValueError as exc:
        assert str(exc) == "explicit signer can only sign plans funded by one matching address"
    else:
        raise AssertionError("expected explicit signer address mismatch to fail")


def test_signed_artifact_persistence_and_listing(tmp_path: Path) -> None:
    store = RewardObserverStore(tmp_path / "observer.sqlite3")
    store.init_schema()
    _batch, _items, plan, inputs, outputs = _planned_transaction()
    artifact, _unsigned_tx = build_unsigned_transaction_artifact(
        plan=plan,
        inputs=inputs,
        outputs=outputs,
        created_at=1_700_000_200,
        created_by="builder",
    )
    signed_artifact, _signed_tx = sign_transaction_artifact(
        artifact=artifact,
        plan=plan,
        inputs=inputs,
        outputs=outputs,
        signer=StubTransactionSigner(),
        created_at=1_700_000_300,
        created_by="signer",
    )

    store.insert_transaction_artifact(artifact)
    store.insert_transaction_artifact(signed_artifact)

    loaded_unsigned = store.get_transaction_artifact(artifact.artifact_id)
    loaded_signed = store.get_transaction_artifact(signed_artifact.artifact_id)
    listed_signed = store.list_transaction_artifacts(signed_only=True)
    status = store.store_status()

    assert loaded_unsigned is not None
    assert loaded_signed is not None
    assert loaded_unsigned.status == "unsigned"
    assert loaded_signed.status == "signed"
    assert loaded_signed.signer_type == "stub"
    assert [entry.artifact_id for entry in listed_signed] == [signed_artifact.artifact_id]
    assert status["artifact_count"] == 2

