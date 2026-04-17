from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from chipcoin.consensus.economics import subsidy_split_chipbits
from chipcoin.consensus.epoch_settlement import RewardAttestation, parse_reward_settlement_metadata
from chipcoin.consensus.models import Block, Transaction
from chipcoin.consensus.params import DEVNET_PARAMS
from chipcoin.consensus.pow import verify_proof_of_work
from chipcoin.node.service import NodeService
from chipcoin.consensus.validation import ValidationError
from chipcoin.wallet.signer import TransactionSigner
from tests.helpers import wallet_key


def _make_params():
    return replace(
        DEVNET_PARAMS,
        node_reward_activation_height=0,
        epoch_length_blocks=5,
        reward_check_windows_per_epoch=4,
        reward_target_checks_per_epoch=1,
        reward_min_passed_checks_per_epoch=1,
        reward_verifier_committee_size=1,
        reward_verifier_quorum=1,
        reward_final_confirmation_window_blocks=1,
        max_rewarded_nodes_per_epoch=4,
    )


def _make_service(database_path: Path, *, start_time: int = 1_700_000_000) -> NodeService:
    timestamps = iter(range(start_time, start_time + 400))
    return NodeService.open_sqlite(database_path, network="devnet", params=_make_params(), time_provider=lambda: next(timestamps))


def _mine_block(block: Block) -> Block:
    for nonce in range(2_000_000):
        header = replace(block.header, nonce=nonce)
        if verify_proof_of_work(header):
            return replace(block, header=header)
    raise AssertionError("Expected to find a valid nonce for the easy target.")


def _mine_local_block(service: NodeService, payout_address: str) -> Block:
    block = _mine_block(service.build_candidate_block(payout_address).block)
    service.apply_block(block)
    return block


def _mine_until_height(service: NodeService, payout_address: str, target_height: int) -> None:
    while service.chain_tip() is not None and service.chain_tip().height < target_height:
        _mine_local_block(service, payout_address)


def _register_reward_node(service: NodeService, *, wallet, node_id: str, port: int) -> None:
    service.receive_transaction(
        TransactionSigner(wallet).build_register_reward_node_transaction(
            node_id=node_id,
            payout_address=wallet.address,
            node_public_key_hex=wallet.public_key.hex(),
            declared_host="127.0.0.1",
            declared_port=port,
            registration_fee_chipbits=service.params.register_node_fee_chipbits,
        )
    )


def _submit_signed_attestation(
    service: NodeService,
    *,
    epoch_index: int,
    candidate_node_id: str,
    verifier_wallet,
    verifier_node_id: str,
    window_index: int,
    endpoint_commitment: str,
    concentration_key: str,
) -> None:
    attestation = TransactionSigner(verifier_wallet).sign_reward_attestation(
        RewardAttestation(
            epoch_index=epoch_index,
            check_window_index=window_index,
            candidate_node_id=candidate_node_id,
            verifier_node_id=verifier_node_id,
            result_code="pass",
            observed_sync_gap=0,
            endpoint_commitment=endpoint_commitment,
            concentration_key=concentration_key,
            signature_hex="",
        )
    )
    service.receive_transaction(
        Transaction(
            version=1,
            inputs=(),
            outputs=(),
            metadata={
                "kind": "reward_attestation_bundle",
                "epoch_index": str(epoch_index),
                "bundle_window_index": str(window_index),
                "bundle_submitter_node_id": verifier_node_id,
                "attestation_count": "1",
                "attestations_json": json.dumps(
                    [
                        {
                            "epoch_index": attestation.epoch_index,
                            "check_window_index": attestation.check_window_index,
                            "candidate_node_id": attestation.candidate_node_id,
                            "verifier_node_id": attestation.verifier_node_id,
                            "result_code": attestation.result_code,
                            "observed_sync_gap": attestation.observed_sync_gap,
                            "endpoint_commitment": attestation.endpoint_commitment,
                            "concentration_key": attestation.concentration_key,
                            "signature_hex": attestation.signature_hex,
                        }
                    ],
                    sort_keys=True,
                ),
            },
        )
    )


