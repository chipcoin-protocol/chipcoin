#!/usr/bin/env python3
"""Verify a persisted raw transaction against its public manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from chipcoin.consensus.serialization import deserialize_transaction


def evidence(raw_text: str) -> dict[str, object]:
    normalized = raw_text.strip()
    payload = bytes.fromhex(normalized)
    tx, offset = deserialize_transaction(payload)
    if offset != len(payload):
        raise ValueError("trailing bytes after serialized transaction")
    return {
        "txid": tx.txid(),
        "raw_sha256": hashlib.sha256((normalized + "\n").encode()).hexdigest(),
        "inputs": [
            {
                "txid": item.previous_output.txid,
                "vout": item.previous_output.index,
                "scheme_id": item.sig_scheme_id,
                "signature_length": len(item.signature),
                "signature_sha256": hashlib.sha256(item.signature).hexdigest(),
                "public_key_length": len(item.public_key),
                "public_key_sha256": hashlib.sha256(item.public_key).hexdigest(),
            }
            for item in tx.inputs
        ],
        "outputs": [
            {"vout": index, "recipient": item.recipient, "value_chipbits": int(item.value)}
            for index, item in enumerate(tx.outputs)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    actual = evidence(args.raw.read_text(encoding="ascii"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    expected = {
        "txid": manifest["expected_txid"],
        "raw_sha256": manifest["raw_sha256"],
        "inputs": manifest["inputs"],
        "outputs": manifest["outputs"],
    }
    if actual != expected:
        print(json.dumps({"status": "FAIL", "expected": expected, "actual": actual}, sort_keys=True))
        return 1
    print(json.dumps({"status": "PASS", **actual}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
