"""Minimal client for the optional bootstrap seed service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class SeedPeer:
    """Peer information returned by the bootstrap seed service."""

    host: str
    port: int
    network: str
    node_id: str
    version: str
    last_seen: int


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
        return [SeedPeer(**peer) for peer in payload.get("peers", [])]

    def announce(self, *, host: str, port: int, network: str, node_id: str, version: str, last_seen: int | None = None) -> SeedPeer:
        """Announce the local node to the bootstrap service."""

        body = {
            "host": host,
            "port": port,
            "network": network,
            "node_id": node_id,
            "version": version,
        }
        if last_seen is not None:
            body["last_seen"] = last_seen
        payload = self._request_json("POST", "/v1/announce", body=body)
        return SeedPeer(**payload["peer"])

    def _request_json(self, method: str, path: str, *, body: dict | None = None) -> dict:
        """Send a request and decode the JSON response."""

        request_body = None if body is None else json.dumps(body, sort_keys=True).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            method=method,
            data=request_body,
            headers={"Content-Type": "application/json"} if request_body is not None else {},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise SeedClientError(f"HTTP {exc.code}: {_extract_error_message(raw)}") from exc
        except URLError as exc:
            raise SeedClientError(f"connection failed: {exc.reason}") from exc


class SeedClientError(RuntimeError):
    """Raised when the bootstrap seed service rejects or fails a request."""


def _extract_error_message(raw: str) -> str:
    """Return a compact error message from a seed service response body."""

    text = raw.strip()
    if not text:
        return "empty response body"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text[:300]
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            code = error.get("code")
            if message and code:
                return f"{code}: {message}"
            if message:
                return str(message)
        message = payload.get("message")
        if message:
            return str(message)
    return text[:300]