def _build_settlement_transaction(preview: dict[str, object]) -> Transaction:
    return Transaction(
        version=1,
        inputs=(),
        outputs=(),
        metadata={
            "kind": "reward_settle_epoch",
            "epoch_index": str(preview["epoch_index"]),
            "epoch_start_height": str(preview["epoch_start_height"]),
            "epoch_end_height": str(preview["epoch_end_height"]),
            "epoch_seed": str(preview["epoch_seed"]),
            "policy_version": str(preview["policy_version"]),
            "candidate_summary_root": str(preview["candidate_summary_root"]),
            "verified_nodes_root": str(preview["verified_nodes_root"]),
            "rewarded_nodes_root": str(preview["rewarded_nodes_root"]),
            "rewarded_node_count": str(preview["rewarded_node_count"]),
            "distributed_node_reward_chipbits": str(preview["distributed_node_reward_chipbits"]),
            "undistributed_node_reward_chipbits": str(preview["undistributed_node_reward_chipbits"]),
            "reward_entries_json": json.dumps(preview["reward_entries"], sort_keys=True),
        },
    )


def _qualify_reward_node_for_epoch(
    service: NodeService,
    *,
    epoch_index: int,
    candidate_node_id: str,
    verifier_wallets_by_node_id: dict[str, object],
) -> None:
    assignment = service.native_reward_assignments(epoch_index=epoch_index, node_id=candidate_node_id)[0]
    window_index = assignment["candidate_check_windows"][-1]
    verifier_node_id = assignment["verifier_committees"][str(window_index)][0]
    _submit_signed_attestation(
        service,
        epoch_index=epoch_index,
        candidate_node_id=candidate_node_id,
        verifier_wallet=verifier_wallets_by_node_id[verifier_node_id],
        verifier_node_id=verifier_node_id,
        window_index=window_index,
        endpoint_commitment=f"{assignment['declared_host']}:{assignment['declared_port']}",
        concentration_key=f"demo:{candidate_node_id}",
    )


def test_native_reward_node_registration_and_renewal_persist_in_local_chain() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "chipcoin.sqlite3")
        owner = wallet_key(0)
        signer = TransactionSigner(owner)

        register_tx = signer.build_register_reward_node_transaction(
            node_id="reward-node-a",
            payout_address=owner.address,
            node_public_key_hex=owner.public_key.hex(),
            declared_host="127.0.0.1",
            declared_port=19001,
            registration_fee_chipbits=service.params.register_node_fee_chipbits,
        )
        service.receive_transaction(register_tx)
        _mine_local_block(service, wallet_key(1).address)

        renew_tx = signer.build_renew_reward_node_transaction(
            node_id="reward-node-a",
            renewal_epoch=service.next_block_epoch(),
            declared_host="127.0.0.1",
            declared_port=19011,
            renewal_fee_chipbits=service.params.renew_node_fee_chipbits,
        )
        service.receive_transaction(renew_tx)
        _mine_local_block(service, wallet_key(1).address)

        record = service.get_registered_node("reward-node-a")
        assert record is not None
        assert record.reward_registration is True
        assert record.node_pubkey == owner.public_key
        assert record.declared_host == "127.0.0.1"
        assert record.declared_port == 19011
        assert record.last_renewed_height == 1


