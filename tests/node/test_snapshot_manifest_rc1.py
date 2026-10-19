from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from chipcoin.config import consensus_params_fingerprint, get_network_config
from chipcoin.node import snapshot_manifest


PUBLISH_PATH = Path(__file__).resolve().parents[2] / "scripts/ops/publish-rc1-snapshot.py"


def _final_config():
    return replace(get_network_config("mainnet"), canonical_genesis_hash="ab" * 32, genesis_finalized=True)


def _entry(config, snapshot: Path) -> dict[str, object]:
    return {
        "network": "mainnet",
        "chain_id": config.chain_id,
        "genesis_hash": config.canonical_genesis_hash,
        "p2p_magic_hex": config.magic.hex(),
        "consensus_params_sha256": consensus_params_fingerprint(config.params),
        "snapshot_height": 7,
        "snapshot_block_hash": "cd" * 32,
        "snapshot_cumulative_work": "8",
        "utxo_sha256": "12" * 32,
        "node_registry_sha256": "34" * 32,
        "checksum_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        "snapshot_url": "https://example.invalid/archive/immutable.snapshot",
        "format_version": 2,
        "signer_pubkeys": ["56" * 32],
    }


def test_mainnet_manifest_requires_complete_canonical_identity(monkeypatch, tmp_path: Path) -> None:
    config = _final_config()
    monkeypatch.setattr(snapshot_manifest, "get_network_config", lambda _: config)
    snapshot = tmp_path / "snapshot"
    snapshot.write_bytes(b"snapshot")
    entry = _entry(config, snapshot)
    snapshot_manifest.validate_manifest_entry(entry, network="mainnet")
    for field in ("chain_id", "genesis_hash", "p2p_magic_hex", "consensus_params_sha256", "utxo_sha256", "snapshot_cumulative_work"):
        invalid = dict(entry)
        invalid.pop(field)
        with pytest.raises(ValueError):
            snapshot_manifest.validate_manifest_entry(invalid, network="mainnet")


def test_manifest_must_match_signed_snapshot_metadata(monkeypatch, tmp_path: Path) -> None:
    config = _final_config()
    monkeypatch.setattr(snapshot_manifest, "get_network_config", lambda _: config)
    snapshot = tmp_path / "snapshot"
    snapshot.write_bytes(b"snapshot")
    entry = _entry(config, snapshot)
    metadata = {field: entry[field] for field in snapshot_manifest.IDENTITY_FIELDS}
    metadata["signatures"] = [{"public_key_hex": entry["signer_pubkeys"][0]}]
    monkeypatch.setattr(snapshot_manifest, "read_snapshot_payload", lambda _: {"metadata": metadata})
    snapshot_manifest.verify_manifest_snapshot(snapshot, entry, network="mainnet")
    metadata["utxo_sha256"] = "00" * 32
    with pytest.raises(ValueError, match="utxo_sha256"):
        snapshot_manifest.verify_manifest_snapshot(snapshot, entry, network="mainnet")


def test_publisher_commits_manifest_last_and_preserves_old_manifest_on_failure(monkeypatch, tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("publish_rc1_snapshot", PUBLISH_PATH)
    assert spec and spec.loader
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)
    config = _final_config()
    monkeypatch.setattr(publisher, "get_network_config", lambda _: config)
    snapshot = tmp_path / "signed.snapshot"
    snapshot.write_bytes(b"signed snapshot bytes")
    entry = _entry(config, snapshot)
    metadata = {field: entry[field] for field in snapshot_manifest.IDENTITY_FIELDS}
    metadata["format_version"] = 2
    monkeypatch.setattr(publisher, "load_snapshot_file", lambda *a, **k: SimpleNamespace(
        metadata=metadata,
        anchor=SimpleNamespace(height=7, block_hash=entry["snapshot_block_hash"]),
        trusted_signature_count=1,
    ))
    out = tmp_path / "public"
    out.mkdir()
    old_manifest = out / "latest.manifest.json"
    old_manifest.write_text('{"previous":true}\n')
    original_replace = publisher.os.replace

    def interrupted_replace(source, destination):
        if Path(destination) == old_manifest:
            raise OSError("interrupted publication")
        return original_replace(source, destination)

    monkeypatch.setattr(publisher.os, "replace", interrupted_replace)
    with pytest.raises(OSError, match="interrupted"):
        publisher.publish(snapshot, out, "https://example.invalid", "mainnet", entry["signer_pubkeys"][0])
    assert json.loads(old_manifest.read_text()) == {"previous": True}
    assert list((out / "archive").glob("*.snapshot"))
    assert not list(out.glob(".manifest-*"))
    monkeypatch.setattr(publisher.os, "replace", original_replace)
    published = publisher.publish(snapshot, out, "https://example.invalid", "mainnet", entry["signer_pubkeys"][0])
    assert json.loads(old_manifest.read_text())["snapshots"] == [published]
    assert (out / "archive" / published["snapshot_url"].rsplit("/", 1)[-1]).read_bytes() == snapshot.read_bytes()
