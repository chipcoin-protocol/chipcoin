"""Immutable logical identities for Chipcoin network profiles."""

from __future__ import annotations

import hashlib


PUBLIC_MAINNET_CHAIN_ID = "chipcoin-mainnet-1"
MAINNET_TEST_ONLY_CHAIN_ID = "chipcoin-mainnet-1-test-only-v1"
TESTNET_CHAIN_ID = "chipcoin-testnet-1"
DEVNET_CHAIN_ID = "chipcoin-devnet-1"

CHAIN_IDS = {
    "mainnet": PUBLIC_MAINNET_CHAIN_ID,
    "mainnet-test-only": MAINNET_TEST_ONLY_CHAIN_ID,
    "testnet": TESTNET_CHAIN_ID,
    "devnet": DEVNET_CHAIN_ID,
}


def chain_id_for_network(network: str) -> str:
    """Return the immutable chain identifier for a supported profile."""

    try:
        return CHAIN_IDS[network]
    except KeyError as exc:
        raise ValueError(f"Unsupported network: {network}") from exc


def derive_p2p_magic(chain_id: str) -> bytes:
    """Derive a documented four-byte P2P discriminator from a chain id."""

    if not chain_id:
        raise ValueError("chain_id cannot be empty")
    return hashlib.sha256(f"chipcoin:p2p-magic:{chain_id}".encode("ascii")).digest()[:4]


PUBLIC_MAINNET_P2P_MAGIC = derive_p2p_magic(PUBLIC_MAINNET_CHAIN_ID)
MAINNET_TEST_ONLY_P2P_MAGIC = derive_p2p_magic(MAINNET_TEST_ONLY_CHAIN_ID)


def uses_mainnet_policy(network: str) -> bool:
    """Return whether a profile must enforce public-mainnet policy rules."""

    return network in {"mainnet", "mainnet-test-only"}

