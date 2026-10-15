"""Cross-network replay regression tests for PQ transaction signatures."""

from __future__ import annotations

import pytest

from chipcoin.consensus.models import OutPoint, TxOutput
from chipcoin.consensus.params import MAINNET_PARAMS, TESTNET_PARAMS
from chipcoin.consensus.pq_activation import pq_support_activation_height
from chipcoin.consensus.serialization import serialize_transaction
from chipcoin.consensus.utxo import InMemoryUtxoView, UtxoEntry
from chipcoin.consensus.validation import ContextualValidationError, ValidationContext, validate_transaction
from chipcoin.wallet.models import SpendCandidate
from chipcoin.wallet.signer import TransactionSigner, wallet_key_from_mldsa44_seed


SOURCE = wallet_key_from_mldsa44_seed(bytes.fromhex("42" * 32))
DESTINATION = wallet_key_from_mldsa44_seed(bytes.fromhex("43" * 32))
OUTPOINT = OutPoint(txid="55" * 32, index=0)
VALUE = 5_000_000
AMOUNT = 4_000_000
FEE = 1_000


def _view() -> InMemoryUtxoView:
    return InMemoryUtxoView.from_entries([
        (
            OUTPOINT,
            UtxoEntry(
                output=TxOutput(value=VALUE, recipient=SOURCE.address),
                height=0,
                is_coinbase=False,
            ),
        ),
    ])


def _context(network: str) -> ValidationContext:
    if network == "mainnet":
        return ValidationContext(height=1, median_time_past=0, params=MAINNET_PARAMS, utxo_view=_view(), network=network)
    return ValidationContext(
        height=pq_support_activation_height("testnet", params=TESTNET_PARAMS),
        median_time_past=0,
        params=TESTNET_PARAMS,
        utxo_view=_view(),
        network=network,
    )


def _signed_for(network: str):
    return TransactionSigner(SOURCE).build_signed_transaction(
        spend_candidates=[
            SpendCandidate(
                txid=OUTPOINT.txid,
                index=OUTPOINT.index,
                amount_chipbits=VALUE,
                recipient=SOURCE.address,
            ),
        ],
        recipient=DESTINATION.address,
        amount_chipbits=AMOUNT,
        fee_chipbits=FEE,
        network=network,
    ).transaction


@pytest.mark.parametrize(
    ("source_network", "target_network"),
    [("mainnet", "testnet"), ("testnet", "mainnet")],
)
def test_same_serialized_pq_transaction_is_rejected_cross_network(source_network: str, target_network: str) -> None:
    transaction = _signed_for(source_network)
    raw_before = serialize_transaction(transaction)
    source_context = _context(source_network)
    target_context = _context(target_network)

    assert validate_transaction(transaction, source_context) == FEE
    with pytest.raises(ContextualValidationError, match="Input signature is invalid"):
        validate_transaction(transaction, target_context)

    assert serialize_transaction(transaction) == raw_before
    assert source_context.utxo_view.get(OUTPOINT) is not None
    assert target_context.utxo_view.get(OUTPOINT) is not None
