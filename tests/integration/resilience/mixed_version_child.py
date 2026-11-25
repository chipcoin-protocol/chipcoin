"""Disposable old-release source node for the mixed-version P2P gate."""

import asyncio
import json
import signal
from pathlib import Path
import sys
import chipcoin
from chipcoin.consensus.serialization import serialize_block_header

from chipcoin.node.runtime import NodeRuntime
from tests.node.test_runtime_integration import _make_service, _mine_block


async def main() -> None:
    service = _make_service(Path(sys.argv[1]), start_time=1_700_000_000)
    blocks = []
    for _ in range(10):
        block = _mine_block(service.build_candidate_block("CHCminer-a").block)
        service.apply_block(block)
        blocks.append(block)
    runtime = NodeRuntime(service=service, listen_host="127.0.0.1", listen_port=0, ping_interval=0.2)
    await runtime.start()
    tip = service.chain_tip()
    print(json.dumps({"source": chipcoin.__file__, "port": runtime.bound_port, "height": tip.height, "hash": tip.block_hash,
                      "first_hash": blocks[0].block_hash(),
                      "first_header": serialize_block_header(blocks[0].header).hex(),
                      "work": service.status(include_supply=False)["cumulative_work"]}), flush=True)
    stop = asyncio.Event()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set)
    try:
        await stop.wait()
    finally:
        await runtime.stop()


asyncio.run(main())
