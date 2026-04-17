from dataclasses import replace
from pathlib import Path

from chipcoin.consensus.models import Block
from chipcoin.consensus.nodes import NodeRecord
from chipcoin.consensus.pow import verify_proof_of_work
from chipcoin.node.peers import PeerInfo
from chipcoin.node.service import NodeService
from chipcoin.rewards.config import RewardObserverConfig
from chipcoin.rewards.observer import RewardObserver
from chipcoin.rewards.store import RewardObserverStore
from tests.helpers import wallet_key


def _config(storage_path: Path, *, warmup_epochs: int = 1) -> RewardObserverConfig:
    return RewardObserverConfig(
        network="devnet",
        storage_path=str(storage_path),
        node_data_path=None,
        epoch_length_blocks=100,
        warmup_epochs=warmup_epochs,
        required_observations_per_epoch=1,
        min_successful_observations=1,
        per_public_ipv4_cap=2,
        per_subnet_v4_prefix=24,
        per_subnet_cap=3,
        fingerprint_cap=None,
        observation_timeout_seconds=5.0,
        observation_retry_count=1,
    )


def _mine_block(block: Block) -> Block:
    for nonce in range(2_000_000):
        header = replace(block.header, nonce=nonce)
        if verify_proof_of_work(header):
            return replace(block, header=header)
    raise AssertionError("Expected to find a valid nonce for the easy target.")


def test_observer_imports_real_registry_and_peer_state(tmp_path: Path) -> None:
    service = NodeService.open_sqlite(tmp_path / "node.sqlite3", network="devnet", time_provider=lambda: 1_700_000_000)
    service.node_registry.upsert(
        NodeRecord(
            node_id="node-a",
            payout_address=wallet_key(0).address,
            owner_pubkey=wallet_key(0).public_key,
            registered_height=0,
            last_renewed_height=0,
        )
    )
    service.node_registry.upsert(
        NodeRecord(
            node_id="node-b",
            payout_address=wallet_key(1).address,
            owner_pubkey=wallet_key(1).public_key,
            registered_height=0,
            last_renewed_height=0,
        )
    )
    mined = _mine_block(service.build_candidate_block("CHCminer").block)
    service.apply_block(mined)
    service.peerbook.add(
        PeerInfo(
            host="203.0.113.10",
            port=18444,
            network="devnet",
            node_id="node-a",
            handshake_complete=True,
            ban_until=None,
        )
    )

    store = RewardObserverStore(tmp_path / "observer.sqlite3")
    observer = RewardObserver(config=_config(tmp_path / "observer.sqlite3"), store=store)
    observer.initialize()

    observations = observer.ingest_node_service_snapshot(service, observed_at=1_700_000_123)
    by_node_id = {observation.node_id: observation for observation in observations}

    assert set(by_node_id) == {"node-a", "node-b"}
    assert by_node_id["node-a"].registration_status == "registered"
    assert by_node_id["node-a"].registration_source == "node_registry"
    assert by_node_id["node-a"].endpoint_source == "peer_state"
    assert by_node_id["node-a"].outcome == "success"
    assert by_node_id["node-a"].public_ip == "203.0.113.10"
    assert by_node_id["node-b"].registration_status == "registered"
    assert by_node_id["node-b"].endpoint_source == "provisional"
    assert by_node_id["node-b"].outcome == "unchecked"
    assert by_node_id["node-b"].reason_code is None


def test_observer_derives_warmup_from_registration_age() -> None:
    observer = RewardObserver(
        config=_config(Path(":memory:"), warmup_epochs=1),
        store=RewardObserverStore(":memory:"),
    )
    row = {
        "registered_at_height": 0,
        "active": True,
        "epoch_status": "current",
    }

    assert observer._derive_warmup_status(row, current_height=0) is False
    assert observer._derive_warmup_status(row, current_height=100) is True


def test_recompute_epoch_marks_unchecked_imports_as_insufficient_observation(tmp_path: Path) -> None:
    service = NodeService.open_sqlite(tmp_path / "node.sqlite3", network="devnet", time_provider=lambda: 1_700_000_000)
    service.node_registry.upsert(
        NodeRecord(
            node_id="node-a",
            payout_address=wallet_key(0).address,
            owner_pubkey=wallet_key(0).public_key,
            registered_height=0,
            last_renewed_height=0,
        )
    )
    mined = _mine_block(service.build_candidate_block("CHCminer").block)
    service.apply_block(mined)

    store = RewardObserverStore(tmp_path / "observer.sqlite3")
    observer = RewardObserver(config=_config(tmp_path / "observer.sqlite3", warmup_epochs=0), store=store)
    observer.initialize()
    observations = observer.ingest_node_service_snapshot(service, observed_at=1_700_000_123)
    summaries = observer.recompute_epoch(observations[0].epoch_index)

    assert len(summaries) == 1
    assert summaries[0].checked_observation_count == 0
    assert summaries[0].final_eligible is False
    assert summaries[0].rejection_reason == "insufficient_observation"
