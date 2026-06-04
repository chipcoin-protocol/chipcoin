#!/usr/bin/env python3
"""Report mining share by coinbase payout address for a block range."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from chipcoin.node.service import NodeService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Examples:\n"
            "  mining-share-report.py 5000 5781\n"
            "  mining-share-report.py --last 700\n"
            "  mining-share-report.py 5000 5781 --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("range", nargs="*", type=int, metavar="HEIGHT", help="Optional positional range: START END.")
    parser.add_argument("--data", type=Path, default=Path("/runtime/node.sqlite3"), help="SQLite node database path.")
    parser.add_argument("--network", default="testnet", choices=("mainnet", "testnet", "devnet"))
    range_group = parser.add_mutually_exclusive_group()
    range_group.add_argument("--last", type=int, help="Count the last N blocks ending at the current tip.")
    range_group.add_argument("--start", type=int, help="Start height, inclusive. Use positional START END by default.")
    parser.add_argument("--end", type=int, help="End height, inclusive. Defaults to tip with --start or --last.")
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        metavar="ADDRESS=NAME",
        help="Optional wallet label. Can be repeated.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a text table.")
    return parser.parse_args()


def parse_labels(values: list[str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"invalid --label {value!r}; expected ADDRESS=NAME")
        address, label = value.split("=", 1)
        address = address.strip()
        label = label.strip()
        if not address or not label:
            raise SystemExit(f"invalid --label {value!r}; address and name are required")
        labels[address] = label
    return labels


def resolve_range(
    *,
    tip_height: int,
    positional_range: list[int],
    last: int | None,
    start: int | None,
    end: int | None,
) -> tuple[int, int]:
    if len(positional_range) not in {0, 2}:
        raise SystemExit("provide either positional START END, --last N, or --start HEIGHT [--end HEIGHT]")
    if positional_range and (last is not None or start is not None or end is not None):
        raise SystemExit("positional START END cannot be combined with --last, --start, or --end")
    if positional_range:
        resolved_start, resolved_end = positional_range
        if resolved_start < 0:
            raise SystemExit("START must be non-negative")
        if resolved_end < resolved_start:
            raise SystemExit("END must be greater than or equal to START")
        return resolved_start, resolved_end

    if last is not None:
        if last <= 0:
            raise SystemExit("--last must be greater than zero")
        resolved_end = tip_height if end is None else end
        resolved_start = max(0, resolved_end - last + 1)
        return resolved_start, resolved_end

    if start is None:
        raise SystemExit("provide positional START END, --last N, or --start HEIGHT")
    if start < 0:
        raise SystemExit("--start must be non-negative")
    resolved_end = tip_height if end is None else end
    if resolved_end < start:
        raise SystemExit("--end must be greater than or equal to --start")
    return start, resolved_end


def main() -> int:
    args = parse_args()
    labels = parse_labels(args.label)
    service = NodeService.open_sqlite(args.data, network=args.network)
    tip = service.chain_tip()
    if tip is None:
        raise SystemExit("no chain tip")

    start, end = resolve_range(
        tip_height=tip.height,
        positional_range=args.range,
        last=args.last,
        start=args.start,
        end=args.end,
    )
    counts: Counter[str] = Counter()
    missing_heights: list[int] = []

    for height in range(start, end + 1):
        block = service.get_block_by_height(height)
        if block is None or not block.transactions or not block.transactions[0].outputs:
            missing_heights.append(height)
            continue
        counts[block.transactions[0].outputs[0].recipient] += 1

    total = sum(counts.values())
    rows = [
        {
            "miner_address": address,
            "label": labels.get(address, ""),
            "blocks_mined": count,
            "share_percent": round((count * 100 / total) if total else 0.0, 2),
        }
        for address, count in counts.most_common()
    ]

    payload = {
        "network": args.network,
        "tip_height": tip.height,
        "start_height": start,
        "end_height": end,
        "requested_block_count": end - start + 1,
        "counted_blocks": total,
        "missing_block_count": len(missing_heights),
        "missing_heights": missing_heights,
        "miners": rows,
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(f"network: {args.network}")
    print(f"tip_height: {tip.height}")
    print(f"height_range: {start}-{end}")
    print(f"counted_blocks: {total}")
    print(f"missing_blocks: {len(missing_heights)}")
    print()
    print(f"{'blocks':>6}  {'share':>7}  {'label':<18}  miner_wallet")
    print(f"{'-' * 6}  {'-' * 7}  {'-' * 18}  {'-' * 42}")
    for row in rows:
        label = row["label"] or "-"
        print(f"{row['blocks_mined']:6d}  {row['share_percent']:6.2f}%  {label:<18}  {row['miner_address']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
