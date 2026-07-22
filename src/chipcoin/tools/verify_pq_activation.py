"""Verify the compiled Post-Quantum activation height for an installed build."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass

from ..consensus.pq_activation import (
    PQ_SUPPORT_DEVNET_ACTIVATION_HEIGHT,
    PQ_SUPPORT_MAINNET_ACTIVATION_HEIGHT,
    PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT,
    pq_support_activation_height,
)


VALID_NETWORKS = {"mainnet", "devnet", "testnet"}
DEFAULT_EXPECTED_HEIGHTS = {
    "mainnet": PQ_SUPPORT_MAINNET_ACTIVATION_HEIGHT,
    "devnet": PQ_SUPPORT_DEVNET_ACTIVATION_HEIGHT,
    "testnet": PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT,
}


@dataclass(frozen=True)
class ActivationVerification:
    schema_version: int
    network: str
    actual_activation_height: int
    expected_activation_height: int
    status: str


def verify_activation_height(network: str, expected_height: int | None = None) -> ActivationVerification:
    """Return the compiled activation height and PASS/FAIL status."""

    normalized = network.lower()
    if normalized not in VALID_NETWORKS:
        raise ValueError(f"unsupported network: {network}")
    expected = DEFAULT_EXPECTED_HEIGHTS[normalized] if expected_height is None else expected_height
    if expected < 0:
        raise ValueError("expected height must be non-negative")
    actual = pq_support_activation_height(normalized)
    return ActivationVerification(
        schema_version=1,
        network=normalized,
        actual_activation_height=actual,
        expected_activation_height=expected,
        status="PASS" if actual == expected else "FAIL",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify the compiled Chipcoin PQ activation height.")
    parser.add_argument("--network", default="testnet", help="Network to verify. Default: testnet.")
    parser.add_argument("--expected-height", type=int, default=None, help="Expected activation height.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = verify_activation_height(args.network, args.expected_height)
    except ValueError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "network": args.network,
                        "status": "ERROR",
                        "error": str(exc),
                    },
                    sort_keys=True,
                )
            )
        else:
            print(f"Status: ERROR\nReason: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - defensive operational boundary
        if args.json:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "network": args.network,
                        "status": "ERROR",
                        "error": str(exc),
                    },
                    sort_keys=True,
                )
            )
        else:
            print(f"Status: ERROR\nReason: {exc}", file=sys.stderr)
        return 3

    payload = asdict(result)
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Network: {result.network}")
        print(f"PQ activation height: {result.actual_activation_height}")
        print(f"Expected activation height: {result.expected_activation_height}")
        print(f"Status: {result.status}")
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
