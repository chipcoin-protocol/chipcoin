"""Measure 100 local WSGI GET /v1/block requests on a disposable chain.

Run with ``PYTHONPATH=src:. .venv/bin/python scripts/benchmarks/bench_block_http.py``
before and after changing NodeService.inspect_block. Chain construction is
excluded from the timed region; no production node is used.
"""

from __future__ import annotations

import json
import statistics
import time
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from chipcoin.interfaces.http_api import HttpApiApp
from tests.node.test_http_api import _make_service, _mine_block


def main() -> None:
    with TemporaryDirectory(prefix="chipcoin-block-bench-") as tempdir:
        service = _make_service(Path(tempdir) / "bench.sqlite3")
        for _ in range(100):
            service.apply_block(_mine_block(service.build_candidate_block("CHCminer").block))
        app = HttpApiApp(service)
        replay_calls = 0
        replay_seconds = 0.0
        original_replay = service._replay_chain_state_before_height

        def timed_replay(height: int):
            nonlocal replay_calls, replay_seconds
            replay_calls += 1
            start = time.perf_counter()
            try:
                return original_replay(height)
            finally:
                replay_seconds += time.perf_counter() - start

        service._replay_chain_state_before_height = timed_replay
        elapsed = []
        for height in range(100):
            environ = {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/v1/block",
                "QUERY_STRING": f"height={height}",
                "CONTENT_LENGTH": "0",
                "wsgi.input": BytesIO(),
            }
            status = []
            start = time.perf_counter()
            body = b"".join(app(environ, lambda code, _headers: status.append(code)))
            elapsed.append(time.perf_counter() - start)
            assert status == ["200 OK"]
            assert json.loads(body)["fees_chipbits"] == 0
        print(json.dumps({
            "requests": len(elapsed),
            "total_seconds": round(sum(elapsed), 6),
            "mean_ms": round(statistics.mean(elapsed) * 1000, 3),
            "median_ms": round(statistics.median(elapsed) * 1000, 3),
            "max_ms": round(max(elapsed) * 1000, 3),
            "replay_calls": replay_calls,
            "replay_seconds": round(replay_seconds, 6),
            "scope": "in-process WSGI /v1/block; 100 coinbase-only heights",
        }, sort_keys=True))


if __name__ == "__main__":
    main()
