"""Monetary policy and reward schedule helpers."""

from __future__ import annotations

from .params import ConsensusParams
from .nodes import NodeRegistryView


CHCBITS_PER_CHC = 100_000_000
REWARD_NODE_FEE_TARGET_COUNT = 20_000
REWARD_NODE_FEE_LOG_SCALE = 1_000_000
REWARD_NODE_MIN_REGISTER_FEE_CHIPBITS = 10_000
REWARD_NODE_MIN_RENEW_FEE_CHIPBITS = 1_000


def _regular_miner_subsidy_chipbits(height: int, params: ConsensusParams) -> int:
    """Return the ordinary halving-based miner subsidy in chipbits."""

    if height < 0:
        raise ValueError("Block height cannot be negative.")

    halvings = height // params.halving_interval
    subsidy_chipbits = params.initial_miner_subsidy_chipbits >> halvings
    return max(subsidy_chipbits, 0)


def _regular_node_epoch_reward_chipbits(height: int, params: ConsensusParams) -> int:
    """Return the ordinary halving-based node epoch reward in chipbits."""

    if height < 0:
        raise ValueError("Block height cannot be negative.")

    halvings = height // params.halving_interval
    reward_chipbits = params.initial_node_epoch_reward_chipbits >> halvings
    return max(reward_chipbits, 0)


def is_epoch_reward_height(height: int, params: ConsensusParams) -> bool:
    """Return whether one block height closes a node reward epoch."""

    if height < 0:
        raise ValueError("Block height cannot be negative.")
    return (height + 1) % params.epoch_length_blocks == 0


def _scheduled_node_epoch_reward_chipbits(height: int, params: ConsensusParams) -> int:
    """Return the scheduled node reward attached to one block height before cap clamp."""

    if not is_epoch_reward_height(height, params):
        return 0
    return _regular_node_epoch_reward_chipbits(height, params)


def subsidy_split_chipbits(height: int, params: ConsensusParams) -> tuple[int, int]:
    """Return the exact miner/node subsidy split for one block height."""

    if height < 0:
        raise ValueError("Block height cannot be negative.")

    scheduled_miner_subsidy = _regular_miner_subsidy_chipbits(height, params)
    scheduled_node_reward = _scheduled_node_epoch_reward_chipbits(height, params)
    if scheduled_miner_subsidy <= 0 and scheduled_node_reward <= 0:
        return 0, 0

    minted_before = total_subsidy_through_height(height - 1, params)
    remaining_supply = max(0, params.max_money_chipbits - minted_before)
    if remaining_supply <= 0:
        return 0, 0

    miner_subsidy = min(scheduled_miner_subsidy, remaining_supply)
    remaining_supply -= miner_subsidy
    node_reward = min(scheduled_node_reward, remaining_supply)
    return miner_subsidy, node_reward


def miner_subsidy_chipbits(height: int, params: ConsensusParams) -> int:
    """Return the miner base subsidy in chipbits for a given height."""

    return subsidy_split_chipbits(height, params)[0]


def node_reward_pool_chipbits(height: int, params: ConsensusParams) -> int:
    """Return the node reward minted at one block height in chipbits."""

    return subsidy_split_chipbits(height, params)[1]


def total_block_subsidy_chipbits(height: int, params: ConsensusParams) -> int:
    """Return total subsidy minted by one block in chipbits."""

    return miner_subsidy_chipbits(height, params) + node_reward_pool_chipbits(height, params)


def block_subsidy(height: int, params: ConsensusParams) -> int:
    """Backward-compatible alias for total per-block subsidy in chipbits."""

    return total_block_subsidy_chipbits(height, params)


def total_subsidy_through_height(height: int, params: ConsensusParams) -> int:
    """Return the total minted subsidy from height zero through the given height."""

    if height < 0:
        return 0

    total = 0
    for current_height in range(height + 1):
        miner_subsidy = _regular_miner_subsidy_chipbits(current_height, params)
        node_reward = _scheduled_node_epoch_reward_chipbits(current_height, params)
        if miner_subsidy <= 0 and node_reward <= 0:
            break
        scheduled_total = miner_subsidy + node_reward
        remaining_supply = max(0, params.max_money_chipbits - total)
        total += min(scheduled_total, remaining_supply)
    return total


def reward_registered_node_count(registry_view: NodeRegistryView) -> int:
    """Return the count of reward-node registrations visible on-chain."""

    return sum(1 for record in registry_view.list_records() if record.reward_registration)


def _approx_log2_scaled(value: int) -> int:
    """Return a monotonic fixed-point approximation of log2(value)."""

    if value <= 0:
        raise ValueError("Logarithm input must be positive.")
    if value == 1:
        return 0
    exponent = value.bit_length() - 1
    lower = 1 << exponent
    upper = lower << 1
    fraction = ((value - lower) * REWARD_NODE_FEE_LOG_SCALE) // (upper - lower)
    return exponent * REWARD_NODE_FEE_LOG_SCALE + fraction


def _adaptive_reward_node_fee_chipbits(
    *,
    registered_reward_node_count: int,
    maximum_fee_chipbits: int,
    minimum_fee_chipbits: int,
) -> int:
    """Return one deterministic logarithmic reward-node fee from registry size."""

    if maximum_fee_chipbits <= 0:
        raise ValueError("Maximum fee must be positive.")
    if minimum_fee_chipbits <= 0:
        raise ValueError("Minimum fee must be positive.")
    if minimum_fee_chipbits > maximum_fee_chipbits:
        raise ValueError("Minimum fee cannot exceed maximum fee.")

    clamped_count = min(max(registered_reward_node_count, 1), REWARD_NODE_FEE_TARGET_COUNT)
    if clamped_count == 1:
        return maximum_fee_chipbits

    target_log = _approx_log2_scaled(REWARD_NODE_FEE_TARGET_COUNT)
    progress = _approx_log2_scaled(clamped_count)
    span = maximum_fee_chipbits - minimum_fee_chipbits
    reduced_fee = maximum_fee_chipbits - ((span * progress) // target_log)
    return max(minimum_fee_chipbits, reduced_fee)


def register_reward_node_fee_chipbits(*, registered_reward_node_count: int, params: ConsensusParams) -> int:
    """Return the current reward-node registration fee in chipbits."""

    return _adaptive_reward_node_fee_chipbits(
        registered_reward_node_count=registered_reward_node_count,
        maximum_fee_chipbits=params.register_node_fee_chipbits,
        minimum_fee_chipbits=REWARD_NODE_MIN_REGISTER_FEE_CHIPBITS,
    )


def renew_reward_node_fee_chipbits(*, registered_reward_node_count: int, params: ConsensusParams) -> int:
    """Return the current reward-node renewal fee in chipbits."""

    return _adaptive_reward_node_fee_chipbits(
        registered_reward_node_count=registered_reward_node_count,
        maximum_fee_chipbits=params.renew_node_fee_chipbits,
        minimum_fee_chipbits=REWARD_NODE_MIN_RENEW_FEE_CHIPBITS,
    )
