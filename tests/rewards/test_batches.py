from pathlib import Path

from chipcoin.rewards.batches import (
    batch_snapshot_hash,
    build_dry_run_batch,
    compare_epoch_to_batch,
    finalize_batch_review_snapshot,
    transition_batch,
    validate_batch,
)
from chipcoin.rewards.models import NodeEpochSummary
from chipcoin.rewards.reporting import batch_audit_report, batch_review_report
from chipcoin.rewards.store import RewardObserverStore


def _summary(
    node_id: str,
    payout_address: str,
    *,
    eligible: bool = True,
    reason: str | None = None,
    endpoint_source: str = "peer_state",
    ban_source: str = "peer_state",
) -> NodeEpochSummary:
    return NodeEpochSummary(
        epoch_index=0,
        node_id=node_id,
        payout_address=payout_address,
        host=f"{node_id}.example",
        port=18444,
        first_seen=1,
        last_success=2,
        success_count=100 if eligible else 0,
        failure_count=0 if eligible else 100,
        consecutive_failures=0,
        handshake_ok=True,
        network_ok=True,
        registration_status="registered",
        warmup_status=True,
        concentration_status="ok",
        final_eligible=eligible,
        rejection_reason=reason,
        registration_source="node_registry",
        warmup_source="derived",
        ban_source=ban_source,
        endpoint_source=endpoint_source,
        public_ip="203.0.113.10",
        subnet_key="203.0.113.0/24",
        fingerprint=None,
        checked_observation_count=100,
        observation_count=100,
    )


def test_dry_run_batch_allocates_equally_with_stable_ordering() -> None:
    batch, items = build_dry_run_batch(
        epoch_index=0,
        network="devnet",
        summaries=[
            _summary("node-b", "CHCb"),
            _summary("node-a", "CHCa"),
        ],
        created_at=1_700_000_000,
        created_by="tester",
    )

    assert batch.batch_id == "dryrun-devnet-epoch-000000-1700000000"
    assert [item.node_id for item in items] == ["node-a", "node-b"]
    assert items[0].allocated_chipbits == 2_500_000_000
    assert items[1].allocated_chipbits == 2_500_000_000
    assert batch.allocated_total_chipbits == 5_000_000_000
    assert batch.unallocated_total_chipbits == 0


def test_dry_run_batch_assigns_remainder_deterministically() -> None:
    batch, items = build_dry_run_batch(
        epoch_index=0,
        network="devnet",
        summaries=[
            _summary("node-c", "CHCc"),
            _summary("node-a", "CHCa"),
            _summary("node-b", "CHCb"),
        ],
        created_at=1_700_000_000,
    )

    assert [item.node_id for item in items] == ["node-a", "node-b", "node-c"]
    assert [item.allocated_chipbits for item in items] == [1_666_666_667, 1_666_666_667, 1_666_666_666]
    assert [item.remainder_assigned for item in items] == [True, True, False]
    assert batch.allocated_total_chipbits == 5_000_000_000


def test_dry_run_batch_handles_zero_eligible_nodes() -> None:
    batch, items = build_dry_run_batch(
        epoch_index=0,
        network="devnet",
        summaries=[_summary("node-a", "CHCa", eligible=False, reason="unreachable")],
        created_at=1_700_000_000,
    )

    assert items == []
    assert batch.eligible_node_count == 0
    assert batch.zero_allocation_reason == "no_eligible_nodes"
    assert batch.allocated_total_chipbits == 0
    assert batch.unallocated_total_chipbits == 5_000_000_000


def test_dry_run_batch_counts_provisional_evidence_flags() -> None:
    batch, items = build_dry_run_batch(
        epoch_index=0,
        network="devnet",
        summaries=[_summary("node-a", "CHCa", endpoint_source="provisional", ban_source="provisional")],
        created_at=1_700_000_000,
    )

    assert batch.provisional_evidence_count == 4
    assert items[0].provisional_fields == ("host", "port", "banned", "fingerprint")


def test_batch_persistence_and_state_transitions(tmp_path: Path) -> None:
    store = RewardObserverStore(tmp_path / "observer.sqlite3")
    store.init_schema()
    batch, items = build_dry_run_batch(
        epoch_index=0,
        network="devnet",
        summaries=[_summary("node-a", "CHCa"), _summary("node-b", "CHCb")],
        created_at=1_700_000_000,
        created_by="alice",
        operator_note="initial proposal",
    )
    store.insert_payout_batch(batch, items)

    loaded = store.get_payout_batch(batch.batch_id)
    assert loaded is not None
    loaded_batch, loaded_items = loaded
    assert loaded_batch.created_by == "alice"
    assert loaded_batch.operator_note == "initial proposal"
    assert loaded_batch.review_result == "pending"
    assert [item.node_id for item in loaded_items] == ["node-a", "node-b"]

    approved = transition_batch(
        loaded_batch,
        status="approved",
        reviewed_at=1_700_000_100,
        reviewed_by="bob",
        operator_note="approved for dry-run only",
    )
    approved = finalize_batch_review_snapshot(approved, loaded_items)
    store.update_payout_batch(approved)
    approved_loaded, _approved_items = store.get_payout_batch(batch.batch_id) or (None, None)
    assert approved_loaded is not None
    assert approved_loaded.status == "approved"
    assert approved_loaded.approved_at == 1_700_000_100
    assert approved_loaded.reviewed_by == "bob"
    assert approved_loaded.operator_note == "approved for dry-run only"
    assert approved_loaded.review_result == "pass"
    assert approved_loaded.review_snapshot_hash is not None


