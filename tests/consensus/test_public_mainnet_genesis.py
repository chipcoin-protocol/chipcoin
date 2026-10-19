"""Frozen invariants for the pending public-mainnet genesis design."""

from __future__ import annotations

from dataclasses import replace

import pytest

from chipcoin.consensus.economics import subsidy_split_chipbits, total_subsidy_through_height
from chipcoin.consensus.genesis import (
    GENESIS_MESSAGE,
    GENESIS_MESSAGE_BYTES,
    build_genesis_block,
    build_genesis_transaction,
    genesis_manifest,
    mine_genesis,
    mine_genesis_parallel,
    verify_genesis,
)
from chipcoin.consensus.merkle import merkle_root
from chipcoin.consensus.params import MAINNET_PARAMS
from chipcoin.consensus.network_identity import MAINNET_TEST_ONLY_CHAIN_ID
from chipcoin.consensus.params import MAINNET_TEST_ONLY_PARAMS
from chipcoin.consensus.serialization import serialize_block


EASY_BITS = 0x207FFFFF


def test_wittgenstein_message_is_exact_utf8_and_committed() -> None:
    transaction = build_genesis_transaction()

    assert GENESIS_MESSAGE == "Die Welt ist alles, was der Fall ist."
    assert GENESIS_MESSAGE_BYTES == GENESIS_MESSAGE.encode("utf-8")
    assert len(GENESIS_MESSAGE_BYTES) == 37
    assert not GENESIS_MESSAGE_BYTES.startswith(b"\xef\xbb\xbf")
    assert b"\n" not in GENESIS_MESSAGE_BYTES
    assert b"\r" not in GENESIS_MESSAGE_BYTES
    assert b"\x00" not in GENESIS_MESSAGE_BYTES
    assert transaction.metadata["genesis_message"].encode("utf-8") == GENESIS_MESSAGE_BYTES

    altered = replace(transaction, metadata={**transaction.metadata, "genesis_message": GENESIS_MESSAGE + " "})
    assert altered.txid() != transaction.txid()
    assert merkle_root([altered.txid()]) != merkle_root([transaction.txid()])


def test_genesis_is_deterministic_output_free_and_reproducible() -> None:
    first = mine_genesis(timestamp=1_800_000_000, bits=EASY_BITS)
    second = mine_genesis(timestamp=1_800_000_000, bits=EASY_BITS)

    assert serialize_block(first) == serialize_block(second)
    assert first.block_hash() == second.block_hash()
    assert first.transactions[0].outputs == ()
    assert genesis_manifest(first).message_utf8_bytes == len(GENESIS_MESSAGE_BYTES)
    verify_genesis(first, bits=EASY_BITS, expected_hash=first.block_hash())


def test_parallel_builder_returns_the_same_first_nonce() -> None:
    serial = mine_genesis(timestamp=1_800_000_000, bits=EASY_BITS)
    parallel = mine_genesis_parallel(
        timestamp=1_800_000_000,
        bits=EASY_BITS,
        workers=2,
        chunk_size=2,
    )

    assert parallel == serial


def test_test_only_genesis_has_distinct_identity_and_real_pow() -> None:
    block = mine_genesis(
        timestamp=1_800_000_000,
        bits=MAINNET_TEST_ONLY_PARAMS.genesis_bits,
        chain_id=MAINNET_TEST_ONLY_CHAIN_ID,
    )

    assert block.transactions[0].metadata["chain_id"] == MAINNET_TEST_ONLY_CHAIN_ID
    assert block.transactions[0].outputs == ()
    verify_genesis(
        block,
        bits=MAINNET_TEST_ONLY_PARAMS.genesis_bits,
        expected_hash=block.block_hash(),
        chain_id=MAINNET_TEST_ONLY_CHAIN_ID,
    )


def test_genesis_rejects_any_alteration() -> None:
    block = mine_genesis(timestamp=1_800_000_000, bits=EASY_BITS)
    changed_transaction = replace(
        block.transactions[0],
        metadata={**block.transactions[0].metadata, "genesis_message": "altered"},
    )
    changed = replace(block, transactions=(changed_transaction,))

    with pytest.raises(ValueError, match="transaction mismatch"):
        verify_genesis(changed, bits=EASY_BITS)


def test_zero_genesis_reward_preserves_halving_boundaries_and_exact_cap() -> None:
    maximum = MAINNET_PARAMS.max_money_chipbits

    assert subsidy_split_chipbits(0, MAINNET_PARAMS) == (0, 0)
    assert subsidy_split_chipbits(1, MAINNET_PARAMS) == (50 * 100_000_000, 0)
    assert subsidy_split_chipbits(110_999, MAINNET_PARAMS)[0] == 50 * 100_000_000
    assert subsidy_split_chipbits(111_000, MAINNET_PARAMS)[0] == 25 * 100_000_000
    assert total_subsidy_through_height(643_327, MAINNET_PARAMS) == maximum - 156_250_000
    assert subsidy_split_chipbits(643_328, MAINNET_PARAMS) == (156_250_000, 0)
    assert total_subsidy_through_height(643_328, MAINNET_PARAMS) == maximum
    assert subsidy_split_chipbits(643_329, MAINNET_PARAMS) == (0, 0)


def test_genesis_never_mints_node_rewards_even_for_one_block_epochs() -> None:
    params = replace(MAINNET_PARAMS, epoch_length_blocks=1)

    assert subsidy_split_chipbits(0, params) == (0, 0)

