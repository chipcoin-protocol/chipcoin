"""Generate or verify public pool vectors against the checked-out Core.

Run from the repository root with PYTHONPATH=src. No wallets or live data are read.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import tempfile

from chipcoin.consensus.genesis import canonical_genesis_block
from chipcoin.consensus.hashes import double_sha256
from chipcoin.consensus.economics import subsidy_split_chipbits
from chipcoin.consensus.merkle import merkle_root
from chipcoin.consensus.models import Block, BlockHeader, TxOutput
from chipcoin.consensus.params import DEVNET_PARAMS, MAINNET_PARAMS, TESTNET_PARAMS
from chipcoin.consensus.pq_activation import pq_support_activation_height
from chipcoin.consensus.pow import bits_to_target, target_to_bits, verify_proof_of_work
from chipcoin.consensus.serialization import (
    deserialize_block, serialize_block, serialize_block_header, serialize_transaction,
)
from chipcoin.consensus.validation import validate_block_stateless, StatelessValidationError
from chipcoin.crypto.addresses import parse_address, public_key_to_address, public_key_to_pq_address
from chipcoin.node.mining import build_coinbase_transaction
from chipcoin.node.service import NodeService


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "v1.json"
# Public, compressed secp256k1 generator point; no signing key is used.
PUBLIC_KEY = bytes.fromhex(
    "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
)
PQ_ADDRESS = "CHCQCqjJWcT8Jqxvmn9xspxBWnTojXQp93Wqu9sP5F6GkFd1f5xKiRhE"


def make_vectors() -> dict:
    genesis = canonical_genesis_block()
    genesis_header = serialize_block_header(genesis.header)
    miner = public_key_to_address(PUBLIC_KEY)
    coinbase = build_coinbase_transaction(
        height=0, miner_address=miner,
        miner_amount_chipbits=DEVNET_PARAMS.initial_miner_subsidy_chipbits,
        rewarded_outputs=(), extra_metadata={"extra_nonce": "pool-vector-1"},
    )
    txid = coinbase.txid()
    header = BlockHeader(version=1, previous_block_hash="00" * 32,
                         merkle_root=merkle_root([txid]), timestamp=1_800_000_000,
                         bits=DEVNET_PARAMS.genesis_bits, nonce=0)
    for nonce in range(100_000):
        solved = replace(header, nonce=nonce)
        if verify_proof_of_work(solved):
            break
    else:
        raise AssertionError("Devnet vector PoW search exhausted")
    block = Block(header=solved, transactions=(coinbase,))
    bad = replace(block, header=replace(solved, merkle_root="00" * 32))
    bad_nonce = solved.nonce + 1
    while verify_proof_of_work(replace(solved, nonce=bad_nonce)):
        bad_nonce += 1
    bad_pow = replace(block, header=replace(solved, nonce=bad_nonce))
    pq = parse_address(PQ_ADDRESS)
    miner_subsidy, node_pool = subsidy_split_chipbits(1099, MAINNET_PARAMS)
    reward_layout = build_coinbase_transaction(
        height=1099, miner_address=PQ_ADDRESS, miner_amount_chipbits=miner_subsidy,
        rewarded_outputs=(TxOutput(value=node_pool, recipient=PQ_ADDRESS),),
    )
    changed_coinbase = build_coinbase_transaction(
        height=0, miner_address=miner, miner_amount_chipbits=DEVNET_PARAMS.initial_miner_subsidy_chipbits,
        rewarded_outputs=(), extra_metadata={"extra_nonce": "pool-vector-2"},
    )
    locktime_coinbase = replace(coinbase, locktime=0x12345678)
    leaves = [double_sha256(f"pool-leaf-{i}".encode()).hex() for i in (1, 2, 3)]
    return {
        "schema_version": 1,
        "core_commit": "4c0984e65de31a50db7558d468167d513769bb20",
        "mainnet_genesis": {
            "network": "mainnet", "height": 0,
            "source": "consensus.genesis.canonical_genesis_block; consensus.serialization; consensus.pow",
            "header_fields": vars(genesis.header),
            "header_hex": genesis_header.hex(), "header_size_bytes": len(genesis_header),
            "block_hex": serialize_block(genesis).hex(),
            "block_hash": genesis.block_hash(), "coinbase_hex": serialize_transaction(genesis.transactions[0]).hex(),
            "coinbase_txid": genesis.transactions[0].txid(),
            "merkle_root": genesis.header.merkle_root,
            "target_hex": f"{bits_to_target(genesis.header.bits):064x}",
            "digest_big_endian_hex": double_sha256(genesis_header).hex(),
        },
        "isolated_devnet_example": {
            "network": "devnet", "height": 0, "synthetic": True,
            "source": "node.mining.build_coinbase_transaction; consensus.serialization; consensus.pow; consensus.merkle",
            "public_key_hex": PUBLIC_KEY.hex(), "miner_address": miner,
            "coinbase_metadata": coinbase.metadata,
            "coinbase_outputs": [{"recipient": o.recipient, "amount_chipbits": int(o.value)} for o in coinbase.outputs],
            "coinbase_hex": serialize_transaction(coinbase).hex(), "coinbase_txid": txid,
            "merkle_root": block.header.merkle_root,
            "header_fields": vars(block.header), "header_hex": serialize_block_header(block.header).hex(),
            "block_hex": serialize_block(block).hex(), "block_hash": block.block_hash(),
            "target_hex": f"{bits_to_target(block.header.bits):064x}",
            "pow_valid": True,
            "legacy_submit": {"template_id": "<issued-id>", "miner_id": "<same-miner-id>", "serialized_block": serialize_block(block).hex()},
            "full_submit": {"serialized_block": serialize_block(block).hex()},
            "invalid_merkle_block_hex": serialize_block(bad).hex(),
            "invalid_merkle_error": "Block Merkle root does not match transaction contents.",
            "invalid_pow_block_hex": serialize_block(bad_pow).hex(),
            "invalid_pow_error": "Block proof of work is invalid.",
            "changed_extra_nonce": {
                "metadata": changed_coinbase.metadata,
                "coinbase_hex": serialize_transaction(changed_coinbase).hex(),
                "coinbase_txid": changed_coinbase.txid(),
                "merkle_root": merkle_root([changed_coinbase.txid()]),
            },
            "changed_locktime": {
                "locktime": locktime_coinbase.locktime,
                "coinbase_hex": serialize_transaction(locktime_coinbase).hex(),
                "coinbase_txid": locktime_coinbase.txid(),
                "merkle_root": merkle_root([locktime_coinbase.txid()]),
            },
        },
        "reward_layout_encoding_only": {
            "network": "mainnet", "height": 1099, "synthetic": True,
            "contextually_validated": False,
            "source": "node.mining.build_coinbase_transaction; consensus.economics.subsidy_split_chipbits",
            "note": "Serialization example only: an actual epoch-closing block also requires valid settlement state and transaction.",
            "coinbase_hex": serialize_transaction(reward_layout).hex(),
            "outputs": [{"recipient": o.recipient, "amount_chipbits": int(o.value)} for o in reward_layout.outputs],
        },
        "merkle_three_leaves": {
            "network": "synthetic", "source": "consensus.merkle.merkle_root",
            "txids": leaves, "root": merkle_root(leaves),
        },
        "compact_targets": [
            {"network": network, "bits": params.genesis_bits,
             "target_hex": f"{bits_to_target(params.genesis_bits):064x}",
             "normalized_bits": target_to_bits(bits_to_target(params.genesis_bits))}
            for network, params in (("mainnet", MAINNET_PARAMS), ("testnet", TESTNET_PARAMS), ("devnet", DEVNET_PARAMS))
        ],
        "chcq_address": {
            "network": "mainnet", "source": "crypto.addresses.parse_address; tests/wallet/test_wallet_signer.py",
            "address": PQ_ADDRESS, "scheme_id": pq.scheme_id,
            "version": pq.version, "payload_hex": pq.payload.hex(),
            "commitment_hex": pq.hash_or_commitment.hex(),
            "checksum_corruption": PQ_ADDRESS[:-1] + ("1" if PQ_ADDRESS[-1] != "1" else "2"),
            "unsupported_scheme_address": public_key_to_pq_address(PUBLIC_KEY, scheme_id=11),
        },
        "profiles": {
            network: {"pq_activation_height": pq_support_activation_height(network, params=params),
                      "coinbase_maturity": params.coinbase_maturity}
            for network, params in (("mainnet", MAINNET_PARAMS), ("testnet", TESTNET_PARAMS), ("devnet", DEVNET_PARAMS))
        },
    }


def verify(data: dict) -> None:
    assert data == make_vectors(), "fixture differs from current Core output"
    g = data["mainnet_genesis"]
    assert g["header_size_bytes"] == 80
    assert int(g["block_hash"], 16) <= int(g["target_hex"], 16)
    d = data["isolated_devnet_example"]
    block, offset = deserialize_block(bytes.fromhex(d["block_hex"]))
    assert offset == len(bytes.fromhex(d["block_hex"]))
    assert block.block_hash() == d["block_hash"]
    assert verify_proof_of_work(block.header)
    validate_block_stateless(block)
    with tempfile.TemporaryDirectory(prefix="chipcoin-pool-vectors-") as root:
        service = NodeService.open_sqlite(
            Path(root) / "devnet.sqlite3", network="devnet", time_provider=lambda: block.header.timestamp,
        )
        accepted = service.accept_full_block(block)
        assert accepted["accepted"] and accepted["on_active_chain"] and accepted["consensus_validity"] == "validated"
        duplicate = service.accept_full_block(block)
        assert duplicate["reason"] == "already_accepted" and duplicate["on_active_chain"]
        service.connection.close()
    bad, _ = deserialize_block(bytes.fromhex(d["invalid_merkle_block_hex"]))
    try:
        validate_block_stateless(bad)
    except StatelessValidationError as exc:
        assert str(exc) == d["invalid_merkle_error"]
    else:
        raise AssertionError("invalid Merkle root accepted")
    bad_pow, _ = deserialize_block(bytes.fromhex(d["invalid_pow_block_hex"]))
    try:
        validate_block_stateless(bad_pow)
    except StatelessValidationError as exc:
        assert str(exc) == d["invalid_pow_error"]
    else:
        raise AssertionError("invalid PoW accepted")
    assert parse_address(data["chcq_address"]["address"]).scheme_id == 10
    assert parse_address(data["chcq_address"]["unsupported_scheme_address"]).scheme_id == 11
    assert d["coinbase_txid"] != d["changed_extra_nonce"]["coinbase_txid"]
    assert d["merkle_root"] != d["changed_extra_nonce"]["merkle_root"]
    assert d["coinbase_txid"] != d["changed_locktime"]["coinbase_txid"]
    for row in data["compact_targets"]:
        assert row["bits"] == row["normalized_bits"]
    try:
        parse_address(data["chcq_address"]["checksum_corruption"])
    except ValueError:
        pass
    else:
        raise AssertionError("bad CHCQ checksum accepted")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="regenerate the checked-in fixture")
    args = parser.parse_args()
    if args.write:
        FIXTURE.write_text(json.dumps(make_vectors(), indent=2, sort_keys=True) + "\n")
    verify(json.loads(FIXTURE.read_text()))
    print("handbook vectors: PASS")
