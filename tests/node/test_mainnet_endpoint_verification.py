"""Authenticated public endpoint verification alongside duplicate P2P sessions."""

import asyncio
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from chipcoin.config import get_network_config
from chipcoin.node.messages import VersionMessage
from chipcoin.node.p2p.protocol import LocalPeerIdentity
from chipcoin.node.runtime import NodeRuntime, OutboundPeer, SessionHandle
from chipcoin.node.service import NodeService


class FakeSession:
    def __init__(self, node_id: str, *, inbound: bool, valid: bool = True):
        config = get_network_config("mainnet")
        self.inbound = inbound
        self.identity = LocalPeerIdentity(
            node_id="local", network="mainnet", start_height=100,
            user_agent="test", network_magic=config.magic,
            chain_id=config.chain_id, genesis_hash=config.canonical_genesis_hash or "",
        )
        self.state = SimpleNamespace(
            handshake_complete=True, closed=False,
            remote_version=VersionMessage(
                protocol_version=1, network="mainnet", node_id=node_id,
                start_height=99, user_agent="test",
                chain_id=config.chain_id if valid else "wrong-chain",
                genesis_hash=config.canonical_genesis_hash or "",
            ),
            errors=[], error_causes=[],
        )
        self.close_reason = None

    async def close(self, *, reason=None, error=None):
        self.state.closed = True
        self.close_reason = reason
        if error is not None:
            self.state.error_causes.append(error)
        if reason is not None:
            self.state.errors.append(reason)


