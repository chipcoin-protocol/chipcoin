from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from chipcoin.consensus.economics import subsidy_split_chipbits
from chipcoin.consensus.merkle import merkle_root
from chipcoin.consensus.models import Block, BlockHeader, OutPoint, Transaction, TxOutput
from chipcoin.consensus.params import MAINNET_PARAMS
from chipcoin.consensus.serialization import serialize_transaction
from chipcoin.consensus.utxo import InMemoryUtxoView, UtxoEntry
from chipcoin.consensus.validation import (
    ContextualValidationError,
    ValidationContext,
    is_coinbase_mature,
    validate_block_stateful,
    validate_transaction,
)
from chipcoin.crypto.pq import SIG_SCHEME_ML_DSA_44
from chipcoin.node.service import NodeService
from chipcoin.wallet.signer import TransactionSigner, wallet_key_from_mldsa44_seed
from tests.helpers import spend_candidates_for_wallet


ORIGIN_HEIGHT = 0
COINBASE_VALUE_CHIPBITS = 5_000_000_000
SPEND_AMOUNT_CHIPBITS = 100_000_000
FEE_CHIPBITS = 1_000
IMMATURE_REASON = "Coinbase output is not mature enough to spend."


def _wallet(seed_byte: int):
    return wallet_key_from_mldsa44_seed(bytes((seed_byte,)) * 32)


def _source_and_spend():
    owner = _wallet(41)
    recipient = _wallet(42)
    source_coinbase = Transaction(
        version=2,
        inputs=(),
        outputs=(TxOutput(value=COINBASE_VALUE_CHIPBITS, recipient=owner.address),),
        metadata={"coinbase": "true", "height": str(ORIGIN_HEIGHT)},
    )
    source_outpoint = OutPoint(txid=source_coinbase.txid(), index=0)
    built = TransactionSigner(owner).build_signed_transaction(
        spend_candidates=spend_candidates_for_wallet(
            source_outpoint,
            value=COINBASE_VALUE_CHIPBITS,
            owner=owner,
        ),
        recipient=recipient.address,
        amount_chipbits=SPEND_AMOUNT_CHIPBITS,
        fee_chipbits=FEE_CHIPBITS,
        change_recipient=owner.address,
        network="mainnet",
    )
    return owner, recipient, source_coinbase, source_outpoint, built.transaction


def _utxo_view(source_outpoint: OutPoint, owner) -> InMemoryUtxoView:
    return InMemoryUtxoView.from_entries(
        [
            (
                source_outpoint,
                UtxoEntry(
                    output=TxOutput(value=COINBASE_VALUE_CHIPBITS, recipient=owner.address),
                    height=ORIGIN_HEIGHT,
                    is_coinbase=True,
                ),
            )
        ]
    )


def _context(candidate_height: int, source_outpoint: OutPoint, owner) -> ValidationContext:
    return ValidationContext(
        height=candidate_height,
        median_time_past=0,
        params=MAINNET_PARAMS,
        utxo_view=_utxo_view(source_outpoint, owner),
        network="mainnet",
    )


def _block(candidate_height: int, spend: Transaction, miner_address: str) -> Block:
    miner_subsidy, _node_pool = subsidy_split_chipbits(candidate_height, MAINNET_PARAMS)
    coinbase = Transaction(
        version=2,
        inputs=(),
        outputs=(TxOutput(value=miner_subsidy + FEE_CHIPBITS, recipient=miner_address),),
        metadata={"coinbase": "true", "height": str(candidate_height)},
    )
    transactions = (coinbase, spend)
    return Block(
        header=BlockHeader(
            version=1,
            previous_block_hash="11" * 32,
            merkle_root=merkle_root([transaction.txid() for transaction in transactions]),
            timestamp=1_800_000_000 + candidate_height,
            bits=MAINNET_PARAMS.genesis_bits,
            nonce=0,
        ),
        transactions=transactions,
    )


def _service_at_candidate_height(path: Path, candidate_height: int, source_outpoint: OutPoint, owner) -> NodeService:
    service = NodeService.open_sqlite(path, network="mainnet", params=MAINNET_PARAMS, time_provider=lambda: 1_800_000_000)
    tip_height = candidate_height - 1
    tip_header = BlockHeader(
        version=1,
        previous_block_hash="00" * 32,
        merkle_root="22" * 32,
        timestamp=1_799_999_999,
        bits=MAINNET_PARAMS.genesis_bits,
        nonce=tip_height,
    )
    service.headers.put(tip_header, height=tip_height, cumulative_work=tip_height + 1, is_main_chain=True)
    service.headers.set_tip(tip_header.block_hash(), tip_height)
    service.chainstate.put_utxo(
        source_outpoint,
        UtxoEntry(
            output=TxOutput(value=COINBASE_VALUE_CHIPBITS, recipient=owner.address),
            height=ORIGIN_HEIGHT,
            is_coinbase=True,
        ),
    )
    return service


