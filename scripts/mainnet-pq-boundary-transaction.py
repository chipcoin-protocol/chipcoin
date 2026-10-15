#!/usr/bin/env python3
"""Build one explicit-input ML-DSA-44 transaction for the mainnet maturity test."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from chipcoin.consensus.serialization import serialize_transaction
from chipcoin.interfaces.cli import _load_wallet_key
from chipcoin.wallet.models import SpendCandidate
from chipcoin.wallet.signer import TransactionSigner


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wallet-file", required=True, type=Path)
    parser.add_argument("--source-txid", required=True)
    parser.add_argument("--source-vout", required=True, type=int)
    parser.add_argument("--source-value", required=True, type=int)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--amount", required=True, type=int)
    parser.add_argument("--fee", required=True, type=int)
    args = parser.parse_args()

    wallet = _load_wallet_key(args.wallet_file)
    built = TransactionSigner(wallet).build_signed_transaction(
        spend_candidates=[
            SpendCandidate(
                txid=args.source_txid,
                index=args.source_vout,
                amount_chipbits=args.source_value,
                recipient=wallet.address,
            )
        ],
        recipient=args.destination,
        amount_chipbits=args.amount,
        fee_chipbits=args.fee,
        network="mainnet",
    )
    transaction = built.transaction
    inputs = [
        {
            "txid": tx_input.previous_output.txid,
            "vout": tx_input.previous_output.index,
            "scheme_id": tx_input.sig_scheme_id,
            "signature_length": len(tx_input.signature),
            "signature_sha256": hashlib.sha256(tx_input.signature).hexdigest(),
            "public_key_length": len(tx_input.public_key),
            "public_key_sha256": hashlib.sha256(tx_input.public_key).hexdigest(),
        }
        for tx_input in transaction.inputs
    ]
    outputs = [
        {"vout": index, "recipient": output.recipient, "value_chipbits": int(output.value)}
        for index, output in enumerate(transaction.outputs)
    ]
    print(json.dumps({
        "txid": transaction.txid(),
        "raw_hex": serialize_transaction(transaction).hex(),
        "source": {
            "txid": args.source_txid,
            "vout": args.source_vout,
            "value_chipbits": args.source_value,
            "address": wallet.address,
        },
        "destination": args.destination,
        "amount_chipbits": args.amount,
        "fee_chipbits": built.fee_chipbits,
        "change_chipbits": built.change_chipbits,
        "signature_scheme_id": wallet.scheme_id,
        "signature_scheme_name": wallet.scheme_name,
        "address_kind": wallet.address_kind,
        "inputs": inputs,
        "outputs": outputs,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
