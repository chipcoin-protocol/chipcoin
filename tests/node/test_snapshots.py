from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from chipcoin.consensus.epoch_settlement import RewardAttestation, RewardAttestationBundle, RewardSettlement, RewardSettlementEntry
from chipcoin.consensus.models import Block
from chipcoin.consensus.nodes import NodeRecord
from chipcoin.consensus.pow import verify_proof_of_work
from chipcoin.node.snapshots import read_snapshot_payload, sign_snapshot_payload, snapshot_checksum, write_snapshot_file
from chipcoin.node.service import NodeService
from chipcoin.node.sync import SyncManager
from chipcoin.storage.native_rewards import StoredEpochSettlement, StoredRewardAttestationBundle


def _make_service(database_path: Path, *, start_time: int) -> NodeService:
    timestamps = iter(range(start_time, start_time + 50_000))
    return NodeService.open_sqlite(database_path, time_provider=lambda: next(timestamps))


def _mine_block(block: Block) -> Block:
    for nonce in range(2_000_000):
        header = replace(block.header, nonce=nonce)
        if verify_proof_of_work(header):
            return replace(block, header=header)
    raise AssertionError("Expected to find a valid nonce for the easy target.")


def _mine_chain(service: NodeService, count: int, miner_address: str) -> list[Block]:
    blocks: list[Block] = []
    for _ in range(count):
        block = _mine_block(service.build_candidate_block(miner_address).block)
        service.apply_block(block)
        blocks.append(block)
    return blocks


def _ed25519_keypair() -> tuple[bytes, bytes]:
    private_key = ed25519.Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private_bytes, public_bytes


def _export_snapshot_v1(service: NodeService, path: Path) -> None:
    service.export_snapshot_file(path, format_version=1)


def test_snapshot_export_import_roundtrip_preserves_anchor_and_utxo_state() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        _mine_chain(source, 4, "CHCminer-source")
        snapshot_path = Path(tempdir) / "snapshot.json"

        metadata = source.export_snapshot_file(snapshot_path)

        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_001_000)
        imported = target.import_snapshot_file(snapshot_path)

        assert imported["checksum_sha256"] == metadata["checksum_sha256"]
        assert target.chain_tip() is not None
        assert source.chain_tip() is not None
        assert target.chain_tip().block_hash == source.chain_tip().block_hash
        assert target.chain_tip().height == source.chain_tip().height
        assert target.snapshot_anchor() is not None
        assert target.snapshot_anchor().block_hash == source.chain_tip().block_hash
        assert target.chainstate.list_utxos() == source.chainstate.list_utxos()
        assert target.node_registry.list_records() == source.node_registry.list_records()
        assert metadata["format_version"] == 2
        assert snapshot_path.read_bytes().startswith(b"CHCSNP2\n")


def test_testnet_rejects_devnet_snapshot_import() -> None:
    with TemporaryDirectory() as tempdir:
        timestamps = iter(range(1_700_000_000, 1_700_000_200))
        source = NodeService.open_sqlite(
            Path(tempdir) / "source-devnet.sqlite3",
            network="devnet",
            time_provider=lambda: next(timestamps),
        )
        _mine_chain(source, 1, "CHCminer-source")
        snapshot_path = Path(tempdir) / "devnet.snapshot"
        source.export_snapshot_file(snapshot_path)
        target = NodeService.open_sqlite(Path(tempdir) / "target-testnet.sqlite3", network="testnet")

        with pytest.raises(ValueError, match="snapshot network does not match configured node network"):
            target.import_snapshot_file(snapshot_path)


