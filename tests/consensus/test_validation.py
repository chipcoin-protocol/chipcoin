import json
from dataclasses import replace

from chipcoin.consensus.economics import block_subsidy, subsidy_split_chipbits
from chipcoin.consensus.economics import renew_reward_node_fee_chipbits, register_reward_node_fee_chipbits
from chipcoin.consensus.epoch_settlement import (
    REWARD_ATTESTATION_BUNDLE_KIND,
    REWARD_SETTLE_EPOCH_KIND,
    RewardAttestation,
    RewardAttestationBundle,
    attestation_identity,
    candidate_check_windows,
    verifier_committee,
)
from chipcoin.consensus.merkle import merkle_root
from chipcoin.consensus.models import Block, BlockHeader, OutPoint, Transaction, TxInput, TxOutput
from chipcoin.consensus.nodes import InMemoryNodeRegistryView, NodeRecord
from chipcoin.consensus.params import MAINNET_PARAMS
from chipcoin.consensus.utxo import InMemoryUtxoView, UtxoEntry
from chipcoin.consensus.validation import (
    ContextualValidationError,
    StatelessValidationError,
    ValidationContext,
    is_coinbase_mature,
    transaction_signature_digest,
    validate_block,
    validate_transaction,
)
from chipcoin.wallet.signer import TransactionSigner
from tests.helpers import signed_payment, wallet_key


def _expect_raises(exc_type: type[BaseException], fn) -> None:
    try:
        fn()
    except exc_type:
        return
    raise AssertionError(f"Expected {exc_type.__name__} to be raised.")


def _mine_easy_header(previous_block_hash: str, merkle_root_hex: str, *, timestamp: int = 1_700_000_000) -> BlockHeader:
    for nonce in range(2_000_000):
        header = BlockHeader(
            version=1,
            previous_block_hash=previous_block_hash,
            merkle_root=merkle_root_hex,
            timestamp=timestamp,
            bits=MAINNET_PARAMS.genesis_bits,
            nonce=nonce,
        )
        from chipcoin.consensus.pow import verify_proof_of_work

        if verify_proof_of_work(header):
            return header
    raise AssertionError("Expected to find a valid header nonce for the easy target.")


def _coinbase_transaction(value: int, recipient: str = "CHCminer") -> Transaction:
    return Transaction(
        version=1,
        inputs=(),
        outputs=(TxOutput(value=value, recipient=recipient),),
        metadata={"coinbase": "true"},
    )


def _spend_transaction(previous_outpoint: OutPoint, *, input_value: int = 100, fee: int = 10, sender=None) -> Transaction:
    return signed_payment(previous_outpoint, value=input_value, sender=sender or wallet_key(0), fee=fee)


def _register_reward_node_transaction(*, node_id: str, owner_index: int = 0, fee_chipbits: int | None = None) -> Transaction:
    owner = wallet_key(owner_index)
    node_key = wallet_key((owner_index + 1) % 3)
    metadata = {
        "kind": "register_reward_node",
        "node_id": node_id,
        "payout_address": owner.address,
        "owner_pubkey_hex": owner.public_key.hex(),
        "node_pubkey_hex": node_key.public_key.hex(),
        "declared_host": f"{node_id}.example",
        "declared_port": "18444",
        "registration_fee_chipbits": str(
            register_reward_node_fee_chipbits(registered_reward_node_count=0, params=MAINNET_PARAMS)
            if fee_chipbits is None
            else fee_chipbits
        ),
        "owner_signature_hex": "",
    }
    unsigned = Transaction(version=1, inputs=(), outputs=(), metadata=metadata)
    from chipcoin.consensus.nodes import special_node_transaction_signature_digest
    from chipcoin.crypto.signatures import sign_digest

    metadata["owner_signature_hex"] = sign_digest(owner.private_key, special_node_transaction_signature_digest(unsigned)).hex()
    return Transaction(version=1, inputs=(), outputs=(), metadata=metadata)


def _renew_reward_node_transaction(*, node_id: str, owner_index: int = 0, renewal_epoch: int = 0, fee_chipbits: int | None = None) -> Transaction:
    owner = wallet_key(owner_index)
    metadata = {
        "kind": "renew_reward_node",
        "node_id": node_id,
        "renewal_epoch": str(renewal_epoch),
        "owner_pubkey_hex": owner.public_key.hex(),
        "declared_host": f"{node_id}.example",
        "declared_port": "18444",
        "renewal_fee_chipbits": str(
            renew_reward_node_fee_chipbits(registered_reward_node_count=0, params=MAINNET_PARAMS)
            if fee_chipbits is None
            else fee_chipbits
        ),
        "owner_signature_hex": "",
    }
    unsigned = Transaction(version=1, inputs=(), outputs=(), metadata=metadata)
    from chipcoin.consensus.nodes import special_node_transaction_signature_digest
    from chipcoin.crypto.signatures import sign_digest

    metadata["owner_signature_hex"] = sign_digest(owner.private_key, special_node_transaction_signature_digest(unsigned)).hex()
    return Transaction(version=1, inputs=(), outputs=(), metadata=metadata)


