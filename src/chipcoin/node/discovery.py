"""Peer discovery flows using local records and optional bootstrap seeds."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

from ..interfaces.seed_client import SeedClient, SeedPeer


@dataclass(frozen=True)
class BootstrapDiscoveryConfig:
    """Configuration for optional bootstrap seed integration."""

    urls: tuple[str, ...] = ()
    network: str = "mainnet"
    peer_limit: int = 4
    refresh_interval_seconds: float = 300.0
    announce_enabled: bool = True
    public_host: str | None = None
    public_p2p_port: int | None = None
    software_version: str = "chipcoin-node/0.1"


class DiscoveryService:
    """Coordinate optional peer discovery across one or more bootstrap seeds."""

    def __init__(
        self,
        config: BootstrapDiscoveryConfig,
        *,
        logger: logging.Logger | None = None,
        client_factory=SeedClient,
    ) -> None:
        self.config = config
        self.logger = logger or logging.getLogger("chipcoin.node.discovery")
        self.client_factory = client_factory

    def discover(self) -> list[SeedPeer]:
        """Return candidate peer endpoints from configured bootstrap URLs."""

        merged: dict[tuple[str, int], SeedPeer] = {}
        for base_url in self.config.urls:
            try:
                peers = self.client_factory(base_url).list_peers(self.config.network)
            except Exception as exc:
                self.logger.warning("bootstrap peer fetch failed url=%s error=%s", base_url, exc)
                continue
            for peer in peers:
                key = (peer.host, peer.p2p_port)
                if key in merged:
                    continue
                merged[key] = peer
                if len(merged) >= self.config.peer_limit:
                    return list(merged.values())
        return list(merged.values())

    def announce(
        self,
        *,
        host: str,
        p2p_port: int,
        node_id: str | None = None,
        height: int | None = None,
        now: int | None = None,
    ) -> None:
        """Announce one node endpoint to every configured bootstrap URL."""

        if not self.config.announce_enabled:
            return
        for base_url in self.config.urls:
            try:
                self.client_factory(base_url).announce(
                    host=host,
                    p2p_port=p2p_port,
                    network=self.config.network,
                    source="announce",
                    software_version=self.config.software_version,
                    advertised_height=height,
                    node_id=node_id,
                    last_seen=now,
                )
            except Exception as exc:
                self.logger.warning("bootstrap announce failed url=%s error=%s", base_url, exc)


def parse_bootstrap_urls(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    """Parse and validate one or more bootstrap discovery URLs."""

    if not values:
        return ()
    parsed_urls: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for chunk in str(raw).replace("\n", ",").split(","):
            url = chunk.strip()
            if not url:
                continue
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"invalid bootstrap URL: {url}")
            normalized = url.rstrip("/")
            if normalized in seen:
                continue
            seen.add(normalized)
            parsed_urls.append(normalized)
    return tuple(parsed_urls)
