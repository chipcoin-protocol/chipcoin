"""Frozen consensus and economic invariants for the mainnet genesis candidate."""

from chipcoin.consensus.economics import (
    node_reward_pool_chipbits,
    subsidy_split_chipbits,
    total_subsidy_through_height,
)
from chipcoin.consensus.epoch_settlement import reward_epoch_seed_version
from chipcoin.consensus.nodes import special_node_signature_version_for_height
from chipcoin.consensus.params import MAINNET_PARAMS
from chipcoin.consensus.pq_activation import pq_support_activation_height


MAINNET_EXACT_CAP_HEIGHT = 643_297


def test_mainnet_consensus_profile_is_frozen() -> None:
    params = MAINNET_PARAMS

    assert params.target_block_time_seconds == 600
    assert params.difficulty_adjustment_window == 1_000
    assert params.target_block_time_activation_height == 0
    assert params.legacy_target_block_time_seconds is None
    assert params.genesis_bits == 0x1D1399AD
    assert params.coinbase_maturity == 100
    assert params.epoch_length_blocks == 100
    assert params.halving_interval == 111_000
    assert params.max_money_chipbits == 11_000_000 * 100_000_000
    assert params.initial_miner_subsidy_chipbits == 50 * 100_000_000
    assert params.initial_node_epoch_reward_chipbits == 50 * 100_000_000
    assert params.node_reward_activation_height == 1_000
    assert params.reward_node_warmup_epochs == 2
    assert params.max_rewarded_nodes_per_epoch == 25
    assert params.reward_node_fee_recent_driver_activation_height == 0
    assert params.require_pq_standard_transactions is True
    assert params.reward_node_signature_scheme_id == 10


def test_mainnet_modern_consensus_rules_are_active_from_genesis() -> None:
    assert pq_support_activation_height("mainnet", params=MAINNET_PARAMS) == 0
    assert reward_epoch_seed_version(network="mainnet", epoch_index=0) == 2
    assert special_node_signature_version_for_height(network="mainnet", height=0) == "v2"


def test_mainnet_emission_ends_at_the_frozen_hard_cap() -> None:
    maximum = MAINNET_PARAMS.max_money_chipbits

    assert node_reward_pool_chipbits(99, MAINNET_PARAMS) == 50 * 100_000_000
    assert total_subsidy_through_height(MAINNET_EXACT_CAP_HEIGHT - 1, MAINNET_PARAMS) == maximum - 156_250_000
    assert subsidy_split_chipbits(MAINNET_EXACT_CAP_HEIGHT, MAINNET_PARAMS) == (156_250_000, 0)
    assert total_subsidy_through_height(MAINNET_EXACT_CAP_HEIGHT, MAINNET_PARAMS) == maximum
    assert subsidy_split_chipbits(MAINNET_EXACT_CAP_HEIGHT + 1, MAINNET_PARAMS) == (0, 0)
