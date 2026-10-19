#!/usr/bin/env python3
"""Mine and emit the public-mainnet genesis after timestamp approval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from chipcoin.consensus.genesis import genesis_manifest, mine_genesis_parallel, write_genesis_artifacts
from chipcoin.consensus.params import MAINNET_PARAMS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timestamp", type=int, required=True, help="Founder-approved UTC Unix timestamp")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--acknowledge-founder-approved-timestamp", action="store_true", required=True)
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise SystemExit(f"output directory already exists: {output_dir}")
    block = mine_genesis_parallel(
        timestamp=args.timestamp,
        bits=MAINNET_PARAMS.genesis_bits,
        workers=args.workers,
    )
    manifest = genesis_manifest(block)
    write_genesis_artifacts(output_dir, block)
    print(json.dumps(manifest.as_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