def test_native_reward_attestation_and_auto_settlement_persist_after_mining() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "chipcoin.sqlite3")
        reward_a = wallet_key(0)
        reward_b = wallet_key(1)

        for node_id, wallet, port in (
            ("reward-node-a", reward_a, 19001),
            ("reward-node-b", reward_b, 19002),
        ):
            _register_reward_node(service, wallet=wallet, node_id=node_id, port=port)
        _mine_local_block(service, wallet_key(2).address)

        assignment = service.native_reward_assignments(epoch_index=0, node_id="reward-node-a")[0]
        assert assignment["declared_host"] == "127.0.0.1"
        assert assignment["declared_port"] == 19001
        window_index = assignment["candidate_check_windows"][0]
        verifier_node_id = assignment["verifier_committees"][str(window_index)][0]
        assert verifier_node_id == "reward-node-b"

        _submit_signed_attestation(
            service,
            epoch_index=0,
            candidate_node_id="reward-node-a",
            verifier_wallet=reward_b,
            verifier_node_id=verifier_node_id,
            window_index=window_index,
            endpoint_commitment="127.0.0.1:19001",
            concentration_key="demo:reward-node-a",
        )
        _mine_local_block(service, wallet_key(2).address)

        stored_bundles = service.native_reward_attestation_diagnostics(epoch_index=0)
        assert len(stored_bundles) == 1
        assert stored_bundles[0]["block_height"] == 1
        assert stored_bundles[0]["bundle_window_index"] == window_index
        assert stored_bundles[0]["attestations"][0]["verifier_node_id"] == "reward-node-b"

        preview = service.native_reward_settlement_preview(epoch_index=0)
        assert preview["rewarded_node_count"] == 1
        assert preview["reward_entries"][0]["node_id"] == "reward-node-a"
        assert preview["distributed_node_reward_chipbits"] == subsidy_split_chipbits(4, service.params)[1]
        built_once = service.build_native_reward_settlement_transaction(epoch_index=0, submission_mode="auto")
        built_twice = service.build_native_reward_settlement_transaction(epoch_index=0, submission_mode="auto")
        assert built_once.metadata == built_twice.metadata
        _mine_until_height(service, wallet_key(2).address, 3)
        closing_block = _mine_local_block(service, wallet_key(2).address)

        stored_settlements = service.native_reward_settlement_diagnostics(epoch_index=0)
        assert len(stored_settlements) == 1
        assert stored_settlements[0]["block_height"] == 4
        assert stored_settlements[0]["submission_mode"] == "auto"
        assert stored_settlements[0]["rewarded_node_count"] == 1
        assert stored_settlements[0]["reward_entries"][0]["node_id"] == "reward-node-a"
        inspect = service.inspect_block(block_hash=closing_block.block_hash())
        assert inspect is not None
        assert inspect["node_reward_payouts"] == [
            {"recipient": reward_a.address, "amount_chipbits": subsidy_split_chipbits(4, service.params)[1]}
        ]
        reward_rows = service.reward_history(reward_a.address, limit=10)
        assert any(row["amount_chipbits"] == subsidy_split_chipbits(4, service.params)[1] for row in reward_rows)


def test_native_reward_settlement_preview_returns_zero_recipients_when_no_candidate_qualifies() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "chipcoin.sqlite3")
        _register_reward_node(service, wallet=wallet_key(0), node_id="reward-node-a", port=19001)
        _register_reward_node(service, wallet=wallet_key(1), node_id="reward-node-b", port=19002)
        _mine_local_block(service, wallet_key(2).address)
        _mine_until_height(service, wallet_key(2).address, 3)

        preview = service.native_reward_settlement_preview(epoch_index=0)

        assert preview["rewarded_node_count"] == 0
        assert preview["reward_entries"] == []
        assert preview["distributed_node_reward_chipbits"] == 0
        assert preview["undistributed_node_reward_chipbits"] == subsidy_split_chipbits(4, service.params)[1]
        closing_block = _mine_local_block(service, wallet_key(2).address)
        stored_settlements = service.native_reward_settlement_diagnostics(epoch_index=0)
        assert len(stored_settlements) == 1
        assert stored_settlements[0]["submission_mode"] == "auto"
        assert stored_settlements[0]["reward_entries"] == []
        inspect = service.inspect_block(block_hash=closing_block.block_hash())
        assert inspect is not None
        assert inspect["node_reward_payouts"] == []


