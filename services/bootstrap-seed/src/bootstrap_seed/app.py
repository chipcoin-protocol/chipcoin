"""Bootstrap seed service HTTP entrypoint."""

from __future__ import annotations

import ipaddress
import json
import re
import sqlite3
from pathlib import Path
from wsgiref.simple_server import make_server

from .config import ServiceConfig
from .models import PeerRecord
from .store import PeerStore, SQLitePeerStore


_HOSTNAME_PATTERN = re.compile(r"^[A-Za-z0-9.-]+$")


class BootstrapSeedApp:
    """Minimal WSGI app exposing health and peer bootstrap endpoints."""

    def __init__(self, *, store: PeerStore, now_provider, config: ServiceConfig) -> None:
        self.store = store
        self.now_provider = now_provider
        self.config = config

    def __call__(self, environ, start_response):
        """Serve a single WSGI request."""

        method = environ["REQUEST_METHOD"]
        path = environ.get("PATH_INFO", "")

        if method == "GET" and path == "/v1/health":
            return self._json_response(start_response, 200, {"status": "ok"})

        if method == "GET" and path == "/v1/peers":
            network = self._query_params(environ).get("network", "")
            if not network:
                return self._json_response(start_response, 400, {"error": "network query parameter is required"})
            if not _is_valid_network(network):
                return self._json_response(start_response, 400, {"error": "invalid network"})
            raw_limit = self._query_params(environ).get("limit")
            try:
                requested_limit = self.config.max_peers_response if not raw_limit else int(raw_limit)
            except ValueError:
                return self._json_response(start_response, 400, {"error": "limit must be an integer"})
            limit = max(1, min(requested_limit, self.config.max_peers_response))
            peers = [record.to_dict() for record in self.store.list_peers(network, now=self.now_provider(), limit=limit)]
            return self._json_response(start_response, 200, {"network": network, "peers": peers})

        if method == "POST" and path == "/v1/announce":
            try:
                payload = self._read_json(environ)
                now = self.now_provider()
                host = str(payload["host"]).strip()
                p2p_port = int(payload.get("p2p_port", payload.get("port")))
                network = str(payload["network"]).strip()
                source = str(payload.get("source", "announce")).strip() or "announce"
                software_version = payload.get("software_version", payload.get("version"))
                advertised_height = payload.get("advertised_height")
                record = PeerRecord(
                    host=host,
                    p2p_port=p2p_port,
                    network=network,
                    first_seen=int(payload.get("first_seen", now)),
                    last_seen=int(payload.get("last_seen", now)),
                    source=source,
                    software_version=None if software_version in {None, ""} else str(software_version),
                    advertised_height=None if advertised_height in {None, ""} else int(advertised_height),
                    node_id=None if payload.get("node_id") in {None, ""} else str(payload["node_id"]),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                return self._json_response(start_response, 400, {"error": f"invalid announce payload: {exc}"})
            validation_error = self._validate_record(record)
            if validation_error is not None:
                return self._json_response(start_response, 400, {"error": validation_error})
            stored = self.store.announce(record)
            self.store.prune(self.now_provider())
            return self._json_response(start_response, 200, {"accepted": True, "peer": stored.to_dict()})

        return self._json_response(start_response, 404, {"error": "not found"})

    def _read_json(self, environ) -> dict:
        """Read and decode a JSON body from the request."""

        content_length = int(environ.get("CONTENT_LENGTH") or "0")
        body = environ["wsgi.input"].read(content_length)
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))

    def _query_params(self, environ) -> dict[str, str]:
        """Parse the WSGI query string into a flat mapping."""

        query_string = environ.get("QUERY_STRING", "")
        result: dict[str, str] = {}
        for chunk in query_string.split("&"):
            if not chunk:
                continue
            key, _, value = chunk.partition("=")
            result[key] = value
        return result

    def _json_response(self, start_response, status_code: int, payload: dict):
        """Serialize a JSON response body."""

        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        status_text = {
            200: "200 OK",
            400: "400 Bad Request",
            404: "404 Not Found",
        }[status_code]
        start_response(
            status_text,
            [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

    def _validate_record(self, record: PeerRecord) -> str | None:
        """Return one validation error string when the peer record is not acceptable."""

        if not _is_valid_network(record.network):
            return "invalid network"
        if record.p2p_port <= 0 or record.p2p_port > 65535:
            return "invalid p2p_port"
        if record.first_seen <= 0 or record.last_seen <= 0 or record.last_seen < record.first_seen:
            return "invalid peer timestamps"
        if not _is_valid_host(record.host):
            return "invalid host"
        if not self.config.allow_private_addresses and not _is_publicly_reachable_host(record.host):
            return "host must be public unless BOOTSTRAP_ALLOW_PRIVATE_ADDRESSES=true"
        if record.advertised_height is not None and record.advertised_height < 0:
            return "invalid advertised_height"
        return None


def create_app(*, config: ServiceConfig | None = None, now_provider=None) -> BootstrapSeedApp:
    """Create the bootstrap seed WSGI app."""

    service_config = config or ServiceConfig.from_env()
    clock = now_provider or (lambda: 0)
    database_path = Path(service_config.database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, check_same_thread=False, timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    store = SQLitePeerStore(
        connection,
        peer_expiry_seconds=service_config.peer_expiry_seconds,
        max_peers_per_network=service_config.max_peers_per_network,
    )
    return BootstrapSeedApp(store=store, now_provider=clock, config=service_config)


def main() -> int:
    """Run the bootstrap seed service."""

    config = ServiceConfig.from_env()
    app = create_app(config=config, now_provider=_unix_time)
    with make_server(config.bind_host, config.bind_port, app) as server:
        server.serve_forever()
    return 0


def _unix_time() -> int:
    """Return the current UNIX timestamp."""

    import time

    return int(time.time())


if __name__ == "__main__":
    raise SystemExit(main())


def _is_valid_network(network: str) -> bool:
    """Return whether one network name is syntactically acceptable."""

    return bool(network) and len(network) <= 32 and network.replace("-", "").isalnum()


def _is_valid_host(host: str) -> bool:
    """Return whether one peer host is syntactically valid."""

    if not host or len(host) > 253 or any(character.isspace() for character in host):
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if host.lower() == "localhost" or host.endswith(".local"):
            return False
        if not _HOSTNAME_PATTERN.match(host):
            return False
        labels = host.split(".")
        if any(not label or len(label) > 63 for label in labels):
            return False
        for label in labels:
            if label.startswith("-") or label.endswith("-"):
                return False
        return True
    return True


def _is_publicly_reachable_host(host: str) -> bool:
    """Return whether one host string is acceptable for public bootstrap discovery."""

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        lowered = host.lower()
        if lowered == "localhost" or lowered.endswith(".local"):
            return False
        return True
    return address.is_global
