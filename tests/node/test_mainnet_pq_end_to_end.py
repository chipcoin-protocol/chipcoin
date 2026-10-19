from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from chipcoin.consensus.economics import subsidy_split_chipbits
from chipcoin.consensus.epoch_settlement import RewardAttestation
from chipcoin.consensus.genesis import mine_genesis
from chipcoin.consensus.models import Block, OutPoint, Transaction
from chipcoin.consensus.params import MAINNET_PARAMS
from chipcoin.consensus.network_identity import PUBLIC_MAINNET_CHAIN_ID
from chipcoin.consensus.pow import verify_proof_of_work
from chipcoin.consensus.validation import ContextualValidationError
from chipcoin.crypto.pq import SIG_SCHEME_ML_DSA_44
from chipcoin.node.service import NodeService
from chipcoin.node.sync import SyncManager
from chipcoin.wallet.signer import TransactionSigner, wallet_key_from_mldsa44_seed
from tests.helpers import spend_candidates_for_wallet, wallet_key


MAINNET_PQ_TEST_PARAMS = replace(
    MAINNET_PARAMS,
    genesis_bits=0x207FFFFF,
    coinbase_maturity=2,
    node_reward_activation_height=0,
    epoch_length_blocks=10,
    reward_node_warmup_epochs=0,
    reward_check_windows_per_epoch=4,
    reward_target_checks_per_epoch=1,
    reward_min_passed_checks_per_epoch=1,
    reward_verifier_committee_size=1,
    reward_verifier_quorum=1,
    reward_final_confirmation_window_blocks=1,
    max_rewarded_nodes_per_epoch=4,
)


def _wallet(seed_byte: int):
    return wallet_key_from_mldsa44_seed(bytes((seed_byte,)) * 32)


def _make_service(database_path: Path, *, start_time: int = 1_800_000_000) -> NodeService:
    timestamps = iter(range(start_time, start_time + 1_000))
    service = NodeService.open_sqlite(
        database_path,
        network="mainnet",
        params=MAINNET_PQ_TEST_PARAMS,
        time_provider=lambda: next(timestamps),
    )
    service.install_or_verify_genesis(
        mine_genesis(timestamp=1_799_999_999, bits=MAINNET_PQ_TEST_PARAMS.genesis_bits),
        chain_id=PUBLIC_MAINNET_CHAIN_ID,
    )
    return service


def _mine_block(block: Block) -> Block:
    for nonce in range(2_000_000):
        header = replace(block.header, nonce=nonce)
        if verify_proof_of_work(header):
            return replace(block, header=header)
    raise AssertionError("Expected to find a valid nonce for the easy test target.")


def _mine(service: NodeService, payout_address: str) -> Block:
    block = _mine_block(service.build_candidate_block(payout_address).block)
    service.apply_block(block)
    return block


def _mine_chain(service: NodeService, count: int, payout_address: str) -> list[Block]:
    return [_mine(service, payout_address) for _ in range(count)]


def _register_reward_node(service: NodeService, *, wallet, node_id: str, port: int) -> None:
    service.receive_transaction(
        TransactionSigner(wallet).build_register_reward_node_transaction(
            node_id=node_id,
            payout_address=wallet.address,
            node_public_key_hex=wallet.public_key.hex(),
            node_signature_scheme_id=wallet.scheme_id,
            declared_host="127.0.0.1",
            declared_port=port,
            registration_fee_chipbits=int(service.reward_node_fee_schedule()["register_fee_chipbits"]),
            network="mainnet",
            height=service.chain_tip().height + 1,
            funded=True,
            spend_candidates=service.list_spendable_outputs(wallet.address),
        )
    )


def _fund_reward_owner(service: NodeService, *, miner, owner, amount_chipbits: int) -> Transaction:
    built = TransactionSigner(miner).build_signed_transaction(
        spend_candidates=service.list_spendable_outputs(miner.address),
        recipient=owner.address,
        amount_chipbits=amount_chipbits,
        fee_chipbits=1_000,
        change_recipient=miner.address,
        network="mainnet",
    )
    service.receive_transaction(built.transaction)
    block = _mine(service, miner.address)
    assert block.transactions[1].txid() == built.transaction.txid()
    block_height = int(block.transactions[0].metadata["height"])
    assert int(block.transactions[0].outputs[0].value) == subsidy_split_chipbits(block_height, service.params)[0] + 1_000
    return built.transaction


