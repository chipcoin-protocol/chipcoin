"""Configuration loading for the reward observer."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class RewardObserverConfig:
    """Static observer configuration for Phase 1 reward tracking."""

    network: str
    storage_path: str
    node_data_path: str | None
    epoch_length_blocks: int
    warmup_epochs: int
    required_observations_per_epoch: int
    min_successful_observations: int
    per_public_ipv4_cap: int
    per_subnet_v4_prefix: int
    per_subnet_cap: int
    fingerprint_cap: int | None
    observation_timeout_seconds: float
    observation_retry_count: int

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "RewardObserverConfig":
        """Create config from one parsed JSON object."""

        return cls(
            network=str(payload["network"]),
            storage_path=str(payload["storage_path"]),
            node_data_path=None if payload.get("node_data_path") is None else str(payload["node_data_path"]),
            epoch_length_blocks=int(payload["epoch_length_blocks"]),
            warmup_epochs=int(payload["warmup_epochs"]),
            required_observations_per_epoch=int(payload["required_observations_per_epoch"]),
            min_successful_observations=int(payload["min_successful_observations"]),
            per_public_ipv4_cap=int(payload["per_public_ipv4_cap"]),
            per_subnet_v4_prefix=int(payload.get("per_subnet_v4_prefix", 24)),
            per_subnet_cap=int(payload["per_subnet_cap"]),
            fingerprint_cap=None
            if payload.get("fingerprint_cap") is None
            else int(payload["fingerprint_cap"]),
            observation_timeout_seconds=float(payload.get("observation_timeout_seconds", 5.0)),
            observation_retry_count=int(payload.get("observation_retry_count", 1)),
        )

    @classmethod
    def load_json(cls, path: str | Path) -> "RewardObserverConfig":
        """Load config from a JSON file."""

        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Observer config must be a JSON object.")
        return cls.from_dict(raw)

    def epoch_index_for_height(self, height: int) -> int:
        """Return the epoch index for one chain height."""

        if height < 0:
            raise ValueError("height must be non-negative")
        return height // self.epoch_length_blocks
