"""Observer-only orchestration over the reward observer store."""

from __future__ import annotations

from collections import defaultdict
from ipaddress import IPv4Address

from .config import RewardObserverConfig
from .concentration import apply_concentration_caps, subnet_key_for_ipv4
from .eligibility import apply_baseline_eligibility
from .models import NodeEpochSummary, NodeIdentity, NodeObservation
from .store import RewardObserverStore


class RewardObserver:
    """Observer-only reward tracker with stubbed ingestion support."""

    def __init__(self, *, config: RewardObserverConfig, store: RewardObserverStore) -> None:
        self.config = config
        self.store = store

    def initialize(self) -> None:
        """Ensure the store schema exists."""

        self.store.init_schema()

    def ingest_observation(self, observation: NodeObservation) -> None:
        """Persist one observation exactly as provided by Phase 1 ingestion."""

        self.store.append_observation(observation)

    def ingest_node_service_snapshot(self, service, *, observed_at: int | None = None) -> list[NodeObservation]:
        """Import observer samples from local node registry and peer state."""

        observed_timestamp = service.time_provider() if observed_at is None else observed_at
        tip = service.chain_tip()
        current_height = 0 if tip is None else tip.height
        epoch_index = self.config.epoch_index_for_height(current_height)
        peers_by_node_id = {peer.node_id: peer for peer in service.list_peers() if peer.node_id}
        observations: list[NodeObservation] = []

        for row in service.node_registry_diagnostics():
            node_id = str(row["node_id"])
            payout_address = str(row["payout_address"])
            peer = peers_by_node_id.get(node_id)
            stored_identity = self.store.get_node(node_id)
            host = stored_identity.host if stored_identity is not None else "<unknown>"
            port = stored_identity.port if stored_identity is not None else 0
            endpoint_source = "provisional"
            if peer is not None:
                host = peer.host
                port = peer.port
                endpoint_source = "peer_state"

            registration_status = self._derive_registration_status(row)
            warmup_status = self._derive_warmup_status(row, current_height=current_height)
            network_ok = peer is not None and peer.network == self.config.network
            handshake_ok = peer is not None and peer.handshake_complete is True
            banned = bool(peer is not None and peer.ban_until is not None and peer.ban_until > observed_timestamp)

            outcome = "unchecked"
            reason_code: str | None = None
            if banned:
                outcome = "failure"
                reason_code = "banned"
            elif peer is None:
                outcome = "unchecked"
            elif not network_ok:
                outcome = "failure"
                reason_code = "wrong_network"
            elif not handshake_ok:
                outcome = "failure"
                reason_code = "protocol_handshake_failed"
            else:
                outcome = "success"

            observation = NodeObservation(
                node_id=node_id,
                payout_address=payout_address,
                host=host,
                port=port,
                height=current_height,
                epoch_index=epoch_index,
                timestamp=observed_timestamp,
                outcome=outcome,
                reason_code=reason_code,
                latency_ms=None,
                handshake_ok=handshake_ok,
                network_ok=network_ok,
                registration_status=registration_status,
                warmup_status=warmup_status,
                banned=banned,
                registration_source="node_registry",
                warmup_source="derived",
                ban_source="peer_state" if peer is not None else "provisional",
                endpoint_source=endpoint_source,
                public_ip=self._coerce_public_ipv4(host),
                fingerprint=None,
            )
            self.store.append_observation(observation)
            observations.append(observation)
        return observations

    def recompute_epoch(self, epoch_index: int) -> list[NodeEpochSummary]:
        """Aggregate raw observations into stored epoch summaries."""

        observations = self.store.list_observations(epoch_index=epoch_index)
        grouped: dict[str, list[NodeObservation]] = defaultdict(list)
        for observation in observations:
            grouped[observation.node_id].append(observation)

        summaries: list[NodeEpochSummary] = []
        for node_id, node_observations in grouped.items():
            node_observations.sort(key=lambda item: (item.timestamp, item.height))
            latest = node_observations[-1]
            identity = self.store.get_node(node_id) or NodeIdentity(
                node_id=latest.node_id,
                payout_address=latest.payout_address,
                host=latest.host,
                port=latest.port,
                first_seen=latest.timestamp,
            )
            success_count = sum(1 for observation in node_observations if observation.outcome == "success")
            failure_count = sum(1 for observation in node_observations if observation.outcome == "failure")
            checked_observation_count = sum(
                1 for observation in node_observations if observation.outcome in {"success", "failure"}
            )
            consecutive_failures = 0
            for observation in reversed(node_observations):
                if observation.outcome != "failure":
                    break
                consecutive_failures += 1
            last_success = None
            for observation in reversed(node_observations):
                if observation.outcome == "success":
                    last_success = observation.timestamp
                    break
            banned = latest.banned
            provisional = NodeEpochSummary(
                epoch_index=epoch_index,
                node_id=identity.node_id,
                payout_address=identity.payout_address,
                host=identity.host,
                port=identity.port,
                first_seen=identity.first_seen,
                last_success=last_success,
                success_count=success_count,
                failure_count=failure_count,
                consecutive_failures=consecutive_failures,
                handshake_ok=any(observation.handshake_ok for observation in node_observations),
                network_ok=all(observation.network_ok for observation in node_observations if observation.outcome != "unchecked")
                if any(observation.outcome != "unchecked" for observation in node_observations)
                else False,
                registration_status=latest.registration_status,
                warmup_status=latest.warmup_status,
                concentration_status="ok",
                final_eligible=False,
                rejection_reason="banned" if banned else None,
                registration_source=latest.registration_source,
                warmup_source=latest.warmup_source,
                ban_source=latest.ban_source,
                endpoint_source=latest.endpoint_source,
                public_ip=latest.public_ip,
                subnet_key=subnet_key_for_ipv4(latest.public_ip, self.config.per_subnet_v4_prefix),
                fingerprint=latest.fingerprint,
                checked_observation_count=checked_observation_count,
                observation_count=len(node_observations),
            )
            summaries.append(apply_baseline_eligibility(provisional, self.config))

        summaries = apply_concentration_caps(summaries, self.config)
        self.store.replace_epoch_summaries(epoch_index, summaries)
        return summaries

    def latest_epoch_index(self) -> int | None:
        """Return the latest observed or summarized epoch."""

        return self.store.latest_epoch_index()

    def _derive_registration_status(self, row: dict[str, object]) -> str:
        if bool(row["active"]) and str(row["epoch_status"]) == "current":
            return "registered"
        return "expired"

    def _derive_warmup_status(self, row: dict[str, object], *, current_height: int) -> bool:
        current_epoch = self.config.epoch_index_for_height(current_height)
        registered_epoch = self.config.epoch_index_for_height(int(row["registered_at_height"]))
        return (current_epoch - registered_epoch) >= self.config.warmup_epochs

    def _coerce_public_ipv4(self, host: str) -> str | None:
        try:
            return str(IPv4Address(host))
        except ValueError:
            return None
