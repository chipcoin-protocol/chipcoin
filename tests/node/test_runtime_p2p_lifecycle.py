"""P2P runtime lifecycle hardening tests."""

from __future__ import annotations

import asyncio
import gc
from pathlib import Path
from tempfile import TemporaryDirectory

from chipcoin.node.messages import VersionMessage
from chipcoin.node.runtime import NodeRuntime, OutboundPeer, SessionHandle
from chipcoin.node.service import NodeService
from tests.node.test_runtime_integration import TEST_PARAMS


class HangingReader:
    async def readexactly(self, size: int) -> bytes:
        await asyncio.sleep(3600)
        return b""


class ClosingReader:
    async def readexactly(self, size: int) -> bytes:
        raise asyncio.IncompleteReadError(partial=b"", expected=size)


class FakeWriter:
    def __init__(self, host: str = "198.51.100.10", port: int = 40000) -> None:
        self.host = host
        self.port = port
        self.closed = False
        self.wait_closed_calls = 0

    def get_extra_info(self, name: str):
        if name == "peername":
            return (self.host, self.port)
        return None

    def write(self, data: bytes) -> None:
        if self.closed:
            raise ConnectionResetError("closed")

    async def drain(self) -> None:
        if self.closed:
            raise ConnectionResetError("closed")

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self.wait_closed_calls += 1
        self.closed = True


def _make_service(path: Path) -> NodeService:
    return NodeService.open_sqlite(path, params=TEST_PARAMS, time_provider=lambda: 1_700_000_000)


async def _quiesce(runtime: NodeRuntime) -> None:
    for session in list(runtime._sessions):
        await session.close(reason="test cleanup")
        await runtime._drop_session(session)
    for task in list(runtime._tasks):
        task.cancel()
    await asyncio.gather(*list(runtime._tasks), return_exceptions=True)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    gc.collect()


def test_runtime_limits_pending_inbound_handshakes_per_ip_before_session_creation() -> None:
    async def scenario() -> None:
        with TemporaryDirectory() as tempdir:
            service = _make_service(Path(tempdir) / "node.sqlite3")
            runtime = NodeRuntime(
                service=service,
                max_inbound_sessions=10,
                max_pending_handshakes=10,
                max_pending_handshakes_per_ip=2,
                inbound_handshake_rate_limit_per_minute=1000,
                handshake_timeout=60.0,
                read_timeout=60.0,
            )
            writers = [FakeWriter("198.51.100.10", 41000 + index) for index in range(5)]

            for writer in writers:
                await runtime._handle_inbound_connection(HangingReader(), writer)
            await asyncio.sleep(0)

            metrics = runtime.runtime_memory_metrics()
            assert metrics["sessions_total"] == 2
            assert metrics["pending_handshakes"] == 2
            assert metrics["inbound_pending"] == 2
            assert sum(writer.closed for writer in writers) == 3
            assert len(runtime._tasks) == 2

            await _quiesce(runtime)
            assert runtime.runtime_memory_metrics()["sessions_total"] == 0
            assert len(runtime._tasks) == 0

    asyncio.run(scenario())


def test_runtime_limits_global_pending_inbound_handshakes_before_session_creation() -> None:
    async def scenario() -> None:
        with TemporaryDirectory() as tempdir:
            service = _make_service(Path(tempdir) / "node.sqlite3")
            runtime = NodeRuntime(
                service=service,
                max_inbound_sessions=10,
                max_pending_handshakes=3,
                max_pending_handshakes_per_ip=10,
                inbound_handshake_rate_limit_per_minute=1000,
                handshake_timeout=60.0,
                read_timeout=60.0,
            )
            writers = [FakeWriter(f"198.51.100.{index + 10}", 42000 + index) for index in range(6)]

            for writer in writers:
                await runtime._handle_inbound_connection(HangingReader(), writer)
            await asyncio.sleep(0)

            assert runtime.runtime_memory_metrics()["pending_handshakes"] == 3
            assert sum(writer.closed for writer in writers) == 3

            await _quiesce(runtime)
            assert runtime.runtime_memory_metrics()["pending_handshakes"] == 0

    asyncio.run(scenario())


def test_runtime_cleans_up_after_inbound_eof_before_handshake() -> None:
    async def scenario() -> None:
        with TemporaryDirectory() as tempdir:
            service = _make_service(Path(tempdir) / "node.sqlite3")
            runtime = NodeRuntime(
                service=service,
                max_pending_handshakes_per_ip=4,
                inbound_handshake_rate_limit_per_minute=1000,
                read_timeout=0.1,
                handshake_timeout=0.1,
            )

            await runtime._handle_inbound_connection(ClosingReader(), FakeWriter())
            await asyncio.sleep(0.2)
            await asyncio.sleep(0)

            assert runtime.runtime_memory_metrics()["sessions_total"] == 0
            assert len(runtime._tasks) == 0
            assert runtime._session_created_count == runtime._session_closed_count == 1

    asyncio.run(scenario())


