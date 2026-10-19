"""Canonical public-mainnet genesis construction and verification."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path

from .merkle import merkle_root
from .models import Block, BlockHeader, Transaction
from .network_identity import MAINNET_TEST_ONLY_CHAIN_ID, PUBLIC_MAINNET_CHAIN_ID
from .pow import bits_to_target, verify_proof_of_work
from .serialization import serialize_block, serialize_block_header


GENESIS_MESSAGE = "Die Welt ist alles, was der Fall ist."
GENESIS_MESSAGE_BYTES = GENESIS_MESSAGE.encode("utf-8")
GENESIS_HEADER_VERSION = 1
GENESIS_TRANSACTION_VERSION = 1
GENESIS_PREVIOUS_BLOCK_HASH = "00" * 32

CANONICAL_GENESIS_TIMESTAMP = 1_792_519_200
CANONICAL_GENESIS_BLOCK_HEX: str | None = "0100000000000000000000000000000000000000000000000000000000000000000000006ec15ed32ddd62c6134b0c867c33f8fa72ba265b4551d327a57b63721cf34c7720acd76aad99131da606e61b01010000000000000000000408636861696e5f69641263686970636f696e2d6d61696e6e65742d3108636f696e6261736504747275650f67656e657369735f6d657373616765254469652057656c742069737420616c6c65732c20776173206465722046616c6c206973742e066865696768740130"
CANONICAL_GENESIS_HASH: str | None = "00000001fb292c1575cc647774e249a7e399b8b2c7b30743bbe9e5090476476d"
TEST_ONLY_GENESIS_BLOCK_HEX: str | None = None
TEST_ONLY_GENESIS_HASH: str | None = None
TEST_ONLY_GENESIS_TIMESTAMP: int | None = None


class GenesisNotFinalizedError(RuntimeError):
    """Raised when a requested network lacks an embedded canonical genesis."""


@dataclass(frozen=True)
class GenesisManifest:
    """Complete reproducible inputs and outputs for one canonical genesis."""

    chain_id: str
    timestamp: int
    bits: int
    nonce: int
    transaction_id: str
    merkle_root: str
    block_hash: str
    serialized_block_sha256: str
    message_utf8_bytes: int

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "chain_id": self.chain_id,
            "height": 0,
            "header_version": GENESIS_HEADER_VERSION,
            "previous_block_hash": GENESIS_PREVIOUS_BLOCK_HASH,
            "timestamp": self.timestamp,
            "bits": self.bits,
            "nonce": self.nonce,
            "genesis_message": GENESIS_MESSAGE,
            "genesis_message_encoding": "UTF-8",
            "genesis_message_utf8_bytes": self.message_utf8_bytes,
            "genesis_reward_chipbits": 0,
            "initial_spendable_supply_chipbits": 0,
            "transaction_id": self.transaction_id,
            "merkle_root": self.merkle_root,
            "block_hash": self.block_hash,
            "serialized_block_sha256": self.serialized_block_sha256,
        }


def build_genesis_transaction(*, chain_id: str = PUBLIC_MAINNET_CHAIN_ID) -> Transaction:
    """Build the output-free transaction committed by the public genesis."""

    if chain_id not in {PUBLIC_MAINNET_CHAIN_ID, MAINNET_TEST_ONLY_CHAIN_ID}:
        raise ValueError("genesis requires an approved public or TEST-ONLY chain id")
    if b"\n" in GENESIS_MESSAGE_BYTES or b"\r" in GENESIS_MESSAGE_BYTES or b"\x00" in GENESIS_MESSAGE_BYTES:
        raise ValueError("genesis message contains a forbidden byte")
    return Transaction(
        version=GENESIS_TRANSACTION_VERSION,
        inputs=(),
        outputs=(),
        locktime=0,
        metadata={
            "chain_id": chain_id,
            "coinbase": "true",
            "genesis_message": GENESIS_MESSAGE,
            "height": "0",
        },
    )


def build_genesis_block(
    *, timestamp: int, bits: int, nonce: int, chain_id: str = PUBLIC_MAINNET_CHAIN_ID
) -> Block:
    """Build a fully specified genesis candidate without runtime entropy."""

    if timestamp < 0 or timestamp > 0xFFFFFFFF:
        raise ValueError("genesis timestamp must fit in uint32")
    if nonce < 0 or nonce > 0xFFFFFFFF:
        raise ValueError("genesis nonce must fit in uint32")
    transaction = build_genesis_transaction(chain_id=chain_id)
    root = merkle_root([transaction.txid()])
    return Block(
        header=BlockHeader(
            version=GENESIS_HEADER_VERSION,
            previous_block_hash=GENESIS_PREVIOUS_BLOCK_HASH,
            merkle_root=root,
            timestamp=timestamp,
            bits=bits,
            nonce=nonce,
        ),
        transactions=(transaction,),
    )


def canonical_genesis_block(*, network: str = "mainnet") -> Block:
    """Decode the embedded genesis for a genesis-bearing network profile."""

    if network == "mainnet":
        block_hex, expected_hash = CANONICAL_GENESIS_BLOCK_HEX, CANONICAL_GENESIS_HASH
        label = "public mainnet"
    elif network == "mainnet-test-only":
        block_hex, expected_hash = TEST_ONLY_GENESIS_BLOCK_HEX, TEST_ONLY_GENESIS_HASH
        label = "TEST-ONLY mainnet rehearsal"
    else:
        raise ValueError(f"network has no canonical genesis: {network}")
    if block_hex is None or expected_hash is None:
        raise GenesisNotFinalizedError(f"{label} genesis is not finalized")
    from .serialization import deserialize_block

    raw = bytes.fromhex(block_hex)
    block, offset = deserialize_block(raw)
    if offset != len(raw):
        raise ValueError("embedded public genesis contains trailing bytes")
    if block.block_hash() != expected_hash:
        raise ValueError(f"embedded {label} genesis hash does not match its constant")
    return block


def mine_genesis(
    *, timestamp: int, bits: int, chain_id: str = PUBLIC_MAINNET_CHAIN_ID
) -> Block:
    """Return the first valid nonce for fixed canonical genesis inputs."""

    candidate = build_genesis_block(timestamp=timestamp, bits=bits, nonce=0, chain_id=chain_id)
    for nonce in range(0x1_0000_0000):
        block = replace(candidate, header=replace(candidate.header, nonce=nonce))
        if verify_proof_of_work(block.header):
            return block
    raise RuntimeError("no valid genesis nonce exists in the uint32 search space")


def _mine_genesis_range(arguments: tuple[int, int, str, int, int]) -> int | None:
    timestamp, bits, chain_id, start, stop = arguments
    candidate = build_genesis_block(timestamp=timestamp, bits=bits, nonce=0, chain_id=chain_id)
    header_prefix = serialize_block_header(candidate.header)[:76]
    target = bits_to_target(bits)
    for nonce in range(start, stop):
        header = header_prefix + nonce.to_bytes(4, byteorder="little", signed=False)
        header_hash = hashlib.sha256(hashlib.sha256(header).digest()).digest()
        if int.from_bytes(header_hash, byteorder="big", signed=False) <= target:
            return nonce
    return None


def mine_genesis_parallel(
    *,
    timestamp: int,
    bits: int,
    workers: int,
    chunk_size: int = 1_000_000,
    chain_id: str = PUBLIC_MAINNET_CHAIN_ID,
) -> Block:
    """Find the same first valid nonce as ``mine_genesis`` using worker batches."""

    if workers < 1:
        raise ValueError("workers must be at least 1")
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    nonce_limit = 0x1_0000_0000
    with ProcessPoolExecutor(max_workers=workers) as executor:
        for batch_start in range(0, nonce_limit, workers * chunk_size):
            ranges = [
                (timestamp, bits, chain_id, start, min(start + chunk_size, nonce_limit))
                for start in range(
                    batch_start,
                    min(batch_start + workers * chunk_size, nonce_limit),
                    chunk_size,
                )
            ]
            valid_nonces = [nonce for nonce in executor.map(_mine_genesis_range, ranges) if nonce is not None]
            if valid_nonces:
                return build_genesis_block(
                    timestamp=timestamp,
                    bits=bits,
                    nonce=min(valid_nonces),
                    chain_id=chain_id,
                )
    raise RuntimeError("no valid genesis nonce exists in the uint32 search space")


def verify_genesis(
    block: Block,
    *,
    bits: int,
    expected_hash: str | None = None,
    chain_id: str = PUBLIC_MAINNET_CHAIN_ID,
) -> None:
    """Reject any deviation from the canonical genesis structure."""

    if block.header.version != GENESIS_HEADER_VERSION:
        raise ValueError("genesis header version mismatch")
    if block.header.previous_block_hash != GENESIS_PREVIOUS_BLOCK_HASH:
        raise ValueError("genesis previous hash mismatch")
    if block.header.bits != bits:
        raise ValueError("genesis difficulty mismatch")
    expected_transaction = build_genesis_transaction(chain_id=chain_id)
    if block.transactions != (expected_transaction,):
        raise ValueError("genesis transaction mismatch")
    if block.header.merkle_root != merkle_root([expected_transaction.txid()]):
        raise ValueError("genesis merkle root mismatch")
    if not verify_proof_of_work(block.header):
        raise ValueError("genesis proof of work is invalid")
    if expected_hash is not None and block.block_hash() != expected_hash:
        raise ValueError("genesis block hash mismatch")


def genesis_manifest(block: Block) -> GenesisManifest:
    """Return deterministic public metadata for a verified genesis block."""

    transaction = block.transactions[0]
    raw = serialize_block(block)
    return GenesisManifest(
        chain_id=transaction.metadata["chain_id"],
        timestamp=block.header.timestamp,
        bits=block.header.bits,
        nonce=block.header.nonce,
        transaction_id=transaction.txid(),
        merkle_root=block.header.merkle_root,
        block_hash=block.block_hash(),
        serialized_block_sha256=hashlib.sha256(raw).hexdigest(),
        message_utf8_bytes=len(GENESIS_MESSAGE_BYTES),
    )


def write_genesis_manifest(path: Path, manifest: GenesisManifest) -> None:
    """Atomically write a canonical JSON manifest with no secret material."""

    payload = json.dumps(manifest.as_dict(), sort_keys=True, indent=2) + "\n"
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def write_genesis_artifacts(output_dir: Path, block: Block) -> dict[str, str]:
    """Write the complete frozen-genesis candidate as deterministic files."""

    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    chain_id = block.transactions[0].metadata.get("chain_id", "")
    verify_genesis(block, bits=block.header.bits, chain_id=chain_id)
    raw = serialize_block(block)
    manifest = genesis_manifest(block)
    output_dir.mkdir(parents=True, exist_ok=False)

    payloads = {
        "genesis-block.hex": (raw.hex() + "\n").encode("ascii"),
        "genesis-manifest.json": (
            json.dumps(manifest.as_dict(), sort_keys=True, indent=2) + "\n"
        ).encode("utf-8"),
        "genesis-constants.txt": (
            f'CANONICAL_GENESIS_BLOCK_HEX = "{raw.hex()}"\n'
            f'CANONICAL_GENESIS_HASH = "{block.block_hash()}"\n'
        ).encode("ascii"),
    }
    for name, payload in payloads.items():
        temporary = output_dir / f".{name}.tmp"
        temporary.write_bytes(payload)
        temporary.replace(output_dir / name)

    checksums = [
        f"{hashlib.sha256(payload).hexdigest()}  {name}"
        for name, payload in payloads.items()
    ]
    (output_dir / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="ascii")
    return {name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()}