def test_snapshot_v2_signed_import_roundtrip() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        _mine_chain(source, 3, "CHCminer-source")
        snapshot_path = Path(tempdir) / "snapshot-v2.bin"
        source.export_snapshot_file(snapshot_path)
        payload = read_snapshot_payload(snapshot_path)
        private_key, public_key = _ed25519_keypair()
        write_snapshot_file(snapshot_path, sign_snapshot_payload(payload, private_key=private_key))

        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_001_000)
        imported = target.import_snapshot_file(snapshot_path, trust_mode="enforce", trusted_keys=(public_key,))

        assert imported["format_version"] == 2
        assert imported["trusted_signature_count"] == 1
        assert target.chain_tip() is not None
        assert target.chain_tip().block_hash == source.chain_tip().block_hash


def test_snapshot_roundtrip_preserves_native_reward_registry_and_payload_tables() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        _mine_chain(source, 4, "CHCminer-source")
        source.node_registry.upsert(
            NodeRecord(
                node_id="reward-node-a",
                payout_address="CHCreward-node-a",
                owner_pubkey=bytes.fromhex("11" * 33),
                registered_height=2,
                last_renewed_height=3,
                node_pubkey=bytes.fromhex("22" * 33),
                declared_host="127.0.0.1",
                declared_port=19001,
                reward_registration=True,
            )
        )
        source.reward_attestations.replace_all(
            [
                StoredRewardAttestationBundle(
                    txid="aa" * 32,
                    block_height=3,
                    bundle=RewardAttestationBundle(
                        epoch_index=0,
                        bundle_window_index=1,
                        bundle_submitter_node_id="reward-node-a",
                        attestations=(
                            RewardAttestation(
                                epoch_index=0,
                                check_window_index=1,
                                candidate_node_id="reward-node-a",
                                verifier_node_id="reward-node-a",
                                result_code="pass",
                                observed_sync_gap=0,
                                endpoint_commitment="127.0.0.1:19001",
                                concentration_key="ip:127.0.0.1",
                                signature_hex="ab",
                            ),
                        ),
                    ),
                )
            ]
        )
        source.reward_settlements.replace_all(
            [
                StoredEpochSettlement(
                    txid="bb" * 32,
                    block_height=3,
                    settlement=RewardSettlement(
                        epoch_index=0,
                        epoch_start_height=0,
                        epoch_end_height=99,
                        epoch_seed_hex="33" * 32,
                        policy_version="native-v1-test",
                        submission_mode="manual",
                        candidate_summary_root="44" * 32,
                        verified_nodes_root="55" * 32,
                        rewarded_nodes_root="66" * 32,
                        rewarded_node_count=1,
                        distributed_node_reward_chipbits=1234,
                        undistributed_node_reward_chipbits=0,
                        reward_entries=(
                            RewardSettlementEntry(
                                node_id="reward-node-a",
                                payout_address="CHCreward-node-a",
                                reward_chipbits=1234,
                                selection_rank=0,
                                concentration_key="ip:127.0.0.1",
                                final_confirmation_passed=True,
                            ),
                        ),
                    ),
                )
            ]
        )
        snapshot_path = Path(tempdir) / "snapshot-native.bin"
        source.export_snapshot_file(snapshot_path)

        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_001_000)
        target.import_snapshot_file(snapshot_path)

        assert target.node_registry.list_records() == source.node_registry.list_records()
        assert target.reward_attestations.list_bundles() == source.reward_attestations.list_bundles()
        assert target.reward_settlements.list_settlements() == source.reward_settlements.list_settlements()


def test_sync_manager_downloads_only_delta_after_snapshot_import() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        initial_blocks = _mine_chain(source, 6, "CHCminer-source")
        snapshot_path = Path(tempdir) / "snapshot.json"
        source.export_snapshot_file(snapshot_path)

        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_001_000)
        target.import_snapshot_file(snapshot_path)
        additional_blocks = _mine_chain(source, 2, "CHCminer-source")

        result = SyncManager(node=target).synchronize(source)

        assert result.headers_received == 2
        assert result.blocks_fetched == 2
        assert target.chain_tip() is not None
        assert target.chain_tip().block_hash == additional_blocks[-1].block_hash()
        assert target.snapshot_anchor() is not None
        assert target.snapshot_anchor().block_hash == initial_blocks[-1].block_hash()


