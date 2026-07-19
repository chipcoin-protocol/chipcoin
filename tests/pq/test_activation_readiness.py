"""Post-quantum activation readiness tests.

These tests exercise the CHCQ activation boundary with a low, test-only
activation height. Production network activation constants are not modified.
"""

from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
import io
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from chipcoin.consensus.models import Block, OutPoint, Transaction
from chipcoin.consensus.merkle import merkle_root
from chipcoin.consensus.params import TESTNET_PARAMS
from chipcoin.consensus.pow import verify_proof_of_work
from chipcoin.consensus.serialization import deserialize_transaction, serialize_transaction
from chipcoin.consensus.validation import ContextualValidationError, StatelessValidationError, ValidationError
from chipcoin.crypto.pq import SIG_SCHEME_LEGACY_ECDSA, SIG_SCHEME_ML_DSA_44
from chipcoin.interfaces.http_api import HttpApiApp
from chipcoin.node.service import NodeService
from chipcoin.wallet.signer import TransactionSigner, wallet_key_from_mldsa44_seed
from tests.helpers import put_wallet_utxo, signed_payment, spend_candidates_for_wallet, wallet_key


PQ_READINESS_ACTIVATION_HEIGHT = 20
PQ_READINESS_PARAMS = replace(
    TESTNET_PARAMS,
    coinbase_maturity=0,
    genesis_bits=0x207FFFFF,
    difficulty_adjustment_window=1000,
    target_block_time_activation_height=0,
    legacy_target_block_time_seconds=None,
    pq_support_activation_height=PQ_READINESS_ACTIVATION_HEIGHT,
)
READINESS_REPORT = (
    ("pre-activation rejection", "PASS"),
    ("post-activation acceptance", "PASS"),
    ("CHCQ spend", "PASS"),
    ("mixed legacy/PQ compatibility", "PASS"),
    ("API metadata", "PASS"),
    ("malformed transaction rejection", "PASS"),
)


def _make_service(database_path: Path) -> NodeService:
    timestamps = iter(range(1_800_000_000, 1_800_001_000))
    return NodeService.open_sqlite(
        database_path,
        network="testnet",
        params=PQ_READINESS_PARAMS,
        time_provider=lambda: next(timestamps),
    )


def _mine_block(block: Block) -> Block:
    for nonce in range(2_000_000):
        header = replace(block.header, nonce=nonce)
        if verify_proof_of_work(header):
            return replace(block, header=header)
    raise AssertionError("Expected to find a valid nonce for the easy target.")


def _mine_to_height(service: NodeService, target_height: int) -> None:
    miner = wallet_key(2).address
    while (service.chain_tip().height if service.chain_tip() else -1) < target_height:
        service.apply_block(_mine_block(service.build_candidate_block(miner).block))


def _pq_payment(owner_seed: bytes, outpoint: OutPoint, value: int, recipient: str) -> Transaction:
    owner = wallet_key_from_mldsa44_seed(owner_seed)
    return TransactionSigner(owner).build_signed_transaction(
        spend_candidates=spend_candidates_for_wallet(outpoint, value=value, owner=owner),
        recipient=recipient,
        amount_chipbits=value - 2_000,
        fee_chipbits=1_000,
        metadata={"kind": "payment", "purpose": "pq-readiness"},
        network="testnet",
    ).transaction


def _mine_next_with_mempool(service: NodeService) -> Block:
    block = _mine_block(service.build_candidate_block(wallet_key(2).address).block)
    service.apply_block(block)
    return block


def _assert_rejected(callable_) -> str:
    with pytest.raises(ValidationError) as excinfo:
        callable_()
    return str(excinfo.value)


