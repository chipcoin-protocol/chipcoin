"""Deterministic PoW/timestamp checks for the isolated accelerated profile."""

from dataclasses import replace

import pytest

from chipcoin.consensus.genesis import mine_genesis
from chipcoin.consensus.merkle import merkle_root
from chipcoin.consensus.models import Block, BlockHeader, Transaction, TxOutput
from chipcoin.consensus.params import MAINNET_PARAMS, MAINNET_TEST_ONLY_PARAMS
from chipcoin.consensus.pow import (
    bits_to_target,
    calculate_next_work_required,
    verify_proof_of_work,
)
from chipcoin.consensus.validation import (
    StatelessValidationError,
    ValidationContext,
    validate_block_stateless,
)


def test_accelerated_profile_changes_only_approved_test_only_parameters() -> None:
    assert MAINNET_TEST_ONLY_PARAMS.genesis_bits == 0x207FFFFF
    assert MAINNET_PARAMS.genesis_bits == 0x1E0537E7
    assert {
        key: value
        for key, value in MAINNET_TEST_ONLY_PARAMS.__dict__.items()
        if key not in {"genesis_bits", "funded_reward_node_activation_height"}
    } == {
        key: value
        for key, value in MAINNET_PARAMS.__dict__.items()
        if key not in {"genesis_bits", "funded_reward_node_activation_height"}
    }
    assert MAINNET_TEST_ONLY_PARAMS.funded_reward_node_activation_height == 300
    assert MAINNET_PARAMS.funded_reward_node_activation_height == 0


def test_height_1000_fast_window_retarget_is_bounded_to_factor_four() -> None:
    next_bits = calculate_next_work_required(
        previous_bits=MAINNET_TEST_ONLY_PARAMS.genesis_bits,
        actual_timespan_seconds=999,
        params=MAINNET_TEST_ONLY_PARAMS,
        candidate_height=1_000,
    )

    assert next_bits == 0x201FFFFF
    assert bits_to_target(next_bits) <= bits_to_target(
        MAINNET_TEST_ONLY_PARAMS.genesis_bits
    ) // 4


def test_retarget_cannot_relax_beyond_test_only_pow_limit() -> None:
    next_bits = calculate_next_work_required(
        previous_bits=MAINNET_TEST_ONLY_PARAMS.genesis_bits,
        actual_timespan_seconds=10_000_000,
        params=MAINNET_TEST_ONLY_PARAMS,
        candidate_height=1_000,
    )

    assert next_bits == MAINNET_TEST_ONLY_PARAMS.genesis_bits


def test_test_only_genesis_uses_real_proof_of_work() -> None:
    block = mine_genesis(
        timestamp=1_800_000_000,
        bits=MAINNET_TEST_ONLY_PARAMS.genesis_bits,
        chain_id="chipcoin-mainnet-1-test-only-v1",
    )

    assert verify_proof_of_work(block.header)
    invalid = None
    for offset in range(1, 100):
        candidate = replace(
            block,
            header=replace(block.header, nonce=block.header.nonce + offset),
        )
        if not verify_proof_of_work(candidate.header):
            invalid = candidate
            break
    assert invalid is not None
    assert not verify_proof_of_work(invalid.header)


def test_timestamp_below_validation_context_is_rejected() -> None:
    coinbase = Transaction(
        version=1,
        inputs=(),
        outputs=(TxOutput(value=50 * 100_000_000, recipient="CHCtest-only-miner"),),
        metadata={"coinbase": "true", "height": "1"},
    )
    root = merkle_root([coinbase.txid()])
    block = None
    for nonce in range(100):
        candidate = Block(
            header=BlockHeader(
                version=1,
                previous_block_hash="11" * 32,
                merkle_root=root,
                timestamp=1_800_000_000,
                bits=MAINNET_TEST_ONLY_PARAMS.genesis_bits,
                nonce=nonce,
            ),
            transactions=(coinbase,),
        )
        if verify_proof_of_work(candidate.header):
            block = candidate
            break
    assert block is not None
    exact_boundary_context = ValidationContext(
        height=1,
        median_time_past=block.header.timestamp,
        params=MAINNET_TEST_ONLY_PARAMS,
        utxo_view=None,
        network="mainnet-test-only",
    )
    validate_block_stateless(block, exact_boundary_context)

    context = ValidationContext(
        height=1,
        median_time_past=block.header.timestamp + 1,
        params=MAINNET_TEST_ONLY_PARAMS,
        utxo_view=None,
        network="mainnet-test-only",
    )

    with pytest.raises(StatelessValidationError, match="below median time past"):
        validate_block_stateless(block, context)
