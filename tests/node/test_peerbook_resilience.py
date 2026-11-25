"""Regression cases for malformed legacy and in-memory peerbook entries."""

from chipcoin.node.peers import PeerInfo, PeerManager
from chipcoin.node.service import NodeService
from chipcoin.node.runtime import NodeRuntime
import pytest


def test_network_filtered_peerbook_survives_malformed_endpoint() -> None:
    manager = PeerManager()
    valid = PeerInfo(host="peer.example", port=8333, network="mainnet", ban_until=123)
    manager.add(valid)
    manager.add(PeerInfo(host=None, port=8333, network="mainnet"))  # type: ignore[arg-type]
    manager.add(PeerInfo(host="unknown.example", port=8333, network=None))  # type: ignore[arg-type]

    assert manager.list_all(network="mainnet") == [valid]
    assert manager.list_all(network="testnet") == []
    assert manager.list_all() == [valid]


def test_quarantined_endpoint_still_enforces_existing_host_ban() -> None:
    manager = PeerManager()
    manager.add(PeerInfo(host="banned.example", port=None, network="mainnet", ban_until=200))  # type: ignore[arg-type]
    assert manager.list_all(network="mainnet") == []
    assert manager.active_host_ban(network="mainnet", host="banned.example", now=100) == 200
    assert manager.active_host_ban(network="testnet", host="banned.example", now=100) is None


def test_peerbook_snapshot_handles_concurrent_additions() -> None:
    from concurrent.futures import ThreadPoolExecutor

    manager = PeerManager()

    def write() -> None:
        for port in range(10000, 10200):
            manager.add(PeerInfo(host="peer.example", port=port, network="mainnet"))

    def read() -> None:
        for _ in range(200):
            peers = manager.list_all(network="mainnet")
            assert all(peer.network == "mainnet" for peer in peers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(write)
        second = pool.submit(read)
        first.result()
        second.result()


def test_legacy_peer_with_null_port_is_quarantined_without_migration(tmp_path) -> None:
    import sqlite3

    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE peers (host TEXT, port INTEGER, network TEXT, "
            "PRIMARY KEY(host, port, network))"
        )
        connection.execute("INSERT INTO peers(host, port, network) VALUES ('bad.example', NULL, 'mainnet')")
        connection.execute("INSERT INTO peers(host, port, network) VALUES (NULL, 8333, 'mainnet')")
        connection.execute("INSERT INTO peers(host, port, network) VALUES ('good.example', 8333, 'mainnet')")
        connection.execute("INSERT INTO peers(host, port, network) VALUES ('other.example', 18333, 'testnet')")
        connection.execute("INSERT INTO peers(host, port, network) VALUES ('unknown.example', 8333, NULL)")
    service = NodeService.open_sqlite(path, network="mainnet")
    peers = service.list_peers()
    assert [(peer.host, peer.port) for peer in peers] == [("good.example", 8333)]
    assert service.status(include_supply=False)["peer_count"] == 1
    assert service.peer_summary()["peer_count"] == 1
    assert service.peer_repository.connection.execute("SELECT COUNT(*) FROM peers").fetchone()[0] == 5
    service.peer_repository.connection.execute(
        "UPDATE peers SET ban_until = ? WHERE host = 'bad.example'", (10**10,)
    )
    assert NodeRuntime(service=service)._ban_state_for_peer("bad.example", 8333) == (True, 10**10)


def test_new_malformed_peer_cannot_enter_memory_or_storage(tmp_path) -> None:
    service = NodeService.open_sqlite(tmp_path / "node.sqlite3", network="mainnet")
    with pytest.raises(ValueError, match="Peer host or port"):
        service.add_peer(None, 8333)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Peer host or port"):
        service.record_peer_observation(host="peer.example", port=None)  # type: ignore[arg-type]
    assert service.list_peers() == []
    assert service.peer_repository.connection.execute("SELECT COUNT(*) FROM peers").fetchone()[0] == 0
