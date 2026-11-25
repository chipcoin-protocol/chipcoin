"""Connect two RC nodes to an old-release source, then verify P2P convergence."""

import asyncio
import json
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, sys.argv[2])
sys.path.insert(0, f"{sys.argv[2]}/src")

from chipcoin.node.peers import PeerInfo
from chipcoin.node.runtime import NodeRuntime, OutboundPeer
from chipcoin.node.sync import SyncManager
from chipcoin.consensus.serialization import deserialize_block_header
from chipcoin.storage.db import SCHEMA_STATEMENTS
from tests.node.test_runtime_integration import _make_service, _wait_until


async def main() -> None:
    with TemporaryDirectory() as directory:
        base = Path(directory)
        old_env = dict(os.environ)
        old_env["PYTHONPATH"] = f"{sys.argv[1]}/src:{sys.argv[2]}"
        old = await asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).with_name("mixed_version_child.py")), str(base / "old.sqlite3"),
            env=old_env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        nodes = []
        try:
            ready = await asyncio.wait_for(old.stdout.readline(), timeout=20)
            if not ready:
                raise RuntimeError((await old.stderr.read()).decode()[-2000:])
            expected = json.loads(ready)
            assert expected["source"].startswith(f"{sys.argv[1]}/src/"), expected["source"]
            target_path = base / "target.sqlite3"
            with sqlite3.connect(target_path) as legacy:
                legacy.execute(SCHEMA_STATEMENTS[0].replace("raw_header BLOB NOT NULL", "raw_header BLOB"))
            for name, start_time in (("target", 1_700_001_000), ("observer", 1_700_002_000)):
                service = _make_service(target_path if name == "target" else base / "observer.sqlite3", start_time=start_time)
                if name == "target":
                    header, offset = deserialize_block_header(bytes.fromhex(expected["first_header"]))
                    assert offset == 80 and header.block_hash() == expected["first_hash"]
                    service.headers.put(header, height=0, cumulative_work=2)
                    service.headers.connection.execute(
                        "UPDATE headers SET raw_header = NULL WHERE block_hash = ?", (expected["first_hash"],),
                    )
                    service.peerbook.add(PeerInfo(host=None, port=8333, network="mainnet"))
                    assert SyncManager(node=service).sync_status()["phase"] == "syncing_from_genesis"
                runtime = NodeRuntime(
                    service=service, listen_host="127.0.0.1", listen_port=0,
                    outbound_peers=[OutboundPeer("127.0.0.1", expected["port"])],
                    connect_interval=0.1, ping_interval=0.2, sync_scheduler_interval=0.1,
                )
                await runtime.start()
                nodes.append((name, service, runtime))
            await _wait_until(
                lambda: all(service.chain_tip() is not None and service.chain_tip().block_hash == expected["hash"]
                            for _, service, _ in nodes), timeout=30,
            )
            for name, service, runtime in nodes:
                status = service.status(include_supply=False)
                assert status["height"] == expected["height"]
                assert status["cumulative_work"] == expected["work"]
                assert runtime.connected_peer_count() >= 1
                if name == "target":
                    assert service.headers.get_record(expected["first_hash"]) is not None
                print(json.dumps({"node": name, "height": status["height"], "hash": service.chain_tip().block_hash,
                                  "work": status["cumulative_work"], "peers": runtime.connected_peer_count()}))
            print("MIXED_VERSION_P2P_PASS")
        finally:
            for _, _, runtime in reversed(nodes):
                await runtime.stop()
            if old.returncode is None:
                old.terminate()
            await asyncio.wait_for(old.wait(), timeout=10)


asyncio.run(main())
