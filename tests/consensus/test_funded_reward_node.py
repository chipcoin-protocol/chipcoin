"""Consensus checks for funded reward-node control transactions."""

from dataclasses import replace

import pytest

from chipcoin.consensus.economics import register_reward_node_fee_chipbits, renew_reward_node_fee_chipbits, subsidy_split_chipbits
from chipcoin.consensus.merkle import merkle_root
from chipcoin.consensus.models import Block, BlockHeader, OutPoint, TxOutput
from chipcoin.consensus.nodes import InMemoryNodeRegistryView, NodeRecord
from chipcoin.consensus.params import MAINNET_PARAMS, MAINNET_TEST_ONLY_PARAMS, TESTNET_PARAMS
from chipcoin.consensus.pow import verify_proof_of_work
from chipcoin.consensus.utxo import InMemoryUtxoView, UtxoEntry
from chipcoin.consensus.validation import (
    ContextualValidationError,
    ValidationContext,
    ValidationError,
    validate_block,
    validate_transaction,
)
from chipcoin.node.mining import MiningCoordinator, build_coinbase_transaction
from chipcoin.storage.mempool import MempoolEntry
from chipcoin.wallet.models import SpendCandidate
from chipcoin.wallet.signer import TransactionSigner, wallet_key_from_mldsa44_seed


OWNER = wallet_key_from_mldsa44_seed(bytes([41]) * 32)
ATTEST = wallet_key_from_mldsa44_seed(bytes([42]) * 32)
OTHER = wallet_key_from_mldsa44_seed(bytes([43]) * 32)
OUTPOINT = OutPoint("ab" * 32, 0)
VALUE = 150_000_000


def _context(height=300, *, owner=OWNER, registry=None, origin=100, coinbase=True):
    return ValidationContext(
        height=height,
        median_time_past=0,
        params=MAINNET_TEST_ONLY_PARAMS,
        network="mainnet-test-only",
        utxo_view=InMemoryUtxoView.from_entries([
            (OUTPOINT, UtxoEntry(TxOutput(VALUE, owner.address), origin, coinbase))
        ]),
        node_registry_view=registry or InMemoryNodeRegistryView(),
    )


def _candidates(owner=OWNER):
    return [SpendCandidate(OUTPOINT.txid, OUTPOINT.index, VALUE, owner.address)]


def _register(*, funded=True, fee=100_000_000, owner=OWNER):
    return TransactionSigner(owner).build_register_reward_node_transaction(
        node_id="funded-node", payout_address=owner.address, node_public_key_hex=ATTEST.public_key.hex(),
        declared_host="node.example", declared_port=38333, registration_fee_chipbits=fee,
        network="mainnet-test-only", height=300 if funded else 299,
        funded=funded, spend_candidates=_candidates(owner) if funded else None,
    )


def _registry():
    return InMemoryNodeRegistryView.from_records([NodeRecord(
        node_id="funded-node", payout_address=OWNER.address, owner_pubkey=OWNER.public_key,
        registered_height=275, last_renewed_height=275, node_pubkey=ATTEST.public_key,
        declared_host="node.example", declared_port=38333, reward_registration=True,
        owner_signature_scheme_id=10, node_signature_scheme_id=10,
    )])


def _mainnet_context(*, registry=None, utxo=True):
    entries = [] if not utxo else [(OUTPOINT, UtxoEntry(TxOutput(VALUE, OWNER.address), 0, False))]
    return ValidationContext(
        height=1,
        median_time_past=0,
        params=MAINNET_PARAMS,
        network="mainnet",
        utxo_view=InMemoryUtxoView.from_entries(entries),
        node_registry_view=registry or InMemoryNodeRegistryView(),
    )


def _mainnet_register(*, funded=True):
    return TransactionSigner(OWNER).build_register_reward_node_transaction(
        node_id="mainnet-funded-node",
        payout_address=OWNER.address,
        node_public_key_hex=ATTEST.public_key.hex(),
        declared_host="node.example",
        declared_port=38333,
        registration_fee_chipbits=100_000_000,
        network="mainnet",
        height=1,
        funded=funded,
        spend_candidates=_candidates() if funded else None,
    )


