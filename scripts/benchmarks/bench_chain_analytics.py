"""Benchmark chain analytics on a disposable dev chain or a copied Mainnet DB.

Run with ``PYTHONPATH=src:. .venv/bin/python scripts/benchmarks/bench_chain_analytics.py``.
``--db`` is copied into a temporary working directory before NodeService opens it.
Chain construction and copying are excluded from timed measurements.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import shutil
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from chipcoin.node.service import NodeService
from chipcoin.storage.headers import ChainTip
from tests.node.test_http_api import _make_service, _mine_block


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, help="consistent SQLite copy, never the live node database")
    parser.add_argument("--max-height", type=int, default=249)
    parser.add_argument(
        "--method", action="append", choices=("reward_history", "mining_history", "top_miners"),
        help="run only this analysis; may be specified more than once",
    )
    args = parser.parse_args()
    with TemporaryDirectory(prefix="chipcoin-analytics-bench-") as tempdir:
        work_db = Path(tempdir) / "bench.sqlite3"
        if args.db is None:
            service = _make_service(work_db)
            for _ in range(100):
                service.apply_block(_mine_block(service.build_candidate_block("CHCminer").block))
            max_height = 99
            recipient = "CHCminer"
            source = "synthetic"
        else:
            if args.max_height < 0:
                parser.error("--max-height must be nonnegative")
            shutil.copy2(args.db, work_db)
            service = NodeService.open_sqlite(work_db, network="mainnet")
            tip = service.chain_tip()
            if tip is None or tip.height < args.max_height:
                parser.error("database tip is below --max-height")
            if service.snapshot_anchor() is not None:
                parser.error("full-history benchmark needs a non-snapshot node copy")
            max_height = args.max_height
            counts = Counter()
            for height in range(max_height + 1):
                block = service.get_block_by_height(height)
                if block and block.transactions and block.transactions[0].outputs:
                    counts[block.transactions[0].outputs[0].recipient] += 1
            if not counts:
                parser.error("no miner payouts found in selected range")
            recipient = max(counts, key=lambda address: (counts[address], address))
            cutoff_hash = service.headers.get_hash_at_height(max_height)
            service.chain_tip = lambda: ChainTip(block_hash=cutoff_hash, height=max_height)
            source = "mainnet_sqlite_copy"

        replay_calls = 0
        original_replay = service._replay_chain_state_before_height

        def counted_replay(height: int):
            nonlocal replay_calls
            replay_calls += 1
            return original_replay(height)

        service._replay_chain_state_before_height = counted_replay
        for name, run in (
            ("reward_history", lambda: service.reward_history(
                recipient, limit=10_000, start_height=0, end_height=max_height,
            )),
            ("mining_history", lambda: service.mining_history(recipient, limit=10_000)),
            ("top_miners", lambda: service.top_miners(limit=10)),
        ):
            if args.method is not None and name not in args.method:
                continue
            replay_calls = 0
            start = time.perf_counter()
            result = run()
            duration = time.perf_counter() - start
            digest = hashlib.sha256(
                json.dumps(result, sort_keys=True).encode("utf-8")
            ).hexdigest()
            print(json.dumps({
                "method": name,
                "seconds": round(duration, 6),
                "replay_calls": replay_calls,
                "rows": len(result),
                "result_sha256": digest,
                "chain_height": max_height,
                "source": source,
            }, sort_keys=True))


if __name__ == "__main__":
    main()