def _submit_attestation(
    service: NodeService,
    *,
    candidate_node_id: str,
    verifier_node_id: str,
    verifier_wallet,
) -> None:
    assignment = service.native_reward_assignments(epoch_index=0, node_id=candidate_node_id)[0]
    window_index = next(
        window
        for window in assignment["candidate_check_windows"]
        if verifier_node_id in assignment["verifier_committees"].get(str(window), [])
    )
    attestation = TransactionSigner(verifier_wallet).sign_reward_attestation(
        RewardAttestation(
            epoch_index=0,
            check_window_index=window_index,
            candidate_node_id=candidate_node_id,
            verifier_node_id=verifier_node_id,
            result_code="pass",
            observed_sync_gap=0,
            endpoint_commitment=f"{assignment['declared_host']}:{assignment['declared_port']}",
            concentration_key=f"mainnet-pq:{candidate_node_id}",
            signature_hex="",
        ),
        network="mainnet",
    )
    service.receive_transaction(
        Transaction(
            version=1,
            inputs=(),
            outputs=(),
            metadata={
                "kind": "reward_attestation_bundle",
                "epoch_index": "0",
                "bundle_window_index": str(window_index),
                "bundle_submitter_node_id": verifier_node_id,
                "attestation_count": "1",
                "attestations_json": json.dumps([asdict(attestation)], sort_keys=True),
            },
        )
    )


def test_mainnet_pq_value_and_reward_node_lifecycle_end_to_end() -> None:
    with TemporaryDirectory() as tempdir:
        database_path = Path(tempdir) / "mainnet-pq.sqlite3"
        service = _make_service(database_path)
        miner = _wallet(1)
        recipient = _wallet(2)
        reward_a = _wallet(3)
        reward_b = _wallet(4)

        genesis_successor = _mine(service, miner.address)
        coinbase = genesis_successor.transactions[0]
        assert coinbase.outputs[0].recipient == miner.address
        assert miner.address.startswith("CHCQ")

        _mine(service, miner.address)
        _fund_reward_owner(service, miner=miner, owner=reward_a, amount_chipbits=200_000_000)
        _fund_reward_owner(service, miner=miner, owner=reward_b, amount_chipbits=200_000_000)

        _register_reward_node(service, wallet=reward_a, node_id="reward-node-a", port=19001)
        _register_reward_node(service, wallet=reward_b, node_id="reward-node-b", port=19002)
        registration_block = _mine(service, miner.address)
        assert sum(int(output.value) for output in registration_block.transactions[0].outputs) == (
            subsidy_split_chipbits(5, service.params)[0] + 200_000_000
        )

        for node_id, wallet in (("reward-node-a", reward_a), ("reward-node-b", reward_b)):
            record = service.get_registered_node(node_id)
            assert record is not None
            assert record.payout_address == wallet.address
            assert record.owner_signature_scheme_id == SIG_SCHEME_ML_DSA_44
            assert record.node_signature_scheme_id == SIG_SCHEME_ML_DSA_44

        spend = TransactionSigner(miner).build_signed_transaction(
            spend_candidates=service.list_spendable_outputs(miner.address),
            recipient=recipient.address,
            amount_chipbits=100_000_000,
            fee_chipbits=1_000,
            change_recipient=miner.address,
            network="mainnet",
        )
        assert spend.transaction.version == 2
        assert all(tx_input.sig_scheme_id == SIG_SCHEME_ML_DSA_44 for tx_input in spend.transaction.inputs)
        service.receive_transaction(spend.transaction)

        renew = TransactionSigner(reward_a).build_renew_reward_node_transaction(
            node_id="reward-node-a",
            renewal_epoch=service.next_block_epoch(),
            declared_host="127.0.0.1",
            declared_port=19101,
            renewal_fee_chipbits=int(service.reward_node_fee_schedule()["renew_fee_chipbits"]),
            network="mainnet",
            height=service.chain_tip().height + 1,
            funded=True,
            spend_candidates=service.list_spendable_outputs(reward_a.address),
        )
        service.receive_transaction(renew)
        _mine(service, miner.address)
        assert service.find_transaction(spend.transaction.txid())["location"] == "chain"
        assert service.get_registered_node("reward-node-a").declared_port == 19101

        assignment = service.native_reward_assignments(epoch_index=0, node_id="reward-node-a")[0]
        verifier_node_id = next(
            verifier
            for window in assignment["candidate_check_windows"]
            for verifier in assignment["verifier_committees"].get(str(window), [])
        )
        verifier_wallet = {"reward-node-a": reward_a, "reward-node-b": reward_b}[verifier_node_id]
        _submit_attestation(
            service,
            candidate_node_id="reward-node-a",
            verifier_node_id=verifier_node_id,
            verifier_wallet=verifier_wallet,
        )
        _mine(service, miner.address)
        _mine(service, miner.address)
        closing_block = _mine(service, miner.address)

        settlement = service.native_reward_settlement_diagnostics(epoch_index=0)[0]
        assert settlement["rewarded_node_count"] == 1
        assert settlement["reward_entries"][0]["node_id"] == "reward-node-a"
        expected_reward = subsidy_split_chipbits(9, service.params)[1]
        assert settlement["distributed_node_reward_chipbits"] == expected_reward
        inspected = service.inspect_block(block_hash=closing_block.block_hash())
        assert inspected is not None
        assert inspected["node_reward_payouts"] == [
            {"recipient": reward_a.address, "amount_chipbits": expected_reward}
        ]

        service.connection.commit()
        service.connection.close()
        reopened = _make_service(database_path)
        persisted = reopened.get_registered_node("reward-node-a")
        assert persisted is not None
        assert persisted.owner_signature_scheme_id == SIG_SCHEME_ML_DSA_44
        assert persisted.node_signature_scheme_id == SIG_SCHEME_ML_DSA_44
        assert reopened.native_reward_settlement_diagnostics(epoch_index=0) == [settlement]


