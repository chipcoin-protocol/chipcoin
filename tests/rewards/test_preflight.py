from pathlib import Path

from chipcoin.rewards.preflight import build_broadcast_preflight, export_signed_transaction_artifact
from chipcoin.rewards.signing import StubTransactionSigner, build_unsigned_transaction_artifact, sign_transaction_artifact
from chipcoin.rewards.store import RewardObserverStore
from tests.rewards.test_signing import _planned_transaction


def _signed_fixture():
    batch, _items, plan, inputs, outputs = _planned_transaction()
    artifact, _unsigned_tx = build_unsigned_transaction_artifact(
        plan=plan,
        inputs=inputs,
        outputs=outputs,
        created_at=1_700_000_200,
        created_by="builder",
    )
    signed_artifact, signed_tx = sign_transaction_artifact(
        artifact=artifact,
        plan=plan,
        inputs=inputs,
        outputs=outputs,
        signer=StubTransactionSigner(),
        created_at=1_700_000_300,
        created_by="signer",
    )
    return batch, plan, inputs, outputs, signed_artifact, signed_tx


def test_serialization_export_is_deterministic_and_reproducible() -> None:
    _batch, _plan, _inputs, _outputs, artifact, signed_tx = _signed_fixture()

    export_a = export_signed_transaction_artifact(artifact)
    export_b = export_signed_transaction_artifact(artifact)

    assert export_a == export_b
    assert export_a["txid"] == signed_tx.txid()
    assert export_a["tx_hex"] == artifact.tx_hex
    assert export_a["broadcasted"] is False
    assert export_a["submitted"] is False
    assert export_a["auto_send"] is False
    assert export_a["manual_broadcast_required"] is True


def test_preflight_record_creation_is_warning_only_without_utxo_freshness() -> None:
    batch, plan, inputs, outputs, artifact, signed_tx = _signed_fixture()

    preflight, report, indexed_inputs = build_broadcast_preflight(
        artifact=artifact,
        plan=plan,
        batch=batch,
        inputs=inputs,
        outputs=outputs,
        network="devnet",
        created_at=1_700_000_400,
        created_by="ops",
    )

    assert preflight.status == "prepared"
    assert preflight.preflight_result == "warn"
    assert preflight.blocking_reason is None
    assert preflight.ready_for_manual_broadcast is True
    assert preflight.txid == signed_tx.txid()
    assert report["checks"]["txid_reproducible"] is True
    assert report["checks"]["stale_utxo_detection_authoritative"] is False
    assert report["warnings"] == ["stale_utxo_detection_unverified", "stub_signature_artifact"]
    assert indexed_inputs == [(0, inputs[0].txid, inputs[0].vout)]


def test_duplicate_input_local_detection_blocks_second_preflight() -> None:
    batch, plan, inputs, outputs, artifact, _signed_tx = _signed_fixture()
    existing_conflicts = {(inputs[0].txid, inputs[0].vout): ["preflight-other"]}

    preflight, report, _indexed_inputs = build_broadcast_preflight(
        artifact=artifact,
        plan=plan,
        batch=batch,
        inputs=inputs,
        outputs=outputs,
        network="devnet",
        created_at=1_700_000_401,
        existing_ready_input_conflicts=existing_conflicts,
    )

    assert preflight.status == "blocked"
    assert preflight.preflight_result == "fail"
    assert preflight.blocking_reason == "duplicate_input_preflight_conflict"
    assert report["checks"]["duplicate_inputs_not_prepared_locally"] is False
    assert report["ready_for_manual_broadcast"] is False


def test_network_mismatch_is_blocking_but_no_broadcast_happens() -> None:
    batch, plan, inputs, outputs, artifact, _signed_tx = _signed_fixture()

    preflight, report, _indexed_inputs = build_broadcast_preflight(
        artifact=artifact,
        plan=plan,
        batch=batch,
        inputs=inputs,
        outputs=outputs,
        network="mainnet",
        created_at=1_700_000_402,
    )

    assert preflight.status == "blocked"
    assert preflight.blocking_reason == "network_mismatch"
    assert report["broadcasted"] is False
    assert report["submitted"] is False
    assert report["auto_send"] is False
    assert report["manual_broadcast_required"] is True


def test_preflight_persistence_and_input_conflict_index(tmp_path: Path) -> None:
    store = RewardObserverStore(tmp_path / "observer.sqlite3")
    store.init_schema()
    batch, plan, inputs, outputs, artifact, _signed_tx = _signed_fixture()
    store.insert_transaction_artifact(artifact)

    preflight, _report, indexed_inputs = build_broadcast_preflight(
        artifact=artifact,
        plan=plan,
        batch=batch,
        inputs=inputs,
        outputs=outputs,
        network="devnet",
        created_at=1_700_000_403,
    )
    store.insert_broadcast_preflight(preflight, input_outpoints=indexed_inputs)

    loaded = store.get_broadcast_preflight(preflight.preflight_id)
    listed = store.list_broadcast_preflights()
    conflicts = store.find_preflight_input_conflicts()
    status = store.store_status()

    assert loaded is not None
    loaded_preflight, loaded_inputs = loaded
    assert loaded_preflight.preflight_id == preflight.preflight_id
    assert loaded_inputs == indexed_inputs
    assert [entry.preflight_id for entry in listed] == [preflight.preflight_id]
    assert conflicts == {(inputs[0].txid, inputs[0].vout): [preflight.preflight_id]}
    assert status["preflight_count"] == 1