def test_reject_transition_is_persisted(tmp_path: Path) -> None:
    store = RewardObserverStore(tmp_path / "observer.sqlite3")
    store.init_schema()
    batch, items = build_dry_run_batch(
        epoch_index=0,
        network="devnet",
        summaries=[_summary("node-a", "CHCa")],
        created_at=1_700_000_000,
    )
    store.insert_payout_batch(batch, items)
    rejected = transition_batch(
        batch,
        status="rejected",
        reviewed_at=1_700_000_200,
        reviewed_by="ops",
        operator_note="insufficient confidence",
    )
    rejected = finalize_batch_review_snapshot(rejected, items)
    store.update_payout_batch(rejected)

    loaded = store.get_payout_batch(batch.batch_id)
    assert loaded is not None
    loaded_batch, _items = loaded
    assert loaded_batch.status == "rejected"
    assert loaded_batch.approved_at is None
    assert loaded_batch.reviewed_at == 1_700_000_200
    assert loaded_batch.reviewed_by == "ops"
    assert loaded_batch.operator_note == "insufficient confidence"
    assert loaded_batch.review_result == "fail"


def test_batch_validation_and_review_report_are_consistent() -> None:
    summaries = [_summary("node-a", "CHCa"), _summary("node-b", "CHCb")]
    batch, items = build_dry_run_batch(
        epoch_index=0,
        network="devnet",
        summaries=summaries,
        created_at=1_700_000_000,
    )
    batch = finalize_batch_review_snapshot(batch, items)
    validation = validate_batch(batch=batch, items=items, epoch_summaries=summaries)
    review = batch_review_report(batch, items, epoch_summaries=summaries, validation=validation)
    audit = batch_audit_report(batch, items, validation=validation)

    assert validation["review_result"] == "warn"
    assert validation["checks"]["scheduled_reward_matches_consensus"] is True
    assert validation["checks"]["totals_balance"] is True
    assert validation["checks"]["items_are_final_eligible_only"] is True
    assert validation["checks"]["stable_ordering_preserved"] is True
    assert validation["checks"]["deterministic_remainder_assignment"] is True
    assert review["decision_summary"]["allocated_total_chipbits"] == 5_000_000_000
    assert review["provisional_evidence_summary"] == {"fingerprint": 2}
    assert audit["review_snapshot_hash"] == batch.review_snapshot_hash


def test_batch_snapshot_hash_is_deterministic() -> None:
    batch, items = build_dry_run_batch(
        epoch_index=0,
        network="devnet",
        summaries=[_summary("node-a", "CHCa"), _summary("node-b", "CHCb")],
        created_at=1_700_000_000,
    )
    first = batch_snapshot_hash(batch, items)
    second = batch_snapshot_hash(batch, items)

    assert first == second


def test_compare_epoch_batch_reports_missing_and_rejections() -> None:
    summaries = [
        _summary("node-a", "CHCa"),
        _summary("node-b", "CHCb"),
        _summary("node-c", "CHCc", eligible=False, reason="unreachable"),
    ]
    batch, items = build_dry_run_batch(
        epoch_index=0,
        network="devnet",
        summaries=[_summary("node-a", "CHCa")],
        created_at=1_700_000_000,
    )
    comparison = compare_epoch_to_batch(epoch_index=0, batch=batch, items=items, epoch_summaries=summaries)

    assert comparison["missing_final_eligible_items"] == [{"node_id": "node-b", "payout_address": "CHCb"}]
    assert comparison["unexpected_batch_items"] == []
    assert comparison["rejection_breakdown"] == {"unreachable": 1}


def test_no_eligible_nodes_review_path_is_explicit() -> None:
    summaries = [_summary("node-a", "CHCa", eligible=False, reason="unreachable")]
    batch, items = build_dry_run_batch(
        epoch_index=0,
        network="devnet",
        summaries=summaries,
        created_at=1_700_000_000,
    )
    batch = finalize_batch_review_snapshot(batch, items)
    validation = validate_batch(batch=batch, items=items, epoch_summaries=summaries)
    review = batch_review_report(batch, items, epoch_summaries=summaries, validation=validation)

    assert validation["review_result"] == "warn"
    assert review["decision_summary"]["zero_allocation_reason"] == "no_eligible_nodes"
    assert review["decision_summary"]["unallocated_total_chipbits"] == 5_000_000_000
    assert review["eligibility_summary_by_reason_code"] == {"unreachable": 1}
