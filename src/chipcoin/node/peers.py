"""Peer manager interfaces and lifecycle state."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import threading

from .p2p.errors import protocol_error_class


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PeerInfo:
    """Minimal peer identity and connectivity state."""

    host: str
    port: int
    network: str
    source: str | None = None
    first_seen: int | None = None
    direction: str | None = None
    last_seen: int | None = None
    last_success: int | None = None
    last_failure: int | None = None
    failure_count: int | None = None
    success_count: int | None = None
    handshake_complete: bool | None = None
    last_known_height: int | None = None
    node_id: str | None = None
    score: int | None = None
    reconnect_attempts: int | None = None
    backoff_until: int | None = None
    last_error: str | None = None
    last_error_at: int | None = None
    protocol_error_class: str | None = None
    disconnect_count: int | None = None
    session_started_at: int | None = None
    misbehavior_score: int | None = None
    misbehavior_last_updated_at: int | None = None
    ban_until: int | None = None
    last_penalty_reason: str | None = None
    last_penalty_at: int | None = None


_PEER_SOURCE_PRIORITY = {"manual": 3, "seed": 2, "discovered": 1}


def is_usable_peer_endpoint(host: object, port: object, network: object) -> bool:
    """Accept only usable endpoint identities, never an unknown network."""

    return (
        isinstance(network, str) and bool(network)
        and isinstance(host, str) and bool(host)
        and type(port) is int and 0 < port <= 65535
    )


def preferred_peer_source(existing: str | None, incoming: str | None) -> str | None:
    """Return the strongest peer source without downgrading explicit operator intent."""

    if existing is None:
        return incoming
    if incoming is None:
        return existing
    existing_rank = _PEER_SOURCE_PRIORITY.get(existing, 0)
    incoming_rank = _PEER_SOURCE_PRIORITY.get(incoming, 0)
    return incoming if incoming_rank > existing_rank else existing


def classify_peer_error(error: Exception | str | None) -> str | None:
    """Map peer/runtime errors into stable diagnostic classes."""

    return protocol_error_class(error)


class PeerManager:
    """Manage known peers and active sessions."""

    def __init__(self) -> None:
        self._peers: dict[tuple[str, int, str], PeerInfo] = {}
        self._lock = threading.RLock()
        self._last_reported_invalid_count = 0

    def add(self, peer: PeerInfo) -> None:
        """Add a peer to the local peerbook."""

        with self._lock:
            self._add_locked(peer)

    def _add_locked(self, peer: PeerInfo) -> None:
        """Merge one record while holding the peerbook lock."""

        key = (peer.host, peer.port, peer.network)
        existing = self._peers.get(key)
        if existing is None:
            self._peers[key] = peer
            return
        self._peers[key] = PeerInfo(
            host=peer.host,
            port=peer.port,
            network=peer.network,
            source=preferred_peer_source(existing.source, peer.source),
            first_seen=existing.first_seen if existing.first_seen is not None else peer.first_seen,
            direction=peer.direction if peer.direction is not None else existing.direction,
            last_seen=peer.last_seen if peer.last_seen is not None else existing.last_seen,
            last_success=peer.last_success if peer.last_success is not None else existing.last_success,
            last_failure=peer.last_failure if peer.last_failure is not None else existing.last_failure,
            failure_count=peer.failure_count if peer.failure_count is not None else existing.failure_count,
            success_count=peer.success_count if peer.success_count is not None else existing.success_count,
            handshake_complete=(
                peer.handshake_complete if peer.handshake_complete is not None else existing.handshake_complete
            ),
            last_known_height=peer.last_known_height if peer.last_known_height is not None else existing.last_known_height,
            node_id=peer.node_id if peer.node_id is not None else existing.node_id,
            score=peer.score if peer.score is not None else existing.score,
            reconnect_attempts=(
                peer.reconnect_attempts if peer.reconnect_attempts is not None else existing.reconnect_attempts
            ),
            backoff_until=peer.backoff_until if peer.backoff_until is not None else existing.backoff_until,
            last_error=peer.last_error if peer.last_error is not None else existing.last_error,
            last_error_at=peer.last_error_at if peer.last_error_at is not None else existing.last_error_at,
            protocol_error_class=(
                peer.protocol_error_class if peer.protocol_error_class is not None else existing.protocol_error_class
            ),
            disconnect_count=peer.disconnect_count if peer.disconnect_count is not None else existing.disconnect_count,
            session_started_at=peer.session_started_at if peer.session_started_at is not None else existing.session_started_at,
            misbehavior_score=(
                peer.misbehavior_score if peer.misbehavior_score is not None else existing.misbehavior_score
            ),
            misbehavior_last_updated_at=(
                peer.misbehavior_last_updated_at
                if peer.misbehavior_last_updated_at is not None
                else existing.misbehavior_last_updated_at
            ),
            ban_until=peer.ban_until if peer.ban_until is not None else existing.ban_until,
            last_penalty_reason=(
                peer.last_penalty_reason if peer.last_penalty_reason is not None else existing.last_penalty_reason
            ),
            last_penalty_at=peer.last_penalty_at if peer.last_penalty_at is not None else existing.last_penalty_at,
        )

    def remove(self, peer: PeerInfo) -> None:
        """Remove a peer from the local peerbook when present."""

        with self._lock:
            self._peers.pop((peer.host, peer.port, peer.network), None)

    def get(self, *, host: str, port: int, network: str) -> PeerInfo | None:
        """Return one peer by endpoint when present."""

        with self._lock:
            return self._peers.get((host, port, network))

    def reset_session_state(self, *, network: str) -> None:
        """Clear runtime-only session markers for one network."""

        with self._lock:
            self._reset_session_state_locked(network=network)

    def _reset_session_state_locked(self, *, network: str) -> None:
        """Reset session flags while holding the peerbook lock."""

        for key, peer in list(self._peers.items()):
            if peer.network != network or peer.handshake_complete is not True:
                continue
            self._peers[key] = PeerInfo(
                host=peer.host,
                port=peer.port,
                network=peer.network,
                source=peer.source,
                first_seen=peer.first_seen,
                direction=peer.direction,
                last_seen=peer.last_seen,
                last_success=peer.last_success,
                last_failure=peer.last_failure,
                failure_count=peer.failure_count,
                success_count=peer.success_count,
                handshake_complete=False,
                last_known_height=peer.last_known_height,
                node_id=peer.node_id,
                score=peer.score,
                reconnect_attempts=peer.reconnect_attempts,
                backoff_until=peer.backoff_until,
                last_error=peer.last_error,
                last_error_at=peer.last_error_at,
                protocol_error_class=peer.protocol_error_class,
                disconnect_count=peer.disconnect_count,
                session_started_at=None,
                misbehavior_score=peer.misbehavior_score,
                misbehavior_last_updated_at=peer.misbehavior_last_updated_at,
                ban_until=peer.ban_until,
                last_penalty_reason=peer.last_penalty_reason,
                last_penalty_at=peer.last_penalty_at,
            )

    def list_all(self, *, network: str | None = None) -> list[PeerInfo]:
        """Return known peers, optionally filtered by network."""

        # Copy before iterating: HTTP requests and the asyncio runtime share this
        # peerbook. Invalid legacy/in-flight endpoints remain stored for diagnosis,
        # but must never be used for dialing, advertising or endpoint probing.
        with self._lock:
            snapshot = tuple(self._peers.values())
        peers = []
        invalid_count = 0
        for peer in snapshot:
            if not is_usable_peer_endpoint(peer.host, peer.port, peer.network):
                invalid_count += 1
                continue
            if network is None or peer.network == network:
                peers.append(peer)
        if invalid_count != self._last_reported_invalid_count:
            if invalid_count:
                logger.warning("peerbook quarantined malformed endpoint records count=%s", invalid_count)
            self._last_reported_invalid_count = invalid_count
        return sorted(peers, key=lambda peer: (peer.network, peer.host, peer.port))

    def active_host_ban(self, *, network: str, host: str, now: int) -> int | None:
        """Include quarantined endpoints when enforcing an existing host ban."""

        with self._lock:
            snapshot = tuple(self._peers.values())
        bans = (
            peer.ban_until for peer in snapshot
            if peer.network == network and peer.host == host
            and type(peer.ban_until) is int and peer.ban_until > now
        )
        return max(bans, default=None)