def test_sync_manager_activates_post_snapshot_delta_incrementally() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        initial_blocks = _mine_chain(source, 4, "CHCminer-source")
        snapshot_path = Path(tempdir) / "snapshot.json"
        source.export_snapshot_file(snapshot_path)

        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_001_000)
        target.import_snapshot_file(snapshot_path)
        additional_blocks = _mine_chain(source, 2, "CHCminer-source")
        manager = SyncManager(node=target)
        manager.ingest_headers(tuple(block.header for block in additional_blocks), peer_id="peer-a")

        first = manager.receive_block(additional_blocks[0])

        assert first.activated_tip == additional_blocks[0].block_hash()
        assert target.chain_tip() is not None
        assert target.chain_tip().block_hash == additional_blocks[0].block_hash()
        assert target.snapshot_anchor() is not None
        assert target.snapshot_anchor().block_hash == initial_blocks[-1].block_hash()


def test_snapshot_anchor_mismatch_is_rejected_before_delta_sync() -> None:
    with TemporaryDirectory() as tempdir:
        trusted = _make_service(Path(tempdir) / "trusted.sqlite3", start_time=1_700_000_000)
        attacker = _make_service(Path(tempdir) / "attacker.sqlite3", start_time=1_700_001_000)
        _mine_chain(trusted, 3, "CHCtrusted")
        _mine_chain(attacker, 3, "CHCattacker")
        snapshot_path = Path(tempdir) / "snapshot.json"
        trusted.export_snapshot_file(snapshot_path)

        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_002_000)
        target.import_snapshot_file(snapshot_path)

        with pytest.raises(ValueError, match="snapshot anchor mismatch"):
            SyncManager(node=target).synchronize(attacker)


def test_snapshot_bootstrap_persists_across_restart_without_replay() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        _mine_chain(source, 5, "CHCminer-source")
        snapshot_path = Path(tempdir) / "snapshot.json"
        source.export_snapshot_file(snapshot_path)

        db_path = Path(tempdir) / "target.sqlite3"
        target = _make_service(db_path, start_time=1_700_001_000)
        target.import_snapshot_file(snapshot_path)

        restarted = _make_service(db_path, start_time=1_700_002_000)

        assert restarted.chain_tip() is not None
        assert restarted.chain_tip().block_hash == source.chain_tip().block_hash
        assert restarted.snapshot_anchor() is not None
        assert restarted.snapshot_anchor().block_hash == source.chain_tip().block_hash


def test_snapshot_import_rejects_anchor_hash_mismatch() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        _mine_chain(source, 2, "CHCminer-source")
        snapshot_path = Path(tempdir) / "snapshot.json"
        _export_snapshot_v1(source, snapshot_path)
        payload = read_snapshot_payload(snapshot_path)
        payload["metadata"]["snapshot_block_hash"] = "11" * 32
        payload["metadata"]["checksum_sha256"] = snapshot_checksum(payload)
        write_snapshot_file(snapshot_path, payload)

        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_001_000)
        with pytest.raises(ValueError, match="snapshot anchor hash"):
            target.import_snapshot_file(snapshot_path)


def test_snapshot_import_rejects_tampered_checksum() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        _mine_chain(source, 2, "CHCminer-source")
        snapshot_path = Path(tempdir) / "snapshot.json"
        _export_snapshot_v1(source, snapshot_path)
        payload = read_snapshot_payload(snapshot_path)
        payload["metadata"]["checksum_sha256"] = "00" * 32
        snapshot_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_001_000)
        with pytest.raises(ValueError, match="snapshot checksum mismatch"):
            target.import_snapshot_file(snapshot_path)


