"""Post-quantum transaction activation policy."""

from __future__ import annotations

from .params import ConsensusParams


PQ_TRANSACTION_VERSION = 2
PQ_SUPPORT_MAINNET_ACTIVATION_HEIGHT = 0
PQ_SUPPORT_DEVNET_ACTIVATION_HEIGHT = 30_000
PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT = 20_000
PQ_SUPPORT_SCHEDULED_NETWORKS = {"devnet", "testnet"}


def pq_support_activation_height(network: str, *, params: ConsensusParams | None = None) -> int:
    """Return the height where CHCQ/v2 wallet spends become valid."""

    if params is not None and params.pq_support_activation_height is not None:
        return params.pq_support_activation_height

    normalized = network.lower()
    if normalized == "mainnet":
        return PQ_SUPPORT_MAINNET_ACTIVATION_HEIGHT
    if normalized == "devnet":
        return PQ_SUPPORT_DEVNET_ACTIVATION_HEIGHT
    if normalized == "testnet":
        return PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT
    return PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT


def pq_support_is_active(*, network: str, height: int, params: ConsensusParams | None = None) -> bool:
    """Return whether CHCQ/v2 wallet-spend support is active."""

    return height >= pq_support_activation_height(network, params=params)