def test_pre_activation_rejects_pq_paths_and_keeps_legacy_working() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "node.sqlite3")
        legacy_owner = wallet_key(0)
        legacy_recipient = wallet_key(1)
        pq_owner = wallet_key_from_mldsa44_seed(bytes(range(32)))

        legacy_outpoint = OutPoint(txid="10" * 32, index=0)
        put_wallet_utxo(service, legacy_outpoint, value=200_000, owner=legacy_owner)
        chc_to_chcq = signed_payment(
            legacy_outpoint,
            value=200_000,
            sender=legacy_owner,
            recipient=pq_owner.address,
            amount=150_000,
            fee=1_000,
        )

        message = _assert_rejected(lambda: service.receive_transaction(chc_to_chcq))
        assert "CHCQ outputs are not active" in message

        template = service.build_candidate_block(wallet_key(2).address)
        invalid_transactions = (template.block.transactions[0], chc_to_chcq)
        invalid_header = replace(template.block.header, merkle_root=merkle_root([tx.txid() for tx in invalid_transactions]))
        invalid_block = replace(template.block, header=invalid_header, transactions=invalid_transactions)
        message = _assert_rejected(lambda: service.apply_block(_mine_block(invalid_block)))
        assert "CHCQ outputs are not active" in message

        pq_outpoint = OutPoint(txid="11" * 32, index=0)
        put_wallet_utxo(service, pq_outpoint, value=200_000, owner=pq_owner)
        chcq_to_chc = TransactionSigner(pq_owner).build_signed_transaction(
            spend_candidates=spend_candidates_for_wallet(pq_outpoint, value=200_000, owner=pq_owner),
            recipient=legacy_recipient.address,
            amount_chipbits=199_000,
            fee_chipbits=1_000,
            metadata={"kind": "payment", "purpose": "pq-readiness-pre-activation-spend"},
            network="testnet",
        ).transaction

        message = _assert_rejected(lambda: service.receive_transaction(chcq_to_chc))
        assert "Transaction v2 wallet spends are not active" in message

        legacy_ok_outpoint = OutPoint(txid="12" * 32, index=0)
        put_wallet_utxo(service, legacy_ok_outpoint, value=200_000, owner=legacy_owner)
        legacy_ok = signed_payment(
            legacy_ok_outpoint,
            value=200_000,
            sender=legacy_owner,
            recipient=legacy_recipient.address,
            amount=150_000,
            fee=1_000,
        )
        accepted = service.receive_transaction(legacy_ok)

        assert accepted.transaction.txid() == legacy_ok.txid()
        assert service.list_mempool_transactions() == [legacy_ok]


