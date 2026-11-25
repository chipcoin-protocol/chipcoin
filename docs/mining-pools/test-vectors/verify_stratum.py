"""Check the original Crypto Connection Devnet vector against Core v0.1.2.

Run with PYTHONPATH pointing at the clean v0.1.2 checkout's src directory.
The fixture is read only; expected values are never regenerated in the JSON.
"""

from __future__ import annotations

from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path

from chipcoin.consensus.hashes import double_sha256
from chipcoin.consensus.merkle import merkle_root
from chipcoin.consensus.pow import bits_to_target, verify_proof_of_work
from chipcoin.consensus.serialization import (
    deserialize_block,
    deserialize_block_header,
    deserialize_transaction,
    serialize_block,
    serialize_block_header,
    serialize_transaction,
)


VECTOR = Path(__file__).with_name("chc_stratum_vector.json")
CORE_COMMIT = "12e4dbc8974bd76885e30e6dacdf1b7be898e126"
EXPECTED_MD5 = "1784e3cc51bb48c256e8cac6badd60f4"
EXPECTED_SHA256 = "924fc787d55f820552973a05586a0123fedd9cf87914ca068623b70409d727a6"


def swapped_words(hex_text: str) -> bytes:
    raw = bytes.fromhex(hex_text)
    assert len(raw) == 32
    return b"".join(raw[index : index + 4][::-1] for index in range(0, 32, 4))


def main() -> None:
    original = VECTOR.read_bytes()
    assert len(original) == 32528
    assert hashlib.md5(original, usedforsecurity=False).hexdigest() == EXPECTED_MD5
    assert hashlib.sha256(original).hexdigest() == EXPECTED_SHA256
    data = json.loads(original)
    assert data["network"] == "devnet" and data["core"]["commit"] == CORE_COMMIT
    vector = data["vector"]
    connection = vector["connection"]
    notify = json.loads(vector["mining.notify"])
    submit = json.loads(vector["mining.submit"])
    subscribe = json.loads(connection["subscribe_response"])
    authorize = json.loads(connection["authorize_request"])
    difficulty = json.loads(connection["set_difficulty"])
    params = notify["params"]
    assert notify["method"] == "mining.notify" and len(params) == 9
    assert params[0] == "0000000b" and params[8] is True
    assert submit["method"] == "mining.submit" and submit["params"][1] == params[0]
    assert submit["params"][0] == authorize["params"][0]
    assert subscribe["result"][1] == connection["extranonce1"]
    assert subscribe["result"][2] == connection["extranonce2_size"] == 2
    assert len(bytes.fromhex(connection["extranonce1"])) == 2
    assert len(bytes.fromhex(submit["params"][2])) == 2
    assert submit["params"][3] == params[7]
    assert int(params[5], 16) == vector["template"]["version"]
    assert int(params[6], 16) == vector["template"]["bits"]
    assert int(params[7], 16) == vector["template"]["curtime"]
    assert difficulty["method"] == "mining.set_difficulty"
    with localcontext() as context:
        context.prec = 100
        share_target = int(Decimal(2) ** 224 / Decimal(str(connection["stratum_difficulty"])))
    assert share_target == int(connection["share_target_hex"], 16)

    derived = vector["derived"]
    coinbase_bytes = bytes.fromhex(params[2] + connection["extranonce1"] + submit["params"][2] + params[3])
    assert coinbase_bytes.hex() == derived["coinbase_hex"]
    coinbase, end = deserialize_transaction(coinbase_bytes)
    assert end == len(coinbase_bytes) and serialize_transaction(coinbase) == coinbase_bytes
    assert coinbase.txid() == derived["coinbase_txid"]
    assert coinbase.version == vector["template"]["coinbase_tx"]["version"]
    assert coinbase.inputs == ()
    assert coinbase.locktime == int.from_bytes(bytes.fromhex(connection["extranonce1"] + submit["params"][2]), "little")
    assert coinbase.locktime == derived["coinbase_locktime_u32"]
    assert coinbase.metadata == derived["coinbase_decoded"]["metadata"]
    assert [(int(output.value), output.recipient) for output in coinbase.outputs] == [
        (output["amount_chipbits"], output["recipient"])
        for output in vector["template"]["coinbase_tx"]["outputs"]
    ]

    transactions = []
    for entry in vector["template"]["transactions"]:
        raw = bytes.fromhex(entry["raw_hex"])
        transaction, end = deserialize_transaction(raw)
        assert end == len(raw) and serialize_transaction(transaction) == raw
        assert transaction.txid() == entry["txid"]
        assert transaction.version == 1  # Synthetic private-Devnet legacy data.
        transactions.append(transaction)
    txids = [coinbase.txid(), *(transaction.txid() for transaction in transactions)]
    root = merkle_root(txids)
    assert root == derived["merkle_root"]
    branch_root = bytes.fromhex(coinbase.txid())
    assert len(params[4]) == len(derived["merkle_branches"]) == 2
    for branch in params[4]:
        branch_root = double_sha256(branch_root + bytes.fromhex(branch))
    assert branch_root.hex() == root

    header_bytes = b"".join((
        bytes.fromhex(params[5])[::-1],
        swapped_words(params[1]),
        bytes.fromhex(root),
        bytes.fromhex(params[7])[::-1],
        bytes.fromhex(params[6])[::-1],
        bytes.fromhex(submit["params"][4])[::-1],
    ))
    assert len(header_bytes) == 80 and header_bytes.hex() == derived["header_hex"]
    header, end = deserialize_block_header(header_bytes)
    assert end == 80 and serialize_block_header(header) == header_bytes
    assert header.previous_block_hash == vector["template"]["previous_block_hash"]
    assert header.merkle_root == root
    assert header.block_hash() == derived["block_hash"]
    assert verify_proof_of_work(header)
    assert bits_to_target(header.bits) == int(derived["block_target_hex"], 16)
    assert int.from_bytes(bytes.fromhex(header.block_hash()), "big") <= bits_to_target(header.bits)

    full_bytes = bytes.fromhex(derived["block_hex"])
    assert len(full_bytes) == derived["block_size_bytes"] == 717
    assert full_bytes[:80] == header_bytes
    block, end = deserialize_block(full_bytes)
    assert end == len(full_bytes) and serialize_block(block) == full_bytes
    assert block.header == header and block.transactions == (coinbase, *transactions)
    assert block.block_hash() == derived["block_hash"]
    assert vector["pool_to_node"]["submit_block_request"]["serialized_block"] == derived["block_hex"]
    assert vector["pool_to_node"]["submit_block_request"]["template_id"] == vector["template"]["template_id"]
    assert vector["pool_to_node"]["submit_block_response"]["block_hash"] == block.block_hash()
    assert json.loads(vector["submit_reply"])["result"] is True
    assert len(vector["active_chain"]) == 2 and all(vector["active_chain"].values())

    summary = data["summary"]
    assert len(summary["blocks"]) == summary["blocks_rebuilt"] == summary["blocks_all_checks_passed"] == 68
    assert sum(bool(row["accepted"]) for row in summary["blocks"]) == summary["blocks_accepted_by_node"] == 41
    assert 68 - 41 == summary["blocks_stale_not_accepted"] == 27
    assert summary["share_check_failures"] == vector["checks_failed"] == []
    print("PASS: original JSON checksum, Stratum/coinbase/header/block bytes, TXIDs, Merkle root, PoW, full parser consumption")
    print("SUMMARY_ONLY: 68 reconstructed, 41 accepted, 27 stale are internally consistent; historical outcomes need original logs")


if __name__ == "__main__":
    main()
