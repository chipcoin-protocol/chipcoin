"""Bootstrap seed service configuration stubs."""

from __future__ import annotations

from dataclasses import dataclass
import os


def _parse_bool(raw: str) -> bool:
    """Parse one environment boolean value."""

    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ServiceConfig:
    """Configuration for the bootstrap seed service."""

    bind_host: str = "0.0.0.0"
    bind_port: int = 8080
    peer_expiry_seconds: int = 300
    database_path: str = "/data/bootstrap-seed.sqlite3"
    max_peers_per_network: int = 1024
    max_peers_response: int = 64
    allow_private_addresses: bool = False

    @classmethod
    def from_env(cls) -> "ServiceConfig":
        """Build service configuration from environment variables."""

        return cls(
            bind_host=os.getenv("BOOTSTRAP_BIND_HOST", "0.0.0.0"),
            bind_port=int(os.getenv("BOOTSTRAP_BIND_PORT", "8080")),
            peer_expiry_seconds=int(os.getenv("BOOTSTRAP_PEER_EXPIRY_SECONDS", "300")),
            database_path=os.getenv("BOOTSTRAP_DATABASE_PATH", "/data/bootstrap-seed.sqlite3"),
            max_peers_per_network=int(os.getenv("BOOTSTRAP_MAX_PEERS_PER_NETWORK", "1024")),
            max_peers_response=int(os.getenv("BOOTSTRAP_MAX_PEERS_RESPONSE", "64")),
            allow_private_addresses=_parse_bool(os.getenv("BOOTSTRAP_ALLOW_PRIVATE_ADDRESSES", "false")),
        )