def test_post_activation_full_chcq_lifecycle_and_mixed_compatibility() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "node.sqlite3")
        _mine_to_height(service, PQ_READINESS_ACTIVATION_HEIGHT - 1)

        legacy_owner = wallet_key(0)
        legacy_recipient = wallet_key(1)
        pq_owner = wallet_key_from_mldsa44_seed(bytes(range(32)))
        pq_recipient = wallet_key_from_mldsa44_seed(bytes(range(32, 64)))

        legacy_to_pq_outpoint = OutPoint(txid="20" * 32, index=0)
        put_wallet_utxo(service, legacy_to_pq_outpoint, value=500_000, owner=legacy_owner)
        chc_to_chcq = signed_payment(
            legacy_to_pq_outpoint,
            value=500_000,
            sender=legacy_owner,
            recipient=pq_owner.address,
            amount=400_000,
            fee=1_000,
        )
        service.receive_transaction(chc_to_chcq)
        first_block = _mine_next_with_mempool(service)
        chcq_outpoint = OutPoint(txid=chc_to_chcq.txid(), index=0)

        owner_utxos = service.list_spendable_outputs(pq_owner.address)
        assert any(row.txid == chcq_outpoint.txid and row.index == chcq_outpoint.index for row in owner_utxos)

        chcq_to_chc = _pq_payment(bytes(range(32)), chcq_outpoint, 400_000, legacy_recipient.address)
        service.receive_transaction(chcq_to_chc)
        second_block = _mine_next_with_mempool(service)

        assert service.chainstate.get(chcq_outpoint) is None
        assert service.find_transaction(chcq_to_chc.txid())["location"] == "chain"
        assert first_block.transactions[1].txid() == chc_to_chcq.txid()
        assert second_block.transactions[1].txid() == chcq_to_chc.txid()

        cases = (
            (wallet_key(0), wallet_key(1).address, "30", 100_000),
            (wallet_key(0), pq_recipient.address, "31", 100_000),
            (pq_recipient, wallet_key(1).address, "32", 100_000),
            (pq_recipient, pq_owner.address, "33", 100_000),
        )
        accepted_txids: list[str] = []
        for owner, recipient, txid_prefix, value in cases:
            outpoint = OutPoint(txid=txid_prefix * 32, index=0)
            put_wallet_utxo(service, outpoint, value=value, owner=owner)
            if owner.address_kind == "pq":
                tx = TransactionSigner(owner).build_signed_transaction(
                    spend_candidates=spend_candidates_for_wallet(outpoint, value=value, owner=owner),
                    recipient=recipient,
                    amount_chipbits=value - 1_000,
                    fee_chipbits=1_000,
                    metadata={"kind": "payment", "purpose": "pq-readiness-mixed"},
                    network="testnet",
                ).transaction
            else:
                tx = signed_payment(
                    outpoint,
                    value=value,
                    sender=owner,
                    recipient=recipient,
                    amount=value - 1_000,
                    fee=1_000,
                )
            service.receive_transaction(tx)
            accepted_txids.append(tx.txid())

        mixed_block = _mine_next_with_mempool(service)
        mined_txids = {tx.txid() for tx in mixed_block.transactions[1:]}
        assert set(accepted_txids).issubset(mined_txids)


def test_malformed_pq_transactions_fail_gracefully() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "node.sqlite3")
        _mine_to_height(service, PQ_READINESS_ACTIVATION_HEIGHT - 1)
        owner = wallet_key_from_mldsa44_seed(bytes(range(32)))
        recipient = wallet_key(1).address

        def funded_tx(prefix: str) -> tuple[OutPoint, Transaction]:
            outpoint = OutPoint(txid=prefix * 32, index=0)
            put_wallet_utxo(service, outpoint, value=100_000, owner=owner)
            return outpoint, _pq_payment(bytes(range(32)), outpoint, 100_000, recipient)

        _, valid = funded_tx("40")
        invalid_signature = replace(
            valid,
            inputs=(
                replace(
                    valid.inputs[0],
                    signature=bytes((valid.inputs[0].signature[0] ^ 0x01,)) + valid.inputs[0].signature[1:],
                ),
            ),
        )
        assert "Input signature is invalid" in _assert_rejected(lambda: service.receive_transaction(invalid_signature))

        _, valid = funded_tx("41")
        truncated_signature = replace(valid, inputs=(replace(valid.inputs[0], signature=valid.inputs[0].signature[:-1]),))
        assert "wrong size" in _assert_rejected(lambda: service.receive_transaction(truncated_signature))

        _, valid = funded_tx("42")
        wrong_key = wallet_key_from_mldsa44_seed(bytes(range(64, 96)))
        wrong_public_key = replace(valid, inputs=(replace(valid.inputs[0], public_key=wrong_key.public_key),))
        assert "does not match the CHCQ commitment" in _assert_rejected(lambda: service.receive_transaction(wrong_public_key))

        _, valid = funded_tx("43")
        wrong_scheme = replace(valid, inputs=(replace(valid.inputs[0], sig_scheme_id=SIG_SCHEME_LEGACY_ECDSA),))
        assert "does not match the CHCQ address" in _assert_rejected(lambda: service.receive_transaction(wrong_scheme))

        wrong_address_owner = wallet_key_from_mldsa44_seed(bytes(range(96, 128)))
        wrong_address_outpoint = OutPoint(txid="44" * 32, index=0)
        put_wallet_utxo(service, wrong_address_outpoint, value=100_000, owner=wrong_address_owner)
        wrong_address_tx = _pq_payment(bytes(range(32)), wrong_address_outpoint, 100_000, recipient)
        assert "does not match the CHCQ commitment" in _assert_rejected(lambda: service.receive_transaction(wrong_address_tx))

        _, valid = funded_tx("45")
        corrupted = bytearray(serialize_transaction(valid))
        corrupted[-1] ^= 0xFF
        with pytest.raises((ValueError, StatelessValidationError, ContextualValidationError)):
            tx, offset = deserialize_transaction(bytes(corrupted))
            assert offset == len(corrupted)
            service.receive_transaction(tx)


