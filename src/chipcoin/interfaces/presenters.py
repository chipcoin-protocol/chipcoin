"""Shared formatting helpers for CLI and HTTP adapters."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from ..consensus.economics import CHCBITS_PER_CHC
from ..consensus.validation import block_weight_units
from ..consensus.models import Block, Transaction
from ..crypto.addresses import parse_address
from ..crypto.pq import get_signature_scheme, is_known_signature_scheme
from ..node.mining import transaction_weight_units


def _signature_scheme_name(scheme_id: int) -> str | None:
    """Return the registered display name for a transaction input scheme."""

    if not is_known_signature_scheme(scheme_id):
        return None
    return get_signature_scheme(scheme_id).name


def _format_output_address(recipient: str) -> dict[str, object]:
    """Return structured address metadata for an output recipient."""

    info = parse_address(recipient)
    return {
        "address_kind": info.kind,
        "address_scheme_id": info.scheme_id,
    }


def format_tip(tip) -> dict | None:
    """Convert a chain tip object into a JSON-friendly mapping."""

    return {"height": None, "block_hash": None} if tip is None else {"height": tip.height, "block_hash": tip.block_hash}


def format_amount_chc(amount_chipbits: int) -> str:
    """Convert an integer chipbit amount to a fixed-scale CHC string."""

    amount_chc = (Decimal(amount_chipbits) / Decimal(CHCBITS_PER_CHC)).quantize(
        Decimal("0.00000001"),
        rounding=ROUND_DOWN,
    )
    return format(amount_chc, "f")


def format_transaction(transaction: Transaction) -> dict:
    """Convert a transaction into an adapter-friendly mapping."""

    return {
        "txid": transaction.txid(),
        "version": transaction.version,
        "locktime": transaction.locktime,
        "inputs": [
            {
                "txid": tx_input.previous_output.txid,
                "index": tx_input.previous_output.index,
                "sequence": tx_input.sequence,
                "sig_scheme_id": tx_input.sig_scheme_id,
                "sig_scheme_name": _signature_scheme_name(tx_input.sig_scheme_id),
                "signature_hex": tx_input.signature.hex(),
                "public_key_hex": tx_input.public_key.hex(),
            }
            for tx_input in transaction.inputs
        ],
        "outputs": [
            {
                "value": int(tx_output.value),
                "recipient": tx_output.recipient,
                **_format_output_address(tx_output.recipient),
            }
            for tx_output in transaction.outputs
        ],
        "metadata": dict(transaction.metadata),
    }


def format_block(block: Block) -> dict:
    """Convert a block into an adapter-friendly mapping."""

    return {
        "block_hash": block.block_hash(),
        "weight_units": block_weight_units(block),
        "transaction_count": len(block.transactions),
        "header": {
            "version": block.header.version,
            "previous_block_hash": block.header.previous_block_hash,
            "merkle_root": block.header.merkle_root,
            "timestamp": block.header.timestamp,
            "bits": block.header.bits,
            "nonce": block.header.nonce,
        },
        "transactions": [
            {
                **format_transaction(transaction),
                "weight_units": transaction_weight_units(transaction),
            }
            for transaction in block.transactions
        ],
    }


def format_transaction_lookup(result: dict | None) -> dict | None:
    """Convert a transaction lookup result into a JSON-friendly mapping."""

    if result is None:
        return None
    return {
        "location": result["location"],
        "block_hash": result["block_hash"],
        "height": result["height"],
        "transaction": format_transaction(result["transaction"]),
    }