def test_native_reward_auto_settlement_materializes_multiple_reward_outputs() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "chipcoin.sqlite3")
        reward_a = wallet_key(0)
        reward_b = wallet_key(1)
        reward_c = wallet_key(2)

        for node_id, wallet, port in (
            ("reward-node-a", reward_a, 19001),
            ("reward-node-b", reward_b, 19002),
            ("reward-node-c", reward_c, 19003),
        ):
            _register_reward_node(service, wallet=wallet, node_id=node_id, port=port)
        _mine_local_block(service, reward_a.address)

        assignments_a = service.native_reward_assignments(epoch_index=0, node_id="reward-node-a")[0]
        window_a = assignments_a["candidate_check_windows"][0]
        verifier_a = assignments_a["verifier_committees"][str(window_a)][0]
        verifier_a_wallet = {"reward-node-a": reward_a, "reward-node-b": reward_b, "reward-node-c": reward_c}[verifier_a]
        _submit_signed_attestation(
            service,
            epoch_index=0,
            candidate_node_id="reward-node-a",
            verifier_wallet=verifier_a_wallet,
            verifier_node_id=verifier_a,
            window_index=window_a,
            endpoint_commitment="127.0.0.1:19001",
            concentration_key="demo:reward-node-a",
        )

        assignments_b = service.native_reward_assignments(epoch_index=0, node_id="reward-node-b")[0]
        window_b = assignments_b["candidate_check_windows"][0]
        verifier_b = assignments_b["verifier_committees"][str(window_b)][0]
        verifier_b_wallet = {"reward-node-a": reward_a, "reward-node-b": reward_b, "reward-node-c": reward_c}[verifier_b]
        _submit_signed_attestation(
            service,
            epoch_index=0,
            candidate_node_id="reward-node-b",
            verifier_wallet=verifier_b_wallet,
            verifier_node_id=verifier_b,
            window_index=window_b,
            endpoint_commitment="127.0.0.1:19002",
            concentration_key="demo:reward-node-b",
        )
        _mine_local_block(service, reward_a.address)

        _mine_until_height(service, reward_a.address, 3)

        preview = service.native_reward_settlement_preview(epoch_index=0)
        expected_pool = subsidy_split_chipbits(4, service.params)[1]
        assert preview["rewarded_node_count"] == 2
        assert preview["distributed_node_reward_chipbits"] == expected_pool
        assert preview["undistributed_node_reward_chipbits"] == 0
        amounts = [entry["reward_chipbits"] for entry in preview["reward_entries"]]
        assert amounts == [expected_pool // 2, expected_pool // 2]

        closing_block = _mine_local_block(service, reward_a.address)
        stored_settlements = service.native_reward_settlement_diagnostics(epoch_index=0)
        assert len(stored_settlements) == 1
        assert stored_settlements[0]["submission_mode"] == "auto"
        inspect = service.inspect_block(block_hash=closing_block.block_hash())
        assert inspect is not None
        assert inspect["node_reward_payouts"] == [
            {"recipient": preview["reward_entries"][0]["payout_address"], "amount_chipbits": preview["reward_entries"][0]["reward_chipbits"]},
            {"recipient": preview["reward_entries"][1]["payout_address"], "amount_chipbits": preview["reward_entries"][1]["reward_chipbits"]},
        ]


def test_native_reward_manual_settlement_takes_precedence_over_auto_generation() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "chipcoin.sqlite3")
        reward_a = wallet_key(0)
        reward_b = wallet_key(1)

        for node_id, wallet, port in (
            ("reward-node-a", reward_a, 19001),
            ("reward-node-b", reward_b, 19002),
        ):
            _register_reward_node(service, wallet=wallet, node_id=node_id, port=port)
        _mine_local_block(service, wallet_key(2).address)

        assignment = service.native_reward_assignments(epoch_index=0, node_id="reward-node-a")[0]
        window_index = assignment["candidate_check_windows"][0]
        verifier_node_id = assignment["verifier_committees"][str(window_index)][0]
        _submit_signed_attestation(
            service,
            epoch_index=0,
            candidate_node_id="reward-node-a",
            verifier_wallet=reward_b,
            verifier_node_id=verifier_node_id,
            window_index=window_index,
            endpoint_commitment="127.0.0.1:19001",
            concentration_key="demo:reward-node-a",
        )
        _mine_until_height(service, wallet_key(2).address, 3)

        manual_preview = service.native_reward_settlement_preview(epoch_index=0)
        assert manual_preview["rewarded_node_count"] == 1
        manual_tx = _build_settlement_transaction(manual_preview)
        service.receive_transaction(manual_tx)
        closing_block = _mine_local_block(service, wallet_key(2).address)

        settlement_transactions = [
            transaction
            for transaction in closing_block.transactions
            if transaction.metadata.get("kind") == "reward_settle_epoch"
        ]
        assert len(settlement_transactions) == 1
        assert settlement_transactions[0].txid() == manual_tx.txid()
        stored_settlements = service.native_reward_settlement_diagnostics(epoch_index=0)
        assert stored_settlements[0]["submission_mode"] == "manual"


def test_native_reward_auto_settlement_does_not_generate_second_settlement_after_epoch_close() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "chipcoin.sqlite3")
        _register_reward_node(service, wallet=wallet_key(0), node_id="reward-node-a", port=19001)
        _register_reward_node(service, wallet=wallet_key(1), node_id="reward-node-b", port=19002)
        _mine_local_block(service, wallet_key(2).address)
        _mine_until_height(service, wallet_key(2).address, 3)
        _mine_local_block(service, wallet_key(2).address)
        assert len(service.native_reward_settlement_diagnostics(epoch_index=0)) == 1
        next_block = _mine_local_block(service, wallet_key(2).address)
        settlement_transactions = [
            transaction
            for transaction in next_block.transactions
            if transaction.metadata.get("kind") == "reward_settle_epoch"
        ]
        assert settlement_transactions == []
        assert len(service.native_reward_settlement_diagnostics(epoch_index=0)) == 1


