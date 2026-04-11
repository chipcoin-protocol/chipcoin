"""Minimal client for the optional bootstrap seed service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class SeedPeer:
    """Peer information returned by the bootstrap seed service."""

    host: str
    p2p_port: int
    network: str
    first_seen: int
    last_seen: int
    source: str
    software_version: str | None = None
    advertised_height: int | None = None
    node_id: str | None = None

    @property
    def port(self) -> int:
        """Compatibility alias for older call sites."""

        return self.p2p_port


class SeedClient:
    """HTTP client for the optional bootstrap seed service."""

    def __init__(self, base_url: str, *, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict[str, str]:
        """Return service health information."""

        return self._request_json("GET", "/v1/health")

    def list_peers(self, network: str) -> list[SeedPeer]:
        """Fetch peer candidates for a network."""

        payload = self._request_json("GET", f"/v1/peers?{urlencode({'network': network})}")
        return [_decode_seed_peer(peer) for peer in payload.get("peers", [])]

    def announce(
        self,
        *,
        host: str,
        p2p_port: int,
        network: str,
        source: str = "announce",
        software_version: str | None = None,
        advertised_height: int | None = None,
        node_id: str | None = None,
        first_seen: int | None = None,
        last_seen: int | None = None,
    ) -> SeedPeer:
        """Announce the local node to the bootstrap service."""

        body = {
            "host": host,
            "p2p_port": p2p_port,
            "network": network,
            "source": source,
        }
        if software_version is not None:
            body["software_version"] = software_version
        if advertised_height is not None:
            body["advertised_height"] = advertised_height
        if node_id is not None:
            body["node_id"] = node_id
        if first_seen is not None:
            body["first_seen"] = first_seen
        if last_seen is not None:
            body["last_seen"] = last_seen
        payload = self._request_json("POST", "/v1/announce", body=body)
        return _decode_seed_peer(payload["peer"])

    def _request_json(self, method: str, path: str, *, body: dict | None = None) -> dict:
        """Send a request and decode the JSON response."""

        request_body = None if body is None else json.dumps(body, sort_keys=True).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            method=method,
            data=request_body,
            headers={"Content-Type": "application/json"} if request_body is not None else {},
        )
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


def _decode_seed_peer(payload: dict) -> SeedPeer:
    """Decode one peer payload from the bootstrap seed service."""

    return SeedPeer(
        host=str(payload["host"]),
        p2p_port=int(payload.get("p2p_port", payload.get("port"))),
        network=str(payload["network"]),
        first_seen=int(payload.get("first_seen", payload.get("last_seen", 0))),
        last_seen=int(payload["last_seen"]),
        source=str(payload.get("source", "seed")),
        software_version=None if payload.get("software_version", payload.get("version")) in {None, ""} else str(payload.get("software_version", payload.get("version"))),
        advertised_height=None if payload.get("advertised_height") is None else int(payload["advertised_height"]),
        node_id=None if payload.get("node_id") in {None, ""} else str(payload["node_id"]),
    )
