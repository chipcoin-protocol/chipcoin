from chipcoin.rewards.config import RewardObserverConfig
from chipcoin.rewards.eligibility import apply_baseline_eligibility
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
        per_public_ipv4_cap=2,
        per_subnet_v4_prefix=24,
        per_subnet_cap=3,
        fingerprint_cap=None,
        observation_timeout_seconds=5.0,
        observation_retry_count=1,
    )


def _summary(**overrides) -> NodeEpochSummary:
    payload = {
        "epoch_index": 3,
        "node_id": "node-a",
        "payout_address": "CHCtest",
        "host": "node-a.example",
        "port": 18444,
        "first_seen": 1000,
        "last_success": 2000,
        "success_count": 80,
        "failure_count": 20,
        "consecutive_failures": 0,
        "handshake_ok": True,
        "network_ok": True,
        "registration_status": "registered",
        "warmup_status": True,
        "concentration_status": "ok",
        "final_eligible": False,
        "rejection_reason": None,
        "registration_source": "node_registry",
        "warmup_source": "derived",
        "ban_source": "peer_state",
        "endpoint_source": "peer_state",
        "public_ip": "203.0.113.10",
        "subnet_key": "203.0.113.0/24",
        "fingerprint": None,
        "checked_observation_count": 100,
        "observation_count": 100,
    }
    payload.update(overrides)
    return NodeEpochSummary(**payload)


def test_eligibility_accepts_baseline_eligible_node() -> None:
    summary = apply_baseline_eligibility(_summary(), _config())

    assert summary.final_eligible is True
    assert summary.rejection_reason is None


def test_eligibility_rejects_insufficient_observation_before_unreachable() -> None:
    summary = apply_baseline_eligibility(
        _summary(observation_count=100, checked_observation_count=74, success_count=74),
        _config(),
    )

    assert summary.final_eligible is False
    assert summary.rejection_reason == "insufficient_observation"


def test_eligibility_rejects_wrong_network() -> None:
    summary = apply_baseline_eligibility(_summary(network_ok=False), _config())

    assert summary.final_eligible is False
    assert summary.rejection_reason == "wrong_network"


def test_eligibility_rejects_banned_node() -> None:
    summary = apply_baseline_eligibility(_summary(rejection_reason="banned"), _config())

    assert summary.final_eligible is False
    assert summary.rejection_reason == "banned"
