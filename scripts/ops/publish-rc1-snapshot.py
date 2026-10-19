#!/usr/bin/env python3
"""Verify and atomically publish a signed snapshot through an immutable URL."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from chipcoin.config import consensus_params_fingerprint, get_network_config
from chipcoin.node.snapshots import load_snapshot_file


def _copy_sync(source: Path, destination: Path) -> None:
    with source.open("rb") as reader, destination.open("xb") as writer:
        shutil.copyfileobj(reader, writer)
        writer.flush()
        os.fsync(writer.fileno())


def publish(snapshot: Path, output_dir: Path, base_url: str, network: str, signer_hex: str) -> dict[str, object]:
    config = get_network_config(network)
    if network != "mainnet" or not config.genesis_finalized or not config.canonical_genesis_hash:
        raise ValueError("RC1 publication requires the finalized public mainnet genesis")
    signer = bytes.fromhex(signer_hex)
    if len(signer) != 32:
        raise ValueError("trusted signer must be a 32-byte Ed25519 public key")
    loaded = load_snapshot_file(
        snapshot, network=network, params=config.params, trust_mode="enforce", trusted_keys=(signer,)
    )
    metadata = loaded.metadata
    if loaded.trusted_signature_count < 1:
        raise ValueError("snapshot has no trusted signature")
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    filename = f"{network}-{loaded.anchor.height}-{digest}.snapshot"
    archive = output_dir / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    final_snapshot = archive / filename
    if final_snapshot.exists():
        if hashlib.sha256(final_snapshot.read_bytes()).hexdigest() != digest:
            raise ValueError("existing immutable snapshot has different bytes")
    else:
        fd, temporary_name = tempfile.mkstemp(prefix=".snapshot-", dir=archive)
        os.close(fd)
        temporary = Path(temporary_name)
        temporary.unlink()
        try:
            _copy_sync(snapshot, temporary)
            os.replace(temporary, final_snapshot)
        finally:
            temporary.unlink(missing_ok=True)
    archive_fd = os.open(archive, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(archive_fd)
    finally:
        os.close(archive_fd)
    url = f"{base_url.rstrip('/')}/archive/{filename}"
    entry = {
        "network": network,
        "chain_id": metadata["chain_id"],
        "genesis_hash": metadata["genesis_hash"],
        "p2p_magic_hex": metadata["p2p_magic_hex"],
        "consensus_params_sha256": metadata["consensus_params_sha256"],
        "snapshot_height": loaded.anchor.height,
        "snapshot_block_hash": loaded.anchor.block_hash,
        "snapshot_cumulative_work": metadata["snapshot_cumulative_work"],
        "utxo_sha256": metadata["utxo_sha256"],
        "node_registry_sha256": metadata["node_registry_sha256"],
        "checksum_sha256": digest,
        "snapshot_url": url,
        "format_version": metadata["format_version"],
        "signer_pubkeys": [signer_hex.lower()],
    }
    if entry["consensus_params_sha256"] != consensus_params_fingerprint(config.params):
        raise ValueError("snapshot consensus fingerprint mismatch")
    manifest = {"snapshots": [entry]}
    fd, temporary_name = tempfile.mkstemp(prefix=".manifest-", dir=output_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, output_dir / "latest.manifest.json")
        directory_fd = os.open(output_dir, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        Path(temporary_name).unlink(missing_ok=True)
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--network", default="mainnet")
    parser.add_argument("--trusted-signer-pubkey", required=True)
    args = parser.parse_args()
    try:
        entry = publish(args.snapshot_file, args.output_dir, args.base_url, args.network, args.trusted_signer_pubkey)
    except (OSError, ValueError, KeyError) as exc:
        print(f"snapshot publication refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(entry, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
