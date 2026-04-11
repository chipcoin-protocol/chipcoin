from bootstrap_seed.models import PeerRecord
from bootstrap_seed.store import InMemoryPeerStore, SQLitePeerStore
import sqlite3
from tempfile import TemporaryDirectory


def test_store_keeps_network_scoped_records() -> None:
    store = InMemoryPeerStore(peer_expiry_seconds=30)
    store.announce(
        PeerRecord(
            host="127.0.0.1",
            p2p_port=8333,
            network="mainnet",
            first_seen=100,
            last_seen=100,
            source="announce",
            software_version="0.1.0",
            node_id="node-1",
        )
    )
    store.announce(
        PeerRecord(
            host="127.0.0.1",
            p2p_port=18333,
            network="testnet",
            first_seen=101,
            last_seen=101,
            source="announce",
            software_version="0.1.0",
            node_id="node-2",
        )
    )

    assert [peer.node_id for peer in store.list_peers("mainnet", now=101)] == ["node-1"]
    assert [peer.node_id for peer in store.list_peers("testnet", now=101)] == ["node-2"]


def test_store_prunes_expired_records() -> None:
    store = InMemoryPeerStore(peer_expiry_seconds=10)
    store.announce(
        PeerRecord(
            host="127.0.0.1",
            p2p_port=8333,
            network="mainnet",
            first_seen=100,
            last_seen=100,
            source="announce",
            software_version="0.1.0",
            node_id="node-1",
        )
    )

    removed = store.prune(111)

    assert removed == 1
    assert store.list_peers("mainnet", now=111) == []


def test_sqlite_store_persists_records_across_restart() -> None:
    with TemporaryDirectory() as tempdir:
        database_path = f"{tempdir}/bootstrap-seed.sqlite3"
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        store = SQLitePeerStore(connection, peer_expiry_seconds=30)
        store.announce(
            PeerRecord(
                host="seed.example",
                p2p_port=18444,
                network="devnet",
                first_seen=100,
                last_seen=101,
                source="announce",
                software_version="chipcoin-node/0.1",
                advertised_height=42,
            )
        )
        connection.close()

        reopened = sqlite3.connect(database_path)
        reopened.row_factory = sqlite3.Row
        store = SQLitePeerStore(reopened, peer_expiry_seconds=30)
        peers = store.list_peers("devnet", now=101)

        assert len(peers) == 1
        assert peers[0].host == "seed.example"
        assert peers[0].advertised_height == 42


def test_store_caps_oldest_records_per_network() -> None:
    store = InMemoryPeerStore(peer_expiry_seconds=60, max_peers_per_network=2)
    for index in range(3):
        store.announce(
            PeerRecord(
                host=f"seed-{index}.example",
                p2p_port=18444,
                network="devnet",
                first_seen=100 + index,
                last_seen=100 + index,
                source="announce",
            )
        )

    peers = store.list_peers("devnet", now=103)

    assert [peer.host for peer in peers] == ["seed-2.example", "seed-1.example"]