def test_snapshot_import_rejects_divergent_embedded_header_chain() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        _mine_chain(source, 3, "CHCminer-source")
        snapshot_path = Path(tempdir) / "snapshot.json"
        _export_snapshot_v1(source, snapshot_path)
        payload = read_snapshot_payload(snapshot_path)
        payload["headers"][1]["raw_hex"] = payload["headers"][0]["raw_hex"]
        payload["headers"][1]["block_hash"] = payload["headers"][0]["block_hash"]
        payload["metadata"]["checksum_sha256"] = snapshot_checksum(payload)
        write_snapshot_file(snapshot_path, payload)

        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_001_000)
        with pytest.raises(ValueError, match="connected main chain|difficulty|cumulative work"):
            target.import_snapshot_file(snapshot_path)


def test_snapshot_sync_rejects_invalid_post_anchor_block_sequence() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        _mine_chain(source, 4, "CHCminer-source")
        snapshot_path = Path(tempdir) / "snapshot.json"
        source.export_snapshot_file(snapshot_path)
        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_001_000)
        target.import_snapshot_file(snapshot_path)
        next_block = _mine_block(source.build_candidate_block("CHCminer-source").block)
        source.apply_block(next_block)

        class InvalidDeltaPeer:
            def handle_getheaders(self, request, *, limit=2000):
                return source.handle_getheaders(request, limit=limit)

            def get_block_by_hash(self, block_hash: str):
                block = source.get_block_by_hash(block_hash)
                if block is None:
                    return None
                bad_coinbase = replace(
                    block.transactions[0],
                    outputs=tuple(
                        replace(output, recipient="CHCtampered") if index == 0 else output
                        for index, output in enumerate(block.transactions[0].outputs)
                    ),
                )
                return replace(block, transactions=(bad_coinbase,) + block.transactions[1:])

        with pytest.raises(Exception, match="Merkle|coinbase|validation|weight|previous"):
            SyncManager(node=target).synchronize(InvalidDeltaPeer())


def test_signed_snapshot_is_accepted_in_enforce_mode() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        _mine_chain(source, 2, "CHCminer-source")
        snapshot_path = Path(tempdir) / "snapshot.json"
        _export_snapshot_v1(source, snapshot_path)
        payload = read_snapshot_payload(snapshot_path)
        private_key, public_key = _ed25519_keypair()
        write_snapshot_file(snapshot_path, sign_snapshot_payload(payload, private_key=private_key))

        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_001_000)
        imported = target.import_snapshot_file(snapshot_path, trust_mode="enforce", trusted_keys=(public_key,))

        assert imported["trusted_signature_count"] == 1
        assert imported["valid_signature_count"] == 1
        assert target.chain_tip() is not None
        assert target.chain_tip().height == 1


def test_unsigned_snapshot_is_rejected_in_enforce_mode() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        _mine_chain(source, 1, "CHCminer-source")
        snapshot_path = Path(tempdir) / "snapshot.json"
        source.export_snapshot_file(snapshot_path)
        _, public_key = _ed25519_keypair()

        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_001_000)
        with pytest.raises(ValueError, match="at least one signature"):
            target.import_snapshot_file(snapshot_path, trust_mode="enforce", trusted_keys=(public_key,))


def test_invalid_snapshot_signature_is_rejected() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        _mine_chain(source, 2, "CHCminer-source")
        snapshot_path = Path(tempdir) / "snapshot.json"
        _export_snapshot_v1(source, snapshot_path)
        payload = read_snapshot_payload(snapshot_path)
        private_key, public_key = _ed25519_keypair()
        signed = sign_snapshot_payload(payload, private_key=private_key)
        signed["metadata"]["signatures"][0]["signature_hex"] = "00" * 64
        write_snapshot_file(snapshot_path, signed)

        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_001_000)
        with pytest.raises(ValueError, match="signature is invalid"):
            target.import_snapshot_file(snapshot_path, trust_mode="enforce", trusted_keys=(public_key,))