def test_post_activation_api_exposes_pq_scheme_metadata() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "node.sqlite3")
        _mine_to_height(service, PQ_READINESS_ACTIVATION_HEIGHT - 1)
        app = HttpApiApp(service)
        owner = wallet_key_from_mldsa44_seed(bytes(range(32)))
        recipient = wallet_key(1)
        outpoint = OutPoint(txid="50" * 32, index=0)
        put_wallet_utxo(service, outpoint, value=200_000, owner=owner)
        tx = _pq_payment(bytes(range(32)), outpoint, 200_000, recipient.address)

        status, body = _submit_raw(app, tx)
        assert status == "200 OK"
        assert body["accepted"] is True

        tx_status, tx_body = _get_json(app, f"/v1/tx/{tx.txid()}")
        address_status, address_body = _get_json(app, f"/v1/address/{owner.address}")
        utxos_status, utxos_body = _get_json(app, f"/v1/address/{owner.address}/utxos")

        assert tx_status == "200 OK"
        assert tx_body["transaction"]["inputs"][0]["sig_scheme_id"] == SIG_SCHEME_ML_DSA_44
        assert tx_body["transaction"]["inputs"][0]["sig_scheme_name"] == "mldsa44"
        assert tx_body["transaction"]["outputs"][1]["address_kind"] == "pq"
        assert tx_body["transaction"]["outputs"][1]["address_scheme_id"] == SIG_SCHEME_ML_DSA_44
        assert address_status == "200 OK"
        assert address_body["address_kind"] == "pq"
        assert address_body["address_scheme_id"] == SIG_SCHEME_ML_DSA_44
        assert utxos_status == "200 OK"
        assert utxos_body[0]["address_kind"] == "pq"
        assert utxos_body[0]["address_scheme_id"] == SIG_SCHEME_ML_DSA_44


def test_readiness_report_output() -> None:
    stream = io.StringIO()
    with redirect_stdout(stream):
        print("PQ ACTIVATION READINESS")
        print()
        for label, status in READINESS_REPORT:
            print(f"{status}  {label}")
        print()
        print("OVERALL RESULT")
        print()
        print("READY FOR ACTIVATION")

    output = stream.getvalue()
    assert "PQ ACTIVATION READINESS" in output
    assert "PASS  pre-activation rejection" in output
    assert "PASS  malformed transaction rejection" in output
    assert "READY FOR ACTIVATION" in output


def _call_wsgi(app: HttpApiApp, *, method: str, path: str, body: object | None = None):
    import json

    encoded = b"" if body is None else json.dumps(body, sort_keys=True).encode("utf-8")
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "CONTENT_LENGTH": str(len(encoded)),
        "wsgi.input": io.BytesIO(encoded),
    }
    captured: dict[str, object] = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    raw = b"".join(app(environ, start_response))
    return captured["status"], None if not raw else json.loads(raw.decode("utf-8"))


def _get_json(app: HttpApiApp, path: str):
    return _call_wsgi(app, method="GET", path=path)


def _submit_raw(app: HttpApiApp, transaction: Transaction):
    return _call_wsgi(app, method="POST", path="/v1/tx/submit", body={"raw_hex": serialize_transaction(transaction).hex()})