def test_registration_fee_and_activation_boundary():
    transaction = _register()
    assert transaction.version == 2
    assert len(transaction.inputs) == 1
    assert [(int(output.value), output.recipient) for output in transaction.outputs] == [(50_000_000, OWNER.address)]
    assert validate_transaction(transaction, _context()) == 100_000_000
    with pytest.raises(ContextualValidationError, match="funding format"):
        validate_transaction(_register(funded=False), _context())
    with pytest.raises(ContextualValidationError, match="funding format"):
        validate_transaction(transaction, _context(299))
    assert validate_transaction(_register(funded=False), _context(299)) == 0


def test_renewal_is_funded_and_legacy_testnet_remains_valid():
    renewal = TransactionSigner(OWNER).build_renew_reward_node_transaction(
        node_id="funded-node", renewal_epoch=3, declared_host="node.example", declared_port=38333,
        renewal_fee_chipbits=10_000_000, network="mainnet-test-only", height=300,
        funded=True, spend_candidates=_candidates(),
    )
    assert validate_transaction(renewal, _context(registry=_registry())) == 10_000_000
    assert int(renewal.outputs[0].value) == 140_000_000
    old = TransactionSigner(OWNER).build_register_reward_node_transaction(
        node_id="historical", payout_address=OWNER.address, node_public_key_hex=ATTEST.public_key.hex(),
        declared_host="node.example", declared_port=38333, registration_fee_chipbits=100_000_000,
        network="testnet", height=22_862,
    )
    context = replace(_context(), params=TESTNET_PARAMS, network="testnet", height=22_862)
    assert validate_transaction(old, context) == 0


def test_mainnet_requires_funded_registration_and_renewal_from_block_one():
    assert MAINNET_PARAMS.funded_reward_node_activation_height == 0
    assert validate_transaction(_mainnet_register(), _mainnet_context()) == 100_000_000
    with pytest.raises(ContextualValidationError, match="funding format"):
        validate_transaction(_mainnet_register(funded=False), _mainnet_context())

    legacy_renewal = TransactionSigner(OWNER).build_renew_reward_node_transaction(
        node_id="funded-node",
        renewal_epoch=0,
        declared_host="node.example",
        declared_port=38333,
        renewal_fee_chipbits=10_000_000,
        network="mainnet",
        height=1,
    )
    with pytest.raises(ContextualValidationError, match="funding format"):
        validate_transaction(legacy_renewal, _mainnet_context(registry=_registry()))


def test_mainnet_funded_registration_rejects_missing_utxo_bad_signature_and_chain_replay():
    transaction = _mainnet_register()
    with pytest.raises(ContextualValidationError, match="does not exist"):
        validate_transaction(transaction, _mainnet_context(utxo=False))

    bad_input = replace(transaction.inputs[0], signature=bytes([transaction.inputs[0].signature[0] ^ 1]) + transaction.inputs[0].signature[1:])
    with pytest.raises(ContextualValidationError, match="signature is invalid"):
        validate_transaction(replace(transaction, inputs=(bad_input,)), _mainnet_context())

    replayed_metadata = {**transaction.metadata, "owner_signature_chain_id": "chipcoin-mainnet-1-test-only-v1"}
    with pytest.raises(ValidationError, match="owner signature is invalid"):
        validate_transaction(replace(transaction, metadata=replayed_metadata), _mainnet_context())


@pytest.mark.parametrize("kind", ["registration", "renewal"])
def test_mainnet_block_one_rejects_legacy_reward_transaction(kind):
    params = replace(MAINNET_PARAMS, genesis_bits=MAINNET_TEST_ONLY_PARAMS.genesis_bits)
    legacy = (
        _mainnet_register(funded=False)
        if kind == "registration"
        else TransactionSigner(OWNER).build_renew_reward_node_transaction(
            node_id="funded-node", renewal_epoch=0, declared_host="node.example",
            declared_port=38333, renewal_fee_chipbits=10_000_000,
            network="mainnet", height=1,
        )
    )
    coinbase = build_coinbase_transaction(
        height=1, miner_address=OTHER.address,
        miner_amount_chipbits=50 * 100_000_000, rewarded_outputs=(),
    )
    txs = (coinbase, legacy)
    root = merkle_root([tx.txid() for tx in txs])
    for nonce in range(1000):
        header = BlockHeader(1, "cd" * 32, root, 1_700_000_000, params.genesis_bits, nonce)
        if verify_proof_of_work(header):
            break
    else:
        raise AssertionError("PoW target unexpectedly unreachable")
    context = replace(
        _mainnet_context(registry=_registry() if kind == "renewal" else None),
        params=params,
    )
    with pytest.raises(ContextualValidationError, match="funding format"):
        validate_block(Block(header, txs), context)


