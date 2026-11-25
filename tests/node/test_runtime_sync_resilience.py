"""Critical runtime loops must survive a recoverable status calculation error."""

import asyncio
from pathlib import Path

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

