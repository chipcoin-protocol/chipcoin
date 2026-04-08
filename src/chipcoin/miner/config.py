"""Configuration models for the lightweight miner worker."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MinerWorkerConfig:
    """Configuration required for one template-based miner worker."""

    network: str
    payout_address: str
    node_urls: tuple[str, ...]
    miner_id: str
    polling_interval_seconds: float = 2.0
    request_timeout_seconds: float = 10.0
    nonce_batch_size: int = 250_000
    template_refresh_skew_seconds: int = 1
    mining_min_interval_seconds: float = 0.0
    run_seconds: float | None = None