@pytest.mark.parametrize("count", [0, 1, 2, 20_000])
def test_dynamic_fee_formula_unchanged(count):
    register = register_reward_node_fee_chipbits(registered_reward_node_count=count, params=MAINNET_TEST_ONLY_PARAMS)
    renew = renew_reward_node_fee_chipbits(registered_reward_node_count=count, params=MAINNET_TEST_ONLY_PARAMS)
    assert (register, renew) == {
        0: (100_000_000, 10_000_000), 1: (100_000_000, 10_000_000),
        2: (92_968_703, 9_296_871), 20_000: (10_000, 1_000),
    }[count]


def test_rejects_wrong_fee_immature_input_other_owner_and_tamper():
    transaction = _register()
    with pytest.raises(ContextualValidationError, match="fee schedule"):
        validate_transaction(_register(fee=99_999_999), _context())
    with pytest.raises(ContextualValidationError, match="not mature"):
        validate_transaction(transaction, _context(origin=201))
    with pytest.raises(ContextualValidationError, match="does not belong"):
        validate_transaction(transaction, _context(owner=OTHER))
    with pytest.raises(ContextualValidationError, match="invalid"):
        validate_transaction(replace(transaction, outputs=(TxOutput(49_999_999, OWNER.address),)), _context())
    with pytest.raises(ValidationError, match="invalid"):
        validate_transaction(
            replace(transaction, metadata={**transaction.metadata, "declared_port": "38334"}),
            _context(),
        )
    with pytest.raises(ContextualValidationError, match="repeats an input"):
        validate_transaction(replace(transaction, inputs=transaction.inputs * 2), _context())


def _block(transactions, miner_amount):
    coinbase = build_coinbase_transaction(
        height=300, miner_address=OTHER.address, miner_amount_chipbits=miner_amount, rewarded_outputs=()
    )
    txs = (coinbase, *transactions)
    root = merkle_root([transaction.txid() for transaction in txs])
    for nonce in range(1000):
        header = BlockHeader(1, "cd" * 32, root, 1_700_000_000, MAINNET_TEST_ONLY_PARAMS.genesis_bits, nonce)
        if verify_proof_of_work(header):
            return Block(header, txs)
    raise AssertionError("PoW target unexpectedly unreachable")


def test_block_coinbase_claims_fee_once_and_spends_utxo():
    transaction = _register()
    subsidy, _ = subsidy_split_chipbits(300, MAINNET_TEST_ONLY_PARAMS)
    context = _context()
    assert validate_block(_block((transaction,), subsidy + 100_000_000), context) == 100_000_000
    with pytest.raises(ContextualValidationError, match="miner payout"):
        validate_block(_block((transaction,), subsidy), context)
    with pytest.raises(ContextualValidationError, match="double spend"):
        validate_block(_block((transaction, transaction), subsidy + 200_000_000), context)


def test_mining_template_claims_fee_and_utxo_replay_is_reversible():
    transaction = _register()
    baseline = _context().utxo_view
    coordinator = MiningCoordinator(params=MAINNET_TEST_ONLY_PARAMS, time_provider=lambda: 1_700_000_000)
    template = coordinator.build_block_template(
        previous_block_hash="cd" * 32,
        network="mainnet-test-only",
        height=300,
        miner_address=OTHER.address,
        bits=MAINNET_TEST_ONLY_PARAMS.genesis_bits,
        mempool_entries=[MempoolEntry(transaction=transaction, fee=100_000_000, added_at=1)],
        node_registry_view=InMemoryNodeRegistryView(),
        utxo_view=baseline,
        confirmed_transaction_ids={OUTPOINT.txid},
    )
    block = coordinator.mine_block(template, max_nonce_attempts=1000)
    assert block is not None
    subsidy, _ = subsidy_split_chipbits(300, MAINNET_TEST_ONLY_PARAMS)
    assert template.total_fees == 100_000_000
    assert int(block.transactions[0].outputs[0].value) == subsidy + 100_000_000
    assert block.transactions[1].txid() == transaction.txid()
    assert validate_block(block, _context()) == 100_000_000

    applied = baseline.clone()
    applied.apply_block(block, 300)
    assert applied.get(OUTPOINT) is None
    change = applied.get(OutPoint(transaction.txid(), 0))
    assert change is not None and int(change.output.value) == 50_000_000
    assert baseline.get(OUTPOINT) is not None
    assert baseline.get(OutPoint(transaction.txid(), 0)) is None
