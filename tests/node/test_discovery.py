from pathlib import Path
from tempfile import TemporaryDirectory

from chipcoin.node.discovery import BootstrapDiscoveryConfig, DiscoveryService, parse_bootstrap_urls
from chipcoin.node.runtime import NodeRuntime
from chipcoin.node.service import NodeService


def _make_service(database_path: Path) -> NodeService:
    timestamps = iter(range(1_700_000_000, 1_700_000_100))
    return NodeService.open_sqlite(database_path, network="devnet", time_provider=lambda: next(timestamps))


def test_parse_bootstrap_urls_deduplicates_and_splits_commas() -> None:
    urls = parse_bootstrap_urls(
        [
            "https://seed-a.example, https://seed-b.example/",
            "https://seed-a.example/",
        ]
    )

    assert urls == ("https://seed-a.example", "https://seed-b.example")


def test_discovery_service_merges_multiple_sources_with_failover() -> None:
    class FakeClient:
        def __init__(self, base_url: str) -> None:
            self.base_url = base_url

        def list_peers(self, network: str):
            assert network == "devnet"
            if self.base_url.endswith("seed-a.example"):
                raise OSError("unreachable")
            if self.base_url.endswith("seed-b.example"):
                return [
                    _peer("198.51.100.10", 18444),
                    _peer("198.51.100.11", 18444),
                ]
            return [
                _peer("198.51.100.11", 18444),
                _peer("198.51.100.12", 18444),
            ]

    discovery = DiscoveryService(
        BootstrapDiscoveryConfig(
            urls=("https://seed-a.example", "https://seed-b.example", "https://seed-c.example"),
            network="devnet",
            peer_limit=4,
        ),
        client_factory=FakeClient,
    )

    peers = discovery.discover()

    assert [(peer.host, peer.p2p_port) for peer in peers] == [
        ("198.51.100.10", 18444),
        ("198.51.100.11", 18444),
        ("198.51.100.12", 18444),
    ]


def test_runtime_bootstrap_cycle_is_nonfatal_when_all_services_fail() -> None:
    class FakeDiscovery:
        def discover(self):
            return []

        def announce(self, **kwargs):
            raise AssertionError("announce should not run without public host")

    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "chipcoin-devnet.sqlite3")
        runtime = NodeRuntime(
            service=service,
            listen_host="0.0.0.0",
            listen_port=18444,
            bootstrap_urls=("https://seed-a.example",),
        )
        runtime._bootstrap_discovery = FakeDiscovery()

        runtime._bootstrap_discovery_cycle()

        assert service.list_peers() == []


def test_runtime_bootstrap_discovery_excludes_self_public_endpoint() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "chipcoin-devnet.sqlite3")
        runtime = NodeRuntime(
            service=service,
            listen_host="0.0.0.0",
            listen_port=18444,
            bootstrap_urls=("https://seed.example",),
            bootstrap_public_host="seed.node.example",
            bootstrap_public_p2p_port=18444,
        )

        assert runtime._add_bootstrap_peer(_peer("seed.node.example", 18444)) is False
        assert service.list_peers() == []


def test_runtime_bootstrap_discovery_adds_seed_peer() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "chipcoin-devnet.sqlite3")
        runtime = NodeRuntime(
            service=service,
            listen_host="0.0.0.0",
            listen_port=18444,
            bootstrap_urls=("https://seed.example",),
        )

        accepted = runtime._add_bootstrap_peer(_peer("93.184.216.34", 18444))

        assert accepted is True
        peers = service.list_peers()
        assert len(peers) == 1
        assert peers[0].host == "93.184.216.34"
        assert peers[0].source == "seed"


def _peer(host: str, port: int):
    from chipcoin.interfaces.seed_client import SeedPeer

    return SeedPeer(
        host=host,
        p2p_port=port,
        network="devnet",
        first_seen=100,
        last_seen=101,
        source="announce",
        software_version="chipcoin-node/0.1",
        advertised_height=42,
    )
