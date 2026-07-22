"""Operational cryptographic benchmark for Chipcoin PQ planning."""

from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path
import statistics
import time
from dataclasses import dataclass

from ..consensus.hashes import double_sha256
from ..crypto.keys import derive_public_key
from ..crypto.pq.mldsa import derive_mldsa44_keypair, sign_mldsa44, verify_mldsa44
from ..crypto.signatures import sign_digest, verify_digest


@dataclass(frozen=True)
class BenchmarkStats:
    operation: str
    iterations: int
    total_seconds: float
    mean_seconds: float
    median_seconds: float
    max_seconds: float
    stdev_seconds: float
    throughput_per_second: float

    def as_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "iterations": self.iterations,
            "total_seconds": round(self.total_seconds, 6),
            "mean_seconds": round(self.mean_seconds, 6),
            "median_seconds": round(self.median_seconds, 6),
            "max_seconds": round(self.max_seconds, 6),
            "stdev_seconds": round(self.stdev_seconds, 6),
            "throughput_per_second": round(self.throughput_per_second, 2),
        }


def run_benchmark(*, verify_1000: bool = True) -> dict[str, object]:
    """Run a deterministic local ECDSA/ML-DSA benchmark."""

    ecdsa_private_key = bytes.fromhex("01".rjust(64, "0"))
    ecdsa_public_key = derive_public_key(ecdsa_private_key)
    mldsa_seed = bytes(range(32))
    digest = double_sha256(b"chipcoin:pq-benchmark:v1")

    mldsa_private_key, mldsa_public_key = _measure_value("mldsa44_keygen", lambda: derive_mldsa44_keypair(mldsa_seed))
    ecdsa_signature = sign_digest(ecdsa_private_key, digest)
    mldsa_signature = sign_mldsa44(mldsa_seed, digest)

    iterations_1000 = 1000 if verify_1000 else 100
    rss_start = _rss_mb()
    cpu_start = time.process_time()
    measurements = [
        _measure("ecdsa_keygen", 25, lambda: derive_public_key(ecdsa_private_key)),
        _measure("ecdsa_sign", 25, lambda: sign_digest(ecdsa_private_key, digest)),
        _measure("ecdsa_verify", 25, lambda: verify_digest(ecdsa_public_key, digest, ecdsa_signature)),
        _measure("ecdsa_verify_100", 100, lambda: verify_digest(ecdsa_public_key, digest, ecdsa_signature)),
        _measure("ecdsa_verify_1000", iterations_1000, lambda: verify_digest(ecdsa_public_key, digest, ecdsa_signature)),
        _measure("mldsa44_keygen", 5, lambda: derive_mldsa44_keypair(mldsa_seed)),
        _measure("mldsa44_sign", 5, lambda: sign_mldsa44(mldsa_seed, digest)),
        _measure("mldsa44_verify", 5, lambda: verify_mldsa44(mldsa_public_key, digest, mldsa_signature)),
        _measure("mldsa44_verify_100", 100, lambda: verify_mldsa44(mldsa_public_key, digest, mldsa_signature)),
        _measure("mldsa44_verify_1000", iterations_1000, lambda: verify_mldsa44(mldsa_public_key, digest, mldsa_signature)),
    ]
    cpu_seconds = time.process_time() - cpu_start
    rss_end = _rss_mb()
    return {
        "environment": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor() or "unknown",
        },
        "resources": {
            "process_cpu_seconds": round(cpu_seconds, 6),
            "rss_mb_start": rss_start,
            "rss_mb_end": rss_end,
            "rss_mb_delta": None if rss_start is None or rss_end is None else round(rss_end - rss_start, 2),
        },
        "digest_bytes": len(digest),
        "mldsa44_public_key_bytes": len(mldsa_public_key),
        "mldsa44_private_key_bytes": len(mldsa_private_key),
        "mldsa44_signature_bytes": len(mldsa_signature),
        "measurements": [measurement.as_dict() for measurement in measurements],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark Chipcoin ECDSA and ML-DSA verification cost.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--quick", action="store_true", help="Use 100 iterations instead of 1000 for the 1000-verify rows.")
    args = parser.parse_args(argv)
    result = run_benchmark(verify_1000=not args.quick)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    print("CHIPCOIN PQ BENCHMARK")
    print()
    for key, value in result["environment"].items():
        print(f"{key}: {value}")
    for key, value in result["resources"].items():
        print(f"{key}: {value}")
    print(f"digest_bytes: {result['digest_bytes']}")
    print(f"mldsa44_public_key_bytes: {result['mldsa44_public_key_bytes']}")
    print(f"mldsa44_private_key_bytes: {result['mldsa44_private_key_bytes']}")
    print(f"mldsa44_signature_bytes: {result['mldsa44_signature_bytes']}")
    print()
    print("operation\titerations\tmean_ms\tmedian_ms\tmax_ms\tstdev_ms\tthroughput_s")
    for row in result["measurements"]:
        print(
            f"{row['operation']}\t{row['iterations']}\t"
            f"{float(row['mean_seconds']) * 1000:.3f}\t"
            f"{float(row['median_seconds']) * 1000:.3f}\t"
            f"{float(row['max_seconds']) * 1000:.3f}\t"
            f"{float(row['stdev_seconds']) * 1000:.3f}\t"
            f"{row['throughput_per_second']}"
        )
    return 0


def _measure(operation: str, iterations: int, callable_) -> BenchmarkStats:
    durations = []
    start_total = time.perf_counter()
    for _ in range(iterations):
        started = time.perf_counter()
        callable_()
        durations.append(time.perf_counter() - started)
    total = time.perf_counter() - start_total
    return BenchmarkStats(
        operation=operation,
        iterations=iterations,
        total_seconds=total,
        mean_seconds=statistics.fmean(durations),
        median_seconds=statistics.median(durations),
        max_seconds=max(durations),
        stdev_seconds=0.0 if len(durations) < 2 else statistics.stdev(durations),
        throughput_per_second=iterations / total if total > 0 else 0.0,
    )


def _measure_value(operation: str, callable_):
    _ = operation
    return callable_()


def _rss_mb() -> float | None:
    statm = Path("/proc/self/statm")
    try:
        resident_pages = int(statm.read_text(encoding="utf-8").split()[1])
        return round((resident_pages * os.sysconf("SC_PAGE_SIZE")) / (1024 * 1024), 2)
    except (OSError, IndexError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