def test_native_reward_rebuilt_closing_block_is_deterministic_and_does_not_double_pay() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "chipcoin.sqlite3")
        reward_a = wallet_key(0)
        reward_b = wallet_key(1)
        _register_reward_node(service, wallet=reward_a, node_id="reward-node-a", port=19001)
        _register_reward_node(service, wallet=reward_b, node_id="reward-node-b", port=19002)
        _mine_local_block(service, wallet_key(2).address)
        assignment = service.native_reward_assignments(epoch_index=0, node_id="reward-node-a")[0]
        window_index = assignment["candidate_check_windows"][0]
        verifier_node_id = assignment["verifier_committees"][str(window_index)][0]
        _submit_signed_attestation(
            service,
            epoch_index=0,
            candidate_node_id="reward-node-a",
            verifier_wallet=reward_b,
            verifier_node_id=verifier_node_id,
            window_index=window_index,
            endpoint_commitment="127.0.0.1:19001",
            concentration_key="demo:reward-node-a",
        )
        _mine_local_block(service, wallet_key(2).address)
        _mine_until_height(service, wallet_key(2).address, 3)

        candidate_one = service.build_candidate_block(wallet_key(2).address).block
        candidate_two = service.build_candidate_block(wallet_key(2).address).block
        settlement_one = next(
            transaction for transaction in candidate_one.transactions if transaction.metadata.get("kind") == "reward_settle_epoch"
        )
        settlement_two = next(
            transaction for transaction in candidate_two.transactions if transaction.metadata.get("kind") == "reward_settle_epoch"
        )
        assert settlement_one.metadata == settlement_two.metadata
        assert candidate_one.transactions[0].outputs == candidate_two.transactions[0].outputs

        closing_block = _mine_local_block(service, wallet_key(2).address)
        inspect = service.inspect_block(block_hash=closing_block.block_hash())
        assert inspect is not None
        assert len(inspect["node_reward_payouts"]) == 1
        next_block = _mine_local_block(service, wallet_key(2).address)
        next_inspect = service.inspect_block(block_hash=next_block.block_hash())
        assert next_inspect is not None
        assert next_inspect["node_reward_payouts"] == []


def test_native_reward_invalid_manual_settlement_is_rejected_before_auto_close() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "chipcoin.sqlite3")
        _register_reward_node(service, wallet=wallet_key(0), node_id="reward-node-a", port=19001)
        _register_reward_node(service, wallet=wallet_key(1), node_id="reward-node-b", port=19002)
        _mine_local_block(service, wallet_key(2).address)
        _mine_until_height(service, wallet_key(2).address, 3)

        preview = service.native_reward_settlement_preview(epoch_index=0)
        invalid_tx = _build_settlement_transaction({**preview, "epoch_seed": "00" * 32})
        try:
            service.receive_transaction(invalid_tx)
        except ValidationError:
            pass
        else:
            raise AssertionError("Expected invalid manual settlement to be rejected.")

        closing_block = _mine_local_block(service, wallet_key(2).address)
        settlement_transactions = [
            parse_reward_settlement_metadata(transaction.metadata)
            for transaction in closing_block.transactions
            if transaction.metadata.get("kind") == "reward_settle_epoch"
        ]
        assert len(settlement_transactions) == 1
        assert settlement_transactions[0].submission_mode == "auto"


def test_native_reward_expired_node_is_not_rewarded_in_following_epoch() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "chipcoin.sqlite3")
        reward_a = wallet_key(0)
        reward_b = wallet_key(1)
        _register_reward_node(service, wallet=reward_a, node_id="reward-node-a", port=19001)
        _register_reward_node(service, wallet=reward_b, node_id="reward-node-b", port=19002)
        _mine_local_block(service, wallet_key(2).address)

        _qualify_reward_node_for_epoch(
            service,
            epoch_index=0,
            candidate_node_id="reward-node-a",
            verifier_wallets_by_node_id={"reward-node-a": reward_a, "reward-node-b": reward_b},
        )
        _mine_local_block(service, wallet_key(2).address)
        _mine_until_height(service, wallet_key(2).address, 4)
        _mine_local_block(service, wallet_key(2).address)

        assert service.native_reward_settlement_diagnostics(epoch_index=0)[0]["rewarded_node_count"] == 1
        epoch_one_preview = service.native_reward_settlement_preview(epoch_index=1)
        assert epoch_one_preview["rewarded_node_count"] == 0
        assert service.native_reward_assignments(epoch_index=1, node_id="reward-node-a") == []


