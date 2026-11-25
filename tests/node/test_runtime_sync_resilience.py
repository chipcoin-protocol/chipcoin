"""Critical runtime loops must survive a recoverable status calculation error."""

import asyncio
from pathlib import Path

import pytest

from chipcoin.node.runtime import NodeRuntime
from chipcoin.node.service import NodeService


def test_sync_scheduler_retries_after_status_error(tmp_path: Path) -> None:
    async def scenario() -> None:
        service = NodeService.open_sqlite(tmp_path / "node.sqlite3", network="devnet")
        runtime = NodeRuntime(service=service, sync_scheduler_interval=0.001)
        runtime._running = True
        service.set_runtime_sync_status({"mode": "synced", "phase": "synced"})
        calls = 0

        async def noop() -> None:
            return None

        def update_status() -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TypeError("synthetic incomplete header")
            assert service.sync_status()["phase"] == "syncing_from_genesis"
            runtime._running = False
            service.set_runtime_sync_status({"mode": "synced", "phase": "synced"})

        runtime._expire_stalled_block_requests = noop
        runtime._drive_header_sync = noop
        runtime._dispatch_block_downloads = noop
        runtime._activate_ready_best_chain = lambda: None
        runtime._update_sync_status = update_status
        await asyncio.wait_for(runtime._sync_scheduler_loop(), timeout=1)
        assert calls == 2
        assert service.sync_status()["phase"] == "synced"

    asyncio.run(scenario())


def test_persistent_status_error_is_rate_limited_and_stays_degraded(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    async def scenario() -> None:
        service = NodeService.open_sqlite(tmp_path / "node.sqlite3", network="devnet")
        runtime = NodeRuntime(service=service, sync_scheduler_interval=0.001)
        runtime._running = True
        calls = 0
        degraded = []

        async def noop() -> None:
            return None

        def update_status() -> None:
            nonlocal calls
            calls += 1
            if calls == 4:
                runtime._running = False
            raise TypeError("synthetic persistent header failure")

        def failed_snapshot() -> dict:
            raise TypeError("synthetic status snapshot failure")

        runtime._expire_stalled_block_requests = noop
        runtime._drive_header_sync = noop
        runtime._dispatch_block_downloads = noop
        runtime._activate_ready_best_chain = lambda: None
        runtime._update_sync_status = update_status
        service.sync_status = failed_snapshot
        service.set_runtime_sync_status = lambda status: degraded.append(status)
        await asyncio.wait_for(runtime._sync_scheduler_loop(), timeout=1)
        assert calls == 4
        assert len(degraded) == 4
        assert all(status["phase"] == "syncing_from_genesis" for status in degraded)

    asyncio.run(scenario())
    assert caplog.text.count("sync scheduler iteration failed") == 1
    assert caplog.text.count("sync status snapshot unavailable") == 1


def test_scheduler_survives_failure_while_marking_degraded_status(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    async def scenario() -> None:
        service = NodeService.open_sqlite(tmp_path / "node.sqlite3", network="devnet")
        runtime = NodeRuntime(service=service, sync_scheduler_interval=0.001)
        runtime._running = True
        calls = 0

        async def noop() -> None:
            return None

        def update_status() -> None:
            nonlocal calls
            calls += 1
            if calls == 3:
                runtime._running = False
            raise TypeError("synthetic sync status error")

        def failed_marker(_status) -> None:
            raise TypeError("synthetic status marker error")

        runtime._expire_stalled_block_requests = noop
        runtime._drive_header_sync = noop
        runtime._dispatch_block_downloads = noop
        runtime._activate_ready_best_chain = lambda: None
        runtime._update_sync_status = update_status
        service.set_runtime_sync_status = failed_marker
        await asyncio.wait_for(runtime._sync_scheduler_loop(), timeout=1)
        assert calls == 3

    asyncio.run(scenario())
    assert caplog.text.count("sync scheduler iteration failed") == 1
    assert caplog.text.count("degraded sync status could not be published") == 1


def test_scheduler_survives_malformed_status_snapshot(tmp_path: Path) -> None:
    async def scenario() -> None:
        service = NodeService.open_sqlite(tmp_path / "node.sqlite3", network="devnet")
        runtime = NodeRuntime(service=service, sync_scheduler_interval=0.001)
        runtime._running = True
        calls = 0
        snapshots = []

        async def noop() -> None:
            return None

        def update_status() -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                runtime._running = False
            raise TypeError("synthetic scheduler failure")

        runtime._expire_stalled_block_requests = noop
        runtime._drive_header_sync = noop
        runtime._dispatch_block_downloads = noop
        runtime._activate_ready_best_chain = lambda: None
        runtime._update_sync_status = update_status
        service.sync_status = lambda: None
        service.set_runtime_sync_status = lambda status: snapshots.append(status)
        await asyncio.wait_for(runtime._sync_scheduler_loop(), timeout=1)
        assert calls == 2
        assert all(status["phase"] == "syncing_from_genesis" and status["mode"] == "headers" for status in snapshots)

    asyncio.run(scenario())
