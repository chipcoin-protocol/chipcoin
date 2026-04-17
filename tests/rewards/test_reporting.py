from chipcoin.rewards.reporting import (
    build_epoch_summary,
    concentration_report,
    eligible_nodes_report,
    observation_stats_report,
    rejected_nodes_report,
)
from chipcoin.rewards.models import NodeEpochSummary, NodeObservation


def _summary(node_id: str, *, eligible: bool, reason: str | None, public_ip: str | None) -> NodeEpochSummary:
    return NodeEpochSummary(
        epoch_index=4,
        node_id=node_id,
        payout_address=f"CHC-{node_id}",
        host=f"{node_id}.example",
        port=18444,
        first_seen=1,
        last_success=2,
        success_count=80 if eligible else 20,
        failure_count=20 if eligible else 80,
        consecutive_failures=0,
        handshake_ok=True,
        network_ok=True,
        registration_status="registered",
        warmup_status=True,
        concentration_status="ok" if reason is None else reason,
        final_eligible=eligible,
        rejection_reason=reason,
        registration_source="node_registry",
        warmup_source="derived",
        ban_source="peer_state",
        endpoint_source="peer_state",
        public_ip=public_ip,
        subnet_key=None if public_ip is None else "203.0.113.0/24",
        fingerprint=None,
        checked_observation_count=100,
        observation_count=100,
    )


def test_reporting_builds_epoch_summary_and_lists() -> None:
    summaries = [
        _summary("node-a", eligible=True, reason=None, public_ip="203.0.113.10"),
        _summary("node-b", eligible=False, reason="unreachable", public_ip="203.0.113.11"),
    ]

    summary = build_epoch_summary(4, summaries)
    eligible = eligible_nodes_report(summaries)
    rejected = rejected_nodes_report(summaries)
    concentration = concentration_report(summaries)

    assert summary["eligible_node_count"] == 1
    assert summary["rejected_node_count"] == 1
    assert summary["top_rejection_codes"] == {"unreachable": 1}
    assert eligible[0]["node_id"] == "node-a"
    assert eligible[0]["derived_eligibility"]["final_eligible"] is True
    assert rejected[0]["derived_eligibility"]["rejection_reason"] == "unreachable"
    assert concentration["public_ip_counts"] == {"203.0.113.10": 1, "203.0.113.11": 1}


def test_reporting_builds_observation_stats() -> None:
    observations = [
        NodeObservation(
            node_id="node-a",
            payout_address="CHCa",
            host="node-a.example",
            port=18444,
            height=400,
            epoch_index=4,
            timestamp=1,
            outcome="success",
            reason_code=None,
            latency_ms=100,
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
        ),
        NodeObservation(
            node_id="node-b",
            payout_address="CHCb",
            host="node-b.example",
            port=18444,
            height=401,
            epoch_index=4,
            timestamp=2,
            outcome="failure",
            reason_code="unreachable",
            latency_ms=None,
            handshake_ok=False,
            network_ok=True,
            registration_status="registered",
            warmup_status=True,
            banned=False,
            registration_source="node_registry",
            warmup_source="derived",
            ban_source="peer_state",
            endpoint_source="peer_state",
            public_ip="203.0.113.11",
            fingerprint=None,
        ),
    ]

    payload = observation_stats_report(4, observations)

    assert payload["observation_count"] == 2
    assert payload["outcome_counts"] == {"failure": 1, "success": 1}
    assert payload["reason_code_counts"] == {"unreachable": 1}
