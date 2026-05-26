import json
from urllib.error import HTTPError

import chipcoin.interfaces.seed_client as seed_client_module
from chipcoin.interfaces.seed_client import SeedClient, SeedClientError


def test_seed_client_lists_peers_and_announces() -> None:
    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def read(self) -> bytes:
            return json.dumps(self.payload, sort_keys=True).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    requests: list[tuple[str, str, bytes | None]] = []

    def fake_urlopen(request, timeout: float):
        requests.append((request.method, request.full_url, request.data))
        assert timeout == 5.0
        if request.full_url.endswith("/v1/health"):
            return FakeResponse({"status": "ok"})
        if "/v1/peers?" in request.full_url:
            return FakeResponse(
                {
                    "network": "mainnet",
                    "peers": [
                        {
                            "host": "127.0.0.1",
                            "port": 8333,
                            "network": "mainnet",
                            "node_id": "node-1",
                            "version": "0.1.0",
                            "last_seen": 100,
                        }
                    ],
                }
            )
        return FakeResponse(
            {
                "accepted": True,
                "peer": {
                    "host": "127.0.0.1",
                    "port": 8333,
                    "network": "mainnet",
                    "node_id": "node-1",
                    "version": "0.1.0",
                    "last_seen": 101,
                },
            }
        )

    original_urlopen = seed_client_module.urlopen
    seed_client_module.urlopen = fake_urlopen
    try:
        client = SeedClient("http://seed.example")
        assert client.health()["status"] == "ok"
        peers = client.list_peers("mainnet")
        announced = client.announce(
            host="127.0.0.1",
            port=8333,
            network="mainnet",
            node_id="node-1",
            version="0.1.0",
            last_seen=101,
        )
    finally:
        seed_client_module.urlopen = original_urlopen

    assert peers[0].node_id == "node-1"
    assert announced.last_seen == 101
    assert requests[0][0] == "GET"
    assert requests[1][0] == "GET"
    assert requests[2][0] == "POST"


def test_seed_client_wraps_http_error_body() -> None:
    class FakeErrorBody:
        def read(self) -> bytes:
            return json.dumps({"error": {"code": "invalid_peer", "message": "peer is not reachable"}}).encode("utf-8")

        def close(self) -> None:
            return None

    def fake_urlopen(request, timeout: float):
        raise HTTPError(request.full_url, 400, "Bad Request", hdrs=None, fp=FakeErrorBody())

    original_urlopen = seed_client_module.urlopen
    seed_client_module.urlopen = fake_urlopen
    try:
        client = SeedClient("http://seed.example")
        try:
            client.announce(
                host="node.example.com",
                port=28444,
                network="testnet",
                node_id="",
                version="0.1.1",
            )
        except SeedClientError as exc:
            assert str(exc) == "HTTP 400: invalid_peer: peer is not reachable"
        else:
            raise AssertionError("Expected SeedClientError")
    finally:
        seed_client_module.urlopen = original_urlopen