async def wait_for(predicate, *, timeout=3.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("P2P condition was not met")
        await asyncio.sleep(0.02)


def test_real_mainnet_handshake_verifies_duplicate_endpoint_without_second_session():
    async def scenario():
        with TemporaryDirectory() as directory:
            left = NodeService.open_sqlite(Path(directory) / "left.sqlite3", network="mainnet")
            right = NodeService.open_sqlite(Path(directory) / "right.sqlite3", network="mainnet")
            left_runtime = NodeRuntime(
                service=left, listen_host="127.0.0.1", listen_port=0, connect_interval=0.05,
            )
            right_runtime = NodeRuntime(
                service=right, listen_host="127.0.0.1", listen_port=0, connect_interval=0.05,
            )
            await left_runtime.start()
            await right_runtime.start()
            try:
                right_runtime._outbound_targets[("127.0.0.1", left_runtime.bound_port)] = OutboundPeer(
                    "127.0.0.1", left_runtime.bound_port,
                )
                await wait_for(
                    lambda: left_runtime.connected_peer_count() == 1
                    and right_runtime.connected_peer_count() == 1,
                )
                endpoint = OutboundPeer("127.0.0.1", right_runtime.bound_port)
                left_runtime._outbound_targets[(endpoint.host, endpoint.port)] = endpoint
                await wait_for(
                    lambda: any(
                        record["port"] == endpoint.port and record["node_id"] == right_runtime.node_id
                        for record in left.recent_endpoint_verifications()
                    ),
                )
                assert left_runtime.connected_peer_count() == 1
                assert right_runtime.connected_peer_count() == 1
                assert left_runtime._has_recent_duplicate_endpoint_verification(endpoint)
                assert any(item["port"] == left_runtime.bound_port for item in right.recent_endpoint_verifications())
            finally:
                await right_runtime.stop()
                await left_runtime.stop()

    asyncio.run(scenario())


def test_duplicate_outbound_verification_keeps_inbound_session_and_expires(monkeypatch):
    async def scenario():
        with TemporaryDirectory() as directory:
            now = [1_700_000_000]
            service = NodeService.open_sqlite(
                Path(directory) / "node.sqlite3", network="mainnet",
                time_provider=lambda: now[0],
            )
            monkeypatch.setattr(
                service, "chain_tip",
                lambda: SimpleNamespace(height=100, block_hash=get_network_config("mainnet").canonical_genesis_hash),
            )
            runtime = NodeRuntime(service=service, listen_host="127.0.0.1", listen_port=8333)
            inbound = FakeSession("janus-id", inbound=True)
            outbound = FakeSession("janus-id", inbound=False)
            endpoint = OutboundPeer("janusart.xyz", 8333)
            runtime._sessions[inbound] = SessionHandle(protocol=inbound, outbound=False)
            runtime._sessions_by_node_id["janus-id"] = inbound
            runtime._sessions[outbound] = SessionHandle(
                protocol=outbound, outbound=True, endpoint=endpoint,
            )
            service.add_peer(endpoint.host, endpoint.port, source="manual")

            await runtime._on_handshake_complete(outbound)
            assert outbound.state.closed
            assert inbound.state.closed is False
            assert runtime._sessions_by_node_id["janus-id"] is inbound
            assert runtime._sessions[outbound].endpoint_verification_only
            assert runtime._has_recent_duplicate_endpoint_verification(endpoint)
            assert service.public_peers()["peers"] == [{
                "host": endpoint.host, "port": 8333,
                "address": "janusart.xyz:8333", "state": "good",
                "last_known_height": 99,
            }]
            await runtime._drop_session(outbound)
            assert runtime._sessions_by_node_id["janus-id"] is inbound
            assert service.peer_info(endpoint.host, endpoint.port).handshake_complete is not True

            # Restarting the service keeps the verification without creating
            # a fabricated operational outbound session.
            reopened = NodeService.open_sqlite(Path(directory) / "node.sqlite3", network="mainnet", time_provider=lambda: now[0])
            monkeypatch.setattr(
                reopened, "chain_tip",
                lambda: SimpleNamespace(height=100, block_hash=get_network_config("mainnet").canonical_genesis_hash),
            )
            assert reopened.public_peers()["count"] == 1
            now[0] += reopened.ENDPOINT_VERIFICATION_TTL_SECONDS
            assert reopened.public_peers()["count"] == 0
            assert not runtime._has_recent_duplicate_endpoint_verification(endpoint)

    asyncio.run(scenario())


def test_verification_rejects_wrong_identity_and_unreachable_endpoint(monkeypatch):
    async def scenario():
        with TemporaryDirectory() as directory:
            service = NodeService.open_sqlite(Path(directory) / "node.sqlite3", network="mainnet")
            monkeypatch.setattr(
                service, "chain_tip",
                lambda: SimpleNamespace(height=100, block_hash=get_network_config("mainnet").canonical_genesis_hash),
            )
            runtime = NodeRuntime(service=service, listen_host="127.0.0.1", listen_port=8333)
            inbound = FakeSession("remote-id", inbound=True)
            runtime._sessions[inbound] = SessionHandle(protocol=inbound, outbound=False)
            runtime._sessions_by_node_id["remote-id"] = inbound
            endpoint = OutboundPeer("janusart.xyz", 8333)
            for invalid in ("chain", "genesis", "network", "magic"):
                wrong = FakeSession("remote-id", inbound=False)
                if invalid == "chain":
                    wrong.state.remote_version = replace(wrong.state.remote_version, chain_id="wrong-chain")
                elif invalid == "genesis":
                    wrong.state.remote_version = replace(wrong.state.remote_version, genesis_hash="0" * 64)
                elif invalid == "network":
                    wrong.state.remote_version = replace(wrong.state.remote_version, network="testnet")
                else:
                    wrong.identity = replace(wrong.identity, network_magic=b"wrong")
                runtime._sessions[wrong] = SessionHandle(protocol=wrong, outbound=True, endpoint=endpoint)
                await runtime._on_handshake_complete(wrong)
                assert service.public_peers()["count"] == 0
                assert wrong.close_reason == "Duplicate peer connection."
                await runtime._drop_session(wrong)

            service.verify_outbound_endpoint(host=endpoint.host, port=endpoint.port, node_id="remote-id", height=99)
            assert service.public_peers()["count"] == 1
            runtime._register_peer_failure(endpoint, error=ConnectionRefusedError("unreachable"))
            assert service.public_peers()["count"] == 0

    asyncio.run(scenario())


def test_recent_verification_does_not_block_outbound_after_inbound_disconnect():
    with TemporaryDirectory() as directory:
        service = NodeService.open_sqlite(Path(directory) / "node.sqlite3", network="mainnet")
        runtime = NodeRuntime(service=service, listen_host="127.0.0.1", listen_port=8333)
        endpoint = OutboundPeer("janusart.xyz", 8333)
        service.verify_outbound_endpoint(host=endpoint.host, port=endpoint.port, node_id="janus-id", height=99)
        assert not runtime._has_recent_duplicate_endpoint_verification(endpoint)


def test_canonical_inbound_endpoint_does_not_suppress_mainnet_verification():
    with TemporaryDirectory() as directory:
        service = NodeService.open_sqlite(Path(directory) / "node.sqlite3", network="mainnet")
        runtime = NodeRuntime(service=service, listen_host="127.0.0.1", listen_port=8333)
        endpoint = OutboundPeer("188.217.94.86", 8333)
        inbound = FakeSession("tobia-id", inbound=True)
        runtime._sessions[inbound] = SessionHandle(
            protocol=inbound, outbound=False, endpoint=endpoint, reusable_endpoint=True,
        )
        runtime._sessions_by_node_id["tobia-id"] = inbound
        service.add_peer(endpoint.host, endpoint.port, source="manual")
        assert runtime._has_active_endpoint(endpoint) is False
        assert runtime._has_recent_duplicate_endpoint_verification(endpoint) is False
        service.verify_outbound_endpoint(
            host=endpoint.host, port=endpoint.port, node_id="tobia-id", height=99,
        )
        assert runtime._has_recent_duplicate_endpoint_verification(endpoint) is True


def test_configured_duplicate_target_survives_startup_cleanup():
    with TemporaryDirectory() as directory:
        service = NodeService.open_sqlite(Path(directory) / "node.sqlite3", network="mainnet")
        service.record_peer_observation(
            host="janusart.xyz", port=8333, direction="outbound",
            handshake_complete=False, protocol_error_class="duplicate_connection",
            node_id="janus-id",
        )
        endpoint = OutboundPeer("janusart.xyz", 8333)
        runtime = NodeRuntime(
            service=service, listen_host="127.0.0.1", listen_port=8333,
            outbound_peers=[endpoint],
        )
        runtime._purge_persisted_startup_duplicate_aliases()
        assert endpoint in runtime._outbound_targets.values()
        assert service.peer_info(endpoint.host, endpoint.port) is not None
        service.record_peer_observation(
            host="crypto-connection.net", port=8333, direction="outbound",
            handshake_complete=False, protocol_error_class="duplicate_connection",
            node_id="other-node",
        )
        runtime._purge_persisted_startup_duplicate_aliases()
        assert service.peer_info("crypto-connection.net", 8333) is not None


def test_verified_dns_and_ip_aliases_publish_one_node(monkeypatch):
    with TemporaryDirectory() as directory:
        service = NodeService.open_sqlite(Path(directory) / "node.sqlite3", network="mainnet")
        monkeypatch.setattr(service, "chain_tip", lambda: SimpleNamespace(height=100))
        for host in ("janusart.xyz", "13.140.151.41"):
            service.verify_outbound_endpoint(host=host, port=8333, node_id="janus-id", height=99)
        assert service.public_peers()["peers"] == [{
            "host": "janusart.xyz", "port": 8333, "address": "janusart.xyz:8333",
            "state": "good", "last_known_height": 99,
        }]
        service.remove_peer("janusart.xyz", 8333)
        assert service.public_peers()["peers"] == [{
            "host": "13.140.151.41", "port": 8333, "address": "13.140.151.41:8333",
            "state": "good", "last_known_height": 99,
        }]


def test_probe_scheduler_renews_with_full_operational_slots(monkeypatch):
    with TemporaryDirectory() as directory:
        now = [1_700_000_000]
        service = NodeService.open_sqlite(Path(directory) / "node.sqlite3", network="mainnet", time_provider=lambda: now[0])
        monkeypatch.setattr(service, "chain_tip", lambda: SimpleNamespace(height=100))
        runtime = NodeRuntime(service=service, listen_host="127.0.0.1", listen_port=8333, max_outbound_sessions=1)
        runtime._running = True
        endpoint = OutboundPeer("janusart.xyz", 8333)
        service.add_peer(endpoint.host, endpoint.port, source="manual")
        service.verify_outbound_endpoint(host=endpoint.host, port=endpoint.port, node_id="janus-id", height=99)
        active = FakeSession("other-id", inbound=False)
        runtime._sessions[active] = SessionHandle(protocol=active, outbound=True, endpoint=OutboundPeer("other.example", 8333))
        assert runtime._active_outbound_session_count() == 1
        scheduled = []
        monkeypatch.setattr(runtime, "_spawn_task", lambda coro, name, **kw: (scheduled.append(name), coro.close()))
        runtime.max_endpoint_probes = 1
        now[0] += 241
        runtime._schedule_endpoint_probes()
        assert scheduled == ["endpoint-probe-janusart.xyz:8333"]
        assert endpoint in runtime._pending_endpoint_probes
        runtime._schedule_endpoint_probes()
        assert len(scheduled) == 1


def test_verified_peer_identity_change_and_fresh_height(monkeypatch):
    with TemporaryDirectory() as directory:
        now = [1_700_000_000]
        service = NodeService.open_sqlite(Path(directory) / "node.sqlite3", network="mainnet", time_provider=lambda: now[0])
        tip = [100]
        monkeypatch.setattr(service, "chain_tip", lambda: SimpleNamespace(height=tip[0]))
        endpoint = OutboundPeer("janusart.xyz", 8333)
        service.record_peer_observation(host=endpoint.host, port=endpoint.port, node_id="old-id", direction="inbound", last_known_height=100)
        service.verify_outbound_endpoint(host=endpoint.host, port=endpoint.port, node_id="new-id", height=99)
        assert service.peer_info(endpoint.host, endpoint.port).node_id == "new-id"
        assert service.public_peers()["count"] == 1
        tip[0] = 121
        assert service.public_peers()["count"] == 0
        assert service.public_peers(diagnostics=True)["excluded"][0]["reason"] == "stale_height"
        service.update_verified_node_height(node_id="new-id", height=120)
        assert service.public_peers()["count"] == 1
        now[0] += service.ENDPOINT_VERIFICATION_TTL_SECONDS
        assert service.public_peers()["count"] == 0
        assert service.public_peers(diagnostics=True)["excluded"][0]["reason"] == "verification_expired"


def test_failed_probe_clears_verification_and_pending_slot(monkeypatch):
    async def scenario():
        with TemporaryDirectory() as directory:
            service = NodeService.open_sqlite(Path(directory) / "node.sqlite3", network="mainnet")
            runtime = NodeRuntime(service=service, listen_host="127.0.0.1", listen_port=8333)
            runtime._running = True
            endpoint = OutboundPeer("janusart.xyz", 8333)
            service.add_peer(endpoint.host, endpoint.port, source="manual")
            service.verify_outbound_endpoint(host=endpoint.host, port=8333, node_id="janus-id", height=99)
            runtime._pending_endpoint_probes.add(endpoint)
            invalid = FakeSession("janus-id", inbound=False, valid=False)
            runtime._sessions[invalid] = SessionHandle(protocol=invalid, outbound=True, endpoint=endpoint, endpoint_probe=True)
            await runtime._on_handshake_complete(invalid)
            await runtime._drop_session(invalid)
            assert endpoint not in runtime._pending_endpoint_probes
            assert service.public_peers()["count"] == 0
            assert service.public_peers(diagnostics=True)["excluded"][0]["reason"] in {"banned_or_backoff", "unverified_endpoint"}

    asyncio.run(scenario())


def test_real_probe_uses_separate_capacity_and_keeps_inbound_session(monkeypatch):
    async def scenario():
        with TemporaryDirectory() as directory:
            left = NodeService.open_sqlite(Path(directory) / "left.sqlite3", network="mainnet")
            right = NodeService.open_sqlite(Path(directory) / "right.sqlite3", network="mainnet")
            left_runtime = NodeRuntime(service=left, listen_host="127.0.0.1", listen_port=0,
                                       connect_interval=0.05, max_outbound_sessions=1)
            right_runtime = NodeRuntime(service=right, listen_host="127.0.0.1", listen_port=0,
                                        connect_interval=0.05)
            monkeypatch.setattr(left, "is_public_peer_host", lambda host: host == "127.0.0.1")
            await left_runtime.start()
            await right_runtime.start()
            try:
                right_runtime._outbound_targets[("127.0.0.1", left_runtime.bound_port)] = OutboundPeer(
                    "127.0.0.1", left_runtime.bound_port,
                )
                await wait_for(lambda: left_runtime.connected_peer_count() == 1)
                endpoint = OutboundPeer("127.0.0.1", right_runtime.bound_port)
                occupied = FakeSession("occupied-slot", inbound=False)
                occupied.state.handshake_complete = False
                left_runtime._sessions[occupied] = SessionHandle(
                    protocol=occupied, outbound=True, endpoint=OutboundPeer("occupied.example", 8333),
                )
                assert left_runtime._active_outbound_session_count() == 1
                config = get_network_config("mainnet")
                monkeypatch.setattr("chipcoin.node.runtime.get_network_config",
                                    lambda network: replace(config, default_p2p_port=endpoint.port))
                left.add_peer(endpoint.host, endpoint.port, source="manual")
                left.record_peer_observation(
                    host=endpoint.host, port=endpoint.port, direction="inbound", handshake_complete=True,
                    last_success=left.time_provider(), node_id=right_runtime.node_id, last_known_height=0,
                )
                await wait_for(lambda: any(item["port"] == endpoint.port for item in left.recent_endpoint_verifications()))
                assert left_runtime._active_outbound_session_count() == 1
                assert left_runtime.connected_peer_count() == 1
                assert right_runtime.connected_peer_count() == 1
            finally:
                await right_runtime.stop()
                await left_runtime.stop()

    asyncio.run(scenario())


def test_active_outbound_refreshes_without_extra_probe(monkeypatch):
    with TemporaryDirectory() as directory:
        now = [1_700_000_000]
        service = NodeService.open_sqlite(Path(directory) / "node.sqlite3", network="mainnet", time_provider=lambda: now[0])
        monkeypatch.setattr(service, "chain_tip", lambda: SimpleNamespace(height=100))
        runtime = NodeRuntime(service=service, listen_host="127.0.0.1", listen_port=8333)
        endpoint = OutboundPeer("janusart.xyz", 8333)
        session = FakeSession("janus-id", inbound=False)
        runtime._sessions[session] = SessionHandle(protocol=session, outbound=True, endpoint=endpoint)
        service.record_peer_observation(host=endpoint.host, port=endpoint.port, direction="outbound",
                                        handshake_complete=True, last_success=now[0], node_id="janus-id",
                                        last_known_height=99)
        service.verify_outbound_endpoint(host=endpoint.host, port=8333, node_id="janus-id", height=99)
        now[0] += 241
        runtime._schedule_endpoint_probes()
        assert not runtime._pending_endpoint_probes
        assert service.recent_endpoint_verifications()[0]["verified_at"] == now[0]


def test_verified_dns_alias_preferred_over_recent_direct_ip(monkeypatch):
    with TemporaryDirectory() as directory:
        service = NodeService.open_sqlite(Path(directory) / "node.sqlite3", network="mainnet")
        monkeypatch.setattr(service, "chain_tip", lambda: SimpleNamespace(height=100))
        service.record_peer_observation(
            host="13.140.151.41", port=8333, direction="outbound", handshake_complete=True,
            last_success=service.time_provider(), last_known_height=99, node_id="janus-id", score=1,
        )
        service.verify_outbound_endpoint(host="janusart.xyz", port=8333, node_id="janus-id", height=99)
        assert service.public_peers()["peers"] == [{
            "host": "janusart.xyz", "port": 8333, "address": "janusart.xyz:8333",
            "state": "good", "last_known_height": 99,
        }]


def test_stale_peerbook_identity_triggers_reverification(monkeypatch):
    with TemporaryDirectory() as directory:
        now = [1_700_000_000]
        service = NodeService.open_sqlite(Path(directory) / "node.sqlite3", network="mainnet", time_provider=lambda: now[0])
        monkeypatch.setattr(service, "chain_tip", lambda: SimpleNamespace(height=100))
        endpoint = OutboundPeer("janusart.xyz", 8333)
        service.record_peer_observation(host=endpoint.host, port=8333, direction="inbound",
                                        last_success=now[0], node_id="old-id", last_known_height=99)
        service.verify_outbound_endpoint(host=endpoint.host, port=8333, node_id="old-id", height=99)
        service.record_peer_observation(host=endpoint.host, port=8333, direction="inbound",
                                        last_success=now[0], node_id="new-id", last_known_height=99)
        assert service.public_peers()["count"] == 0
        assert service.public_peers(diagnostics=True)["excluded"][0]["reason"] == "identity_changed_since_verification"
        runtime = NodeRuntime(service=service, listen_host="127.0.0.1", listen_port=8333)
        scheduled = []
        monkeypatch.setattr(runtime, "_spawn_task", lambda coro, name, **kw: (scheduled.append(name), coro.close()))
        runtime._schedule_endpoint_probes()
        assert scheduled == ["endpoint-probe-janusart.xyz:8333"]
        service.verify_outbound_endpoint(host=endpoint.host, port=8333, node_id="new-id", height=99)
        assert service.public_peers()["count"] == 1


def test_endpoint_probe_concurrency_is_bounded(monkeypatch):
    with TemporaryDirectory() as directory:
        service = NodeService.open_sqlite(Path(directory) / "node.sqlite3", network="mainnet")
        runtime = NodeRuntime(service=service, listen_host="127.0.0.1", listen_port=8333)
        scheduled = []
        monkeypatch.setattr(runtime, "_spawn_task", lambda coro, name, **kw: (scheduled.append(name), coro.close()))
        for number in range(4):
            service.record_peer_observation(host=f"peer{number}.example", port=8333,
                                            direction="inbound", handshake_complete=True,
                                            last_success=service.time_provider(), node_id=f"id-{number}")
        runtime._schedule_endpoint_probes()
        assert len(scheduled) == 2
        assert len(runtime._pending_endpoint_probes) == 2


def test_verified_endpoints_renew_before_unverified_candidates(monkeypatch):
    with TemporaryDirectory() as directory:
        now = [1_700_000_000]
        service = NodeService.open_sqlite(Path(directory) / "node.sqlite3", network="mainnet", time_provider=lambda: now[0])
        runtime = NodeRuntime(service=service, listen_host="127.0.0.1", listen_port=8333)
        scheduled = []
        monkeypatch.setattr(runtime, "_spawn_task", lambda coro, name, **kw: (scheduled.append(name), coro.close()))
        for number in range(4):
            service.record_peer_observation(
                host=f"a{number}.example", port=8333, direction="inbound",
                handshake_complete=True, last_success=now[0], node_id=f"unverified-{number}",
            )
        for number in range(2):
            host = f"z{number}.example"
            service.record_peer_observation(
                host=host, port=8333, direction="inbound", handshake_complete=True,
                last_success=now[0], node_id=f"verified-{number}",
            )
            service.verify_outbound_endpoint(host=host, port=8333, node_id=f"verified-{number}", height=99)
        now[0] += 241
        runtime._schedule_endpoint_probes()
        assert scheduled == ["endpoint-probe-z0.example:8333", "endpoint-probe-z1.example:8333"]


def test_probe_scheduler_runs_while_normal_connect_loop_is_blocked(monkeypatch):
    async def scenario():
        with TemporaryDirectory() as directory:
            service = NodeService.open_sqlite(Path(directory) / "node.sqlite3", network="mainnet")
            runtime = NodeRuntime(service=service, listen_host="127.0.0.1", listen_port=0,
                                  connect_interval=0.05, memory_metrics_interval_seconds=0)
            blocked = asyncio.Event()
            calls = []
            monkeypatch.setattr(runtime, "_connect_loop", lambda: blocked.wait())
            monkeypatch.setattr(runtime, "_schedule_endpoint_probes", lambda: calls.append(1))
            await runtime.start()
            try:
                await wait_for(lambda: len(calls) >= 2)
                assert not blocked.is_set()
            finally:
                await runtime.stop()

    asyncio.run(scenario())
