"""SQLite bootstrap checks for the output-free canonical genesis."""

from dataclasses import replace

import pytest

from chipcoin.consensus.genesis import mine_genesis
from chipcoin.consensus.network_identity import PUBLIC_MAINNET_CHAIN_ID
from chipcoin.consensus.params import MAINNET_PARAMS
from chipcoin.consensus.pow import verify_proof_of_work
from chipcoin.node.service import NodeService
from chipcoin.wallet.signer import wallet_key_from_mldsa44_seed


EASY_BITS = 0x207FFFFF


def test_empty_database_installs_genesis_without_utxos(tmp_path) -> None:
    params = replace(MAINNET_PARAMS, genesis_bits=EASY_BITS)
    block = mine_genesis(timestamp=1_800_000_000, bits=EASY_BITS)
    service = NodeService.open_sqlite(tmp_path / "public-mainnet.sqlite3", params=params)

    service.install_or_verify_genesis(block, chain_id=PUBLIC_MAINNET_CHAIN_ID)
    service.install_or_verify_genesis(block, chain_id=PUBLIC_MAINNET_CHAIN_ID)

    assert service.chain_tip().height == 0
    assert service.chain_tip().block_hash == block.block_hash()
    assert service.chainstate.list_utxos() == []
    assert service._get_chain_meta("chain_id") == PUBLIC_MAINNET_CHAIN_ID
    assert service._get_chain_meta("genesis_hash") == block.block_hash()


def test_existing_database_rejects_different_genesis(tmp_path) -> None:
    params = replace(MAINNET_PARAMS, genesis_bits=EASY_BITS)
    first = mine_genesis(timestamp=1_800_000_000, bits=EASY_BITS)
    second = mine_genesis(timestamp=1_800_000_001, bits=EASY_BITS)
    service = NodeService.open_sqlite(tmp_path / "public-mainnet.sqlite3", params=params)
    service.install_or_verify_genesis(first, chain_id=PUBLIC_MAINNET_CHAIN_ID)

    with pytest.raises(ValueError, match="database genesis"):
        service.install_or_verify_genesis(second, chain_id=PUBLIC_MAINNET_CHAIN_ID)


def test_first_ordinary_block_after_genesis_pays_fifty_chc(tmp_path) -> None:
    params = replace(MAINNET_PARAMS, genesis_bits=EASY_BITS)
    block = mine_genesis(timestamp=1_800_000_000, bits=EASY_BITS)
    service = NodeService.open_sqlite(
        tmp_path / "public-mainnet.sqlite3",
        params=params,
        time_provider=lambda: 1_800_000_001,
    )
    service.install_or_verify_genesis(block, chain_id=PUBLIC_MAINNET_CHAIN_ID)
    miner = wallet_key_from_mldsa44_seed(b"\x01" * 32)
    candidate = service.build_candidate_block(miner.address).block

    solved = None
    for nonce in range(2_000_000):
        proposed = replace(candidate, header=replace(candidate.header, nonce=nonce))
        if verify_proof_of_work(proposed.header):
            solved = proposed
            break
    assert solved is not None
    assert solved.transactions[0].metadata["height"] == "1"
    assert int(solved.transactions[0].outputs[0].value) == 50 * 100_000_000
    service.apply_block(solved)

    assert service.chain_tip().height == 1

