"""Public mainnet snapshot manifest identity checks."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..config import consensus_params_fingerprint, get_network_config
from .snapshots import read_snapshot_payload


IDENTITY_FIELDS = (
    "network", "chain_id", "genesis_hash", "p2p_magic_hex", "consensus_params_sha256",
    "snapshot_height", "snapshot_block_hash", "snapshot_cumulative_work",
    "utxo_sha256", "node_registry_sha256",
)


def validate_manifest_entry(entry: dict[str, object], *, network: str) -> None:
    if network != "mainnet":
        return
    config = get_network_config(network)
    if not config.genesis_finalized or not config.canonical_genesis_hash:
        raise ValueError("public mainnet genesis is not finalized")
    expected = {
        "network": network,
        "chain_id": config.chain_id,
        "genesis_hash": config.canonical_genesis_hash,
        "p2p_magic_hex": config.magic.hex(),
        "consensus_params_sha256": consensus_params_fingerprint(config.params),
    }
    for field, value in expected.items():
        if entry.get(field) != value:
            raise ValueError(f"snapshot manifest {field} mismatch")
    for field in ("snapshot_block_hash", "utxo_sha256", "node_registry_sha256", "checksum_sha256"):
        value = entry.get(field)
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError(f"snapshot manifest {field} is missing or invalid")
    if not isinstance(entry.get("snapshot_height"), int) or entry["snapshot_height"] < 0:
        raise ValueError("snapshot manifest height is invalid")
    if not isinstance(entry.get("snapshot_cumulative_work"), str) or not entry["snapshot_cumulative_work"].isdigit():
        raise ValueError("snapshot manifest cumulative work is invalid")
    if not isinstance(entry.get("snapshot_url"), str) or not entry["snapshot_url"].startswith("https://"):
        raise ValueError("snapshot manifest URL must use HTTPS")
    signers = entry.get("signer_pubkeys")
    if not isinstance(signers, list) or not signers:
        raise ValueError("snapshot manifest trusted signer is missing")


def verify_manifest_snapshot(path: Path, entry: dict[str, object], *, network: str) -> None:
    validate_manifest_entry(entry, network=network)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != entry.get("checksum_sha256"):
        raise ValueError("snapshot manifest checksum mismatch")
    metadata = read_snapshot_payload(path)["metadata"]
    for field in IDENTITY_FIELDS:
        if metadata.get(field) != entry.get(field):
            raise ValueError(f"snapshot manifest {field} differs from signed snapshot")
    signatures = metadata.get("signatures")
    if not isinstance(signatures, list) or not signatures:
        raise ValueError("snapshot has no signatures")
    public_keys = {record.get("public_key_hex") for record in signatures if isinstance(record, dict)}
    if not public_keys.intersection(entry["signer_pubkeys"]):
        raise ValueError("snapshot signer differs from manifest")
