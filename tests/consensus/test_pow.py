from dataclasses import replace

import pytest

from chipcoin.consensus.models import BlockHeader

from chipcoin.consensus.params import MAINNET_PARAMS
from chipcoin.consensus.pow import (
    bits_to_target,
    calculate_next_work_required,
    header_work,
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


def test_rc4_genesis_bits_match_three_miner_bootstrap_calibration() -> None:
    bits = MAINNET_PARAMS.genesis_bits
    target = bits_to_target(bits)
    work = (1 << 256) // (target + 1)

    assert bits == 0x1E0537E7
    assert target_to_bits(target) == bits
    assert 0 < target < (1 << 256)
    assert work == 3_215_030
    assert work / 3_572 == pytest.approx(900.0644, abs=0.001)
    assert work / (2 * 3_572) == pytest.approx(450.0322, abs=0.001)
    assert work / (3 * 3_572) == pytest.approx(300.0215, abs=0.001)


def test_rc4_first_retarget_uses_six_hundred_second_target_and_genesis_cap() -> None:
    target = bits_to_target(MAINNET_PARAMS.genesis_bits)
    retargeted = calculate_next_work_required(
        previous_bits=MAINNET_PARAMS.genesis_bits,
        actual_timespan_seconds=299_700,
        params=MAINNET_PARAMS,
        candidate_height=1_000,
    )
    slow_clamped = calculate_next_work_required(
        previous_bits=MAINNET_PARAMS.genesis_bits,
        actual_timespan_seconds=2_400_000,
        params=MAINNET_PARAMS,
        candidate_height=1_000,
    )

    assert MAINNET_PARAMS.target_block_time_seconds == 600
    assert MAINNET_PARAMS.difficulty_adjustment_window == 1_000
    assert retargeted == 0x1E029B48
    assert bits_to_target(retargeted) == bits_to_target(target_to_bits(target * 299_700 // 600_000))
    adjusted_work = (1 << 256) // (bits_to_target(retargeted) + 1)
    assert adjusted_work / (3 * 3_572) == pytest.approx(600.6455, abs=0.001)
    assert bits_to_target(slow_clamped) == target


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
