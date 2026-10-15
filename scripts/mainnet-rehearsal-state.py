#!/usr/bin/env python3
"""Emit deterministic consensus state fingerprints without exposing secrets."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from chipcoin.node.service import NodeService


def digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument(
        "--address",
        action="append",
        default=[],
        metavar="LABEL=ADDRESS",
        help="Include a derived balance without reading wallet private material.",
    )
    args = parser.parse_args()
    service = NodeService.open_sqlite(Path(args.data), network="mainnet")
    status = service.status()
    utxos = sorted([
        {
            "txid": outpoint.txid,
            "index": outpoint.index,
            "value": entry.output.value,
            "recipient": entry.output.recipient,
            "coinbase": entry.is_coinbase,
            "origin_height": entry.height,
        }
        for outpoint, entry in service.chainstate.list_utxos()
    ], key=lambda item: (item["txid"], item["index"]))
    registry = sorted(
        [asdict(record) for record in service.node_registry.list_records()],
        key=lambda item: (str(item["node_id"]), str(item["payout_address"])),
    )
    settlements = sorted(
        [asdict(stored) for stored in service.reward_settlements.list_settlements()],
        key=lambda item: (
            int(item["block_height"]),
            int(item["settlement"]["epoch_index"]),
            str(item["txid"]),
        ),
    )
    attestations = sorted(
        [asdict(stored) for stored in service.reward_attestations.list_bundles()],
        key=lambda item: (
            int(item["block_height"]),
            int(item["bundle"]["epoch_index"]),
            int(item["bundle"]["bundle_window_index"]),
            str(item["txid"]),
        ),
    )
    balances = {}
    for raw in args.address:
        if "=" not in raw:
            raise SystemExit(f"invalid --address {raw!r}; expected LABEL=ADDRESS")
        label, address = raw.split("=", 1)
        balances[label] = service.balance_diagnostics(address)
    sqlite_checks = {"quick_check": [], "foreign_key_check": []}
    if service.connection is not None:
        sqlite_checks = {
            "quick_check": [str(row[0]) for row in service.connection.execute("PRAGMA quick_check").fetchall()],
            "foreign_key_check": [list(row) for row in service.connection.execute("PRAGMA foreign_key_check").fetchall()],
        }
    print(json.dumps({
        "height": status["height"],
        "tip_hash": status["tip_hash"],
        "cumulative_work": status["cumulative_work"],
        "handshaken_peer_count": status["handshaken_peer_count"],
        "mempool_size": status["mempool_size"],
        "sync_phase": status["sync_phase"],
        "supply": service.supply_snapshot(),
        "utxo_count": len(utxos),
        "utxo_hash": digest(utxos),
        "reward_registry_count": len(registry),
        "reward_registry_hash": digest(registry),
        "reward_settlement_count": len(settlements),
        "reward_settlement_hash": digest(settlements),
        "reward_attestation_bundle_count": len(attestations),
        "reward_attestation_hash": digest(attestations),
        "reward_distributed_chipbits": sum(
            int(item["settlement"]["distributed_node_reward_chipbits"])
            for item in settlements
        ),
        "balances": balances,
        "balances_hash": digest(balances),
        "sqlite": sqlite_checks,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