def _reward_attestation_bundle_transaction(
    *,
    attestations: list[dict[str, object]],
    bundle_window_index: int = 0,
    epoch_index: int = 1,
    bundle_submitter_node_id: str = "submitter-1",
) -> Transaction:
    return Transaction(
        version=1,
        inputs=(),
        outputs=(),
        metadata={
            "kind": REWARD_ATTESTATION_BUNDLE_KIND,
            "epoch_index": str(epoch_index),
            "bundle_window_index": str(bundle_window_index),
            "bundle_submitter_node_id": bundle_submitter_node_id,
            "attestation_count": str(len(attestations)),
            "attestations_json": json.dumps(attestations, sort_keys=True),
        },
    )


def _reward_settle_epoch_transaction(
    *,
    reward_entries: list[dict[str, object]],
    epoch_index: int = 1,
    epoch_start_height: int = 100,
    epoch_end_height: int = 199,
    epoch_seed_hex: str = "11" * 32,
    distributed_node_reward_chipbits: int | None = None,
    undistributed_node_reward_chipbits: int = 0,
) -> Transaction:
    return Transaction(
        version=1,
        inputs=(),
        outputs=(),
        metadata={
            "kind": REWARD_SETTLE_EPOCH_KIND,
            "epoch_index": str(epoch_index),
            "epoch_start_height": str(epoch_start_height),
            "epoch_end_height": str(epoch_end_height),
            "epoch_seed": epoch_seed_hex,
            "policy_version": "v1",
            "candidate_summary_root": "22" * 32,
            "verified_nodes_root": "33" * 32,
            "rewarded_nodes_root": "44" * 32,
            "rewarded_node_count": str(len(reward_entries)),
            "distributed_node_reward_chipbits": str(
                sum(int(item["reward_chipbits"]) for item in reward_entries)
                if distributed_node_reward_chipbits is None
                else distributed_node_reward_chipbits
            ),
            "undistributed_node_reward_chipbits": str(undistributed_node_reward_chipbits),
            "reward_entries_json": json.dumps(reward_entries, sort_keys=True),
        },
    )


def _native_reward_test_params():
    return replace(
        MAINNET_PARAMS,
        node_reward_activation_height=0,
        epoch_length_blocks=10,
        reward_node_warmup_epochs=0,
        reward_check_windows_per_epoch=4,
        reward_target_checks_per_epoch=1,
        reward_min_passed_checks_per_epoch=1,
        reward_verifier_committee_size=1,
        reward_verifier_quorum=1,
        reward_final_confirmation_window_blocks=1,
        reward_sync_lag_tolerance_blocks=5,
        max_rewarded_nodes_per_epoch=4,
    )


def _native_reward_registry_records() -> list[NodeRecord]:
    return [
        NodeRecord(
            node_id=f"reward-node-{label}",
            payout_address=wallet_key(index).address,
            owner_pubkey=wallet_key(index).public_key,
            registered_height=10,
            last_renewed_height=10,
            node_pubkey=wallet_key(index).public_key,
            declared_host=f"reward-node-{label}.example",
            declared_port=18_440 + index,
            reward_registration=True,
        )
        for index, label in enumerate(("a", "b", "c"))
    ]


