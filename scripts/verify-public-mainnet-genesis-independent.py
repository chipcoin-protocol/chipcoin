#!/usr/bin/env python3
"""Verify emitted public-mainnet genesis bytes without importing Chipcoin."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import struct


DEFAULT_EXPECTED_CHAIN_ID = "chipcoin-mainnet-1"
EXPECTED_MESSAGE = "Die Welt ist alles, was der Fall ist."


def double_sha256(payload: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(payload).digest()).digest()


def read_varint(payload: bytes, offset: int) -> tuple[int, int]:
    prefix = payload[offset]
    offset += 1
    if prefix < 0xFD:
        return prefix, offset
    sizes = {0xFD: 2, 0xFE: 4, 0xFF: 8}
    size = sizes[prefix]
    return int.from_bytes(payload[offset : offset + size], "little"), offset + size


def read_bytes(payload: bytes, offset: int) -> tuple[bytes, int]:
    size, offset = read_varint(payload, offset)
    return payload[offset : offset + size], offset + size


def compact_target(bits: int) -> int:
    exponent = bits >> 24
    mantissa = bits & 0x007FFFFF
    return mantissa >> (8 * (3 - exponent)) if exponent <= 3 else mantissa << (8 * (exponent - 3))


def _find_valid_nonce(arguments: tuple[bytes, int, int, int]) -> int | None:
    header_prefix, start, stop, target = arguments
    for nonce in range(start, stop):
        digest = double_sha256(header_prefix + nonce.to_bytes(4, "little"))
        if int.from_bytes(digest, "big") <= target:
            return nonce
    return None


def has_no_lower_valid_nonce(
    header_prefix: bytes,
    nonce: int,
    bits: int,
    *,
    workers: int = 2,
    chunk_size: int = 1_000_000,
) -> bool:
    if len(header_prefix) != 76 or workers < 1 or chunk_size < 1:
        raise ValueError("invalid nonce-minimality scan parameters")
    target = compact_target(bits)
    ranges = (
        (header_prefix, start, min(start + chunk_size, nonce), target)
        for start in range(0, nonce, chunk_size)
    )
    with ProcessPoolExecutor(max_workers=workers) as executor:
        return not any(result is not None for result in executor.map(_find_valid_nonce, ranges))


def verify(
    directory: Path,
    *,
    expected_chain_id: str = DEFAULT_EXPECTED_CHAIN_ID,
    verify_nonce_minimality: bool = False,
    nonce_workers: int = 2,
    nonce_chunk_size: int = 1_000_000,
) -> dict[str, object]:
    block_path = directory / "genesis-block.hex"
    manifest_path = directory / "genesis-manifest.json"
    constants_path = directory / "genesis-constants.txt"
    block_hex = block_path.read_text(encoding="ascii").strip()
    block = bytes.fromhex(block_hex)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if len(block) < 81:
        raise ValueError("genesis block is truncated")
    version, = struct.unpack_from("<I", block, 0)
    previous_hash = block[4:36].hex()
    merkle = block[36:68].hex()
    timestamp, bits, nonce = struct.unpack_from("<III", block, 68)
    transaction_count, offset = read_varint(block, 80)
    transaction_start = offset
    tx_version, = struct.unpack_from("<I", block, offset)
    offset += 4
    input_count, offset = read_varint(block, offset)
    output_count, offset = read_varint(block, offset)
    locktime, = struct.unpack_from("<I", block, offset)
    offset += 4
    metadata_count, offset = read_varint(block, offset)
    metadata: dict[str, str] = {}
    for _ in range(metadata_count):
        key, offset = read_bytes(block, offset)
        value, offset = read_bytes(block, offset)
        metadata[key.decode("utf-8")] = value.decode("utf-8")
    if offset != len(block):
        raise ValueError("genesis block has trailing bytes")
    transaction = block[transaction_start:offset]
    txid = double_sha256(transaction).hex()
    header_hash = double_sha256(block[:80])
    block_hash = header_hash.hex()
    checks = {
        "version": version == 1 and tx_version == 1,
        "previous_hash": previous_hash == "00" * 32,
        "transaction_count": transaction_count == 1,
        "no_inputs": input_count == 0,
        "no_outputs": output_count == 0,
        "locktime": locktime == 0,
        "metadata": metadata == {
            "chain_id": expected_chain_id,
            "coinbase": "true",
            "genesis_message": EXPECTED_MESSAGE,
            "height": "0",
        },
        "merkle": merkle == txid,
        "pow": int.from_bytes(header_hash, "big") <= compact_target(bits),
        "manifest": (
            manifest["chain_id"] == expected_chain_id
            and manifest["timestamp"] == timestamp
            and manifest["bits"] == bits
            and manifest["nonce"] == nonce
            and manifest["transaction_id"] == txid
            and manifest["merkle_root"] == merkle
            and manifest["block_hash"] == block_hash
            and manifest["serialized_block_sha256"] == hashlib.sha256(block).hexdigest()
            and manifest["genesis_message_utf8_bytes"] == len(EXPECTED_MESSAGE.encode("utf-8"))
            and manifest["genesis_reward_chipbits"] == 0
            and manifest["initial_spendable_supply_chipbits"] == 0
        ),
    }
    if verify_nonce_minimality:
        checks["lowest_nonce"] = has_no_lower_valid_nonce(
            block[:76],
            nonce,
            bits,
            workers=nonce_workers,
            chunk_size=nonce_chunk_size,
        )
    expected_sums = {}
    for line in (directory / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        expected_sums[name] = digest
    checks["checksums"] = expected_sums == {
        block_path.name: hashlib.sha256(block_path.read_bytes()).hexdigest(),
        manifest_path.name: hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        constants_path.name: hashlib.sha256(constants_path.read_bytes()).hexdigest(),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise ValueError(f"independent genesis verification failed: {', '.join(failed)}")
    return {"block_hash": block_hash, "nonce": nonce, "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("--expected-chain-id", default=DEFAULT_EXPECTED_CHAIN_ID)
    parser.add_argument("--verify-lowest-nonce", action="store_true")
    parser.add_argument("--nonce-workers", type=int, default=2)
    parser.add_argument("--nonce-chunk-size", type=int, default=1_000_000)
    args = parser.parse_args()
    print(json.dumps(verify(
        args.artifact_dir,
        expected_chain_id=args.expected_chain_id,
        verify_nonce_minimality=args.verify_lowest_nonce,
        nonce_workers=args.nonce_workers,
        nonce_chunk_size=args.nonce_chunk_size,
    ), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