def test_native_reward_snapshot_restore_mid_cycle_preserves_auto_settlement_path() -> None:
    with TemporaryDirectory() as tempdir:
        source_path = Path(tempdir) / "source.sqlite3"
        target_path = Path(tempdir) / "target.sqlite3"
        snapshot_path = Path(tempdir) / "midcycle.snapshot"
        source = _make_service(source_path)
        reward_a = wallet_key(0)
        reward_b = wallet_key(1)
        _register_reward_node(source, wallet=reward_a, node_id="reward-node-a", port=19001)
        _register_reward_node(source, wallet=reward_b, node_id="reward-node-b", port=19002)
        _mine_local_block(source, wallet_key(2).address)
        _qualify_reward_node_for_epoch(
            source,
            epoch_index=0,
            candidate_node_id="reward-node-a",
            verifier_wallets_by_node_id={"reward-node-a": reward_a, "reward-node-b": reward_b},
        )
        _mine_local_block(source, wallet_key(2).address)
        source.export_snapshot_file(snapshot_path)

        target = _make_service(target_path, start_time=1_700_001_000)
        target.import_snapshot_file(snapshot_path)
        _mine_until_height(target, wallet_key(2).address, 3)
        closing_block = _mine_local_block(target, wallet_key(2).address)
        inspect = target.inspect_block(block_hash=closing_block.block_hash())
        assert inspect is not None
        assert inspect["node_reward_payouts"] == [
            {"recipient": reward_a.address, "amount_chipbits": subsidy_split_chipbits(4, target.params)[1]}
        ]
        stored = target.native_reward_settlement_diagnostics(epoch_index=0)
        assert len(stored) == 1
        assert stored[0]["submission_mode"] == "auto"


def test_native_reward_multi_epoch_consecutive_auto_settlement_operation() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "chipcoin.sqlite3")
        reward_a = wallet_key(0)
        reward_b = wallet_key(1)
        verifier_wallets = {"reward-node-a": reward_a, "reward-node-b": reward_b}
        _register_reward_node(service, wallet=reward_a, node_id="reward-node-a", port=19001)
        _register_reward_node(service, wallet=reward_b, node_id="reward-node-b", port=19002)
        _mine_local_block(service, wallet_key(2).address)

        _qualify_reward_node_for_epoch(
            service,
            epoch_index=0,
            candidate_node_id="reward-node-a",
            verifier_wallets_by_node_id=verifier_wallets,
        )
        _mine_local_block(service, wallet_key(2).address)
        _mine_until_height(service, wallet_key(2).address, 4)
        _mine_local_block(service, wallet_key(2).address)
        assert service.native_reward_settlement_diagnostics(epoch_index=0)[0]["rewarded_node_count"] == 1

        service.receive_transaction(
            TransactionSigner(reward_a).build_renew_reward_node_transaction(
                node_id="reward-node-a",
                renewal_epoch=service.next_block_epoch(),
                declared_host="127.0.0.1",
                declared_port=19001,
                renewal_fee_chipbits=service.params.renew_node_fee_chipbits,
            )
        )
        service.receive_transaction(
            TransactionSigner(reward_b).build_renew_reward_node_transaction(
                node_id="reward-node-b",
                renewal_epoch=service.next_block_epoch(),
                declared_host="127.0.0.1",
                declared_port=19002,
                renewal_fee_chipbits=service.params.renew_node_fee_chipbits,
            )
        )
        _mine_local_block(service, wallet_key(2).address)
        _qualify_reward_node_for_epoch(
            service,
            epoch_index=1,
            candidate_node_id="reward-node-a",
            verifier_wallets_by_node_id=verifier_wallets,
        )
        _mine_local_block(service, wallet_key(2).address)
        _mine_until_height(service, wallet_key(2).address, 8)
        second_closing = _mine_local_block(service, wallet_key(2).address)

        settlements = service.native_reward_settlement_diagnostics()
        assert [row["epoch_index"] for row in settlements] == [0, 1]
        assert all(row["submission_mode"] == "auto" for row in settlements)
        inspect = service.inspect_block(block_hash=second_closing.block_hash())
        assert inspect is not None
        assert inspect["node_reward_payouts"] == [
            {"recipient": reward_a.address, "amount_chipbits": subsidy_split_chipbits(9, service.params)[1]}
        ]
