from pathlib import Path

from chipcoin.rewards.models import NodeEpochSummary, NodeObservation
from chipcoin.rewards.store import RewardObserverStore


def test_store_initializes_and_persists_observations_and_summaries(tmp_path: Path) -> None:
    store = RewardObserverStore(tmp_path / "observer.sqlite3")
    store.init_schema()

    store.append_observation(
        NodeObservation(
            node_id="node-a",
            payout_address="CHCa",
            host="node-a.example",
            port=18444,
            height=150,
            epoch_index=1,
            timestamp=1_700_000_000,
            outcome="success",
            reason_code=None,
            latency_ms=120,
            handshake_ok=True,
            network_ok=True,
            registration_status="registered",
            warmup_status=True,
            banned=False,
            registration_source="node_registry",
            warmup_source="derived",
            ban_source="peer_state",
            endpoint_source="peer_state",
            public_ip="203.0.113.10",
            fingerprint=None,
        )
    )

    summaries = [
        NodeEpochSummary(
            epoch_index=1,
            node_id="node-a",
            payout_address="CHCa",
            host="node-a.example",
            port=18444,
            first_seen=1_700_000_000,
            last_success=1_700_000_000,
            success_count=1,
            failure_count=0,
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
            public_ip="203.0.113.10",
            subnet_key="203.0.113.0/24",
            fingerprint=None,
            checked_observation_count=1,
            observation_count=1,
        )
    ]
    store.replace_epoch_summaries(1, summaries)

    status = store.store_status()
    loaded_observations = store.list_observations(epoch_index=1)
    loaded_summaries = store.list_epoch_summaries(1)

    assert status["schema_version"] == 7
    assert status["observation_count"] == 1
    assert status["batch_count"] == 0
    assert status["plan_count"] == 0
    assert status["artifact_count"] == 0
    assert status["preflight_count"] == 0
    assert len(loaded_observations) == 1
    assert loaded_observations[0].node_id == "node-a"
    assert len(loaded_summaries) == 1
    assert loaded_summaries[0].final_eligible is True