def _valid_native_attestation_bundle_transaction(*, params=None) -> tuple[Transaction, RewardAttestation, list[NodeRecord], bytes]:
    resolved_params = _native_reward_test_params() if params is None else params
    records = _native_reward_registry_records()
    seed = bytes.fromhex("11" * 32)
    candidate = records[0]
    verifier_records = sorted(records, key=lambda item: item.node_id)
    window_index = candidate_check_windows(node_id=candidate.node_id, seed=seed, params=resolved_params)[0]
    verifier_node_id = verifier_committee(
        candidate_node_id=candidate.node_id,
        active_verifier_node_ids=[record.node_id for record in verifier_records],
        check_window_index=window_index,
        seed=seed,
        params=resolved_params,
    )[0]
    verifier_index = next(index for index, record in enumerate(records) if record.node_id == verifier_node_id)
    signer = TransactionSigner(wallet_key(verifier_index))
    attestation = signer.sign_reward_attestation(
        RewardAttestation(
            epoch_index=1,
            check_window_index=window_index,
            candidate_node_id=candidate.node_id,
            verifier_node_id=verifier_node_id,
            result_code="pass",
            observed_sync_gap=0,
            endpoint_commitment=f"{candidate.declared_host}:{candidate.declared_port}",
            concentration_key="ip:127.0.0.1",
            signature_hex="",
        )
    )
    transaction = _reward_attestation_bundle_transaction(
        attestations=[
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
        epoch_index=attestation.epoch_index,
        bundle_window_index=window_index,
        bundle_submitter_node_id=verifier_node_id,
    )
    return transaction, attestation, records, seed


def test_validate_transaction_accepts_balanced_spend_and_returns_fee() -> None:
    previous_outpoint = OutPoint(txid="11" * 32, index=0)
    sender = wallet_key(0)
    utxo_view = InMemoryUtxoView.from_entries(
        [
            (
                previous_outpoint,
                UtxoEntry(
                    output=TxOutput(value=100, recipient=sender.address),
                    height=1,
                    is_coinbase=False,
                ),
            )
        ]
    )
    transaction = _spend_transaction(previous_outpoint, fee=10, sender=sender)
    context = ValidationContext(
        height=5,
        median_time_past=0,
        params=MAINNET_PARAMS,
        utxo_view=utxo_view,
    )

    fee = validate_transaction(transaction, context)

    assert fee == 10


def test_validate_transaction_rejects_overspend() -> None:
    previous_outpoint = OutPoint(txid="22" * 32, index=0)
    sender = wallet_key(0)
    utxo_view = InMemoryUtxoView.from_entries(
        [
            (
                previous_outpoint,
                UtxoEntry(
                    output=TxOutput(value=50, recipient=sender.address),
                    height=1,
                    is_coinbase=False,
                ),
            )
        ]
    )
    signer = TransactionSigner(sender)
    unsigned = Transaction(
        version=1,
        inputs=(TxInput(previous_output=previous_outpoint),),
        outputs=(TxOutput(value=51, recipient=wallet_key(1).address),),
        metadata={"kind": "payment"},
    )
    digest = transaction_signature_digest(
        unsigned,
        0,
        previous_output=TxOutput(value=50, recipient=sender.address),
    )
    transaction = Transaction(
        version=unsigned.version,
        inputs=(
            TxInput(
                previous_output=previous_outpoint,
                signature=signer.sign(digest),
                public_key=sender.public_key,
            ),
        ),
        outputs=unsigned.outputs,
        locktime=unsigned.locktime,
        metadata=unsigned.metadata,
    )
    context = ValidationContext(
        height=2,
        median_time_past=0,
        params=MAINNET_PARAMS,
        utxo_view=utxo_view,
    )

    _expect_raises(ContextualValidationError, lambda: validate_transaction(transaction, context))


def test_validate_transaction_rejects_duplicate_inputs_statelessly() -> None:
    sender = wallet_key(0)
    previous_outpoint = OutPoint(txid="33" * 32, index=0)
    transaction = Transaction(
        version=1,
        inputs=(
            TxInput(previous_output=previous_outpoint, signature=b"\x01", public_key=sender.public_key),
            TxInput(previous_output=previous_outpoint, signature=b"\x01", public_key=sender.public_key),
        ),
        outputs=(TxOutput(value=1, recipient=wallet_key(1).address),),
    )
    context = ValidationContext(
        height=1,
        median_time_past=0,
        params=MAINNET_PARAMS,
        utxo_view=InMemoryUtxoView(),
    )

    _expect_raises(StatelessValidationError, lambda: validate_transaction(transaction, context))


def test_coinbase_maturity_rule_is_enforced_separately() -> None:
    entry = UtxoEntry(
        output=TxOutput(value=50, recipient="CHCminer"),
        height=100,
        is_coinbase=True,
    )

    assert is_coinbase_mature(entry, 200, MAINNET_PARAMS) is True
    assert is_coinbase_mature(entry, 199, MAINNET_PARAMS) is False


def test_validate_block_accepts_valid_coinbase_and_fee_accounting() -> None:
    previous_outpoint = OutPoint(txid="44" * 32, index=0)
    sender = wallet_key(0)
    spend_entry = UtxoEntry(
        output=TxOutput(value=100, recipient=sender.address),
        height=1,
        is_coinbase=False,
    )
    spend_transaction = _spend_transaction(previous_outpoint, fee=10, sender=sender)
    fees = 10
    coinbase = _coinbase_transaction(block_subsidy(5, MAINNET_PARAMS) + fees)
    transactions = (coinbase, spend_transaction)
    header = _mine_easy_header("55" * 32, merkle_root([tx.txid() for tx in transactions]))
    block = Block(header=header, transactions=transactions)
    context = ValidationContext(
        height=5,
        median_time_past=1_699_999_000,
        params=MAINNET_PARAMS,
        utxo_view=InMemoryUtxoView.from_entries([(previous_outpoint, spend_entry)]),
        expected_previous_block_hash="55" * 32,
        expected_bits=MAINNET_PARAMS.genesis_bits,
    )

    total_fees = validate_block(block, context)

    assert total_fees == fees


def test_validate_block_rejects_coinbase_overclaim() -> None:
    coinbase = _coinbase_transaction(block_subsidy(3, MAINNET_PARAMS) + 1)
    transactions = (coinbase,)
    header = _mine_easy_header("66" * 32, merkle_root([tx.txid() for tx in transactions]))
    block = Block(header=header, transactions=transactions)
    context = ValidationContext(
        height=3,
        median_time_past=1_699_999_000,
        params=MAINNET_PARAMS,
        utxo_view=InMemoryUtxoView(),
        expected_previous_block_hash="66" * 32,
        expected_bits=MAINNET_PARAMS.genesis_bits,
    )

    _expect_raises(ContextualValidationError, lambda: validate_block(block, context))


def test_validate_block_accepts_cap_clamped_coinbase() -> None:
    height = 643_297
    miner_subsidy_chipbits, node_reward_chipbits = subsidy_split_chipbits(height, MAINNET_PARAMS)
    node_record = NodeRecord(
        node_id="node-cap",
        payout_address=wallet_key(2).address,
        owner_pubkey=wallet_key(2).public_key,
        registered_height=height - 1,
        last_renewed_height=height - 1,
    )
    registry = InMemoryNodeRegistryView.from_records([node_record])
    coinbase = Transaction(
        version=1,
        inputs=(),
        outputs=(
            (TxOutput(value=miner_subsidy_chipbits, recipient="CHCminer"),)
            if node_reward_chipbits == 0
            else (
                TxOutput(value=miner_subsidy_chipbits, recipient="CHCminer"),
                TxOutput(value=node_reward_chipbits, recipient=wallet_key(2).address),
            )
        ),
        metadata={"coinbase": "true"},
    )
    transactions = (coinbase,)
    header = _mine_easy_header("67" * 32, merkle_root([tx.txid() for tx in transactions]))
    block = Block(header=header, transactions=transactions)
    context = ValidationContext(
        height=height,
        median_time_past=1_699_999_000,
        params=MAINNET_PARAMS,
        utxo_view=InMemoryUtxoView(),
        node_registry_view=registry,
        expected_previous_block_hash="67" * 32,
        expected_bits=MAINNET_PARAMS.genesis_bits,
    )

    assert validate_block(block, context) == 0


def test_validate_block_accepts_epoch_closing_coinbase_with_unminted_node_reward_when_no_nodes_are_eligible() -> None:
    height = 99
    miner_subsidy_chipbits, node_reward_chipbits = subsidy_split_chipbits(height, MAINNET_PARAMS)
    assert node_reward_chipbits > 0
    coinbase = Transaction(
        version=1,
        inputs=(),
        outputs=(TxOutput(value=miner_subsidy_chipbits, recipient="CHCminer"),),
        metadata={"coinbase": "true"},
    )
    transactions = (coinbase,)
    header = _mine_easy_header("68" * 32, merkle_root([tx.txid() for tx in transactions]))
    block = Block(header=header, transactions=transactions)
    context = ValidationContext(
        height=height,
        median_time_past=1_699_999_000,
        params=MAINNET_PARAMS,
        utxo_view=InMemoryUtxoView(),
        expected_previous_block_hash="68" * 32,
        expected_bits=MAINNET_PARAMS.genesis_bits,
    )

    assert validate_block(block, context) == 0


def test_validate_block_rejects_double_spend_within_block() -> None:
    previous_outpoint = OutPoint(txid="77" * 32, index=0)
    sender = wallet_key(0)
    utxo_entry = UtxoEntry(
        output=TxOutput(value=100, recipient=sender.address),
        height=1,
        is_coinbase=False,
    )
    first_spend = _spend_transaction(previous_outpoint, fee=10, sender=sender)
    second_spend = _spend_transaction(previous_outpoint, fee=20, sender=sender)
    coinbase = _coinbase_transaction(block_subsidy(6, MAINNET_PARAMS) + 30)
    transactions = (coinbase, first_spend, second_spend)
    header = _mine_easy_header("88" * 32, merkle_root([tx.txid() for tx in transactions]))
    block = Block(header=header, transactions=transactions)
    context = ValidationContext(
        height=6,
        median_time_past=1_699_999_000,
        params=MAINNET_PARAMS,
        utxo_view=InMemoryUtxoView.from_entries([(previous_outpoint, utxo_entry)]),
        expected_previous_block_hash="88" * 32,
        expected_bits=MAINNET_PARAMS.genesis_bits,
    )

    _expect_raises(ContextualValidationError, lambda: validate_block(block, context))


def test_validate_transaction_accepts_register_reward_node_with_matching_fee_param() -> None:
    transaction = _register_reward_node_transaction(node_id="reward-node-1")
    context = ValidationContext(
        height=301,
        median_time_past=0,
        params=MAINNET_PARAMS,
        utxo_view=InMemoryUtxoView(),
        node_registry_view=InMemoryNodeRegistryView(),
    )

    assert validate_transaction(transaction, context) == 0


def test_validate_transaction_rejects_register_reward_node_with_wrong_fee_param() -> None:
    transaction = _register_reward_node_transaction(node_id="reward-node-2", fee_chipbits=123)
    context = ValidationContext(
        height=301,
        median_time_past=0,
        params=MAINNET_PARAMS,
        utxo_view=InMemoryUtxoView(),
        node_registry_view=InMemoryNodeRegistryView(),
    )

    _expect_raises(ContextualValidationError, lambda: validate_transaction(transaction, context))


def test_validate_transaction_accepts_renew_reward_node_with_matching_fee_param() -> None:
    existing = NodeRecord(
        node_id="reward-node-3",
        payout_address=wallet_key(0).address,
        owner_pubkey=wallet_key(0).public_key,
        registered_height=1,
        last_renewed_height=1,
        node_pubkey=wallet_key(1).public_key,
        declared_host="reward-node-3.example",
        declared_port=18444,
        reward_registration=True,
    )
    transaction = _renew_reward_node_transaction(node_id="reward-node-3", renewal_epoch=3)
    context = ValidationContext(
        height=300,
        median_time_past=0,
        params=MAINNET_PARAMS,
        utxo_view=InMemoryUtxoView(),
        node_registry_view=InMemoryNodeRegistryView.from_records([existing]),
    )

    assert validate_transaction(transaction, context) == 0


def test_validate_transaction_rejects_duplicate_attestation_in_bundle() -> None:
    attestation = {
        "epoch_index": 1,
        "check_window_index": 0,
        "candidate_node_id": "candidate-1",
        "verifier_node_id": "verifier-1",
        "result_code": "pass",
        "observed_sync_gap": 1,
        "endpoint_commitment": "endpoint-1",
        "concentration_key": "key-1",
        "signature_hex": "aa",
    }
    transaction = _reward_attestation_bundle_transaction(attestations=[attestation, attestation])
    context = ValidationContext(height=150, median_time_past=0, params=MAINNET_PARAMS, utxo_view=InMemoryUtxoView())

    _expect_raises(ContextualValidationError, lambda: validate_transaction(transaction, context))


def test_validate_block_rejects_too_many_attestation_bundles() -> None:
    bundle_transactions = [
        _reward_attestation_bundle_transaction(
            attestations=[
                {
                    "epoch_index": 1,
                    "check_window_index": index,
                    "candidate_node_id": f"candidate-{index}",
                    "verifier_node_id": f"verifier-{index}",
                    "result_code": "pass",
                    "observed_sync_gap": 0,
                    "endpoint_commitment": f"endpoint-{index}",
                    "concentration_key": f"key-{index}",
                    "signature_hex": "aa",
                }
            ],
            bundle_window_index=index,
        )
        for index in range(MAINNET_PARAMS.max_attestation_bundles_per_block + 1)
    ]
    coinbase = _coinbase_transaction(block_subsidy(5, MAINNET_PARAMS))
    transactions = (coinbase, *bundle_transactions)
    header = _mine_easy_header("99" * 32, merkle_root([tx.txid() for tx in transactions]))
    block = Block(header=header, transactions=transactions)
    context = ValidationContext(
        height=5,
        median_time_past=1_699_999_000,
        params=MAINNET_PARAMS,
        utxo_view=InMemoryUtxoView(),
        expected_previous_block_hash="99" * 32,
        expected_bits=MAINNET_PARAMS.genesis_bits,
    )

    _expect_raises(StatelessValidationError, lambda: validate_block(block, context))


def test_validate_transaction_accepts_reward_settle_epoch_payload_shape() -> None:
    transaction = _reward_settle_epoch_transaction(
        reward_entries=[],
        epoch_index=10,
        epoch_start_height=1000,
        epoch_end_height=1099,
        epoch_seed_hex="11" * 32,
        distributed_node_reward_chipbits=0,
        undistributed_node_reward_chipbits=MAINNET_PARAMS.initial_node_epoch_reward_chipbits,
    )
    context = ValidationContext(
        height=1099,
        median_time_past=0,
        params=MAINNET_PARAMS,
        utxo_view=InMemoryUtxoView(),
        epoch_seed_by_index={10: bytes.fromhex("11" * 32)},
    )

    assert validate_transaction(transaction, context) == 0


def test_validate_transaction_accepts_reward_attestation_bundle_with_valid_assignment_and_signature() -> None:
    params = _native_reward_test_params()
    transaction, _attestation, records, seed = _valid_native_attestation_bundle_transaction(params=params)
    context = ValidationContext(
        height=11,
        median_time_past=0,
        params=params,
        utxo_view=InMemoryUtxoView(),
        node_registry_view=InMemoryNodeRegistryView.from_records(records),
        epoch_seed_by_index={1: seed},
    )

    assert validate_transaction(transaction, context) == 0


def test_validate_transaction_rejects_reward_attestation_bundle_replay_identity() -> None:
    params = _native_reward_test_params()
    transaction, attestation, records, seed = _valid_native_attestation_bundle_transaction(params=params)
    context = ValidationContext(
        height=11,
        median_time_past=0,
        params=params,
        utxo_view=InMemoryUtxoView(),
        node_registry_view=InMemoryNodeRegistryView.from_records(records),
        reward_attestation_identities=frozenset({attestation_identity(attestation)}),
        epoch_seed_by_index={1: seed},
    )

    _expect_raises(ContextualValidationError, lambda: validate_transaction(transaction, context))


def test_validate_transaction_rejects_reward_attestation_bundle_with_wrong_epoch_timing() -> None:
    params = _native_reward_test_params()
    transaction, _attestation, records, seed = _valid_native_attestation_bundle_transaction(params=params)
    metadata = dict(transaction.metadata)
    metadata["epoch_index"] = "2"
    attestations = json.loads(metadata["attestations_json"])
    attestations[0]["epoch_index"] = 2
    metadata["attestations_json"] = json.dumps(attestations, sort_keys=True)
    tampered = Transaction(version=transaction.version, inputs=transaction.inputs, outputs=transaction.outputs, metadata=metadata)
    context = ValidationContext(
        height=11,
        median_time_past=0,
        params=params,
        utxo_view=InMemoryUtxoView(),
        node_registry_view=InMemoryNodeRegistryView.from_records(records),
        epoch_seed_by_index={1: seed, 2: bytes.fromhex("22" * 32)},
    )

    _expect_raises(ContextualValidationError, lambda: validate_transaction(tampered, context))


def test_validate_transaction_rejects_reward_attestation_bundle_with_wrong_candidate_window_assignment() -> None:
    params = _native_reward_test_params()
    transaction, attestation, records, seed = _valid_native_attestation_bundle_transaction(params=params)
    bad_window = attestation.check_window_index + 1
    metadata = dict(transaction.metadata)
    metadata["bundle_window_index"] = str(bad_window)
    metadata["attestations_json"] = json.dumps(
        [
            {
                "epoch_index": attestation.epoch_index,
                "check_window_index": bad_window,
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
    )
    tampered = Transaction(version=transaction.version, inputs=transaction.inputs, outputs=transaction.outputs, metadata=metadata)
    context = ValidationContext(
        height=11,
        median_time_past=0,
        params=params,
        utxo_view=InMemoryUtxoView(),
        node_registry_view=InMemoryNodeRegistryView.from_records(records),
        epoch_seed_by_index={1: seed},
    )

    _expect_raises(ContextualValidationError, lambda: validate_transaction(tampered, context))


def test_validate_transaction_rejects_reward_attestation_bundle_with_wrong_verifier_assignment() -> None:
    params = _native_reward_test_params()
    transaction, attestation, records, seed = _valid_native_attestation_bundle_transaction(params=params)
    wrong_verifier = "reward-node-c" if attestation.verifier_node_id != "reward-node-c" else "reward-node-b"
    metadata = dict(transaction.metadata)
    metadata["attestations_json"] = json.dumps(
        [
            {
                "epoch_index": attestation.epoch_index,
                "check_window_index": attestation.check_window_index,
                "candidate_node_id": attestation.candidate_node_id,
                "verifier_node_id": wrong_verifier,
                "result_code": attestation.result_code,
                "observed_sync_gap": attestation.observed_sync_gap,
                "endpoint_commitment": attestation.endpoint_commitment,
                "concentration_key": attestation.concentration_key,
                "signature_hex": attestation.signature_hex,
            }
        ],
        sort_keys=True,
    )
    tampered = Transaction(version=transaction.version, inputs=transaction.inputs, outputs=transaction.outputs, metadata=metadata)
    context = ValidationContext(
        height=11,
        median_time_past=0,
        params=params,
        utxo_view=InMemoryUtxoView(),
        node_registry_view=InMemoryNodeRegistryView.from_records(records),
        epoch_seed_by_index={1: seed},
    )

    _expect_raises(ContextualValidationError, lambda: validate_transaction(tampered, context))


def test_validate_transaction_rejects_reward_attestation_bundle_with_invalid_verifier_signature() -> None:
    params = _native_reward_test_params()
    transaction, attestation, records, seed = _valid_native_attestation_bundle_transaction(params=params)
    metadata = dict(transaction.metadata)
    metadata["attestations_json"] = json.dumps(
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
                "signature_hex": "aa",
            }
        ],
        sort_keys=True,
    )
    tampered = Transaction(version=transaction.version, inputs=transaction.inputs, outputs=transaction.outputs, metadata=metadata)
    context = ValidationContext(
        height=11,
        median_time_past=0,
        params=params,
        utxo_view=InMemoryUtxoView(),
        node_registry_view=InMemoryNodeRegistryView.from_records(records),
        epoch_seed_by_index={1: seed},
    )

    _expect_raises(ContextualValidationError, lambda: validate_transaction(tampered, context))


def test_validate_transaction_accepts_reward_settle_epoch_with_valid_bundle_quorum_at_epoch_boundary() -> None:
    params = _native_reward_test_params()
    _bundle_transaction, attestation, records, seed = _valid_native_attestation_bundle_transaction(params=params)
    distributed_reward = subsidy_split_chipbits(19, params)[1]
    bundle = RewardAttestationBundle(
        epoch_index=1,
        bundle_window_index=attestation.check_window_index,
        bundle_submitter_node_id=attestation.verifier_node_id,
        attestations=(attestation,),
    )
    transaction = _reward_settle_epoch_transaction(
        reward_entries=[
            {
                "node_id": "reward-node-a",
                "payout_address": wallet_key(0).address,
                "reward_chipbits": distributed_reward,
                "selection_rank": 0,
                "concentration_key": attestation.concentration_key,
                "final_confirmation_passed": True,
            }
        ],
        epoch_index=1,
        epoch_start_height=10,
        epoch_end_height=19,
        epoch_seed_hex=seed.hex(),
        distributed_node_reward_chipbits=distributed_reward,
        undistributed_node_reward_chipbits=0,
    )
    context = ValidationContext(
        height=19,
        median_time_past=0,
        params=params,
        utxo_view=InMemoryUtxoView(),
        node_registry_view=InMemoryNodeRegistryView.from_records(records),
        reward_attestation_bundles=(bundle,),
        epoch_seed_by_index={1: seed},
    )

    assert validate_transaction(transaction, context) == 0


def test_validate_transaction_rejects_reward_settle_epoch_with_wrong_epoch_timing() -> None:
    params = _native_reward_test_params()
    transaction = _reward_settle_epoch_transaction(
        reward_entries=[],
        epoch_index=1,
        epoch_start_height=10,
        epoch_end_height=19,
        epoch_seed_hex="11" * 32,
        distributed_node_reward_chipbits=0,
        undistributed_node_reward_chipbits=subsidy_split_chipbits(19, params)[1],
    )
    context = ValidationContext(
        height=18,
        median_time_past=0,
        params=params,
        utxo_view=InMemoryUtxoView(),
        epoch_seed_by_index={1: bytes.fromhex("11" * 32)},
    )

    _expect_raises(ContextualValidationError, lambda: validate_transaction(transaction, context))


def test_validate_transaction_rejects_reward_settle_epoch_with_wrong_epoch_seed() -> None:
    params = _native_reward_test_params()
    transaction = _reward_settle_epoch_transaction(
        reward_entries=[],
        epoch_index=1,
        epoch_start_height=10,
        epoch_end_height=19,
        epoch_seed_hex="22" * 32,
        distributed_node_reward_chipbits=0,
        undistributed_node_reward_chipbits=subsidy_split_chipbits(19, params)[1],
    )
    context = ValidationContext(
        height=19,
        median_time_past=0,
        params=params,
        utxo_view=InMemoryUtxoView(),
        epoch_seed_by_index={1: bytes.fromhex("11" * 32)},
    )

    _expect_raises(ContextualValidationError, lambda: validate_transaction(transaction, context))


def test_validate_transaction_rejects_reward_settle_epoch_when_epoch_is_already_settled() -> None:
    params = _native_reward_test_params()
    transaction = _reward_settle_epoch_transaction(
        reward_entries=[],
        epoch_index=1,
        epoch_start_height=10,
        epoch_end_height=19,
        epoch_seed_hex="11" * 32,
        distributed_node_reward_chipbits=0,
        undistributed_node_reward_chipbits=subsidy_split_chipbits(19, params)[1],
    )
    context = ValidationContext(
        height=19,
        median_time_past=0,
        params=params,
        utxo_view=InMemoryUtxoView(),
        settled_epoch_indexes=frozenset({1}),
        epoch_seed_by_index={1: bytes.fromhex("11" * 32)},
    )

    _expect_raises(ContextualValidationError, lambda: validate_transaction(transaction, context))


def test_validate_transaction_rejects_reward_settle_epoch_with_duplicate_rewarded_recipient() -> None:
    params = _native_reward_test_params()
    transaction = _reward_settle_epoch_transaction(
        reward_entries=[
            {
                "node_id": "reward-node-a",
                "payout_address": wallet_key(0).address,
                "reward_chipbits": 10,
                "selection_rank": 0,
                "concentration_key": "demo:a",
                "final_confirmation_passed": True,
            },
            {
                "node_id": "reward-node-a",
                "payout_address": wallet_key(0).address,
                "reward_chipbits": 20,
                "selection_rank": 1,
                "concentration_key": "demo:a",
                "final_confirmation_passed": True,
            },
        ],
        epoch_index=1,
        epoch_start_height=10,
        epoch_end_height=19,
        epoch_seed_hex="11" * 32,
        distributed_node_reward_chipbits=30,
        undistributed_node_reward_chipbits=subsidy_split_chipbits(19, params)[1] - 30,
    )
    context = ValidationContext(
        height=19,
        median_time_past=0,
        params=params,
        utxo_view=InMemoryUtxoView(),
        epoch_seed_by_index={1: bytes.fromhex("11" * 32)},
    )

    _expect_raises(ContextualValidationError, lambda: validate_transaction(transaction, context))


def test_validate_transaction_rejects_reward_settle_epoch_when_distributed_reward_exceeds_budget() -> None:
    params = _native_reward_test_params()
    scheduled_pool = subsidy_split_chipbits(19, params)[1]
    transaction = _reward_settle_epoch_transaction(
        reward_entries=[
            {
                "node_id": "reward-node-a",
                "payout_address": wallet_key(0).address,
                "reward_chipbits": scheduled_pool + 1,
                "selection_rank": 0,
                "concentration_key": "demo:a",
                "final_confirmation_passed": True,
            }
        ],
        epoch_index=1,
        epoch_start_height=10,
        epoch_end_height=19,
        epoch_seed_hex="11" * 32,
        distributed_node_reward_chipbits=scheduled_pool + 1,
        undistributed_node_reward_chipbits=0,
    )
    context = ValidationContext(
        height=19,
        median_time_past=0,
        params=params,
        utxo_view=InMemoryUtxoView(),
        epoch_seed_by_index={1: bytes.fromhex("11" * 32)},
    )

    _expect_raises(ContextualValidationError, lambda: validate_transaction(transaction, context))


def test_validate_block_accepts_coinbase_outputs_that_match_included_reward_settlement() -> None:
    params = _native_reward_test_params()
    _bundle_transaction, attestation, records, seed = _valid_native_attestation_bundle_transaction(params=params)
    distributed_reward = subsidy_split_chipbits(19, params)[1]
    settlement_tx = _reward_settle_epoch_transaction(
        reward_entries=[
            {
                "node_id": "reward-node-a",
                "payout_address": wallet_key(0).address,
                "reward_chipbits": distributed_reward,
                "selection_rank": 0,
                "concentration_key": attestation.concentration_key,
                "final_confirmation_passed": True,
            }
        ],
        epoch_index=1,
        epoch_start_height=10,
        epoch_end_height=19,
        epoch_seed_hex=seed.hex(),
        distributed_node_reward_chipbits=distributed_reward,
        undistributed_node_reward_chipbits=0,
    )
    bundle = RewardAttestationBundle(
        epoch_index=1,
        bundle_window_index=attestation.check_window_index,
        bundle_submitter_node_id=attestation.verifier_node_id,
        attestations=(attestation,),
    )
    miner_subsidy = subsidy_split_chipbits(19, params)[0]
    coinbase = Transaction(
        version=1,
        inputs=(),
        outputs=(
            TxOutput(value=miner_subsidy, recipient="CHCminer"),
            TxOutput(value=distributed_reward, recipient=wallet_key(0).address),
        ),
        metadata={"coinbase": "true"},
    )
    transactions = (coinbase, settlement_tx)
    header = _mine_easy_header("11" * 32, merkle_root([tx.txid() for tx in transactions]))
    block = Block(header=header, transactions=transactions)
    context = ValidationContext(
        height=19,
        median_time_past=0,
        params=params,
        utxo_view=InMemoryUtxoView(),
        node_registry_view=InMemoryNodeRegistryView.from_records(records),
        reward_attestation_bundles=(bundle,),
        epoch_seed_by_index={1: seed},
        expected_previous_block_hash="11" * 32,
        expected_bits=params.genesis_bits,
    )

    assert validate_block(block, context) == 0


def test_validate_block_rejects_coinbase_outputs_that_do_not_match_included_reward_settlement() -> None:
    params = _native_reward_test_params()
    _bundle_transaction, attestation, records, seed = _valid_native_attestation_bundle_transaction(params=params)
    distributed_reward = subsidy_split_chipbits(19, params)[1]
    settlement_tx = _reward_settle_epoch_transaction(
        reward_entries=[
            {
                "node_id": "reward-node-a",
                "payout_address": wallet_key(0).address,
                "reward_chipbits": distributed_reward,
                "selection_rank": 0,
                "concentration_key": attestation.concentration_key,
                "final_confirmation_passed": True,
            }
        ],
        epoch_index=1,
        epoch_start_height=10,
        epoch_end_height=19,
        epoch_seed_hex=seed.hex(),
        distributed_node_reward_chipbits=distributed_reward,
        undistributed_node_reward_chipbits=0,
    )
    bundle = RewardAttestationBundle(
        epoch_index=1,
        bundle_window_index=attestation.check_window_index,
        bundle_submitter_node_id=attestation.verifier_node_id,
        attestations=(attestation,),
    )
    miner_subsidy = subsidy_split_chipbits(19, params)[0]
    coinbase = Transaction(
        version=1,
        inputs=(),
        outputs=(
            TxOutput(value=miner_subsidy, recipient="CHCminer"),
            TxOutput(value=distributed_reward, recipient=wallet_key(1).address),
        ),
        metadata={"coinbase": "true"},
    )
    transactions = (coinbase, settlement_tx)
    header = _mine_easy_header("11" * 32, merkle_root([tx.txid() for tx in transactions]))
    block = Block(header=header, transactions=transactions)
    context = ValidationContext(
        height=19,
        median_time_past=0,
        params=params,
        utxo_view=InMemoryUtxoView(),
        node_registry_view=InMemoryNodeRegistryView.from_records(records),
        reward_attestation_bundles=(bundle,),
        epoch_seed_by_index={1: seed},
        expected_previous_block_hash="11" * 32,
        expected_bits=params.genesis_bits,
    )

    _expect_raises(ContextualValidationError, lambda: validate_block(block, context))


def test_validate_block_rejects_immature_coinbase_spend() -> None:
    matured_height = 50
    previous_outpoint = OutPoint(txid="99" * 32, index=0)
    sender = wallet_key(0)
    utxo_entry = UtxoEntry(
        output=TxOutput(value=50, recipient=sender.address),
        height=matured_height,
        is_coinbase=True,
    )
    spend = signed_payment(previous_outpoint, value=50, sender=sender, amount=40, fee=10)
    coinbase = _coinbase_transaction(block_subsidy(120, MAINNET_PARAMS) + 10)
    transactions = (coinbase, spend)
    header = _mine_easy_header("AA" * 32, merkle_root([tx.txid() for tx in transactions]))
    block = Block(header=header, transactions=transactions)
    context = ValidationContext(
        height=120,
        median_time_past=1_699_999_000,
        params=MAINNET_PARAMS,
        utxo_view=InMemoryUtxoView.from_entries([(previous_outpoint, utxo_entry)]),
        expected_previous_block_hash="AA" * 32,
        expected_bits=MAINNET_PARAMS.genesis_bits,
    )

    _expect_raises(ContextualValidationError, lambda: validate_block(block, context))


def test_validate_transaction_rejects_invalid_signature() -> None:
    previous_outpoint = OutPoint(txid="AB" * 32, index=0)
    sender = wallet_key(0)
    utxo_view = InMemoryUtxoView.from_entries(
        [
            (
                previous_outpoint,
                UtxoEntry(
                    output=TxOutput(value=100, recipient=sender.address),
                    height=1,
                    is_coinbase=False,
                ),
            )
        ]
    )
    valid_transaction = signed_payment(previous_outpoint, value=100, sender=sender, fee=10)
    invalid_input = TxInput(
        previous_output=valid_transaction.inputs[0].previous_output,
        signature=valid_transaction.inputs[0].signature[:-1] + bytes((valid_transaction.inputs[0].signature[-1] ^ 0x01,)),
        public_key=valid_transaction.inputs[0].public_key,
        sequence=valid_transaction.inputs[0].sequence,
    )
    invalid_transaction = Transaction(
        version=valid_transaction.version,
        inputs=(invalid_input,),
        outputs=valid_transaction.outputs,
        locktime=valid_transaction.locktime,
        metadata=valid_transaction.metadata,
    )
    context = ValidationContext(
        height=5,
        median_time_past=0,
        params=MAINNET_PARAMS,
        utxo_view=utxo_view,
    )

    _expect_raises(ContextualValidationError, lambda: validate_transaction(invalid_transaction, context))