def test_unknown_snapshot_signer_is_rejected_in_enforce_mode() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        _mine_chain(source, 2, "CHCminer-source")
        snapshot_path = Path(tempdir) / "snapshot.json"
        _export_snapshot_v1(source, snapshot_path)
        payload = read_snapshot_payload(snapshot_path)
        private_key, _ = _ed25519_keypair()
        _, trusted_public_key = _ed25519_keypair()
        write_snapshot_file(snapshot_path, sign_snapshot_payload(payload, private_key=private_key))

        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_001_000)
        with pytest.raises(ValueError, match="trusted signer"):
            target.import_snapshot_file(snapshot_path, trust_mode="enforce", trusted_keys=(trusted_public_key,))


def test_tampered_signed_snapshot_is_rejected() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        _mine_chain(source, 2, "CHCminer-source")
        snapshot_path = Path(tempdir) / "snapshot.json"
        _export_snapshot_v1(source, snapshot_path)
        payload = read_snapshot_payload(snapshot_path)
        private_key, public_key = _ed25519_keypair()
        signed = sign_snapshot_payload(payload, private_key=private_key)
        signed["utxos"][0]["recipient"] = "CHCtampered"
        signed["metadata"]["checksum_sha256"] = snapshot_checksum(signed)
        write_snapshot_file(snapshot_path, signed)

        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_001_000)
        with pytest.raises(ValueError, match="signature is invalid"):
            target.import_snapshot_file(snapshot_path, trust_mode="enforce", trusted_keys=(public_key,))


def test_tampered_v2_snapshot_container_is_rejected() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        _mine_chain(source, 2, "CHCminer-source")
        snapshot_path = Path(tempdir) / "snapshot-v2.bin"
        source.export_snapshot_file(snapshot_path)
        raw = bytearray(snapshot_path.read_bytes())
        raw[-1] ^= 0x01
        snapshot_path.write_bytes(bytes(raw))

        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_001_000)
        with pytest.raises(ValueError, match="compressed payload checksum mismatch|payload checksum mismatch|compressed payload is invalid"):
            target.import_snapshot_file(snapshot_path)


def test_snapshot_v1_backward_compatibility_import_is_retained() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        _mine_chain(source, 2, "CHCminer-source")
        snapshot_path = Path(tempdir) / "snapshot-v1.json"
        _export_snapshot_v1(source, snapshot_path)

        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_001_000)
        imported = target.import_snapshot_file(snapshot_path)

        assert imported["format_version"] == 1
        assert target.chain_tip() is not None
        assert target.chain_tip().block_hash == source.chain_tip().block_hash


def test_status_shows_snapshot_trust_metadata_after_bootstrap() -> None:
    with TemporaryDirectory() as tempdir:
        source = _make_service(Path(tempdir) / "source.sqlite3", start_time=1_700_000_000)
        _mine_chain(source, 2, "CHCminer-source")
        snapshot_path = Path(tempdir) / "snapshot.json"
        source.export_snapshot_file(snapshot_path)
        payload = read_snapshot_payload(snapshot_path)
        private_key, public_key = _ed25519_keypair()
        write_snapshot_file(snapshot_path, sign_snapshot_payload(payload, private_key=private_key))

        target = _make_service(Path(tempdir) / "target.sqlite3", start_time=1_700_001_000)
        target.import_snapshot_file(snapshot_path, trust_mode="enforce", trusted_keys=(public_key,))
        status = target.status()

        assert status["bootstrap_mode"] == "snapshot"
        assert status["snapshot_anchor_height"] == 1
        assert status["snapshot_anchor_hash"] == source.chain_tip().block_hash
        assert status["snapshot_trust_mode"] == "enforce"
        assert status["snapshot_signature_verified"] is True
        assert status["accepted_snapshot_signer_pubkeys"] == [public_key.hex()]
        assert status["snapshot_trust_warnings"] == []
        assert status["sync_phase"] == "snapshot_imported"
        assert status["sync"]["phase"] == "snapshot_imported"
