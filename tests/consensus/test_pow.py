from dataclasses import replace

from chipcoin.consensus.models import BlockHeader

from chipcoin.consensus.params import MAINNET_PARAMS, TESTNET_PARAMS
from chipcoin.consensus.pow import (
    bits_to_target,
    calculate_next_work_required,
    header_work,
    should_use_minimum_difficulty,
    target_to_bits,
    verify_proof_of_work,
)


def test_compact_target_roundtrip_preserves_target() -> None:
    original_bits = 0x1D00FFFF
    target = bits_to_target(original_bits)

    assert target_to_bits(target) == original_bits


def test_header_work_is_positive() -> None:
    header = BlockHeader(
        version=1,
        previous_block_hash="00" * 32,
        merkle_root="11" * 32,
        timestamp=1,
        bits=0x207FFFFF,
        nonce=0,
    )

    assert header_work(header) > 0


def test_verify_proof_of_work_accepts_easy_header() -> None:
    merkle = "22" * 32
    previous = "00" * 32

    for nonce in range(1_000_000):
        header = BlockHeader(
            version=1,
            previous_block_hash=previous,
            merkle_root=merkle,
            timestamp=1_700_000_000,
            bits=0x207FFFFF,
            nonce=nonce,
        )
        if verify_proof_of_work(header):
            assert True
            return

    raise AssertionError("Expected to find a valid nonce for an easy target.")


def test_calculate_next_work_required_increases_difficulty_when_blocks_are_fast() -> None:
    faster_bits = calculate_next_work_required(
        previous_bits=MAINNET_PARAMS.genesis_bits,
        actual_timespan_seconds=(MAINNET_PARAMS.target_block_time_seconds * MAINNET_PARAMS.difficulty_adjustment_window) // 2,
        params=MAINNET_PARAMS,
    )

    assert bits_to_target(faster_bits) < bits_to_target(MAINNET_PARAMS.genesis_bits)


def test_calculate_next_work_required_decreases_difficulty_when_blocks_are_slow() -> None:
    slower_bits = calculate_next_work_required(
        previous_bits=MAINNET_PARAMS.genesis_bits,
        actual_timespan_seconds=(MAINNET_PARAMS.target_block_time_seconds * MAINNET_PARAMS.difficulty_adjustment_window) * 2,
        params=MAINNET_PARAMS,
    )

    assert bits_to_target(slower_bits) >= bits_to_target(MAINNET_PARAMS.genesis_bits)


def test_calculate_next_work_required_uses_activation_height_schedule() -> None:
    params = replace(
        MAINNET_PARAMS,
        difficulty_adjustment_window=10,
        target_block_time_seconds=600,
        target_block_time_activation_height=100,
        legacy_target_block_time_seconds=300,
    )

    legacy_bits = calculate_next_work_required(
        previous_bits=MAINNET_PARAMS.genesis_bits,
        actual_timespan_seconds=3_000,
        params=params,
        candidate_height=90,
    )
    activated_bits = calculate_next_work_required(
        previous_bits=MAINNET_PARAMS.genesis_bits,
        actual_timespan_seconds=3_000,
        params=params,
        candidate_height=100,
    )

    assert legacy_bits == MAINNET_PARAMS.genesis_bits
    assert bits_to_target(activated_bits) < bits_to_target(MAINNET_PARAMS.genesis_bits)


def test_minimum_difficulty_escape_hatch_requires_activation_delay_and_non_retarget() -> None:
    params = replace(
        TESTNET_PARAMS,
        difficulty_adjustment_window=500,
        min_difficulty_activation_height=7_182,
        min_difficulty_delay_seconds=1_200,
    )

    assert not should_use_minimum_difficulty(
        params=params,
        candidate_height=7_181,
        previous_timestamp=1_000,
        candidate_timestamp=3_000,
    )
    assert not should_use_minimum_difficulty(
        params=params,
        candidate_height=7_182,
        previous_timestamp=1_000,
        candidate_timestamp=2_199,
    )
    assert not should_use_minimum_difficulty(
        params=params,
        candidate_height=7_500,
        previous_timestamp=1_000,
        candidate_timestamp=3_000,
    )
    assert should_use_minimum_difficulty(
        params=params,
        candidate_height=7_182,
        previous_timestamp=1_000,
        candidate_timestamp=2_200,
    )