def test_mainnet_rejects_legacy_miner_payout() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "mainnet-legacy-miner.sqlite3")
        block = _mine_block(service.build_candidate_block(wallet_key().address).block)

        with pytest.raises(
            ContextualValidationError,
            match="transaction outputs must use ML-DSA-44 CHCQ addresses",
        ):
            service.apply_block(block)


def test_mainnet_rejects_legacy_reward_node_owner() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "mainnet-legacy-reward-node.sqlite3")
        legacy = wallet_key()
        registration = TransactionSigner(legacy).build_register_reward_node_transaction(
            node_id="legacy-reward-node",
            payout_address=_wallet(9).address,
            node_public_key_hex=legacy.public_key.hex(),
            node_signature_scheme_id=legacy.scheme_id,
            declared_host="127.0.0.1",
            declared_port=19003,
            registration_fee_chipbits=int(service.reward_node_fee_schedule()["register_fee_chipbits"]),
            network="mainnet",
        )

        with pytest.raises(
            ContextualValidationError,
            match="reward-node owner signatures must use ML-DSA-44",
        ):
            service.receive_transaction(registration)


def test_mainnet_pq_multi_input_payment_is_mined() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "mainnet-pq-multi-input.sqlite3")
        miner = _wallet(11)
        recipient = _wallet(12)
        blocks = _mine_chain(service, 3, miner.address)
        coinbases = [block.transactions[0] for block in blocks[:2]]
        input_total = sum(int(transaction.outputs[0].value) for transaction in coinbases)
        amount_chipbits = 6_000_000_000
        candidates = [
            candidate
            for transaction in coinbases
            for candidate in spend_candidates_for_wallet(
                OutPoint(txid=transaction.txid(), index=0),
                value=int(transaction.outputs[0].value),
                owner=miner,
            )
        ]
        built = TransactionSigner(miner).build_signed_transaction(
            spend_candidates=candidates,
            recipient=recipient.address,
            amount_chipbits=amount_chipbits,
            fee_chipbits=2_000,
            change_recipient=miner.address,
            network="mainnet",
        )

        assert built.transaction.version == 2
        assert len(built.transaction.inputs) == 2
        assert all(tx_input.sig_scheme_id == SIG_SCHEME_ML_DSA_44 for tx_input in built.transaction.inputs)
        assert built.change_chipbits == input_total - amount_chipbits - 2_000
        service.receive_transaction(built.transaction)
        _mine(service, miner.address)

        located = service.find_transaction(built.transaction.txid())
        assert located is not None
        assert located["location"] == "chain"


def test_mainnet_pq_nodes_sync_and_reorg_to_more_work() -> None:
    with TemporaryDirectory() as tempdir:
        root = Path(tempdir)
        origin = _make_service(root / "origin.sqlite3")
        node_a = _make_service(root / "node-a.sqlite3", start_time=1_800_010_000)
        node_b = _make_service(root / "node-b.sqlite3", start_time=1_800_020_000)
        miner_a = _wallet(13)
        miner_b = _wallet(14)
        common_blocks = _mine_chain(origin, 3, miner_a.address)

        assert SyncManager(node=node_a).synchronize(origin).headers_received == 3
        assert SyncManager(node=node_b).synchronize(origin).headers_received == 3
        assert node_a.chain_tip() == node_b.chain_tip() == origin.chain_tip()

        coinbase = common_blocks[0].transactions[0]
        spend_a = TransactionSigner(miner_a).build_signed_transaction(
            spend_candidates=spend_candidates_for_wallet(
                OutPoint(txid=coinbase.txid(), index=0),
                value=int(coinbase.outputs[0].value),
                owner=miner_a,
            ),
            recipient=_wallet(15).address,
            amount_chipbits=100_000_000,
            fee_chipbits=1_000,
            change_recipient=miner_a.address,
            network="mainnet",
        ).transaction
        spend_b = TransactionSigner(miner_a).build_signed_transaction(
            spend_candidates=spend_candidates_for_wallet(
                OutPoint(txid=coinbase.txid(), index=0),
                value=int(coinbase.outputs[0].value),
                owner=miner_a,
            ),
            recipient=miner_b.address,
            amount_chipbits=200_000_000,
            fee_chipbits=1_000,
            change_recipient=miner_a.address,
            network="mainnet",
        ).transaction
        node_a.receive_transaction(spend_a)
        branch_a = _mine(node_a, miner_a.address)
        node_b.receive_transaction(spend_b)
        branch_b = _mine_chain(node_b, 2, miner_b.address)

        result = SyncManager(node=node_a).synchronize(node_b)

        assert result.reorged is True
        assert result.old_tip == branch_a.block_hash()
        assert result.new_tip == branch_b[-1].block_hash()
        assert node_a.find_transaction(spend_b.txid())["location"] == "chain"
        assert node_a.find_transaction(spend_a.txid()) is None


