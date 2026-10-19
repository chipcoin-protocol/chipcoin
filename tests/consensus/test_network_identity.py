"""Network identity invariants for the new public mainnet."""

import pytest

from chipcoin.config import DEVNET_CONFIG, MAINNET_CONFIG, MAINNET_TEST_ONLY_CONFIG, TESTNET_CONFIG, require_finalized_public_mainnet
from chipcoin.consensus.genesis import GenesisNotFinalizedError
from chipcoin.consensus.network_identity import (
    PUBLIC_MAINNET_CHAIN_ID,
    PUBLIC_MAINNET_P2P_MAGIC,
    MAINNET_TEST_ONLY_CHAIN_ID,
    MAINNET_TEST_ONLY_P2P_MAGIC,
    derive_p2p_magic,
)


def test_public_mainnet_identity_is_distinct_and_deterministic() -> None:
    assert MAINNET_CONFIG.chain_id == PUBLIC_MAINNET_CHAIN_ID == "chipcoin-mainnet-1"
    assert PUBLIC_MAINNET_P2P_MAGIC == derive_p2p_magic(PUBLIC_MAINNET_CHAIN_ID)
    assert PUBLIC_MAINNET_P2P_MAGIC.hex() == "c0897c0d"
    assert len({MAINNET_CONFIG.magic, TESTNET_CONFIG.magic, DEVNET_CONFIG.magic, bytes.fromhex("F9BEB4D9")}) == 4
    assert len({MAINNET_CONFIG.chain_id, TESTNET_CONFIG.chain_id, DEVNET_CONFIG.chain_id}) == 3


def test_accelerated_rehearsal_identity_is_distinct() -> None:
    assert MAINNET_TEST_ONLY_CONFIG.chain_id == MAINNET_TEST_ONLY_CHAIN_ID
    assert MAINNET_TEST_ONLY_P2P_MAGIC == derive_p2p_magic(MAINNET_TEST_ONLY_CHAIN_ID)
    assert MAINNET_TEST_ONLY_CONFIG.magic not in {
        MAINNET_CONFIG.magic,
        TESTNET_CONFIG.magic,
        DEVNET_CONFIG.magic,
    }
    assert MAINNET_TEST_ONLY_CONFIG.params.genesis_bits == 0x207FFFFF
    assert MAINNET_CONFIG.params.genesis_bits == 0x1D1399AD


def test_public_mainnet_startup_is_fail_closed_while_genesis_is_pending() -> None:
    with pytest.raises(GenesisNotFinalizedError, match="pending founder-approved timestamp"):
        require_finalized_public_mainnet("mainnet")

    require_finalized_public_mainnet("testnet")

