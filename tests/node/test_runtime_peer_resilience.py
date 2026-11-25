"""Inbound and ban handling survive one malformed persisted peer."""

import asyncio
from pathlib import Path

from chipcoin.node.peers import PeerInfo
from chipcoin.node.runtime import NodeRuntime
from chipcoin.node.service import NodeService


def test_inbound_admission_error_closes_only_its_writer(tmp_path: Path) -> None:
    class Writer:
        closed = False

        def close(self) -> None:
            self.closed = True

        async def wait_closed(self) -> None:
            return None

    async def scenario() -> None:
        service = NodeService.open_sqlite(tmp_path / "node.sqlite3", network="devnet")
        runtime = NodeRuntime(service=service)

        async def failed_admission(_reader, _writer) -> None:
            raise TypeError("synthetic peerbook error")

        runtime._accept_inbound_connection = failed_admission
        writer = Writer()
        await runtime._handle_inbound_connection(None, writer)
        assert writer.closed
        assert runtime._sessions == {}

    asyncio.run(scenario())


def test_ban_enforcement_includes_quarantined_same_network_alias(tmp_path: Path) -> None:
    service = NodeService.open_sqlite(tmp_path / "node.sqlite3", network="devnet", time_provider=lambda: 100)
    service.peerbook.add(PeerInfo(host="banned.example", port=None, network="devnet", ban_until=200))  # type: ignore[arg-type]
    runtime = NodeRuntime(service=service)
    assert runtime._ban_state_for_peer("banned.example", 12345) == (True, 200)
