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
