from io import BytesIO

from bootstrap_seed.app import BootstrapSeedApp
from bootstrap_seed.models import PeerRecord
from bootstrap_seed.store import InMemoryPeerStore
from bootstrap_seed.config import ServiceConfig


def test_health_endpoint_returns_ok() -> None:
    app = BootstrapSeedApp(
        store=InMemoryPeerStore(peer_expiry_seconds=60),
        now_provider=lambda: 100,
        config=ServiceConfig(),
    )

    status, headers, body = _call_wsgi(app, method="GET", path="/v1/health")

    assert status == "200 OK"
    assert headers["Content-Type"] == "application/json"
    assert body["status"] == "ok"


def test_announce_and_list_peers_roundtrip() -> None:
    app = BootstrapSeedApp(
        store=InMemoryPeerStore(peer_expiry_seconds=60),
        now_provider=lambda: 100,
        config=ServiceConfig(),
    )

    announce_status, _, announce_body = _call_wsgi(
        app,
        method="POST",
        path="/v1/announce",
        body={
            "host": "93.184.216.34",
            "p2p_port": 8333,
            "network": "mainnet",
            "first_seen": 100,
            "source": "announce",
            "software_version": "0.1.0",
        },
    )
    list_status, _, list_body = _call_wsgi(app, method="GET", path="/v1/peers", query="network=mainnet")

    assert announce_status == "200 OK"
    assert announce_body["accepted"] is True
    assert list_status == "200 OK"
    assert len(list_body["peers"]) == 1
    assert list_body["peers"][0]["p2p_port"] == 8333


def test_peers_expire_after_timeout() -> None:
    clock = {"now": 100}
    app = BootstrapSeedApp(
        store=InMemoryPeerStore(peer_expiry_seconds=10),
        now_provider=lambda: clock["now"],
        config=ServiceConfig(peer_expiry_seconds=10),
    )
    _call_wsgi(
        app,
        method="POST",
        path="/v1/announce",
        body={
            "host": "93.184.216.34",
            "p2p_port": 8333,
            "network": "mainnet",
            "first_seen": 100,
            "source": "announce",
            "software_version": "0.1.0",
        },
    )

    clock["now"] = 111
    _, _, body = _call_wsgi(app, method="GET", path="/v1/peers", query="network=mainnet")

    assert body["peers"] == []


def test_announce_rejects_private_addresses_by_default() -> None:
    app = BootstrapSeedApp(
        store=InMemoryPeerStore(peer_expiry_seconds=60),
        now_provider=lambda: 100,
        config=ServiceConfig(),
    )

    status, _, body = _call_wsgi(
        app,
        method="POST",
        path="/v1/announce",
        body={
            "host": "127.0.0.1",
            "p2p_port": 18444,
            "network": "devnet",
            "first_seen": 100,
            "source": "announce",
        },
    )

    assert status == "400 Bad Request"
    assert "public" in body["error"]


def test_peers_endpoint_caps_limit() -> None:
    app = BootstrapSeedApp(
        store=InMemoryPeerStore(peer_expiry_seconds=60),
        now_provider=lambda: 100,
        config=ServiceConfig(max_peers_response=1, allow_private_addresses=True),
    )
    for index in range(2):
        _call_wsgi(
            app,
            method="POST",
            path="/v1/announce",
            body={
                "host": f"10.0.0.{index + 1}",
                "p2p_port": 18444,
                "network": "devnet",
                "first_seen": 100 + index,
                "last_seen": 100 + index,
                "source": "announce",
            },
        )

    status, _, body = _call_wsgi(app, method="GET", path="/v1/peers", query="network=devnet&limit=99")

    assert status == "200 OK"
    assert len(body["peers"]) == 1


def _call_wsgi(app, *, method: str, path: str, query: str = "", body: dict | None = None):
    import json

    encoded_body = b"" if body is None else json.dumps(body, sort_keys=True).encode("utf-8")
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "CONTENT_LENGTH": str(len(encoded_body)),
        "wsgi.input": BytesIO(encoded_body),
    }
    captured: dict[str, object] = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    chunks = app(environ, start_response)
    payload = json.loads(b"".join(chunks).decode("utf-8"))
    return captured["status"], captured["headers"], payload
