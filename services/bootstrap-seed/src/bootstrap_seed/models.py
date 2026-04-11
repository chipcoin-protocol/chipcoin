"""Data models for peer discovery records."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PeerRecord:
    """Bootstrap service representation of one live peer candidate."""

    host: str
    p2p_port: int
    network: str
    first_seen: int
    last_seen: int
    source: str
    software_version: str | None = None
    advertised_height: int | None = None
    node_id: str | None = None

    def to_dict(self) -> dict[str, int | str | None]:
        """Return a JSON-serializable mapping."""

        return {
            "host": self.host,
            "p2p_port": self.p2p_port,
            "network": self.network,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "source": self.source,
            "software_version": self.software_version,
            "advertised_height": self.advertised_height,
            "node_id": self.node_id,
        }