def run_boundary_validation() -> dict[str, object]:
    owner, recipient, source_coinbase, source_outpoint, spend = _source_and_spend()
    raw = serialize_transaction(spend)
    raw_hash = hashlib.sha256(raw).hexdigest()
    source_entry = _utxo_view(source_outpoint, owner).get(source_outpoint)
    assert source_entry is not None
    assert MAINNET_PARAMS.coinbase_maturity == 100
    assert spend.version == 2
    assert len(spend.inputs) == 1
    assert spend.inputs[0].sig_scheme_id == SIG_SCHEME_ML_DSA_44

    direct_results: dict[int, dict[str, object]] = {}
    for candidate_height in (99, 100, 101):
        context = _context(candidate_height, source_outpoint, owner)
        try:
            fee = validate_transaction(spend, context)
            direct_results[candidate_height] = {"accepted": True, "fee_chipbits": fee, "reason": None}
        except ContextualValidationError as exc:
            direct_results[candidate_height] = {"accepted": False, "fee_chipbits": None, "reason": str(exc)}

    assert direct_results[99] == {"accepted": False, "fee_chipbits": None, "reason": IMMATURE_REASON}
    assert direct_results[100] == {"accepted": True, "fee_chipbits": FEE_CHIPBITS, "reason": None}
    assert direct_results[101] == {"accepted": True, "fee_chipbits": FEE_CHIPBITS, "reason": None}
    assert is_coinbase_mature(source_entry, 99, MAINNET_PARAMS) is False
    assert is_coinbase_mature(source_entry, 100, MAINNET_PARAMS) is True

    block_results: dict[int, dict[str, object]] = {}
    for candidate_height in (99, 100):
        context = _context(candidate_height, source_outpoint, owner)
        try:
            fee = validate_block_stateful(_block(candidate_height, spend, owner.address), context)
            block_results[candidate_height] = {"accepted": True, "fee_chipbits": fee, "reason": None}
        except ContextualValidationError as exc:
            block_results[candidate_height] = {"accepted": False, "fee_chipbits": None, "reason": str(exc)}

    assert block_results[99] == {"accepted": False, "fee_chipbits": None, "reason": IMMATURE_REASON}
    assert block_results[100] == {"accepted": True, "fee_chipbits": FEE_CHIPBITS, "reason": None}

    with TemporaryDirectory() as tempdir:
        root = Path(tempdir)
        service_99 = _service_at_candidate_height(root / "candidate-99.sqlite3", 99, source_outpoint, owner)
        try:
            with pytest.raises(ContextualValidationError, match="Coinbase output is not mature enough") as rejected:
                service_99.receive_transaction(spend)
            mempool_99 = {
                "accepted": False,
                "reason": str(rejected.value),
                "mempool_size": len(service_99.mempool.list_transactions()),
            }
        finally:
            service_99.connection.close()

        service_100 = _service_at_candidate_height(root / "candidate-100.sqlite3", 100, source_outpoint, owner)
        try:
            accepted = service_100.receive_transaction(spend)
            mempool_100 = {
                "accepted": True,
                "reason": None,
                "mempool_size": len(service_100.mempool.list_transactions()),
                "fee_chipbits": accepted.fee,
            }
        finally:
            service_100.connection.close()

    assert mempool_99 == {"accepted": False, "reason": IMMATURE_REASON, "mempool_size": 0}
    assert mempool_100 == {
        "accepted": True,
        "reason": None,
        "mempool_size": 1,
        "fee_chipbits": FEE_CHIPBITS,
    }

    return {
        "result": "PASS",
        "network": "mainnet",
        "coinbase_maturity": MAINNET_PARAMS.coinbase_maturity,
        "rule": "spend_height - coinbase_origin_height >= coinbase_maturity",
        "source_coinbase": {
            "origin_height": ORIGIN_HEIGHT,
            "txid": source_coinbase.txid(),
            "vout": 0,
            "amount_chipbits": COINBASE_VALUE_CHIPBITS,
            "owner": owner.address,
            "address_kind": "pq",
            "scheme_id": owner.scheme_id,
        },
        "transaction": {
            "txid": spend.txid(),
            "raw_sha256": raw_hash,
            "raw_size": len(raw),
            "input": f"{source_outpoint.txid}:{source_outpoint.index}",
            "destination": recipient.address,
            "amount_chipbits": SPEND_AMOUNT_CHIPBITS,
            "fee_chipbits": FEE_CHIPBITS,
            "change_chipbits": COINBASE_VALUE_CHIPBITS - SPEND_AMOUNT_CHIPBITS - FEE_CHIPBITS,
            "version": spend.version,
            "scheme_id": spend.inputs[0].sig_scheme_id,
        },
        "same_transaction_proof": {
            "txid_all_contexts": spend.txid(),
            "raw_sha256_all_contexts": raw_hash,
        },
        "direct_consensus_validation": {str(height): result for height, result in direct_results.items()},
        "block_stateful_validation": {str(height): result for height, result in block_results.items()},
        "node_mempool_validation": {"99": mempool_99, "100": mempool_100},
        "assertions": {
            "99_lt_100_immature": True,
            "100_gte_100_mature": True,
            "candidate_99_reject": True,
            "candidate_100_accept": True,
            "candidate_101_accept": True,
            "same_raw_transaction": True,
        },
    }


def test_mainnet_coinbase_maturity_exact_boundary_through_production_paths() -> None:
    result = run_boundary_validation()
    assert result["result"] == "PASS"


if __name__ == "__main__":
    print(json.dumps(run_boundary_validation(), indent=2, sort_keys=True))