def test_runtime_cancels_session_task_without_orphaning_reader_or_session() -> None:
    async def scenario() -> None:
        with TemporaryDirectory() as tempdir:
            service = _make_service(Path(tempdir) / "node.sqlite3")
            runtime = NodeRuntime(
                service=service,
                max_pending_handshakes_per_ip=4,
                inbound_handshake_rate_limit_per_minute=1000,
                read_timeout=60.0,
                handshake_timeout=60.0,
            )

            await runtime._handle_inbound_connection(HangingReader(), FakeWriter())
            await asyncio.sleep(0)
            tasks = list(runtime._tasks)
            assert len(tasks) == 1

            tasks[0].cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0)
            await asyncio.sleep(0)

            assert runtime.runtime_memory_metrics()["sessions_total"] == 0
            assert len(runtime._tasks) == 0
            assert runtime._session_created_count == runtime._session_closed_count == 1

    asyncio.run(scenario())


def test_runtime_prunes_aliases_without_removing_configured_canonical_or_connected_peers() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "node.sqlite3")
        for index, host in enumerate(("configured.example", "canonical.example", "connected.example", "stale-a.example", "stale-b.example")):
            service.record_peer_observation(
                host=host,
                port=18444,
                source="manual" if host == "configured.example" else "discovered",
                handshake_complete=host in {"canonical.example", "connected.example"},
                node_id="node-a",
                success_count=1 if host == "canonical.example" else 0,
                score=10 - index,
                last_success=1_700_000_000 + index,
            )
        runtime = NodeRuntime(
            service=service,
            outbound_peers=[OutboundPeer("configured.example", 18444)],
            max_peer_aliases_per_node_id=3,
        )

        class _FakeState:
            closed = False
            handshake_complete = True
            remote_version = VersionMessage(
                protocol_version=1,
                network=service.network,
                node_id="node-a",
                start_height=0,
                user_agent="/test/",
            )
            errors: list[str] = []
            error_causes: list[Exception] = []

        class _FakeSession:
            inbound = True
            state = _FakeState()
            transport = None

        session = _FakeSession()
        runtime._sessions[session] = SessionHandle(
            protocol=session,  # type: ignore[arg-type]
            outbound=False,
            endpoint=OutboundPeer("connected.example", 18444),
        )

        runtime._prune_peer_aliases_for_node_id(
            "node-a",
            canonical_endpoint=OutboundPeer("canonical.example", 18444),
            prefer_configured=OutboundPeer("configured.example", 18444),
        )

        endpoints = {(peer.host, peer.port) for peer in service.list_peers()}
        assert ("configured.example", 18444) in endpoints
        assert ("canonical.example", 18444) in endpoints
        assert ("connected.example", 18444) in endpoints
        assert len([peer for peer in service.list_peers() if peer.node_id == "node-a"]) == 3


def test_runtime_stress_incomplete_handshakes_returns_to_baseline() -> None:
    async def scenario() -> None:
        with TemporaryDirectory() as tempdir:
            service = _make_service(Path(tempdir) / "node.sqlite3")
            runtime = NodeRuntime(
                service=service,
                max_inbound_sessions=20,
                max_pending_handshakes=6,
                max_pending_handshakes_per_ip=2,
                inbound_handshake_rate_limit_per_minute=1000,
                handshake_timeout=0.05,
                read_timeout=0.05,
                max_peer_aliases_per_node_id=3,
            )
            baseline_tasks = len(runtime._tasks)
            baseline_sessions = len(runtime._sessions)

            for batch in range(20):
                for index in range(12):
                    host = f"198.51.100.{10 + (index % 3)}"
                    await runtime._handle_inbound_connection(HangingReader(), FakeWriter(host, 43000 + batch * 20 + index))
                await asyncio.sleep(0.06)

            await asyncio.sleep(1.2)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            gc.collect()

            metrics = runtime.runtime_memory_metrics()
            assert metrics["sessions_total"] == baseline_sessions
            assert metrics["pending_handshakes"] == 0
            assert len(runtime._tasks) == baseline_tasks
            assert metrics["peerbook_entries"] <= runtime.peerbook_max_size
            assert metrics["aliases_total"] <= runtime.max_peer_aliases_per_node_id

    asyncio.run(scenario())