def test_mainnet_funded_registration_rolls_back_and_returns_to_mempool_after_reorg() -> None:
    with TemporaryDirectory() as tempdir:
        root = Path(tempdir)
        origin = _make_service(root / "origin.sqlite3")
        node_a = _make_service(root / "node-a.sqlite3", start_time=1_800_010_000)
        node_b = _make_service(root / "node-b.sqlite3", start_time=1_800_020_000)
        miner = _wallet(17)
        owner = _wallet(18)

        _mine_chain(origin, 3, miner.address)
        _fund_reward_owner(origin, miner=miner, owner=owner, amount_chipbits=200_000_000)
        assert SyncManager(node=node_a).synchronize(origin).blocks_fetched == 4
        assert SyncManager(node=node_b).synchronize(origin).blocks_fetched == 4

        registration = TransactionSigner(owner).build_register_reward_node_transaction(
            node_id="reorg-funded-node",
            payout_address=owner.address,
            node_public_key_hex=owner.public_key.hex(),
            node_signature_scheme_id=owner.scheme_id,
            declared_host="127.0.0.1",
            declared_port=19018,
            registration_fee_chipbits=int(node_a.reward_node_fee_schedule()["register_fee_chipbits"]),
            network="mainnet",
            height=node_a.chain_tip().height + 1,
            funded=True,
            spend_candidates=node_a.list_spendable_outputs(owner.address),
        )
        node_a.receive_transaction(registration)
        orphaned_block = _mine(node_a, miner.address)
        orphaned_coinbase = OutPoint(orphaned_block.transactions[0].txid(), 0)
        assert node_a.get_registered_node("reorg-funded-node") is not None

        winning_branch = _mine_chain(node_b, 2, miner.address)
        result = SyncManager(node=node_a).synchronize(node_b)

        assert result.reorged is True
        assert result.old_tip == orphaned_block.block_hash()
        assert result.new_tip == winning_branch[-1].block_hash()
        assert node_a.get_registered_node("reorg-funded-node") is None
        assert node_a.chainstate.get(registration.inputs[0].previous_output) is not None
        assert node_a.chainstate.get(OutPoint(registration.txid(), 0)) is None
        assert node_a.chainstate.get(orphaned_coinbase) is None
        assert [transaction.txid() for transaction in node_a.list_mempool_transactions()] == [
            registration.txid()
        ]
        assert node_a.chain_tip() == node_b.chain_tip()
        assert node_a.chainstate.list_utxos() == node_b.chainstate.list_utxos()


def test_mainnet_pq_snapshot_roundtrip_and_delta_sync() -> None:
    with TemporaryDirectory() as tempdir:
        root = Path(tempdir)
        source = _make_service(root / "source.sqlite3")
        miner = _wallet(16)
        initial_blocks = _mine_chain(source, 3, miner.address)
        snapshot_path = root / "mainnet-pq.snapshot"
        metadata = source.export_snapshot_file(snapshot_path)

        target = _make_service(root / "target.sqlite3")
        imported = target.import_snapshot_file(snapshot_path)
        assert imported["checksum_sha256"] == metadata["checksum_sha256"]
        assert target.chain_tip() == source.chain_tip()
        assert target.chainstate.list_utxos() == source.chainstate.list_utxos()
        assert target.snapshot_anchor() is not None
        assert target.snapshot_anchor().block_hash == initial_blocks[-1].block_hash()

        extension = _mine_chain(source, 2, miner.address)
        result = SyncManager(node=target).synchronize(source)
        assert result.blocks_fetched == 2
        assert result.reorged is False
        assert target.chain_tip() is not None
        assert target.chain_tip().block_hash == extension[-1].block_hash()
