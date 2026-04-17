from chipcoin.rewards.config import RewardObserverConfig
from chipcoin.rewards.concentration import apply_concentration_caps, subnet_key_for_ipv4
from chipcoin.rewards.models import NodeEpochSummary


def _config() -> RewardObserverConfig:
    return RewardObserverConfig(
        network="devnet",
        storage_path=":memory:",
        node_data_path=None,
        epoch_length_blocks=100,
        warmup_epochs=1,
        required_observations_per_epoch=100,
        min_successful_observations=75,
        per_public_ipv4_cap=1,
        per_subnet_v4_prefix=24,
        per_subnet_cap=2,
        fingerprint_cap=1,
        observation_timeout_seconds=5.0,
        observation_retry_count=1,
    )


def _summary(node_id: str, payout_address: str, *, public_ip: str, fingerprint: str | None = None) -> NodeEpochSummary:
    return NodeEpochSummary(
        epoch_index=1,
        node_id=node_id,
        payout_address=payout_address,
        host=f"{node_id}.example",
        port=18444,
        first_seen=1,
        last_success=2,
        success_count=80,
        failure_count=20,
        consecutive_failures=0,
        handshake_ok=True,
        network_ok=True,
        registration_status="registered",
        warmup_status=True,
        concentration_status="ok",
        final_eligible=True,
        rejection_reason=None,
        registration_source="node_registry",
        warmup_source="derived",
        ban_source="peer_state",
        endpoint_source="peer_state",
        public_ip=public_ip,
        subnet_key=subnet_key_for_ipv4(public_ip, 24),
        fingerprint=fingerprint,
        checked_observation_count=100,
        observation_count=100,
    )


def test_concentration_applies_per_ip_cap_deterministically() -> None:
    summaries = apply_concentration_caps(
        [
            _summary("node-a", "CHCa", public_ip="203.0.113.10"),
            _summary("node-b", "CHCb", public_ip="203.0.113.10"),
        ],
        _config(),
    )

    assert summaries[0].final_eligible is True
    assert summaries[1].final_eligible is False
    assert summaries[1].rejection_reason == "ip_concentration_cap"


def test_concentration_applies_subnet_cap() -> None:
    config = _config()
    config = RewardObserverConfig(**{**config.__dict__, "per_public_ipv4_cap": 5})
    summaries = apply_concentration_caps(
        [
            _summary("node-a", "CHCa", public_ip="203.0.113.10"),
            _summary("node-b", "CHCb", public_ip="203.0.113.11"),
            _summary("node-c", "CHCc", public_ip="203.0.113.12"),
        ],
        config,
    )

    assert [summary.rejection_reason for summary in summaries] == [None, None, "subnet_concentration_cap"]


def test_concentration_applies_fingerprint_cap_placeholder() -> None:
    config = _config()
    config = RewardObserverConfig(**{**config.__dict__, "per_public_ipv4_cap": 5, "per_subnet_cap": 5})
    summaries = apply_concentration_caps(
        [
            _summary("node-a", "CHCa", public_ip="203.0.113.10", fingerprint="fp-1"),
            _summary("node-b", "CHCb", public_ip="203.0.113.11", fingerprint="fp-1"),
        ],
        config,
    )

    assert summaries[0].final_eligible is True
    assert summaries[1].rejection_reason == "fingerprint_concentration_cap"
